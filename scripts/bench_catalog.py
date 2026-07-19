"""Full-catalog runtime + peak-RSS benchmark: every solver on every design,
across ground models.

Sizing question this answers: what does a single ``engine.impedance()`` cost —
wall-clock and resident memory — for each built-in design on each of the four
engines (PyNEC / Sinusoidal / BSpline d=1 / BSpline d=2), at the design's
as-shipped default mesh, under each ground model? This is the per-tick cost the
web UI pays, catalogued across the free → fast-finite → Sommerfeld axis where
the finite-ground models dominate the runtime.

Ground models (same specs as ``profile_ground_models.py`` / the web adapter):

  free  — free space (no ground)
  pec   — perfectly conducting plane (image method; no material solve)
  fast  — reflection-coefficient finite ground  (NEC gn 0 / momwire refl-coef)
  somm  — Sommerfeld-Norton finite ground        (NEC gn 2 / momwire sommerfeld)

It reuses ``bench_converge.py``'s pure ``solve_design`` for the measurement but
runs it in its OWN subprocess worker so each solve gets (a) a clean ``getrusage``
peak RSS from a fresh interpreter, and (b) an ``RLIMIT_AS`` address-space cap so
a runaway finite-ground solve on a huge design dies with a clean MemoryError
instead of thrashing the machine into swap. BLAS+OpenMP are pinned to the
physical core count (mirrors ``web/server.py``); dispatch is serial.

Three caveats, stated up front so the tables aren't misread:

  - **Memory floor.** Peak RSS includes the fixed interpreter + numpy + PyNEC +
    momwire import cost (~90 MB here), which dwarfs the solve's own allocation on
    small designs. The rollup prints the observed floor (min peak RSS) so the
    per-solve *delta* is recoverable; only heavy designs on finite grounds lift
    RSS meaningfully above it.
  - **Sommerfeld is the expensive model.** Its cells are seconds, not
    milliseconds, and its memory can be gigabytes on the biggest meshes — hence
    the ``--max-seg-finite`` guard, which skips finite-ground solves (free/pec
    still run) for designs whose Σseg exceeds the cap, logged not hidden. The
    default cap excludes only ``verticals.elt_whip`` (the intentional 4392-seg
    W8IO stress design).
  - **Default variant / default frequency.** One variant per design; each design
    solved at its own default frequency and mesh.

Usage:
    python scripts/bench_catalog.py                          # all designs+grounds
    python scripts/bench_catalog.py --grounds free fast somm
    python scripts/bench_catalog.py --engines sin bs2 --grounds free somm
    python scripts/bench_catalog.py --designs loops.quad beams.yagi
    python scripts/bench_catalog.py --out catalog_perf.json
"""

from __future__ import annotations

# Mirror bench_nec_corpus.py: libgomp reads these once, before the scientific
# stack loads. Fresh worker subprocesses inherit them.
import os

os.environ.setdefault("OMP_WAIT_POLICY", "PASSIVE")
os.environ.setdefault("GOMP_SPINCOUNT", "0")

import argparse  # noqa: E402
import json  # noqa: E402
import resource  # noqa: E402
import statistics  # noqa: E402
import subprocess  # noqa: E402
import sys  # noqa: E402
from pathlib import Path  # noqa: E402

# Reuse bench_converge.py (which itself reuses bench_nec_corpus.py's harness).
sys.path.insert(0, str(Path(__file__).resolve().parent))
import bench_converge as cvg  # noqa: E402
import bench_nec_corpus as bnc  # noqa: E402

ENGINE_KEYS = cvg.ENGINE_KEYS  # ("pynec", "sin", "bs1", "bs2")
ENGINE_LABEL = cvg.ENGINE_LABEL

# Ground specs by CLI label — identical to profile_ground_models.py, so the
# numbers line up with that tool and the web adapter. `fast` and `somm` share
# DEFAULT_GROUND's eps_r/sigma and differ only in solve method.
from antennaknobs.engines.pynec import DEFAULT_GROUND  # noqa: E402

