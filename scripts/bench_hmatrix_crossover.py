"""Where does the H-matrix route actually start paying? (momwire#977)

The 2026-09-08 catalog cost ladder reported HMatrixSolver slower than dense on
all 196 cells, and momwire#977 asked the obvious question back: the ladder's two
rungs put `wire.rhombic` at 1,010 and 2,020 segments, and the laptop repro on
momwire v0.51.0 puts the crossover near 3,500. Both rungs were below it. So the
ladder measured the wrong side of a curve, not the absence of one.

This walks the curve. Per cell: warm wall (cold solve discarded, `_solved_cache`
cleared — the momwire#1235 trap), tracemalloc PEAK, |dZ|/|Z| against dense
b-spline at the same degree, and for the accelerator the far fraction, the
mean/max ACA rank and the near-block count.

    python scripts/bench_hmatrix_crossover.py --out docs/status/<date>-....jsonl

ONE PROCESS PER CELL, and tracemalloc rather than `ru_maxrss`, because a forked
child inherits its PARENT's RSS high-water mark: a subprocess-per-arm memory
gate on this box once read 1,610 MB for an arm that takes 900 MB alone
(momwire#967). tracemalloc starts at zero per process and cannot inherit.

CHECK THE CHECK. `--engine hmatrix-nocompress` runs the H-matrix route with the
ACA turned off (far blocks stored dense). If the timer is measuring what it
claims, that cell's wall time collapses towards the dense fill's — a timer that
reads the same either way is not measuring the compression.
"""

from __future__ import annotations

import argparse
import importlib.util
import json
import subprocess
import sys
import time
import tracemalloc
import warnings
from pathlib import Path

_HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(_HERE))

GROUNDS = {"free": None, "finite": ("finite", 13.0, 0.005)}

# rhombic is the design the win is on record for; lpda is the compact
# multi-wire class and reaches 4,906 segments, where `beams.yagi` tops out at
# 1,232 and could not straddle a crossover at ~3,500; elt_whip is the many-wire
# class that timed out (momwire#972 fragmentation) and whose segment count
# barely moves with `nominal_nsegs` (4,392 -> 4,588), so it gets one rung.
LADDER = {
    "wire.rhombic": [21, 42, 63, 84, 126, 168],
    "broadband.lpda": [21, 42, 63, 84, 126, 168],
    "verticals.elt_whip": [21],
    # The ground-coupled compact loop (momwire#973). Added after Haswell found
    # the skyloop defect is NOT a far block but the single global n x n ACA in
    # `_sommerfeld_global_lowrank`, which factorises the WHOLE Sommerfeld
    # remainder on the premise that it is globally low rank. On the refined
    # rung that block stops at rank 13 with a TRUE relative error of 0.78 while
    # every other admissible block sits at 1e-9..1e-7 — partial-pivoting
    # STAGNATION, where the update goes small because the pivots are exhausted
    # in a subspace rather than because the approximation is good.
    #
    # That is why accuracy is a column in every row here and not an assumption:
    # on this class the H-matrix route can be 78 % WRONG at the default
    # tolerance, and a wall-and-RSS ladder would have called that "slow".
    "loops.skyloop_lmatch": [21, 42, 63, 84],
}


def _load(name):
    spec = importlib.util.spec_from_file_location(name, _HERE / f"{name}.py")
    mod = importlib.util.module_from_spec(spec)
    sys.modules[name] = mod
    spec.loader.exec_module(mod)
    return mod


def _engine(builder, engine, degree, ground, aca_tol=None):
    from antennaknobs.engines.momwire import MomwireEngine
    from momwire import BSplineSolver, HMatrixSolver

    kw = {} if ground is None else {"ground": ground}
    opts = {"degree": degree}
    if aca_tol is not None and engine.startswith("hmatrix"):
        opts["aca_tol"] = float(aca_tol)
    if engine == "dense":
        return MomwireEngine(builder, solver=BSplineSolver, solver_kwargs=opts, **kw)
    if engine == "hmatrix":
        return MomwireEngine(builder, solver=HMatrixSolver, solver_kwargs=opts, **kw)
    if engine == "hmatrix-nocompress":
        # The mutation: admissibility so tight nothing is far, so every block
        # is stored dense and the ACA never runs. If the timer is measuring
        # compression, this collapses towards the dense fill.
        return MomwireEngine(
            builder,
            solver=HMatrixSolver,
            solver_kwargs={**opts, "aca_eta": 1e-9},
            **kw,
        )
    raise SystemExit(f"unknown engine {engine!r}")


