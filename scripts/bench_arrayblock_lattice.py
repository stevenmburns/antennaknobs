"""Phased-array scaling benchmark: dense vs H-matrix vs ArrayBlock on one
lattice family grown by element count.

Sizing question this answers: at what array size does the dense B-spline fill
stop being the right tool, and what do the two accelerators buy at that point
and beyond? One shape family — an N x N grid of identical half-wave dipoles at
a fixed pitch, free space — is swept over N, and each rung is solved for the
same 2x2 short-circuit admittance (`compute_y_matrix()`) by each of

  dense       BSplineSolver     — the O(n^2) fill + O(n^3) LU reference
  hmatrix     HMatrixSolver     — ACA-compressed far field, iterative solve
  arrayblock  ArrayBlockSolver  — element-aware blocks; on a regular same-shape
                                  lattice the block-Toeplitz FFT coupling path,
                                  asserted here with `require_lattice_fft=True`
                                  so a silent degradation to the parent
                                  H-matrix is a reported rung failure, not a
                                  number quietly attributed to the wrong path.

Every rung is solved in its OWN subprocess so each gets (a) a clean
`getrusage` peak RSS from a fresh interpreter, and (b) an `RLIMIT_AS`
address-space cap, so an over-large dense fill dies with a clean MemoryError
instead of thrashing the machine into swap. BLAS + OpenMP are pinned to the
physical core count (mirrors `web/server.py`); dispatch is strictly serial,
one rung at a time.

Caveats, stated up front so the tables aren't misread:

  - **Memory floor.** Peak RSS includes the fixed interpreter + numpy +
    momwire import cost (~90 MB here), which dwarfs the operator's own
    allocation on small grids. The report prints the observed floor (min peak
    RSS across rungs) so the per-rung *delta* is recoverable.
  - **Cold process, one fill.** Each number is a first-and-only
    `compute_y_matrix()` — fill plus factor plus one back-substitution per
    port. A warm second solve at another frequency is NOT measured here; the
    scaling story is a fill story.
  - **Free space only.** Ground would confound the scaling comparison; all
    three bases ride the accelerated path on ground already, which is a
    separate question.
  - **The dense column has a wall and we find it by estimate.** Dense peak RSS
    runs about 12x the n_basis^2 * 16 bytes of Z itself (see
    `DENSE_FOOTPRINT_FACTOR` — the batched assembly's quadrature gather, not
    the matrix, sets the peak), so a rung whose estimate exceeds the cap is
    recorded `skipped (est > cap)` rather than discovered the hard way. Once a
    column caps, times out, or is skipped, that column is CLOSED — larger
    rungs are not probed.

Usage:
    python scripts/bench_arrayblock_lattice.py
    python scripts/bench_arrayblock_lattice.py --sizes 4 8 16 --solvers arrayblock
    python scripts/bench_arrayblock_lattice.py --out lattice_bench.json
"""

from __future__ import annotations

# Mirror bench_catalog.py: libgomp reads these once, before the scientific
# stack loads. Fresh worker subprocesses inherit them.
import os

os.environ.setdefault("OMP_WAIT_POLICY", "PASSIVE")
os.environ.setdefault("GOMP_SPINCOUNT", "0")

import argparse  # noqa: E402
import json  # noqa: E402
import resource  # noqa: E402
import subprocess  # noqa: E402
import sys  # noqa: E402
import time  # noqa: E402
from pathlib import Path  # noqa: E402

sys.path.insert(0, str(Path(__file__).resolve().parent))
import bench_nec_corpus as bnc  # noqa: E402

C_LIGHT = 299_792_458.0

SOLVER_KEYS = ("dense", "hmatrix", "arrayblock")

# Lattice defaults. 9 segments per half-wave dipole: odd, so a segment centre
# lands on the feed point, and well past the 3-segment minimum the portal test
# uses — the FFT gate is about lattice bookkeeping, not mesh size, so the test
# can afford a toy mesh where a benchmark cannot. 0.6 lambda pitch is inside
# the usual 0.5-0.7 broadside-array window and keeps the elements' near fields
# genuinely coupled. 14 MHz, free space.
DEFAULT_SIZES = (4, 6, 8, 12, 16, 24, 32, 48)
DEFAULT_SEGS = 9
DEFAULT_PITCH_LAMBDA = 0.6
DEFAULT_FREQ_MHZ = 14.0

