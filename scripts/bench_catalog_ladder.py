"""Catalog cost ladder: what every engine COSTS on every design (AK#1235).

The push lane gates correctness on every merge but records neither wall time
nor memory, and runs only the default engine per design. This measures the
other axis: for each catalog design x each engine that serves it, at the
design's default mesh and ONE refinement rung, the WARM wall time, the peak
RSS, the driving-point Z, the peak gain, and -- where an engine refuses -- the
refusal SENTENCE.

    python scripts/bench_catalog_ladder.py --out docs/status/<date>-ladder.jsonl

WARM, not cold. Each cell solves twice and times the SECOND: the first pays
engine construction, mesh build and any first-touch import, which is a real
cost but not the per-tick cost the web UI pays on a knob change, and it swamps
the solve on small designs. Both are recorded (`cold_s`, `warm_s`) so the
construction cost stays visible instead of being quietly dropped.

PEAK RSS is `ru_maxrss` from a FRESH interpreter per cell, which is why every
cell is its own subprocess: a peak is a moment, and a shared interpreter
reports the high-water mark of everything that ran before. The interpreter +
numpy + engine import floor (~90 MB here) is included and is reported in the
rollup, so the per-solve delta is recoverable.

REFUSALS ARE SENTENCES. A refusal is recorded verbatim; the rollup separates
declared refusals from faults, and any refusal that arrives as a bare
exception class name with no sentence is called out for an issue (#1235's
rule).

Reuses `bench_catalog.all_designs` and `bench_converge.load_design` rather
than re-deriving the catalog, so this cannot drift from what the push lane
certifies.
"""

from __future__ import annotations

import argparse
import importlib.util
import json
import os
import platform
import resource
import subprocess
import sys
import time
from pathlib import Path

_HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(_HERE))


def _load(name):
    spec = importlib.util.spec_from_file_location(name, _HERE / f"{name}.py")
    mod = importlib.util.module_from_spec(spec)
    sys.modules[name] = mod
    spec.loader.exec_module(mod)
    return mod


# The engine set #1235 names. `razor-nec5` is a deprecated alias of
# `razor-2p`; both bind RazorSolver's identified two-point quadrature, so the
# current spelling is used and the alias noted rather than measured twice.
ENGINES = ("bs2", "bs1", "sin", "razor-2p", "pynec", "nec5")
# The two accelerators are BSplineSolver SUBCLASSES at the same degree, so
# they are measured against bs2 rather than against each other: same basis,
# same answer expected, only the matrix representation differs.
ACCELERATORS = ("hmatrix", "arrayblock")
DEFAULT_GROUND = ("finite", 13.0, 0.005)


def worker_main(design, nseg, engine, ground_json, mem_gb):
    """One cell in a fresh interpreter. Prints one JSON line."""
    out = {"error": None}
    try:
        # argv arrives as strings; mem_gb is compared and formatted as a number.
        mem_gb = float(mem_gb)
        if mem_gb > 0:
            cap = int(mem_gb * 1024**3)
            resource.setrlimit(resource.RLIMIT_AS, (cap, cap))
        bnc = _load("bench_converge")
        # The BLAS/thread pin lives in bench_nec_corpus, not bench_converge --
        # same policy the corpus sweep runs under (AK#897/#898), so the two
        # measurements are comparable.
        cores = _load("bench_nec_corpus").apply_server_thread_policy()
        ground = json.loads(ground_json)
        if isinstance(ground, list):
            ground = tuple(ground)
        cls = bnc.load_design(design)
        b = cls()
        b.nominal_nsegs = int(nseg)

        eng = _build(b, engine, ground)
        t0 = time.perf_counter()
        zs = eng.impedance()
        cold = time.perf_counter() - t0
        # MomwireEngine memoises the solve in `_solved_cache`, so a second
        # impedance() on an unchanged engine is a dict lookup, not a solve --
        # measured 0.19 ms against a 259 ms cold solve on dipoles.invvee/bs2,
        # a 1300x "speedup" that is purely the cache. Drop it so the warm
        # number is a real second solve: that is what the UI pays on a knob
        # change, where the geometry moves and the cache key misses anyway.
        eng._solved_cache = None
        t1 = time.perf_counter()
        zs = eng.impedance()
        warm = time.perf_counter() - t1

        gain = None
        try:
            if getattr(eng, "supports_far_field", False):
                ff = eng.far_field(n_theta=18, n_phi=36, del_theta=5, del_phi=10)
                gain = float(ff.max_gain)
        except Exception as e:  # noqa: BLE001 — a missing pattern is not a failed solve
            out["gain_error"] = f"{type(e).__name__}: {e}"[:200]

        out.update(
            z=[[float(z.real), float(z.imag)] for z in zs],
            cold_s=cold,
            warm_s=warm,
            peak_gain_dbi=gain,
            peak_rss_mb=resource.getrusage(resource.RUSAGE_SELF).ru_maxrss * 1024 / 1e6,
            cores=cores,
            nominal_segs=bnc.total_nominal_segs(cls, int(nseg)),
        )
    except MemoryError:
        out["error"] = f"MemoryError: exceeded {mem_gb:g} GB cap"
    except Exception as e:  # noqa: BLE001 — report, never crash the ladder
        out["error"] = f"{type(e).__name__}: {e}"
    print(json.dumps(out))