GROUNDS = {
    "free": "free",
    "pec": "pec",
    "fast": ("finite-fast",) + tuple(DEFAULT_GROUND[1:]),
    "somm": tuple(DEFAULT_GROUND),
}
GROUND_ORDER = ("free", "pec", "fast", "somm")
FINITE_GROUNDS = ("fast", "somm")  # the ones the --max-seg-finite guard gates

# Default finite-ground Σseg cap: excludes only elt_whip (4392) from the
# expensive finite solves while keeping its free/pec rows and every other design.
DEFAULT_MAX_SEG_FINITE = 2000
# Address-space ceiling per worker (GB). A finite-ground solve that would exceed
# it dies with a clean MemoryError instead of swapping the box. 24 GB on a 31 GB
# machine leaves headroom for the OS + this driver.
DEFAULT_MEM_GB = 24.0


def all_designs() -> list[str]:
    """Every built-in design as a sorted ``family.name`` dotted path."""
    from antennaknobs.cli import list_builtin_designs

    return list_builtin_designs()


def default_nseg(design: str) -> int:
    """The design's as-shipped ``nominal_nsegs`` (framework default, injected at
    construction — 21 across the current catalog, but read it, don't assume)."""
    return cvg.load_design(design)().nominal_nsegs


# --------------------------------------------------------------------------
# subprocess worker (fresh interpreter -> clean peak RSS; RLIMIT_AS guard)
# --------------------------------------------------------------------------
def worker_main(design, nseg, engine, ground_json, mem_gb):
    """Runs in a fresh interpreter. Prints one JSON line to stdout. Reuses
    bench_converge.solve_design for the actual measurement; adds an address-
    space cap so a runaway finite-ground solve fails cleanly."""
    result = {"error": None}
    try:
        if mem_gb and mem_gb > 0:
            cap = int(mem_gb * 1024**3)
            resource.setrlimit(resource.RLIMIT_AS, (cap, cap))
        cores = bnc.apply_server_thread_policy()
        ground = json.loads(ground_json)
        if isinstance(ground, list):
            ground = tuple(ground)
        cls = cvg.load_design(design)
        res = cvg.solve_design(cls, nseg, engine, ground)
        peak = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss * 1024
        res["peak_rss_mb"] = peak / 1e6
        res["cores"] = cores
        result = res
    except MemoryError:
        result["error"] = f"MemoryError: exceeded {mem_gb:g} GB cap"
        result["error_kind"] = "mem"
    except Exception as e:  # noqa: BLE001 — report, never crash the sweep
        import traceback

        result["error"] = f"{type(e).__name__}: {e}"
        result["traceback"] = traceback.format_exc()[-800:]
    print(json.dumps(result))


def run_engine(design, nseg, engine, ground, timeout, mem_gb):
    """Dispatch a worker subprocess for one (design, nseg, engine, ground)."""
    try:
        proc = subprocess.run(
            [
                sys.executable,
                __file__,
                "--worker",
                design,
                str(nseg),
                engine,
                json.dumps(ground),
                str(mem_gb),
            ],
            capture_output=True,
            text=True,
            timeout=None if timeout is None else timeout + 15,
        )
    except subprocess.TimeoutExpired:
        return {"error": f"timeout > {timeout}s", "error_kind": "timeout"}
    if proc.returncode != 0 and not proc.stdout.strip():
        tail = (proc.stderr or "").strip()[-200:]
        # A hard OOM kill (RLIMIT_AS can also trip the OOM killer via SIGKILL).
        kind = "mem" if proc.returncode in (-9, 137) else "err"
        return {"error": f"worker exited {proc.returncode}: {tail}", "error_kind": kind}
    try:
        return json.loads(proc.stdout.strip().splitlines()[-1])
    except (json.JSONDecodeError, IndexError):
        return {"error": f"unparseable worker output: {proc.stdout[-200:]!r}"}


