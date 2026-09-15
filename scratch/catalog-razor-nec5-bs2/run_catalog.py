"""Solve every built-in design three ways -- razor-2p, NEC-5, bs2 -- and record it.

    python scratch/catalog-razor-nec5-bs2/run_catalog.py --out records.jsonl

See PLAN.md for the question, the held-fixed axes, the three labelled confounds
and the registered predictions. This file is only the measurement.

ONE WORKER SUBPROCESS PER (design, engine, ground), serially. A fresh
interpreter per cell buys three things worth the ~0.4 s of import each time:

  * a solver that segfaults, OOMs or wedges takes down a worker, not the sweep;
  * `RLIMIT_AS` makes a runaway finite-ground fill die with a clean MemoryError
    instead of pushing the box into swap;
  * NEC-5 runs through intermediate files in a per-cell temp dir, so no two
    cells can see each other's printouts.

A cell that fails is a RECORD, not a gap: `status` is one of `ok`, `refused`,
`error`, `timeout`, and a refusal carries the engine's own sentence verbatim.
An engine that refuses a design is a finding about coverage (prediction P4), and
silently dropping the row would erase it.
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

ENGINES = ("razor", "nec5", "bs2")

# The app's DEFAULT_GROUND, spelled out rather than imported so the record says
# what was solved even if the constant later moves. `fast` is deliberately
# absent -- PLAN.md section 2 says why.
GROUNDS = {
    "free": "free",
    "somm": ("finite", 13.0, 0.005),
}

DEFAULT_TIMEOUT_S = 300.0
DEFAULT_MEM_GB = 40.0

# NEC-5 refuses a deck whose conductors touch or cross the ground plane, and
# momwire has its own refusals. Both arrive as exceptions; these are the types
# that mean "this engine declines this design", as opposed to "this engine
# broke". Anything else is recorded as `error` and shows up in the report.
REFUSAL_TYPES = ("NotImplementedError", "ValueError", "TypeError")


# --------------------------------------------------------------------------
# worker: runs in a fresh interpreter, prints one JSON object on stdout
# --------------------------------------------------------------------------
def build_engine(builder, engine, ground):
    from antennaknobs.engines.momwire import MomwireEngine
    from momwire import BSplineSolver, RazorSolver

    if engine == "bs2":
        return MomwireEngine(
            builder, solver=BSplineSolver, solver_kwargs={"degree": 2}, ground=ground
        )
    if engine == "razor":
        # `razor-2p` as the web roster binds it: the two-point NEC-5 quadrature
        # on, `extended_kernel` left at the solver default.
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


def design_flags(builder_cls):
    """Traits of the DESIGN, read once and attached to every engine's row so a
    distribution can be cut by them. Computed from the builder, never from a
    solve, so an engine that refuses still carries its flags."""
    import numpy as np

    from antennaknobs.engine import _builder_network

    flags = []
    b = builder_cls()
    try:
        wires = b.build_wires()
    except Exception as e:  # noqa: BLE001 -- a build failure is a recorded flag
        return [f"build_wires_failed:{type(e).__name__}"], None
    zmin = None
    for w in wires:
        p0, p1 = np.asarray(w[0], float), np.asarray(w[1], float)
        lo = min(float(p0[2]), float(p1[2]))
        zmin = lo if zmin is None else min(zmin, lo)
    if zmin is not None and zmin < 0.0:
        flags.append("buried")

    # `build_network()`, not a `network` attribute -- reading the wrong name
    # gives every design the same (absent) flag, which is a distribution that
    # cuts nothing while looking like it cut something.
    net = _builder_network(b)
    if net is not None:
        flags.append("network")
        kinds = {type(p).__name__ for p in net.ports.values()}
        for kind, label in (
            ("PortAtEnd", "end_ports"),
            ("PortAtVertex", "vertex_ports"),
            ("PortOnWire", "gap_ports"),
        ):
            if kind in kinds:
                flags.append(label)
        flags.append(f"n_network_ports:{len(net.ports)}")
    return flags, zmin


def worker_main(design, engine, ground_key, mem_gb):
    result = {"status": "error", "error": None, "error_type": None}
    t0 = time.perf_counter()
    try:
        resource.setrlimit(
            resource.RLIMIT_AS, (int(mem_gb * 2**30), int(mem_gb * 2**30))
        )
        sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "scripts"))
        import bench_converge as cvg

        builder_cls = cvg.load_design(design)
        flags, zmin = design_flags(builder_cls)
        result["flags"] = flags
        result["z_min_m"] = zmin
        result["total_nominal_segs"] = cvg.total_nominal_segs(builder_cls, 21)

        b = builder_cls()
        b.nominal_nsegs = 21
        result["freq_hz"] = float(getattr(b, "freq", float("nan")))

        eng = build_engine(b, engine, GROUNDS[ground_key])
        result["parity"] = getattr(eng, "segment_parity", None)
        try:
            result["fed_segments"] = eng.fed_segments()
        except Exception as e:  # noqa: BLE001 -- informational, never fatal
            result["fed_segments"] = f"{type(e).__name__}: {e}"

        ts = time.perf_counter()
        zs = eng.impedance()
        result["solve_s"] = time.perf_counter() - ts
        result["z"] = [[float(z.real), float(z.imag)] for z in zs]
        # Advisories are ABSORBED by the engine, not raised: read them off the
        # engine rather than trusting a warnings filter to have seen anything.
        adv = getattr(eng, "advisories", None)
        result["advisories"] = [str(a) for a in adv] if adv else []
        result["status"] = "ok"
    except MemoryError:
        result["status"] = "error"
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


# --------------------------------------------------------------------------
# driver
# --------------------------------------------------------------------------
def run_cell(design, engine, ground_key, timeout_s, mem_gb, nec5_exe):
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
        engine,
        ground_key,
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
            "error": f"no result in {timeout_s:g}s",
            "error_type": "TimeoutExpired",
            "wall_s": time.perf_counter() - t0,
        }
    line = cp.stdout.strip().splitlines()
    if not line:
        return {
            "status": "error",
            "error_type": "NoOutput",
            "error": (cp.stderr or "")[-2000:],
            "returncode": cp.returncode,
            "wall_s": time.perf_counter() - t0,
        }
    try:
        rec = json.loads(line[-1])
    except json.JSONDecodeError:
        return {
            "status": "error",
            "error_type": "BadOutput",
            "error": line[-1][:2000],
            "wall_s": time.perf_counter() - t0,
        }
    rec["driver_wall_s"] = time.perf_counter() - t0
    return rec


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("--worker", nargs=4, default=None, help=argparse.SUPPRESS)
    ap.add_argument("--designs", nargs="*", default=None)
    ap.add_argument("--engines", nargs="*", default=list(ENGINES), choices=ENGINES)
    ap.add_argument("--grounds", nargs="*", default=["free", "somm"])
    ap.add_argument("--out", default=None)
    ap.add_argument("--timeout", type=float, default=DEFAULT_TIMEOUT_S)
    ap.add_argument("--mem-gb", type=float, default=DEFAULT_MEM_GB)
    ap.add_argument(
        "--nec5-exe", default=os.environ.get("NEC5_EXE", ""), help="path to nec5cl"
    )
    a = ap.parse_args(argv)

    if a.worker:
        d, e, g, mem = a.worker
        return worker_main(d, e, g, float(mem))

    if not a.nec5_exe or not Path(a.nec5_exe).is_file():
        print("--nec5-exe (or NEC5_EXE) must name a NEC-5 binary", file=sys.stderr)
        return 2

    sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "scripts"))
    from antennaknobs.cli import list_builtin_designs

    designs = a.designs or list_builtin_designs()
    out_path = Path(a.out) if a.out else Path(__file__).with_name("records.jsonl")
    # PROVENANCE AS THE FIRST LINE OF THE DATA, not as a commit message. Both
    # SHAs, both package versions, every extension's resolved path and the
    # accelerator variant travel with the records, so a reader of the JSONL
    # alone can tell what produced it -- and a stale checkout cannot be
    # discovered after the fact. Added for the 2026-09-15 published re-run;
    # `report.py` skips any line without a "design" key, so a records file
    # written before this (b9bc3e2f0's) still loads.
    sys.path.insert(0, str(Path(__file__).resolve().parent))
    import verify_env

    provenance = verify_env.collect(a.nec5_exe)
    if not provenance["all_checks_pass"]:
        failed = [k for k, v in provenance["checks"].items() if not v]
        print(f"STALENESS GUARD FAILED: {failed}", file=sys.stderr)
        return 3
    total = len(designs) * len(a.engines) * len(a.grounds)
    done = 0
    t_start = time.perf_counter()
    with open(out_path, "w", encoding="utf-8") as fh:
        fh.write(json.dumps(provenance) + "\n")
        for design in designs:
            for ground in a.grounds:
                for engine in a.engines:
                    rec = run_cell(
                        design, engine, ground, a.timeout, a.mem_gb, a.nec5_exe
                    )
                    rec.update(design=design, engine=engine, ground=ground)
                    fh.write(json.dumps(rec) + "\n")
                    fh.flush()
                    done += 1
                    z = rec.get("z")
                    zs = f"{z[0][0]:.4g}{z[0][1]:+.4g}j" if z else rec["status"]
                    print(
                        f"[{done:4d}/{total}] {design:42s} {ground:5s} {engine:6s} "
                        f"{rec.get('driver_wall_s', 0.0):7.2f}s  {zs}",
                        flush=True,
                    )
    print(f"\n{done} cells in {time.perf_counter() - t_start:.1f}s -> {out_path}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
