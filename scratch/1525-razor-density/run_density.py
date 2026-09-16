"""Density ladder for razor-2p over the whole catalog, with bs2 as the yardstick.

    NEC5_EXE=<nec5cl> python scratch/1525-razor-density/run_density.py

Measurement only. `PLAN.md` holds the question, the setup and the registered
predictions D1-D5.

Same dispatch as the catalog and #1516 harnesses: one worker subprocess per
(design, ground, rung, engine), serially, with an `RLIMIT_AS` cap so a fill that
outgrows the box dies with a clean MemoryError instead of swapping it. A cell
that breaches the cap or the timeout is a RECORD carrying the reason, because
"how big can this get before it stops fitting" is one of the things being priced.

TWO SOLVES PER WORKER, cold then warm. The second `impedance()` call re-solves
with whatever the engine has cached, which is what a second UI tick pays.
Caveat carried with the number: peak RSS is a per-process high-water mark, so it
covers BOTH solves and cannot be attributed to one.

SEGMENT COUNTS ARE RECORDED, NOT THE KNOB -- both of them. `nominal_nsegs` is a
density and each design decides which edges follow it; `verticals.elt_whip` goes
4392 -> 4577 across the whole ladder while `arrays.bowtie16x1` goes 1376 ->
10496. An exponent fitted against the knob would be fitted against the wrong
x-axis. Two counts are kept because they are not the same number:

  * `total_nominal_segs` -- the framework's projection, identical for every
    engine, which is what makes it the honest shared x-axis for a fit;
  * `built_segs` -- what THIS engine actually meshed, which differs by one
    segment per feed between the even-parity pair and bs2's odd parity.

The fit uses the nominal count; the built count is there so a reader can see the
parity offset rather than take it on trust.
"""

from __future__ import annotations

import argparse
import json
import os
import resource
import subprocess
import sys
import time
from pathlib import Path

RUNGS = (21, 40, 80, 160)
SERVED_RUNG = 40
GROUNDS = {"free": "free", "somm": ("finite", 13.0, 0.005)}
ENGINES = ("razor", "bs2")

# The brief calls a matched-density NEC-5 column optional and worth having on the
# four designs #1516 examined.
NEC5_DESIGNS = (
    "loops.skyloop_lmatch",
    "verticals.rectangle",
    "dipoles.koch_dipole",
    "verticals.four_square",
)

# Designs that cannot be laddered on this box, decided from GEOMETRY AND A COST
# MODEL before any cell runs, and recorded as rows rather than dropped. Two
# grounds for a skip:
#   * the achieved segment count grows by less than 1.10x from the lowest rung to
#     the highest, so there is no ladder to fit -- refining the knob does not
#     refine the mesh, and a convergence statement about it would be measured
#     over a refinement that did not happen;
#   * a rung's predicted peak RSS or wall time breaches the budget.
# A SKIPPED DESIGN IS NOT CLASSIFIED. "Cannot be laddered on this box" is the
# finding; it is neither "converging" nor "not converging".
SKIP_LIST = Path(__file__).with_name("skip-list.json")

DEFAULT_TIMEOUT_S = 1200.0
DEFAULT_MEM_GB = 40.0
REFUSAL_TYPES = ("NotImplementedError", "ValueError", "TypeError")


def build_engine(builder, engine, ground):
    from antennaknobs.engines.momwire import MomwireEngine
    from momwire import BSplineSolver, RazorSolver

    if engine == "bs2":
        return MomwireEngine(
            builder, solver=BSplineSolver, solver_kwargs={"degree": 2}, ground=ground
        )
    if engine == "razor":
        return MomwireEngine(
            builder,
            solver=RazorSolver,
            solver_kwargs={"nec5_quadrature": True},
            ground=ground,
        )
    if engine == "nec5":
        from antennaknobs.engines.nec5 import NEC5Engine

        return NEC5Engine(builder, ground=ground)
    raise ValueError(f"unknown engine {engine!r}")


def worker_main(design, ground_key, rung, engine, mem_gb):
    result = {"status": "error", "error": None, "error_type": None}
    t0 = time.perf_counter()
    try:
        cap = int(mem_gb * 2**30)
        resource.setrlimit(resource.RLIMIT_AS, (cap, cap))
        sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "scripts"))
        import bench_converge as cvg

        cls = cvg.load_design(design)
        b = cls()
        b.nominal_nsegs = rung
        result["freq_hz"] = float(b.freq)
        result["total_nominal_segs"] = cvg.total_nominal_segs(cls, rung)

        eng = build_engine(b, engine, GROUNDS[ground_key])
        result["parity"] = getattr(eng, "segment_parity", None)
        if engine == "nec5":
            result["built_segs"] = sum(
                int(line.split()[2])
                for line in eng.deck([b.freq]).splitlines()
                if line.startswith("GW")
            )
        else:
            result["built_segs"] = sum(sum(e) for e in eng._edge_segments)
        try:
            result["fed_segments"] = eng.fed_segments()
        except Exception as e:  # noqa: BLE001 -- informational, never fatal
            result["fed_segments"] = f"{type(e).__name__}: {e}"

        ts = time.perf_counter()
        zs = eng.impedance()
        result["cold_s"] = time.perf_counter() - ts
        result["z"] = [[float(z.real), float(z.imag)] for z in zs]

        ts = time.perf_counter()
        zw = eng.impedance()
        result["warm_s"] = time.perf_counter() - ts
        # A warm solve that returns a DIFFERENT answer is a finding, not a timing
        # detail, so the disagreement is recorded rather than discarded.
        result["warm_matches_cold"] = [
            [float(z.real), float(z.imag)] for z in zw
        ] == result["z"]

        adv = getattr(eng, "advisories", None)
        result["advisories"] = [str(x) for x in adv] if adv else []
        result["status"] = "ok"
    except MemoryError:
        result["error_type"] = "MemoryError"
        result["error"] = f"RLIMIT_AS {mem_gb} GB exceeded"
    except BaseException as e:  # noqa: BLE001 -- the worker must never die silently
        result["error_type"] = type(e).__name__
        result["error"] = str(e)[:2000]
        result["status"] = "refused" if type(e).__name__ in REFUSAL_TYPES else "error"
    result["wall_s"] = time.perf_counter() - t0
    result["peak_rss_mb"] = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss / 1024.0
    sys.stdout.write(json.dumps(result) + "\n")
    return 0