# --------------------------------------------------------------------------
# driver
# --------------------------------------------------------------------------
def bench_one(design, engines, grounds, timeout, mem_gb, nseg_override, max_seg_finite):
    """Solve one design on each (ground, engine); return a row."""
    try:
        nseg = nseg_override if nseg_override is not None else default_nseg(design)
    except Exception as e:  # noqa: BLE001 — a design that won't even construct
        row = {"design": design, "load_error": f"{type(e).__name__}: {e}"}
        _print_row(row, engines, grounds)
        return row

    # Σseg is engine/ground-independent — the honest mesh size and the guard key.
    seg = cvg.total_nominal_segs(cvg.load_design(design), nseg)
    row = {"design": design, "nseg": nseg, "total_nominal_segs": seg, "grounds": {}}
    for g in grounds:
        if g in FINITE_GROUNDS and max_seg_finite and seg > max_seg_finite:
            row["grounds"][g] = {
                e: {
                    "error": f"skipped: Σseg {seg} > {max_seg_finite}",
                    "error_kind": "skip",
                }
                for e in engines
            }
            continue
        row["grounds"][g] = {
            e: run_engine(design, nseg, e, GROUNDS[g], timeout, mem_gb) for e in engines
        }
    _print_row(row, engines, grounds)
    return row


def _cell(res):
    """(solve_ms, rss_mb) or None from a worker result."""
    if not res or res.get("error"):
        return None
    return res.get("solve_s", 0.0) * 1e3, res.get("peak_rss_mb", 0.0)


def _tag(res):
    """Short failure tag for a non-successful cell."""
    kind = (res or {}).get("error_kind")
    return {"skip": "skip", "mem": "MEM", "timeout": "TIME"}.get(kind, "ERR")


def _print_row(row, engines, grounds):
    if row.get("load_error"):
        print(f"  {row['design']:<40} LOAD-ERR {row['load_error'][:50]}", flush=True)
        return
    seg = row.get("total_nominal_segs")
    print(
        f"  {row['design']:<40} Σseg={seg if seg is not None else '??':>5}", flush=True
    )
    for g in grounds:
        cells = []
        gres = row["grounds"].get(g, {})
        for e in engines:
            c = _cell(gres.get(e))
            if c is None:
                cells.append(f"{ENGINE_LABEL[e]}={_tag(gres.get(e)):>7}    ")
            else:
                cells.append(f"{ENGINE_LABEL[e]}={c[0]:8.1f}ms/{c[1]:5.0f}MB")
        print(f"      {g:<5} " + "  ".join(cells), flush=True)