def worker_main(design, nseg, engine, degree, ground_key, mem_gb, aca_tol="none"):
    out = {"error": None}
    try:
        import resource

        mem_gb = float(mem_gb)
        if mem_gb > 0:
            cap = int(mem_gb * 1024**3)
            resource.setrlimit(resource.RLIMIT_AS, (cap, cap))
        bnc = _load("bench_converge")
        cores = _load("bench_nec_corpus").apply_server_thread_policy()
        cls = bnc.load_design(design)
        b = cls()
        b.nominal_nsegs = int(nseg)

        with warnings.catch_warnings():
            warnings.simplefilter("ignore")
            eng = _engine(
                b,
                engine,
                int(degree),
                GROUNDS[ground_key],
                None if aca_tol == "none" else float(aca_tol),
            )
            t0 = time.perf_counter()
            eng.impedance()
            cold = time.perf_counter() - t0
            # The momwire#1235 cache trap: a second impedance() on an
            # unchanged engine is a dict lookup, not a solve.
            eng._solved_cache = None
            tracemalloc.start()
            t1 = time.perf_counter()
            zs = eng.impedance()
            warm = time.perf_counter() - t1
            traced_peak = tracemalloc.get_traced_memory()[1] / 1e6
            tracemalloc.stop()

        out.update(
            aca_tol=None if aca_tol == "none" else float(aca_tol),
            z=[[float(z.real), float(z.imag)] for z in zs],
            cold_s=cold,
            warm_s=warm,
            traced_peak_mb=traced_peak,
            rss_mb=resource.getrusage(resource.RUSAGE_SELF).ru_maxrss * 1024 / 1e6,
            cores=cores,
            segs=bnc.total_nominal_segs(cls, int(nseg)),
        )
        out.update(_hmatrix_stats(eng, engine))
    except MemoryError:
        out["error"] = f"MemoryError: exceeded {mem_gb:g} GB cap"
    except Exception as e:  # noqa: BLE001 — a refused or failing cell is a RESULT
        out["error"] = f"{type(e).__name__}: {e}"[:300]
    print(json.dumps(out))


def _hmatrix_stats(eng, engine):
    """far fraction, ACA rank and near-block count — the shape numbers #977
    asked for, alongside the timing that motivated them."""
    if not engine.startswith("hmatrix"):
        return {}
    try:
        with warnings.catch_warnings():
            warnings.simplefilter("ignore")
            sim = eng._make_solver(wavelength=eng._wavelength_for(eng.builder.freq))
            part = sim.build_partition()
            H = sim.build_hmatrix()
            st = H.stats()
        return {
            "n_basis": int(st["n"]),
            "far_frac": float(part["stats"]["far_frac"]),
            "mean_rank": float(st["mean_rank"]),
            "max_rank": int(st["max_rank"]),
            "far_blocks": len(part["far"]),
            "near_blocks": len(part["near"]),
            "compression": float(st["compression"]),
            # momwire#973: the global Sommerfeld remainder's ACA rank. A
            # rank/N approaching 1 is a DENSE FILL IN A LOW-RANK COSTUME —
            # the factorisation cost with none of the saving — and it is the
            # tell that the stopping test has stagnated rather than converged.
            "somm_rank": _attr(sim, "_last_somm_rank", int),
            # momwire#979's own instrumentation. THE COLUMN THAT SEES THE
            # FAILURE is not |dZ|/|Z|: two of the three stagnant catalog
            # designs had the Sommerfeld remainder correction ABSENT and still
            # agreed with dense to 3.7e-8 and 1.1e-4 dGamma, so nothing keyed
            # on impedance could have flagged them at any threshold. The probe
            # residual and whether the fallback fired are what do.
            "somm_residual": _attr(sim, "_last_somm_residual", float),
            "somm_fallback": _attr(sim, "_last_somm_fallback", bool),
            "somm_rank_over_n": (
                None
                if _attr(sim, "_last_somm_rank", int) is None or not st["n"]
                else float(_attr(sim, "_last_somm_rank", int)) / float(st["n"])
            ),
        }
    except Exception as e:  # noqa: BLE001 — stats are a bonus, never the cell
        return {"stats_error": f"{type(e).__name__}: {str(e)[:120]}"}


def _attr(sim, name, cast):
    v = getattr(sim, name, None)
    return None if v is None else cast(v)


