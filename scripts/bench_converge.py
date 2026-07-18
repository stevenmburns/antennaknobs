"""Segment-refinement convergence sweep (issue #408).

Formalizes the ad-hoc convergence study from the 2026-07-16 corpus benchmark
(``docs/status/2026-07-16-nec2c-corpus-benchmark.md``) into a repeatable tool.
For each parameterized design it sweeps ``nominal_nsegs`` over a ladder and
solves the geometry with all four engines, reusing ``bench_nec_corpus.py``'s
subprocess / peak-RSS / thread-policy harness (one fresh interpreter per solve,
BLAS+OpenMP pinned to the physical-core count, serial dispatch).

Two questions it answers:

  1. **Convergence rate** — how many segments each engine needs to reach within
     a tolerance of its OWN finest-mesh value. This is basis-relative and needs
     no external reference: a higher-order basis (BSpline d=2) that settles at a
     coarse mesh converges *faster*.
  2. **Convergence value** — with ``--anchor-nec2c``, each mesh is also solved by
     ``nec2c`` on the matched-dimension deck (``antennaknobs.nec_export``, a
     faithful text twin of what PyNEC builds). nec2c anchors the *value* the
     curve should approach, so the sweep can say whether a basis converges to the
     SAME answer faster or to a DIFFERENT one — the open question the corpus
     benchmark's inline sweep on the quad loop could not settle (BSpline plateaus
     ~130 Ω while the pulse/sinusoidal pair climbs past 136 Ω).

Usage:
    python scripts/bench_converge.py                     # default designs+ladder
    python scripts/bench_converge.py --designs loops.quad beams.yagi
    python scripts/bench_converge.py --nseg-ladder 7 15 31 61 121 201
    python scripts/bench_converge.py --anchor-nec2c --out converge.json
    python scripts/bench_converge.py --engines sin bs2 --anchor-nec2c
"""

from __future__ import annotations

# Mirror bench_nec_corpus.py: libgomp reads these once, before numpy/PyNEC/
# momwire load. Fresh subprocesses inherit them.
import os

os.environ.setdefault("OMP_WAIT_POLICY", "PASSIVE")
os.environ.setdefault("GOMP_SPINCOUNT", "0")

import argparse  # noqa: E402
import importlib  # noqa: E402
import json  # noqa: E402
import resource  # noqa: E402
import shutil  # noqa: E402
import subprocess  # noqa: E402
import sys  # noqa: E402
import tempfile  # noqa: E402
import time  # noqa: E402
from pathlib import Path  # noqa: E402

# Reuse bench_nec_corpus.py's harness (same directory, not on the package path).
sys.path.insert(0, str(Path(__file__).resolve().parent))
import bench_nec_corpus as bnc  # noqa: E402

# Loop-heavy default set: the corpus sweep found closed loops are where the
# higher-order basis diverges most from NEC's segmentation, so they are the
# designs that test whether "loops favor the higher-order basis" generalizes.
# The yagi (open linear elements) is the well-behaved control.
DEFAULT_DESIGNS = (
    "loops.quad",
    "loops.delta_loop",
    "loops.diamond_loop",
    "beams.yagi",
)
DEFAULT_LADDER = (7, 11, 15, 21, 31, 45, 61, 85)
ENGINE_KEYS = bnc.ENGINE_KEYS  # ("pynec", "sin", "bs1", "bs2")
ENGINE_LABEL = bnc.ENGINE_LABEL


# --------------------------------------------------------------------------
# design loading + mesh sizing (pure)
# --------------------------------------------------------------------------
def load_design(dotted: str):
    """``"loops.quad"`` -> ``antennaknobs.designs.loops.quad.Builder``."""
    mod = importlib.import_module(f"antennaknobs.designs.{dotted}")
    return mod.Builder


def total_nominal_segs(builder_cls, nseg: int) -> int:
    """Total segments the design dials at ``nominal_nsegs=nseg`` (sum of the
    per-wire counts from ``build_wires``, pre-parity-coercion). Engine-
    independent — the honest x-axis of the sweep, the mesh the user asked for
    before a solver rounds it to its parity."""
    b = builder_cls()
    b.nominal_nsegs = nseg
    return sum(int(t[2]) for t in b.build_wires())