def print_report(rows, engines, grounds):
    ok = [r for r in rows if not r.get("load_error")]
    errs = [r for r in rows if r.get("load_error")]

    # Per (ground, engine) rollup: the headline matrix.
    print("\n" + "=" * 100)
    print("ROLLUP — solve wall-clock + peak RSS, per ground model × engine")
    print("=" * 100)
    print(
        f"{'ground':<6} {'engine':<12} {'n':>4} {'median':>9} {'max':>10} "
        f"{'RSS floor':>10} {'RSS max':>9}"
    )
    print("-" * 64)
    for g in grounds:
        for e in engines:
            solves, rss = [], []
            for r in ok:
                c = _cell(r["grounds"].get(g, {}).get(e))
                if c is not None:
                    solves.append(c[0])
                    rss.append(c[1])
            if not solves:
                print(f"{g:<6} {ENGINE_LABEL[e]:<12} {'0':>4}  (no successful solves)")
                continue
            print(
                f"{g:<6} {ENGINE_LABEL[e]:<12} {len(solves):>4} "
                f"{statistics.median(solves):>7.1f}ms {max(solves):>8.1f}ms "
                f"{min(rss):>8.0f}MB {max(rss):>6.0f}MB"
            )
        print("-" * 64)

    # Slowest solves overall — where the interactive budget is tightest.
    print("\n" + "=" * 100)
    print("SLOWEST 12 (design, ground, engine) SOLVES")
    print("=" * 100)
    flat = []
    for r in ok:
        for g in grounds:
            for e in engines:
                c = _cell(r["grounds"].get(g, {}).get(e))
                if c is not None:
                    flat.append(
                        (c[0], c[1], r["design"], g, e, r.get("total_nominal_segs"))
                    )
    for ms, mb, design, g, e, seg in sorted(flat, reverse=True)[:12]:
        print(
            f"  {ms:9.1f}ms  {mb:6.0f}MB  Σseg={seg!s:>5}  {design}  "
            f"[{g}/{ENGINE_LABEL[e]}]"
        )

    # Failures / skips.
    fails = []
    for r in ok:
        for g in grounds:
            for e in engines:
                res = r["grounds"].get(g, {}).get(e)
                if res and res.get("error"):
                    fails.append(
                        (
                            r["design"],
                            g,
                            e,
                            res.get("error_kind") or "err",
                            res["error"],
                        )
                    )
    if fails or errs:
        skips = [f for f in fails if f[3] == "skip"]
        hard = [f for f in fails if f[3] != "skip"]
        print("\n" + "=" * 100)
        print(
            f"NON-SOLVES: {len(errs)} load, {len(hard)} error/mem/timeout, {len(skips)} guard-skipped"
        )
        print("=" * 100)
        for r in errs:
            print(f"  LOAD  {r['design']:<40} {r['load_error'][:60]}")
        for design, g, e, kind, err in hard:
            print(
                f"  {kind.upper():<5} {design:<30} [{g}/{ENGINE_LABEL[e]:<10}] {err[:44]}"
            )
        if skips:
            skipped_designs = sorted({d for d, *_ in skips})
            print(
                f"  guard-skipped finite grounds (Σseg cap): {', '.join(skipped_designs)}"
            )


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument(
        "--worker",
        nargs=5,
        metavar=("DESIGN", "NSEG", "ENGINE", "GROUND", "MEM_GB"),
        help=argparse.SUPPRESS,
    )
    ap.add_argument("--designs", nargs="+", default=None)
    ap.add_argument(
        "--engines", nargs="+", default=list(ENGINE_KEYS), choices=ENGINE_KEYS
    )
    ap.add_argument(
        "--grounds",
        nargs="+",
        default=list(GROUND_ORDER),
        choices=list(GROUNDS),
        help="ground models to sweep (default: all four)",
    )
    ap.add_argument(
        "--nseg",
        type=int,
        default=None,
        help="override nominal_nsegs for every design (default: per-design default)",
    )
    ap.add_argument(
        "--max-seg-finite",
        type=int,
        default=DEFAULT_MAX_SEG_FINITE,
        help="skip finite-ground (fast/somm) solves for designs whose Σseg "
        f"exceeds this (default {DEFAULT_MAX_SEG_FINITE}; 0 = no cap). free/pec "
        "always run.",
    )
    ap.add_argument(
        "--mem-gb",
        type=float,
        default=DEFAULT_MEM_GB,
        help=f"per-solve address-space cap in GB (default {DEFAULT_MEM_GB}; "
        "0 = no cap). A solve exceeding it fails clean instead of swapping.",
    )
    ap.add_argument("--timeout", type=float, default=600.0)
    ap.add_argument("--out", type=Path, default=None)
    args = ap.parse_args(argv)

    if args.worker:
        design, nseg, engine, ground, mem_gb = args.worker
        worker_main(design, int(nseg), engine, ground, float(mem_gb))
        return

    designs = args.designs if args.designs is not None else all_designs()
    grounds = [g for g in GROUND_ORDER if g in args.grounds]  # canonical order
    cores = bnc.physical_cpu_count()
    print(f"catalog runtime + peak-RSS benchmark   designs: {len(designs)}")
    print(f"engines: {', '.join(ENGINE_LABEL[e] for e in args.engines)}")
    print(
        f"grounds: {', '.join(grounds)}   "
        + (
            f"mesh: nominal_nsegs={args.nseg}"
            if args.nseg
            else "mesh: per-design default"
        )
    )
    print(
        f"finite-ground Σseg cap: {args.max_seg_finite or 'none'}   "
        f"per-solve mem cap: {args.mem_gb or 'none'} GB"
    )
    print(
        "concurrency (mirrors web/server.py): "
        f"BLAS={cores} OpenMP={cores} OMP_WAIT_POLICY=PASSIVE GOMP_SPINCOUNT=0  "
        "(serial dispatch)"
    )
    print("-" * 100)

    rows = [
        bench_one(
            d,
            args.engines,
            grounds,
            args.timeout,
            args.mem_gb,
            args.nseg,
            args.max_seg_finite,
        )
        for d in designs
    ]
    print_report(rows, args.engines, grounds)

    if args.out:
        args.out.write_text(json.dumps(rows, indent=2))
        print(f"\nfull results -> {args.out}")


if __name__ == "__main__":
    main()
