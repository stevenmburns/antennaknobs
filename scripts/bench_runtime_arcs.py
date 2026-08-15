#!/usr/bin/env python3
"""Runtime before/after the momwire memory arcs (issue #927).

Drives the same antennaknobs checkout against two interpreters — a
pre-arc venv holding the momwire==0.29.0 PyPI wheel and the working
venv holding momwire@main editable — over the #927 matrix:
{sin pm, sin galerkin, bs2} x {free, PEC, refl-coef, sommerfeld} x
{single-k, 20-pt sweep} x an N ladder on arrays.bowtiearray2x4, plus
EK rungs and the grounded-enrichment cells (verticals.vertical) for
the momwire#328 path.

Ladder discipline (scratch/bs2-memory-ladder.json): each rung is a
fresh subprocess under /usr/bin/time -v (wall + child max RSS) with an
address-space cap, BLAS/OpenMP pinned per the 2026-06-15 engine
comparison doc (physical cores, PASSIVE waits). Old and new venvs run
back-to-back per rung so slow machine drift can't masquerade as a
regression. Results append to a JSONL in scratch/.

Usage:
    .venv/bin/python scripts/bench_runtime_arcs.py --list
    .venv/bin/python scripts/bench_runtime_arcs.py --filter 'N35'
    .venv/bin/python scripts/bench_runtime_arcs.py            # full matrix
"""

from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
import sys
import time

_WORKER = "--worker"
OLD_PY = os.path.expanduser("~/stevenmburns/venv-momwire-0290/bin/python")
NEW_PY = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
    ".venv",
    "bin",
    "python",
)
OUT = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
    "scratch",
    "runtime-arcs-ladders.jsonl",
)
AS_CAP_KB = 24 * 1024 * 1024  # ulimit -v 24 GB on the 32 GB box

SOLVERS = {
    "sin": ("SinusoidalSolver", {}),
    "sing": ("SinusoidalGalerkinSolver", {}),
    "bs2": ("BSplineSolver", {"degree": 2}),
}
GROUNDS = {
    "free": None,
    "pec": "pec",
    "refl": ["finite-fast", 13.0, 0.005],
    "somm": ["finite", 13.0, 0.005],
}
SWEEP_PTS = 20


def cell_id(spec) -> str:
    bits = [
        spec["design"].split(".")[-1],
        spec["solver"],
        spec["ground"],
        spec["mode"],
        f"N{spec['n_per_wire']}",
    ]
    if spec.get("ek"):
        bits.append("ek")
    if spec.get("enrich"):
        bits.append("enr")
    return "|".join(bits)


def build_matrix() -> list[dict]:
    specs = []

    def add(design, solver, ground, mode, n, ek=False, enrich=False, repeats=1):
        specs.append(
            {
                "design": design,
                "solver": solver,
                "ground": ground,
                "mode": mode,
                "n_per_wire": n,
                "ek": ek,
                "enrich": enrich,
                "repeats": repeats,
            }
        )

    bowtie = "arrays.bowtiearray2x4"
    # Single-k ladder, full cross: basis ~304 / 1216 / 3968 / 8320.
    for sk in SOLVERS:
        for gk in GROUNDS:
            for n, reps in ((9, 3), (35, 3), (115, 1), (241, 1)):
                add(bowtie, sk, gk, "single", n, repeats=reps)
    # 20-pt sweeps: full cross at the two small rungs...
    for sk in SOLVERS:
        for gk in GROUNDS:
            for n, reps in ((9, 3), (35, 1)):
                add(bowtie, sk, gk, "sweep", n, repeats=reps)
    # ...plus the accepted-cost-B config (sin pm, refl, basis ~600) and
    # selected mid-size rungs to see the sweep costs at scale.
    add(bowtie, "sin", "refl", "sweep", 17, repeats=3)
    for sk, gk in (("sin", "refl"), ("sing", "somm"), ("bs2", "free"), ("bs2", "somm")):
        add(bowtie, sk, gk, "sweep", 115)
    # EK rungs (sin family; bs2+EK exists but EK is a sin-study knob here).
    add(bowtie, "sin", "free", "single", 35, ek=True, repeats=3)
    add(bowtie, "sing", "free", "single", 35, ek=True, repeats=3)
    add(bowtie, "sin", "free", "sweep", 35, ek=True)
    # Grounded enrichment (momwire#328 path): verticals.vertical, K=4 feed
    # junction, variant "raw" so the correction can't self-suppress.
    vert = "verticals.vertical"
    for n, reps in ((21, 3), (81, 3), (161, 1)):
        add(vert, "bs2", "somm", "single", n, enrich=True, repeats=reps)
    add(vert, "bs2", "refl", "single", 81, enrich=True, repeats=3)
    add(vert, "bs2", "somm", "single", 81, repeats=3)  # no-enrichment baseline
    return specs


# ----------------------------------------------------------------- worker