# --------------------------------------------------------------------------
# convergence-rate metric (pure)
# --------------------------------------------------------------------------
def nseg_to_converge(series, tol: float = 0.02):
    """Smallest ``N`` at which a mesh *coarser than the finest* already agrees
    with the finest mesh to within ``tol`` (relative |ΔZ|).

    ``series`` is ``[(N, z), ...]`` ordered by increasing N; the finest mesh is
    the self-reference. Only coarser meshes are convergence candidates: the
    finest trivially matches itself, so answering "N≥finest" would hide whether
    the curve has actually plateaued. Returns ``None`` when no coarser mesh lands
    within ``tol`` — meaning the impedance is still moving at the finest mesh (no
    evidence of a plateau on this ladder) — or when there are fewer than two
    points to compare.
    """
    if len(series) < 2:
        return None
    z_fin = series[-1][1]
    denom = abs(z_fin) or 1.0
    for N, z in series[:-1]:
        if abs(z - z_fin) / denom <= tol:
            return N
    return None


# --------------------------------------------------------------------------
# nec2c anchor: matched-dimension deck at a given mesh
# --------------------------------------------------------------------------
def anchor_deck(builder_cls, nseg: int, ground="free") -> str:
    """NEC2 deck for the design at ``nominal_nsegs=nseg``. ``export_nec`` reuses
    PyNECEngine's resolved geometry, so nec2c on this deck reproduces what PyNEC
    solves — a true anchor of the convergence *value* at that mesh, not just a
    fixed geometry."""
    from antennaknobs.nec_export import export_nec

    b = builder_cls()
    b.nominal_nsegs = nseg
    return export_nec(b, ground=ground, include_rp=False)


def run_anchor(builder_cls, nseg: int, ground, timeout: float):
    """Export the design at this mesh and solve it with nec2c. Returns the
    bench_nec_corpus run_nec2c dict (``{"z": [[re, im], ...], ...}``) or an
    error dict."""
    try:
        deck = anchor_deck(builder_cls, nseg, ground=ground)
    except Exception as e:  # noqa: BLE001 — export can reject networked designs
        return {"error": f"export: {type(e).__name__}: {e}"}
    with tempfile.TemporaryDirectory(prefix="cvg_") as d:
        nec = Path(d) / "d.nec"
        nec.write_text(deck)
        return bnc.run_nec2c(nec, timeout)


# --------------------------------------------------------------------------
# the solve (in-process; the subprocess worker just wraps this for RSS)
# --------------------------------------------------------------------------
def solve_design(builder_cls, nseg: int, engine: str, ground):
    """Build one engine on the design at ``nominal_nsegs=nseg`` and return its
    driving-point impedance plus mesh size. Pure enough to call directly in a
    test; the subprocess worker calls it for peak-RSS isolation."""
    from antennaknobs.engines.momwire import MomwireEngine
    from momwire import BSplineSolver, SinusoidalSolver

    if isinstance(ground, list):
        ground = tuple(ground)

    b = builder_cls()
    b.nominal_nsegs = nseg

    t0 = time.perf_counter()
    if engine == "pynec":
        from antennaknobs.engines.pynec import PyNECEngine

        eng = PyNECEngine(b, ground=ground)
    elif engine == "sin":
        eng = MomwireEngine(b, solver=SinusoidalSolver, ground=ground)
    elif engine == "bs1":
        eng = MomwireEngine(
            b, solver=BSplineSolver, solver_kwargs={"degree": 1}, ground=ground
        )
    elif engine == "bs2":
        eng = MomwireEngine(
            b, solver=BSplineSolver, solver_kwargs={"degree": 2}, ground=ground
        )
    else:
        raise ValueError(f"unknown engine {engine!r}")
    zs = eng.impedance()
    solve_s = time.perf_counter() - t0

    return {
        "error": None,
        "z": [[float(z.real), float(z.imag)] for z in zs],
        "solve_s": solve_s,
        "total_nominal_segs": total_nominal_segs(builder_cls, nseg),
    }


