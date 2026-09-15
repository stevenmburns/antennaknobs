"""Refinement ladders on the four designs where bs2 leaves the tent pair (#1516).

    NEC5_EXE=<nec5cl> python scratch/1516-ladders/run_ladders.py

Measure only. `PLAN.md` holds the question, the setup and the registered
predictions; this file is the harness.

ONE WORKER SUBPROCESS PER CELL, serially, as in the catalog run: a fresh
interpreter per (design, variant, ground, rung, engine) so an `RLIMIT_AS` cap
turns a runaway fill into a clean MemoryError, a crash takes down a worker
rather than the sweep, and NEC-5's intermediate files cannot be seen by the next
cell.

EVERY CELL RECORDS THE MESH IT ACTUALLY BUILT, not the knob it was asked for.
That is the point of step 1: `nominal_nsegs` is a density, each design decides
which edges scale with it and which (feed gaps, corner stubs) stay fixed, and
the two parities coerce the fed edge differently. A ladder table that reports
the knob would compare rungs that are not the meshes that were solved.
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
RUNGS = (21, 40, 42, 84, 168)

# `nominal_nsegs=40` is the served razor-2p mesh: `_BackendSpec(name="razor-2p",
# default_n_per_wire=40)` and `adapter.py` assigns `n_per_wire` straight to
# `builder.nominal_nsegs`. All three engines run it so the rung stands alone.
SERVED_RUNG = 40

GROUNDS = {"free": "free", "somm": ("finite", 13.0, 0.005)}

# design -> (variants, grounds)
CASES = {
    "loops.skyloop_lmatch": (("stock", "bare"), ("free",)),
    "verticals.rectangle": (("stock",), ("free",)),
    "dipoles.koch_dipole": (("stock",), ("free",)),
    "verticals.four_square": (("stock",), ("free", "somm")),
}

DEFAULT_TIMEOUT_S = 300.0
DEFAULT_MEM_GB = 40.0
REFUSAL_TYPES = ("NotImplementedError", "ValueError", "TypeError")


# --------------------------------------------------------------------------
# worker
# --------------------------------------------------------------------------
def load_builder_cls(design, variant):
    sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "scripts"))
    import bench_converge as cvg

    cls = cvg.load_design(design)
    if variant == "stock":
        return cls
    if variant != "bare":
        raise ValueError(f"unknown variant {variant!r}")
    # The same antenna with its matching network removed and the SAME port
    # driven directly. A builder routes unknown attribute sets into `params`,
    # so monkeypatching `build_network` on the INSTANCE silently does nothing
    # and the engine keeps the L-match -- it has to be a subclass.
    from antennaknobs.network import Driven, Network, PortOnWire

    return type(
        "BareFeed",
        (cls,),
        {
            "build_network": lambda self: Network(
                ports={"feed": PortOnWire(name="feed")},
                sources=[Driven(port="feed", voltage=1 + 0j)],
            )
        },
    )


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


def built_mesh(engine_name, eng, builder):
    """The mesh the engine ACTUALLY built, KEYED BY GEOMETRY, plus the flat
    counts and the total.

    The key is each run's two endpoints rounded to 1e-4 m. NOT tighter: the
    deck antennaknobs writes formats coordinates as `%E` with six significant
    figures, so a metres-scale coordinate arrives with text rounding, and a
    1e-9 key matched NOTHING -- every wire read as "only one side has it", which
    is a total-mismatch signature rather than a difference. 1e-5 was still on
    the boundary (`verticals.rectangle` read 3.55379 one side and 3.55380 the
    other, and reported two phantom wire differences on every rung). 0.1 mm is
    500x below the smallest feature here, a 50 mm feed wire.

    Keyed by geometry because the flat lists are not comparable: momwire's
    `_edge_segments` walks the fed polyline first while the NEC-5 deck lists
    `GW` cards in builder-wire order, so on `verticals.rectangle` the two read
    [2, 4, 35, 8, 35, 4] and [4, 2, 4, 35, 8, 35] -- the SAME mesh, and a
    positional comparison calls that a deck difference on every rung. Each run
    of segments is therefore keyed by its two endpoints, rounded to 1e-9 m, so
    "same mesh in a different order" and "different mesh" stop looking alike.
    """
    if engine_name == "nec5":
        by_wire = {}
        counts = []
        for line in eng.deck([builder.freq]).splitlines():
            if not line.startswith("GW"):
                continue
            f = line.split()
            n = int(f[2])
            p0 = tuple(round(float(x), 4) for x in f[3:6])
            p1 = tuple(round(float(x), 4) for x in f[6:9])
            by_wire[tuple(sorted((p0, p1)))] = n
            counts.append(n)
        return by_wire, counts, sum(counts)
    by_wire = {}
    counts = []
    for pl, edges in enumerate(eng._edge_segments):
        poly = eng._polylines[pl]
        for e, n in enumerate(edges):
            p0 = tuple(round(float(x), 4) for x in poly[e])
            p1 = tuple(round(float(x), 4) for x in poly[e + 1])
            by_wire[tuple(sorted((p0, p1)))] = int(n)
            counts.append(int(n))
    return by_wire, counts, sum(counts)


def min_delta_over_a(builder):
    """Smallest segment length over wire radius anywhere in the mesh, and the
    segment length that produced it. Read from the builder's own wires, so it
    needs no solve and is the same number for every engine."""
    import numpy as np

    from antennaknobs.engine import as_wire

    spec = getattr(builder, "build_wire_material", None)
    spec = spec() if callable(spec) else None
    default_a = spec.radius if spec is not None else 5e-4
    best = None
    for t in builder.build_wires():
        w = as_wire(t)
        length = float(np.linalg.norm(np.asarray(w.p1) - np.asarray(w.p0)))
        seg = length / max(1, w.n_seg)
        a = w.spec.radius if w.spec is not None else default_a
        cand = (seg / a, seg, a)
        if best is None or cand[0] < best[0]:
            best = cand
    return best


def worker_main(design, variant, ground_key, rung, engine, mem_gb):
    result = {"status": "error", "error": None, "error_type": None}
    t0 = time.perf_counter()
    try:
        cap = int(mem_gb * 2**30)
        resource.setrlimit(resource.RLIMIT_AS, (cap, cap))
        cls = load_builder_cls(design, variant)
        b = cls()
        b.nominal_nsegs = rung
        result["freq_hz"] = float(b.freq)
        ratio, seg, a = min_delta_over_a(b)
        result["min_delta_over_a"] = ratio
        result["min_seg_m"] = seg
        result["radius_m"] = a

        eng = build_engine(b, engine, GROUNDS[ground_key])
        result["parity"] = getattr(eng, "segment_parity", None)
        by_wire, counts, total = built_mesh(engine, eng, b)
        result["seg_counts"] = counts
        result["total_segs"] = total
        # JSON keys must be strings; the geometry key is what makes the
        # cross-engine mesh comparison positional-order-proof.
        result["mesh_by_wire"] = {repr(k): v for k, v in by_wire.items()}
        try:
            result["fed_segments"] = eng.fed_segments()
        except Exception as e:  # noqa: BLE001 -- informational, never fatal
            result["fed_segments"] = f"{type(e).__name__}: {e}"
        # The network as the BUILDER states it -- the one object all three
        # engines consume (`momwire.py` keeps it on `_network`, `nec5.py:394`
        # runs the same thing through `_network_as_meshed`). Read from the
        # builder so the record does not depend on an engine's private name.
        from antennaknobs.engine import _builder_network

        bnet = _builder_network(b)
        result["builder_network"] = repr(bnet)[:1500] if bnet is not None else None
        # Which NEC-5 card types antennaknobs wrote. A matching network applied
        # in Python leaves NO NT/LD line here, and that is the difference
        # between "the network is a deck difference" and "the network is an
        # amplifier applied identically to every engine" -- so it is recorded
        # rather than asserted.
        if engine == "nec5":
            result["deck_card_types"] = sorted(
                {
                    line.split()[0]
                    for line in eng.deck([b.freq]).splitlines()
                    if line.strip()
                }
            )

        ts = time.perf_counter()
        zs = eng.impedance()
        result["solve_s"] = time.perf_counter() - ts
        result["z"] = [[float(z.real), float(z.imag)] for z in zs]
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


# --------------------------------------------------------------------------
# driver
# --------------------------------------------------------------------------
def run_cell(design, variant, ground, rung, engine, timeout_s, mem_gb, nec5_exe):
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
        variant,
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
    ap.add_argument("--worker", nargs=6, default=None, help=argparse.SUPPRESS)
    ap.add_argument("--designs", nargs="*", default=None)
    ap.add_argument("--rungs", nargs="*", type=int, default=list(RUNGS))
    ap.add_argument("--out", default=None)
    ap.add_argument("--timeout", type=float, default=DEFAULT_TIMEOUT_S)
    ap.add_argument("--mem-gb", type=float, default=DEFAULT_MEM_GB)
    ap.add_argument("--nec5-exe", default=os.environ.get("NEC5_EXE", ""))
    a = ap.parse_args(argv)

    if a.worker:
        d, v, g, rung, e, mem = a.worker
        return worker_main(d, v, g, int(rung), e, float(mem))

    if not a.nec5_exe or not Path(a.nec5_exe).is_file():
        print("--nec5-exe (or NEC5_EXE) must name a NEC-5 binary", file=sys.stderr)
        return 2

    designs = a.designs or list(CASES)
    cells = [
        (d, v, g, rung, e)
        for d in designs
        for v in CASES[d][0]
        for g in CASES[d][1]
        for rung in a.rungs
        for e in ENGINES
    ]
    out_path = Path(a.out) if a.out else Path(__file__).with_name("records.jsonl")
    t_start = time.perf_counter()
    with open(out_path, "w", encoding="utf-8") as fh:
        for i, (d, v, g, rung, e) in enumerate(cells, 1):
            rec = run_cell(d, v, g, rung, e, a.timeout, a.mem_gb, a.nec5_exe)
            rec.update(design=d, variant=v, ground=g, rung=rung, engine=e)
            fh.write(json.dumps(rec) + "\n")
            fh.flush()
            z = rec.get("z")
            shown = f"{z[0][0]:.5g}{z[0][1]:+.5g}j" if z else rec["status"]
            print(
                f"[{i:3d}/{len(cells)}] {d:22s} {v:5s} {g:4s} x{rung:<3d} {e:5s} "
                f"segs={rec.get('total_segs', '?'):>5} "
                f"{rec.get('driver_wall_s', 0.0):7.2f}s  {shown}",
                flush=True,
            )
    print(f"\n{len(cells)} cells in {time.perf_counter() - t_start:.1f}s -> {out_path}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