def _build(b, engine, ground):
    from antennaknobs.engines.momwire import MomwireEngine
    from momwire import (
        ArrayBlockSolver,
        BSplineSolver,
        HMatrixSolver,
        RazorSolver,
        SinusoidalSolver,
    )

    if engine == "pynec":
        from antennaknobs.engines.pynec import PyNECEngine

        return PyNECEngine(b, ground=ground)
    if engine == "nec5":
        from antennaknobs.engines.nec5 import NEC5Engine

        return NEC5Engine(
            b, ground=ground, capture_dir=os.environ.get("NEC5_CAPTURE_DIR") or None
        )
    if engine == "sin":
        return MomwireEngine(b, solver=SinusoidalSolver, ground=ground)
    if engine == "razor-2p":
        return MomwireEngine(
            b,
            solver=RazorSolver,
            solver_kwargs={"nec5_quadrature": True},
            ground=ground,
        )
    if engine in ("hmatrix", "arrayblock"):
        return MomwireEngine(
            b,
            solver=HMatrixSolver if engine == "hmatrix" else ArrayBlockSolver,
            solver_kwargs={"degree": 2},
            ground=ground,
        )
    if engine in ("bs1", "bs2"):
        return MomwireEngine(
            b,
            solver=BSplineSolver,
            solver_kwargs={"degree": 1 if engine == "bs1" else 2},
            ground=ground,
        )
    raise ValueError(f"unknown engine {engine!r}")


def run_cell(design, nseg, engine, ground, timeout, mem_gb):
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
        return {"error": f"timeout > {timeout}s"}
    if proc.returncode != 0 and not proc.stdout.strip():
        tail = (proc.stderr or "").strip()[-200:]
        return {"error": f"worker exited {proc.returncode}: {tail}"}
    try:
        return json.loads(proc.stdout.strip().splitlines()[-1])
    except (json.JSONDecodeError, IndexError):
        return {"error": f"unparseable worker output: {proc.stdout[-200:]!r}"}


def _sha(path):
    try:
        return subprocess.run(
            ["git", "-C", str(path), "rev-parse", "HEAD"],
            capture_output=True,
            text=True,
            timeout=30,
        ).stdout.strip()[:12]
    except Exception:  # noqa: BLE001 — meta, never fatal
        return "unknown"


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--designs", nargs="+", default=None)
    ap.add_argument("--engines", nargs="+", default=list(ENGINES))
    ap.add_argument("--timeout", type=float, default=600.0)
    ap.add_argument("--mem-gb", type=float, default=12.0)
    ap.add_argument("--out", type=Path, required=True)
    a = ap.parse_args(argv)

    bc = _load("bench_catalog")
    designs = a.designs or bc.all_designs()
    root = Path(__file__).resolve().parents[1]

    meta = {
        "_meta": {
            "box": platform.node(),
            "cpus": os.cpu_count(),
            "engines": a.engines,
            "ground": list(DEFAULT_GROUND),
            "mem_gb_cap": a.mem_gb,
            "timeout_s": a.timeout,
            "antennaknobs_sha": _sha(root),
            "momwire_sha": _sha(root / "momwire"),
            "blas_pin": "physical cores via threadpoolctl (AK#897/#898)",
            "started": time.strftime("%Y-%m-%d %H:%M:%S"),
            "designs": len(designs),
        }
    }
    a.out.parent.mkdir(parents=True, exist_ok=True)
    with open(a.out, "w") as fh:
        fh.write(json.dumps(meta) + "\n")
        for i, design in enumerate(designs, 1):
            base = bc.default_nseg(design)
            for rung, nseg in (("default", base), ("refined", base * 2)):
                for engine in a.engines:
                    t0 = time.perf_counter()
                    res = run_cell(
                        design, nseg, engine, list(DEFAULT_GROUND), a.timeout, a.mem_gb
                    )
                    row = {
                        "design": design,
                        "engine": engine,
                        "rung": rung,
                        "nominal_nsegs": nseg,
                        "cell_wall_s": time.perf_counter() - t0,
                        **res,
                    }
                    fh.write(json.dumps(row) + "\n")
                    fh.flush()
            print(f"[{i}/{len(designs)}] {design}", flush=True)
    print(f"wrote {a.out}")
    return 0


if __name__ == "__main__":
    if len(sys.argv) > 1 and sys.argv[1] == "--worker":
        worker_main(*sys.argv[2:])
    else:
        raise SystemExit(main())