# Per-rung address-space cap (GB) and wall-clock timeout (s). 8 GB on a 16 GB
# box leaves the OS and this driver room; a rung past either is a RESULT.
DEFAULT_CAP_GB = 8.0
DEFAULT_TIMEOUT = 600.0

# Dense live-footprint estimate, as a multiple of Z itself (n^2 complex128).
# The obvious arithmetic — Z plus the LU's working copy — says ~2.2x, and that
# is WRONG by a factor of five: the batched C++ assembly materialises a
# per-pair quadrature gather before it reduces to Z, so the peak lands well
# above the matrix. Measured on the 2026-08-09 run (peak RSS minus the ~91 MB
# import floor, divided by n^2*16): 12.3x at n=1296, 12.1x at n=2304, 12.1x at
# n=5184. Flat enough across a 4x span in n to extrapolate with, so this is the
# measurement, not the arithmetic.
DENSE_FOOTPRINT_FACTOR = 12.0

# Agreement bound the accelerated columns are held to (issue #833 gate 3).
AGREEMENT_BOUND = 1e-4


def lattice(grid: int, segs: int, pitch_lambda: float, freq_mhz: float):
    """The rung's geometry: `grid` x `grid` identical centre-fed half-wave
    dipoles on a square lattice, as momwire constructor kwargs.

    Two feeds, always: element 0 (the corner) and the central element, so Y is
    2x2 and the agreement column compares a corner-to-interior mutual as well
    as two self terms. Both are declared on every solver identically — the
    measured quantity has to be the same quantity."""
    import numpy as np

    wavelength = C_LIGHT / (freq_mhz * 1e6)
    arm = 0.25 * wavelength
    pitch = pitch_lambda * wavelength
    wires = [
        np.array([[ix * pitch, iy * pitch, -arm], [ix * pitch, iy * pitch, arm]])
        for ix in range(grid)
        for iy in range(grid)
    ]
    centre = (grid // 2) * grid + (grid // 2)
    return {
        "wires": wires,
        "n_per_edge_per_wire": [[segs]] * len(wires),
        # Arc-length arm is the wire's midpoint (it runs -arm..+arm).
        "feeds": [(0, arm, 1.0), (centre, arm, 0.0)],
        "wavelength": wavelength,
        "wire_radius": 0.001,
    }


def n_basis_of(grid: int, segs: int) -> int:
    """B-spline basis count for the rung. One basis per segment on an open
    wire with no junctions, so it is exactly elements x segments — cheap
    enough to compute in the parent for the dense-feasibility estimate
    without building any geometry."""
    return grid * grid * segs


def dense_estimate_gb(n_basis: int) -> float:
    """Estimated live footprint (GB) of the dense fill + factor at `n_basis`."""
    return n_basis**2 * 16 * DENSE_FOOTPRINT_FACTOR / 1024**3


# --------------------------------------------------------------------------
# subprocess worker (fresh interpreter -> clean peak RSS; RLIMIT_AS guard)
# --------------------------------------------------------------------------
def worker_main(solver_key, grid, segs, pitch_lambda, freq_mhz, cap_gb):
    """Runs in a fresh interpreter. Solves ONE rung and prints one JSON line.

    The measured span is `compute_y_matrix()` alone — geometry construction is
    outside it, because the interesting cost is the operator, not the python
    list of endpoints."""
    result = {"error": None}
    try:
        if cap_gb and cap_gb > 0:
            cap = int(cap_gb * 1024**3)
            resource.setrlimit(resource.RLIMIT_AS, (cap, cap))
        cores = bnc.apply_server_thread_policy()

        from momwire import ArrayBlockSolver, BSplineSolver, HMatrixSolver

        kwargs = lattice(grid, segs, pitch_lambda, freq_mhz)
        cls, extra = {
            "dense": (BSplineSolver, {}),
            "hmatrix": (HMatrixSolver, {}),
            # The whole point of the arrayblock rung: assert the FFT path
            # engaged rather than assume it. A miss raises
            # LatticeFFTUnavailable naming the unmet gate, and that is a
            # reportable failure of this rung.
            "arrayblock": (ArrayBlockSolver, {"require_lattice_fft": True}),
        }[solver_key]
        solver = cls(**kwargs, **extra)

        started = time.perf_counter()
        y = solver.compute_y_matrix()
        result["wall_s"] = time.perf_counter() - started
        result["peak_rss_mb"] = (
            resource.getrusage(resource.RUSAGE_SELF).ru_maxrss * 1024 / 1e6
        )
        result["cores"] = cores
        result["n_basis"] = int(solver._build_geometry()["n_segs_total"])
        result["y_real"] = y.real.tolist()
        result["y_imag"] = y.imag.tolist()
        diag = getattr(solver, "solver_diag", lambda: None)()
        if diag is not None:
            result["diag"] = {k: v for k, v in diag.items() if k != "reason"}
            result["diag"]["reason"] = diag.get("reason")
    except MemoryError:
        result["error"] = f"MemoryError: exceeded {cap_gb:g} GB cap"
        result["error_kind"] = "capped"
    except Exception as e:  # noqa: BLE001 — report, never crash the sweep
        kind = "fft" if type(e).__name__ == "LatticeFFTUnavailable" else "err"
        result["error"] = f"{type(e).__name__}: {e}"
        result["error_kind"] = kind
    print(json.dumps(result))


def run_rung(solver_key, grid, segs, pitch_lambda, freq_mhz, cap_gb, timeout):
    """Dispatch one worker subprocess. Serial by construction — the caller
    loops, there is no pool."""
    try:
        proc = subprocess.run(
            [
                sys.executable,
                __file__,
                "--worker",
                solver_key,
                str(grid),
                str(segs),
                str(pitch_lambda),
                str(freq_mhz),
                str(cap_gb),
            ],
            capture_output=True,
            text=True,
            timeout=timeout,
        )
    except subprocess.TimeoutExpired:
        return {"error": f"timeout > {timeout:g}s", "error_kind": "timeout"}
    if proc.returncode != 0 and not proc.stdout.strip():
        tail = (proc.stderr or "").strip()[-200:]
        # RLIMIT_AS usually surfaces as MemoryError inside the worker, but a
        # C-level allocation can take the process down instead.
        kind = "capped" if proc.returncode in (-9, 137) else "err"
        return {"error": f"worker exited {proc.returncode}: {tail}", "error_kind": kind}
    try:
        return json.loads(proc.stdout.strip().splitlines()[-1])
    except (json.JSONDecodeError, IndexError):
        return {"error": f"unparseable worker output: {proc.stdout[-200:]!r}"}


# --------------------------------------------------------------------------
# driver
# --------------------------------------------------------------------------
def _y_of(res):
    """The rung's Y as a complex array, or None if it did not produce one."""
    import numpy as np

    if not res or res.get("error") or "y_real" not in res:
        return None
    return np.array(res["y_real"]) + 1j * np.array(res["y_imag"])


def _rel_err(y, y_ref):
    """max|Y - Y_ref| / max|Y_ref| — one scalar per rung, normalised on the
    reference's largest entry so the self terms don't hide a bad mutual."""
    import numpy as np

    if y is None or y_ref is None:
        return None
    scale = float(np.abs(y_ref).max())
    if scale == 0.0:
        return None
    return float(np.abs(y - y_ref).max() / scale)


def _status(res):
    """ok / capped / timeout / fft-unavailable / error for one rung result."""
    if not res:
        return "error"
    kind = res.get("error_kind")
    if kind is None:
        return "ok" if not res.get("error") else "error"
    return {
        "capped": "capped (MemoryError)",
        "timeout": "timeout",
        "fft": "fft-unavailable",
    }.get(kind, "error")


def sweep(sizes, solvers, segs, pitch_lambda, freq_mhz, cap_gb, timeout):
    """Run the ladder, one rung at a time, closing a column at its first
    non-ok rung. Returns the row list."""
    rows = []
    closed: dict[str, str] = {}  # solver -> why the column stopped
    for grid in sizes:
        n_basis = n_basis_of(grid, segs)
        est = dense_estimate_gb(n_basis)
        print(
            f"\ngrid {grid}x{grid}   elements={grid * grid}  n_basis={n_basis}  "
            f"dense est {est:.2f} GB",
            flush=True,
        )
        results = {}
        for key in solvers:
            if key in closed:
                results[key] = {
                    "error": f"column closed: {closed[key]}",
                    "error_kind": "closed",
                }
                print(f"  {key:<11} skipped (column closed: {closed[key]})", flush=True)
                continue
            if key == "dense" and cap_gb and est > cap_gb:
                results[key] = {
                    "error": f"skipped: dense est {est:.2f} GB > {cap_gb:g} GB cap",
                    "error_kind": "skip-est",
                }
                closed[key] = (
                    f"dense estimate {est:.2f} GB exceeded the {cap_gb:g} GB cap"
                )
                print(
                    f"  {key:<11} skipped (est {est:.2f} GB > {cap_gb:g} GB cap)",
                    flush=True,
                )
                continue
            res = run_rung(key, grid, segs, pitch_lambda, freq_mhz, cap_gb, timeout)
            results[key] = res
            if res.get("error"):
                print(f"  {key:<11} {_status(res):<20} {res['error'][:70]}", flush=True)
                closed[key] = _status(res)
            else:
                fft = (res.get("diag") or {}).get("lattice_fft")
                tag = "  fft" if fft else ""
                print(
                    f"  {key:<11} {res['wall_s']:8.2f}s  "
                    f"{res['peak_rss_mb']:7.0f} MB{tag}",
                    flush=True,
                )

        # Agreement: dense while it ran, hmatrix as the reference beyond it.
        y_dense = _y_of(results.get("dense"))
        y_hm = _y_of(results.get("hmatrix"))
        ref_key = "dense" if y_dense is not None else ("hmatrix" if y_hm else None)
        y_ref = y_dense if y_dense is not None else y_hm
        for key in solvers:
            if key == ref_key:
                continue
            err = _rel_err(_y_of(results.get(key)), y_ref)
            if err is not None:
                results[key]["rel_err"] = err
                results[key]["rel_err_vs"] = ref_key
                flag = "" if err <= AGREEMENT_BOUND else "   <-- OVER BOUND"
                print(f"    {key} vs {ref_key}: rel err {err:.2e}{flag}", flush=True)

        rows.append(
            {
                "grid": grid,
                "elements": grid * grid,
                "n_basis": n_basis,
                "dense_est_gb": est,
                "solvers": results,
            }
        )
    return rows


def print_report(rows, solvers):
    """The table the status doc quotes, plus the floor and the ratios."""
    print("\n" + "=" * 96)
    print("RUNGS — wall clock, peak RSS, agreement")
    print("=" * 96)
    header = f"{'grid':<8} {'elem':>5} {'n_basis':>8} {'solver':<11} {'wall s':>9} {'peak MB':>8} {'rel err':>10}  status"
    print(header)
    print("-" * len(header))
    for row in rows:
        for key in solvers:
            res = row["solvers"].get(key) or {}
            status = (
                "skipped (est > cap)"
                if res.get("error_kind") == "skip-est"
                else "skipped (column closed)"
                if res.get("error_kind") == "closed"
                else _status(res)
            )
            wall = f"{res['wall_s']:9.2f}" if "wall_s" in res else f"{'-':>9}"
            rss = f"{res['peak_rss_mb']:8.0f}" if "peak_rss_mb" in res else f"{'-':>8}"
            err = f"{res['rel_err']:10.2e}" if "rel_err" in res else f"{'-':>10}"
            print(
                f"{row['grid']}x{row['grid']:<5} {row['elements']:>5} "
                f"{row['n_basis']:>8} {key:<11} {wall} {rss} {err}  {status}"
            )

    floors = [
        r["solvers"][k]["peak_rss_mb"]
        for r in rows
        for k in solvers
        if "peak_rss_mb" in (r["solvers"].get(k) or {})
    ]
    if floors:
        print(
            f"\nobserved memory floor (min peak RSS across rungs): {min(floors):.0f} MB"
        )

    # Ratios — the portable finding; absolute times drift with hardware.
    print("\n" + "=" * 96)
    print("RATIOS vs dense (wall clock / peak RSS), where dense ran")
    print("=" * 96)
    for row in rows:
        d = row["solvers"].get("dense") or {}
        if "wall_s" not in d:
            continue
        parts = []
        for key in solvers:
            if key == "dense":
                continue
            res = row["solvers"].get(key) or {}
            if "wall_s" not in res:
                continue
            parts.append(
                f"{key}: {d['wall_s'] / res['wall_s']:5.1f}x faster, "
                f"{d['peak_rss_mb'] / res['peak_rss_mb']:4.2f}x RSS"
            )
        print(f"  {row['grid']}x{row['grid']:<4} " + "   ".join(parts))

    worst = {}
    for row in rows:
        for key in solvers:
            res = row["solvers"].get(key) or {}
            if "rel_err" in res:
                prev = worst.get(key)
                if prev is None or res["rel_err"] > prev[0]:
                    worst[key] = (res["rel_err"], row["grid"], res["rel_err_vs"])
    if worst:
        print(f"\nworst measured agreement per column (bound {AGREEMENT_BOUND:g}):")
        for key, (err, grid, ref) in worst.items():
            flag = "  OK" if err <= AGREEMENT_BOUND else "  OVER BOUND"
            print(f"  {key:<11} {err:.2e} vs {ref} at {grid}x{grid}{flag}")


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument(
        "--worker",
        nargs=6,
        metavar=("SOLVER", "GRID", "SEGS", "PITCH", "FREQ", "CAP_GB"),
        help=argparse.SUPPRESS,
    )
    ap.add_argument(
        "--sizes",
        nargs="+",
        type=int,
        default=list(DEFAULT_SIZES),
        help=f"grid edge lengths, ascending (default: {' '.join(map(str, DEFAULT_SIZES))})",
    )
    ap.add_argument(
        "--solvers", nargs="+", default=list(SOLVER_KEYS), choices=SOLVER_KEYS
    )
    ap.add_argument(
        "--segs",
        type=int,
        default=DEFAULT_SEGS,
        help=f"segments per half-wave dipole (default {DEFAULT_SEGS}, odd)",
    )
    ap.add_argument(
        "--pitch",
        type=float,
        default=DEFAULT_PITCH_LAMBDA,
        help=f"lattice pitch in wavelengths (default {DEFAULT_PITCH_LAMBDA})",
    )
    ap.add_argument("--freq-mhz", type=float, default=DEFAULT_FREQ_MHZ)
    ap.add_argument(
        "--cap-gb",
        type=float,
        default=DEFAULT_CAP_GB,
        help=f"per-rung address-space cap in GB (default {DEFAULT_CAP_GB}; 0 = none)",
    )
    ap.add_argument(
        "--timeout",
        type=float,
        default=DEFAULT_TIMEOUT,
        help=f"per-rung wall-clock timeout in seconds (default {DEFAULT_TIMEOUT})",
    )
    ap.add_argument("--out", type=Path, default=None)
    args = ap.parse_args(argv)

    if args.worker:
        solver_key, grid, segs, pitch, freq, cap_gb = args.worker
        worker_main(
            solver_key, int(grid), int(segs), float(pitch), float(freq), float(cap_gb)
        )
        return

    sizes = sorted(set(args.sizes))
    solvers = [k for k in SOLVER_KEYS if k in args.solvers]  # canonical order
    cores = bnc.physical_cpu_count()
    print("arrayblock lattice scaling benchmark (free space)")
    print(
        f"lattice: NxN half-wave dipoles, {args.segs} segs each, "
        f"{args.pitch}λ pitch, {args.freq_mhz} MHz"
    )
    print(f"sizes: {', '.join(f'{n}x{n}' for n in sizes)}")
    print(f"solvers: {', '.join(solvers)}   feeds: corner + centre element (2x2 Y)")
    print(
        f"per-rung cap: {args.cap_gb or 'none'} GB address space, "
        f"{args.timeout:g}s wall"
    )
    print(
        "concurrency (mirrors web/server.py): "
        f"BLAS={cores} OpenMP={cores} OMP_WAIT_POLICY=PASSIVE GOMP_SPINCOUNT=0  "
        "(serial dispatch, one rung at a time)"
    )

    started = time.perf_counter()
    rows = sweep(
        sizes,
        solvers,
        args.segs,
        args.pitch,
        args.freq_mhz,
        args.cap_gb,
        args.timeout,
    )
    print_report(rows, solvers)
    print(f"\ntotal sweep wall clock: {time.perf_counter() - started:.1f}s")

    if args.out:
        payload = {
            "segs": args.segs,
            "pitch_lambda": args.pitch,
            "freq_mhz": args.freq_mhz,
            "cap_gb": args.cap_gb,
            "timeout_s": args.timeout,
            "cores": cores,
            "rows": rows,
        }
        args.out.write_text(json.dumps(payload, indent=2))
        print(f"full results -> {args.out}")


if __name__ == "__main__":
    main()