# --------------------------------------------------------------------------
# subprocess worker (fresh interpreter -> clean getrusage peak RSS)
# --------------------------------------------------------------------------
def worker_main(design: str, nseg: int, engine: str, ground_json: str):
    """Runs in a fresh interpreter. Prints one JSON line to stdout."""
    result = {"error": None}
    try:
        cores = bnc.apply_server_thread_policy()
        ground = json.loads(ground_json)
        cls = load_design(design)
        res = solve_design(cls, nseg, engine, ground)
        peak_rss = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss * 1024
        res["peak_rss_mb"] = peak_rss / 1e6
        res["cores"] = cores
        result = res
    except Exception as e:  # noqa: BLE001 — report, never crash the sweep
        import traceback

        result["error"] = f"{type(e).__name__}: {e}"
        result["traceback"] = traceback.format_exc()[-800:]
    print(json.dumps(result))


def run_engine(design, nseg, engine, ground, timeout):
    """Dispatch a worker subprocess for one (design, nseg, engine)."""
    proc = subprocess.run(
        [
            sys.executable,
            __file__,
            "--worker",
            design,
            str(nseg),
            engine,
            json.dumps(ground),
        ],
        capture_output=True,
        text=True,
        timeout=None if timeout is None else timeout + 15,
    )
    if proc.returncode != 0 and not proc.stdout.strip():
        tail = (proc.stderr or "").strip()[-200:]
        return {"error": f"worker exited {proc.returncode}: {tail}"}
    try:
        return json.loads(proc.stdout.strip().splitlines()[-1])
    except (json.JSONDecodeError, IndexError):
        return {"error": f"unparseable worker output: {proc.stdout[-200:]!r}"}


# --------------------------------------------------------------------------
# driver
# --------------------------------------------------------------------------
def sweep_design(design, ladder, engines, ground, timeout, anchor):
    """Sweep one design across the ladder; return a result row."""
    cls = load_design(design)
    row = {"design": design, "ground": ground, "meshes": []}
    for nseg in ladder:
        cell = {"nseg": nseg, "engines": {}}
        for e in engines:
            res = run_engine(design, nseg, e, ground, timeout)
            cell["engines"][e] = res
            if res.get("total_nominal_segs") is not None:
                cell["total_nominal_segs"] = res["total_nominal_segs"]
        if anchor:
            cell["nec2c"] = run_anchor(cls, nseg, ground, timeout)
        row["meshes"].append(cell)
        _print_mesh_line(cell, engines, anchor)
    return row


def _zc(res):
    """Feed-0 complex impedance from a worker/nec2c result, or None."""
    if not res or res.get("error") or not res.get("z"):
        return None
    return complex(res["z"][0][0], res["z"][0][1])


def _fmt_z(z):
    return "     n/a    " if z is None else f"{z.real:7.1f}{z.imag:+7.1f}j"


def _print_mesh_line(cell, engines, anchor):
    parts = [f"  N={cell['nseg']:>4}"]
    tns = cell.get("total_nominal_segs")
    parts.append(f"(Σseg={tns:>5})" if tns is not None else "(Σseg=   ??)")
    for e in engines:
        parts.append(f"{ENGINE_LABEL[e]}={_fmt_z(_zc(cell['engines'].get(e)))}")
    if anchor:
        parts.append(f"nec2c={_fmt_z(_zc(cell.get('nec2c')))}")
    print("   ".join(parts), flush=True)