def run_cell(design, ground, rung, engine, timeout_s, mem_gb, nec5_exe):
    env = dict(os.environ)
    env.update(
        OMP_NUM_THREADS="4",
        OPENBLAS_NUM_THREADS="4",
        MKL_NUM_THREADS="4",
        NEC5_EXE=nec5_exe,
    )
    cmd = [
        sys.executable,
        str(Path(__file__).resolve()),
        "--worker",
        design,
        ground,
        str(rung),
        engine,
        str(mem_gb),
    ]
    t0 = time.perf_counter()
    try:
        cp = subprocess.run(
            cmd, capture_output=True, text=True, timeout=timeout_s, env=env, check=False
        )
    except subprocess.TimeoutExpired:
        return {
            "status": "timeout",
            "error_type": "TimeoutExpired",
            "error": f"no result in {timeout_s:g}s",
            "wall_s": time.perf_counter() - t0,
        }
    lines = cp.stdout.strip().splitlines()
    if not lines:
        return {
            "status": "error",
            "error_type": "NoOutput",
            "error": (cp.stderr or "")[-2000:],
            "returncode": cp.returncode,
            "wall_s": time.perf_counter() - t0,
        }
    try:
        rec = json.loads(lines[-1])
    except json.JSONDecodeError:
        return {
            "status": "error",
            "error_type": "BadOutput",
            "error": lines[-1][:2000],
            "wall_s": time.perf_counter() - t0,
        }
    rec["driver_wall_s"] = time.perf_counter() - t0
    return rec


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("--worker", nargs=5, default=None, help=argparse.SUPPRESS)
    ap.add_argument("--designs", nargs="*", default=None)
    ap.add_argument("--rungs", nargs="*", type=int, default=list(RUNGS))
    ap.add_argument("--grounds", nargs="*", default=list(GROUNDS))
    ap.add_argument("--out", default=None)
    ap.add_argument("--timeout", type=float, default=DEFAULT_TIMEOUT_S)
    ap.add_argument("--mem-gb", type=float, default=DEFAULT_MEM_GB)
    ap.add_argument("--nec5-exe", default=os.environ.get("NEC5_EXE", ""))
    a = ap.parse_args(argv)

    if a.worker:
        d, g, rung, e, mem = a.worker
        return worker_main(d, g, int(rung), e, float(mem))

    if not a.nec5_exe or not Path(a.nec5_exe).is_file():
        print("--nec5-exe (or NEC5_EXE) must name a NEC-5 binary", file=sys.stderr)
        return 2

    sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "scripts"))
    from antennaknobs.cli import list_builtin_designs

    designs = a.designs or list_builtin_designs()
    cells = []
    for d in designs:
        engines = (*ENGINES, "nec5") if d in NEC5_DESIGNS else ENGINES
        for g in a.grounds:
            for rung in a.rungs:
                cells.extend((d, g, rung, e) for e in engines)

    skips = json.loads(SKIP_LIST.read_text()) if SKIP_LIST.is_file() else {}
    out_path = Path(a.out) if a.out else Path(__file__).with_name("records.jsonl")
    # Provenance as the first line of the data. `--dev-mode` because this study
    # deliberately runs momwire ahead of the recorded pointer: the pointer check
    # still runs and is recorded as excused, and the other six still gate.
    sys.path.insert(0, str(Path(__file__).resolve().parent))
    import verify_env

    provenance = verify_env.collect(a.nec5_exe, dev_mode=True)
    if not provenance["all_checks_pass"]:
        failed = [k for k, v in provenance["checks"].items() if not v]
        print(f"STALENESS GUARD FAILED: {failed}", file=sys.stderr)
        return 3
    t_start = time.perf_counter()
    with open(out_path, "w", encoding="utf-8") as fh:
        fh.write(json.dumps(provenance) + "\n")
        for i, (d, g, rung, e) in enumerate(cells, 1):
            if d in skips:
                rec = {
                    "status": "skipped",
                    "error_type": "NotLadderable",
                    "error": skips[d]["reason"],
                    **{k: v for k, v in skips[d].items() if k != "reason"},
                    "wall_s": 0.0,
                }
            else:
                rec = run_cell(d, g, rung, e, a.timeout, a.mem_gb, a.nec5_exe)
            rec.update(design=d, ground=g, rung=rung, engine=e)
            fh.write(json.dumps(rec) + "\n")
            fh.flush()
            z = rec.get("z")
            shown = f"{z[0][0]:.5g}{z[0][1]:+.5g}j" if z else rec["status"]
            el = time.perf_counter() - t_start
            print(
                f"[{i:4d}/{len(cells)}] {el / 60:5.1f}m {d:34s} {g:4s} x{rung:<3d} "
                f"{e:5s} N={rec.get('total_nominal_segs', '?'):>6} "
                f"{rec.get('driver_wall_s', 0.0):7.2f}s "
                f"rss={rec.get('peak_rss_mb', 0.0):7.0f}M  {shown}",
                flush=True,
            )
    print(f"\n{len(cells)} cells in {time.perf_counter() - t_start:.1f}s -> {out_path}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