def run_worker(spec_json: str) -> None:
    import importlib
    import time as _t

    spec = json.loads(spec_json)
    mod = importlib.import_module(f"antennaknobs.designs.{spec['design']}")
    b = mod.Builder()
    b.nominal_nsegs = spec["n_per_wire"]
    basis = sum(int(w[2]) for w in b.build_wires())

    import momwire
    from antennaknobs.engines.momwire import MomwireEngine

    solver_name, skw = SOLVERS[spec["solver"]]
    skw = dict(skw)
    if spec.get("enrich"):
        skw.update({"use_singular_enrichment": True, "enrichment_variant": "raw"})
    ground = GROUNDS[spec["ground"]]
    if isinstance(ground, list):
        ground = tuple(ground)

    t0 = _t.perf_counter()
    eng = MomwireEngine(
        b,
        solver=getattr(momwire, solver_name),
        solver_kwargs=skw or None,
        ground=ground,
        ground_z=0.0,
        extended_kernel=bool(spec.get("ek")),
    )
    t_build = _t.perf_counter() - t0

    f0 = float(b.freq)
    t0 = _t.perf_counter()
    if spec["mode"] == "sweep":
        import numpy as np

        freqs = np.linspace(0.97 * f0, 1.03 * f0, SWEEP_PTS)
        zs = eng.impedance_sweep(freqs)
        z = complex(zs[0][0])
    else:
        z = complex(eng.impedance()[0])
    t_solve = _t.perf_counter() - t0

    import importlib.metadata as md

    print(
        "RESULT "
        + json.dumps(
            {
                "momwire": md.version("momwire"),
                "basis": basis,
                "t_build_s": round(t_build, 4),
                "t_solve_s": round(t_solve, 4),
                "z_re": z.real,
                "z_im": z.imag,
            }
        ),
        flush=True,
    )


# ------------------------------------------------------------- orchestrator


def pinned_env() -> dict:
    env = dict(os.environ)
    env.update(
        {
            "OPENBLAS_NUM_THREADS": "1",
            "OMP_NUM_THREADS": "4",  # physical cores on the Haswell box
            "MKL_NUM_THREADS": "4",
            "OMP_WAIT_POLICY": "PASSIVE",
            "GOMP_SPINCOUNT": "0",
        }
    )
    return env


def run_rung(py: str, spec: dict) -> dict:
    import resource

    def cap():
        resource.setrlimit(resource.RLIMIT_AS, (AS_CAP_KB * 1024, AS_CAP_KB * 1024))

    best = None
    for _ in range(spec.get("repeats", 1)):
        proc = subprocess.run(
            [
                "/usr/bin/time",
                "-v",
                py,
                os.path.abspath(__file__),
                _WORKER,
                json.dumps(spec),
            ],
            capture_output=True,
            text=True,
            env=pinned_env(),
            preexec_fn=cap,
        )
        line = next(
            (ln for ln in proc.stdout.splitlines() if ln.startswith("RESULT ")), None
        )
        if line is None:
            return {"error": proc.stderr.strip()[-800:], "rc": proc.returncode}
        res = json.loads(line[len("RESULT ") :])
        m = re.search(r"Maximum resident set size \(kbytes\): (\d+)", proc.stderr)
        res["max_rss_mb"] = round(int(m.group(1)) / 1024.0, 1) if m else None
        if best is None or res["t_solve_s"] < best["t_solve_s"]:
            best = res
    return best


def main() -> None:
    if len(sys.argv) >= 3 and sys.argv[1] == _WORKER:
        run_worker(sys.argv[2])
        return

    ap = argparse.ArgumentParser()
    ap.add_argument("--list", action="store_true", help="Print the matrix and exit")
    ap.add_argument("--filter", default="", help="Substring filter on cell id")
    ap.add_argument("--out", default=OUT)
    args = ap.parse_args()

    specs = [s for s in build_matrix() if args.filter in cell_id(s)]
    if args.list:
        for s in specs:
            print(cell_id(s))
        print(f"{len(specs)} cells x 2 venvs")
        return

    lanes = [("old", OLD_PY), ("new", NEW_PY)]
    t_start = time.time()
    with open(args.out, "a") as fh:
        for i, spec in enumerate(specs):
            for lane, py in lanes:
                res = run_rung(py, spec)
                row = {"cell": cell_id(spec), "lane": lane, **spec, **res}
                fh.write(json.dumps(row) + "\n")
                fh.flush()
                tag = (
                    f"solve={res['t_solve_s']:.2f}s rss={res['max_rss_mb']}MB"
                    if "t_solve_s" in res
                    else f"ERROR rc={res.get('rc')}"
                )
                print(
                    f"[{i + 1}/{len(specs)} {lane}] {cell_id(spec)}  {tag}  "
                    f"(elapsed {time.time() - t_start:.0f}s)",
                    flush=True,
                )


if __name__ == "__main__":
    main()