def _meta(engines, mem_gb, timeout_s):
    import platform
    import subprocess as sp

    import numpy as np

    def sha(p):
        return sp.run(
            ["git", "-C", str(p), "rev-parse", "HEAD"], capture_output=True, text=True
        ).stdout.strip()

    root = _HERE.parent
    return {
        "_meta": True,
        "utc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "box": platform.node(),
        "python": platform.python_version(),
        "numpy": np.__version__,
        "antennaknobs_sha": sha(root),
        "momwire_sha": sha(root / "momwire"),
        "engines": list(engines),
        "grounds": {k: list(v) if v else None for k, v in GROUNDS.items()},
        "ladder": {k: list(v) for k, v in LADDER.items()},
        "mem_gb": mem_gb,
        "aca_tol_override": None,
        "timeout_s": timeout_s,
    }


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", required=True)
    ap.add_argument("--mem-gb", type=float, default=36.0)
    ap.add_argument("--timeout", type=float, default=600.0)
    ap.add_argument("--engines", default="dense,hmatrix")
    ap.add_argument("--designs", default=",".join(LADDER))
    ap.add_argument("--degrees", default="1,2")
    ap.add_argument("--grounds", default="free,finite")
    ap.add_argument(
        "--aca-tol",
        default="none",
        help="override the H-matrix truncation tolerance for every cell. "
        "ISOLATES momwire#974's default change EXACTLY, which a SHA swap "
        "cannot: af2cf6e -> main also carries #883, #975 and #976.",
    )
    args = ap.parse_args()

    engines = args.engines.split(",")
    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    with out.open("a") as fh:
        fh.write(json.dumps(_meta(engines, args.mem_gb, args.timeout)) + "\n")
        for design in args.designs.split(","):
            for nseg in LADDER[design]:
                for degree in (int(d) for d in args.degrees.split(",")):
                    for gkey in args.grounds.split(","):
                        for engine in engines:
                            rec = _cell(
                                design,
                                nseg,
                                engine,
                                degree,
                                gkey,
                                args.mem_gb,
                                args.timeout,
                                args.aca_tol,
                            )
                            fh.write(json.dumps(rec) + "\n")
                            fh.flush()
                            tag = rec.get("error") or f"{rec.get('warm_s', 0):.2f}s"
                            print(
                                f"  {design} n={nseg} d={degree} {gkey} "
                                f"{engine}: {tag}",
                                flush=True,
                            )
    print(f"wrote {out}")


def _cell(design, nseg, engine, degree, gkey, mem_gb, timeout_s, aca_tol="none"):
    cp = (
        subprocess.run(
            [
                sys.executable,
                __file__,
                "--worker",
                design,
                str(nseg),
                engine,
                str(degree),
                gkey,
                str(mem_gb),
                aca_tol,
            ],
            capture_output=True,
            text=True,
            timeout=None,
            cwd=str(_HERE.parent),
        )
        if timeout_s <= 0
        else _run_capped(
            [
                sys.executable,
                __file__,
                "--worker",
                design,
                str(nseg),
                engine,
                str(degree),
                gkey,
                str(mem_gb),
                aca_tol,
            ],
            timeout_s,
        )
    )
    try:
        rec = json.loads(cp.stdout.strip().splitlines()[-1])
    except Exception:  # noqa: BLE001 — a dead or killed worker IS a cell
        rec = {
            "error": (
                f"timeout>{timeout_s:g}s"
                if getattr(cp, "timed_out", False)
                else f"worker exit {cp.returncode}: {cp.stderr.strip()[-200:]}"
            )
        }
    rec.update(design=design, nseg=nseg, engine=engine, degree=degree, ground=gkey)
    return rec


def _run_capped(cmd, timeout_s):
    """Run with a wall cap. A TIMEOUT IS A RESULT — elt_whip is in this ladder
    precisely because both accelerators exceeded 600 s on it, and waiting for
    that cell would cost an hour to learn what the cap already says."""
    try:
        cp = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=timeout_s,
            cwd=str(_HERE.parent),
        )
        cp.timed_out = False
        return cp
    except subprocess.TimeoutExpired as e:

        class _Killed:
            stdout = (
                (e.stdout or b"").decode(errors="replace")
                if isinstance(e.stdout, bytes)
                else (e.stdout or "")
            )
            stderr = ""
            returncode = -1
            timed_out = True

        return _Killed()


if __name__ == "__main__":
    if len(sys.argv) > 1 and sys.argv[1] == "--worker":
        worker_main(*sys.argv[2:])
    else:
        main()