def print_report(rows, engines, anchor, tol):
    for row in rows:
        print("\n" + "=" * 100)
        print(f"CONVERGENCE — {row['design']}   ground={row['ground']}")
        print("=" * 100)
        meshes = row["meshes"]

        # per-engine convergence-rate + finest-mesh value
        print(
            f"convergence to within {tol:.0%} of own finest mesh "
            f"(N ladder {meshes[0]['nseg']}..{meshes[-1]['nseg']}):"
        )
        cols = list(engines) + (["nec2c"] if anchor else [])
        for e in cols:
            if e == "nec2c":
                series = [(m["nseg"], _zc(m.get("nec2c"))) for m in meshes]
                label = "nec2c"
            else:
                series = [(m["nseg"], _zc(m["engines"].get(e))) for m in meshes]
                label = ENGINE_LABEL[e]
            series = [(n, z) for n, z in series if z is not None]
            if len(series) < 2:
                print(f"  {label:<12} no data")
                continue
            n_conv = nseg_to_converge(series, tol)
            z_fin = series[-1][1]
            conv_txt = f"N≥{n_conv}" if n_conv is not None else "not settled"
            print(
                f"  {label:<12} finest(N={series[-1][0]}) = {_fmt_z(z_fin)}   "
                f"converged: {conv_txt}"
            )

        # cross-engine agreement at the finest mesh, vs nec2c if anchored
        if anchor:
            anc = _zc(meshes[-1].get("nec2c"))
            if anc is not None:
                print(f"\n  finest-mesh value vs nec2c anchor ({_fmt_z(anc)}):")
                for e in engines:
                    z = _zc(meshes[-1]["engines"].get(e))
                    if z is None:
                        continue
                    dgamma = abs(bnc._gamma(z) - bnc._gamma(anc))
                    rel = abs(z - anc) / (abs(anc) or 1.0)
                    print(
                        f"    {ENGINE_LABEL[e]:<12} ΔΓ={dgamma:.4f}  rel|ΔZ|={rel:.1%}"
                    )


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument(
        "--worker",
        nargs=4,
        metavar=("DESIGN", "NSEG", "ENGINE", "GROUND"),
        help=argparse.SUPPRESS,
    )
    ap.add_argument("--designs", nargs="+", default=list(DEFAULT_DESIGNS))
    ap.add_argument(
        "--engines", nargs="+", default=list(ENGINE_KEYS), choices=ENGINE_KEYS
    )
    ap.add_argument(
        "--nseg-ladder",
        nargs="+",
        type=int,
        default=list(DEFAULT_LADDER),
        help="nominal_nsegs values to sweep",
    )
    ap.add_argument(
        "--ground",
        default="free",
        help='engine/nec2c ground: "free" | "pec" (finite grounds need the '
        "corpus tooling; convergence studies are free-space by default)",
    )
    ap.add_argument(
        "--anchor-nec2c",
        action="store_true",
        help="also solve each mesh with nec2c on the matched-dimension deck "
        "(export_nec) to anchor the convergence value (issue #408 part 1)",
    )
    ap.add_argument(
        "--tol",
        type=float,
        default=0.02,
        help="relative-|Z| tolerance for the convergence-rate metric",
    )
    ap.add_argument("--timeout", type=float, default=600.0)
    ap.add_argument("--out", type=Path, default=None)
    args = ap.parse_args(argv)

    if args.worker:
        design, nseg, engine, ground = args.worker
        worker_main(design, int(nseg), engine, ground)
        return

    ladder = sorted(set(args.nseg_ladder))
    if args.anchor_nec2c and shutil.which("nec2c") is None:
        sys.exit("--anchor-nec2c needs nec2c on PATH — build it into ~/.local/bin")

    cores = bnc.physical_cpu_count()
    print(f"designs: {', '.join(args.designs)}")
    print(f"engines: {', '.join(args.engines)}   ladder: {ladder}")
    print(
        f"ground: {args.ground}   anchor-nec2c: {args.anchor_nec2c}   "
        f"concurrency (mirrors web/server.py): BLAS={cores} OpenMP={cores} "
        "(serial dispatch)"
    )

    rows = []
    for design in args.designs:
        print(f"\n### {design}")
        rows.append(
            sweep_design(
                design,
                ladder,
                args.engines,
                args.ground,
                args.timeout,
                args.anchor_nec2c,
            )
        )

    print_report(rows, args.engines, args.anchor_nec2c, args.tol)

    if args.out:
        args.out.write_text(json.dumps(rows, indent=2))
        print(f"\nfull results -> {args.out}")


if __name__ == "__main__":
    main()
