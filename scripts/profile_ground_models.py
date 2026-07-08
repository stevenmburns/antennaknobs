"""Solve-time sweep across solver × ground model × segmentation, per design.

The sibling `profile_compare_engines.py` times the solvers free-space only.
This one adds the GROUND-MODEL axis: for each design it prints one table per
ground model (rows = engine, columns = N), so you can read the cost the finite
grounds add on top of the free-space solve — especially the momwire 0.8.0
"Sommerfeld everywhere" path, which is the expensive model.

Ground models (same four the web UI exposes, driven directly through each
engine's `ground=` spec — the constants match `DEFAULT_GROUND`):
  free  — free space (no ground)
  pec   — perfectly conducting plane (image method; no material solve)
  fast  — reflection-coefficient finite ground (NEC gn 0 / momwire "refl-coef")
  somm  — TRUE Sommerfeld-Norton finite ground (NEC gn 2 / momwire "sommerfeld")

Engines (rows within each table):
  Bs1   — momwire BSplineSolver(degree=1)
  Bs2   — momwire BSplineSolver(degree=2)
  Sin   — momwire SinusoidalSolver
  Arr   — momwire ArrayBlockSolver (element-aware block-low-rank)
  ACA   — momwire HMatrixSolver (hierarchical matrix / adaptive cross approx)
  PyNEC — antennaknobs.engines.pynec.PyNECEngine (NEC2 reference)

(TriangularSolver is retired from the antennaknobs backend and omitted.)

Both engines honour the identical ground spec, so PyNEC is wired for all four
models here — its Sommerfeld solve is the NEC gn 2 reference the momwire path
is validated against. Each cell is the mean wall-clock of impedance() across
the design's target bands, with an off-band warm-up call beforehand; geometry
and matrix size are fixed by (design, N), so per-call cost is essentially
N-solver-ground-only and averaging hides one-shot jitter.

Runtime warning: the Sommerfeld cells are seconds each (PyNEC gn 2 ~2× the
momwire dense path), so the full 10×4×3×6 matrix takes a while. Use the
--designs / --grounds / --engines / --nsegs filters to carve out a subset,
or --once to time a single in-band point instead of averaging the band set.

The tables print to stdout; momwire/CLI icecream tracing goes to stderr, so
pipe 2>/dev/null (or 2>run.log) for a clean capture:

    .venv/bin/python scripts/profile_ground_models.py 2>/dev/null | tee run.txt
"""

from __future__ import annotations

# Mirror the UI backend's threading setup (web/server.py) BEFORE numpy/scipy/
# PyNEC import — each library snapshots the env at its own import time. Keep
# this in sync with web/server.py: physical-core count for OMP/MKL, OpenBLAS
# pinned to 1, OMP workers parked between regions.
import os


def _physical_cpu_count() -> int:
    try:
        cores = set()
        phys, coreid = None, None
        with open("/proc/cpuinfo") as f:
            for line in f:
                key, _, val = line.partition(":")
                key, val = key.strip(), val.strip()
                if key == "physical id":
                    phys = val
                elif key == "core id":
                    coreid = val
                elif not line.strip() and phys is not None and coreid is not None:
                    cores.add((phys, coreid))
                    phys, coreid = None, None
        if phys is not None and coreid is not None:
            cores.add((phys, coreid))
        if cores:
            return len(cores)
    except OSError:
        pass
    return max(1, (os.cpu_count() or 1) // 2)


_NPROC = str(_physical_cpu_count())
os.environ.setdefault("OPENBLAS_NUM_THREADS", "1")
os.environ.setdefault("OMP_NUM_THREADS", _NPROC)
os.environ.setdefault("MKL_NUM_THREADS", _NPROC)
os.environ.setdefault("OMP_WAIT_POLICY", "PASSIVE")
os.environ.setdefault("GOMP_SPINCOUNT", "0")

import argparse  # noqa: E402
import time  # noqa: E402

from antennaknobs.designs.arrays.bowtiearray2x4 import (  # noqa: E402
    Builder as BowtieArrayBuilder,
)
from antennaknobs.designs.arrays.delta_looparray_1x4 import (  # noqa: E402
    Builder as DeltaLoopArray1x4Builder,
)
from antennaknobs.designs.beams.moxon import (  # noqa: E402
    Builder as MoxonBuilder,
)
from antennaknobs.designs.beams.yagi import (  # noqa: E402
    Builder as YagiBuilder,
)
from antennaknobs.designs.broadband.lpda import (  # noqa: E402
    Builder as LpdaBuilder,
)
from antennaknobs.designs.dipoles.invvee import (  # noqa: E402
    Builder as InvVeeBuilder,
)
from antennaknobs.designs.loops.delta_loop import (  # noqa: E402
    Builder as DeltaLoopBuilder,
)
from antennaknobs.designs.multiband.fandipole import (  # noqa: E402
    Builder as FanBuilder,
)
from antennaknobs.designs.multiband.trap_fan_dipole import (  # noqa: E402
    Builder as TrapBuilder,
)
from antennaknobs.designs.wire.rhombic import (  # noqa: E402
    Builder as RhombicBuilder,
)
from antennaknobs.engines.momwire import MomwireEngine  # noqa: E402
from antennaknobs.engines.pynec import DEFAULT_GROUND, PyNECEngine  # noqa: E402
from momwire import (  # noqa: E402
    ArrayBlockSolver,
    BSplineSolver,
    HMatrixSolver,
    SinusoidalSolver,
)


NSEGS = (21, 41, 81)

# Ground specs, keyed by the label used on the command line / table headers.
# `somm` and `fast` share DEFAULT_GROUND's eps_r/sigma so the two finite
# models differ only in the solve method, matching the web adapter.
GROUNDS = {
    "free": "free",
    "pec": "pec",
    "fast": ("finite-fast",) + DEFAULT_GROUND[1:],
    "somm": DEFAULT_GROUND,
}

# trap_fan_dipole target bands (17m / 15m / 12m / 10m measurement freqs)
TRAP_BANDS = (18.1575, 21.383, 24.97, 28.47)
TRAP_WARMUP = 17.0

# fandipole target bands (20m / 17m / 15m / 12m / 10m)
FAN_BANDS = (14.300, 18.1575, 21.383, 24.97, 28.47)
FAN_WARMUP = 13.0

# Single-band 10m designs (moxon, delta_loop, arrays, …). Geometry/Z size is
# fixed by (design, N), so these in-band points only average solve jitter.
TEN_M_BANDS = (28.0, 28.3, 28.57, 28.85)
TEN_M_WARMUP = 27.0


def make_momwire_solver(solver_cls, solver_kwargs):
    def solve(builder_cls, n, f, ground):
        b = builder_cls()
        b.nominal_nsegs = n
        b.freq = f
        MomwireEngine(
            b, solver=solver_cls, solver_kwargs=solver_kwargs, ground=ground
        ).impedance()

    return solve


def solve_pynec(builder_cls, n, f, ground):
    b = builder_cls()
    b.nominal_nsegs = n
    b.freq = f
    PyNECEngine(b, ground=ground).impedance()


ENGINES = [
    ("Bs1", make_momwire_solver(BSplineSolver, {"degree": 1})),
    ("Bs2", make_momwire_solver(BSplineSolver, {"degree": 2})),
    ("Sin", make_momwire_solver(SinusoidalSolver, None)),
    # ACA-accelerated B-spline solvers (degree=2 basis): the element-aware
    # array-block solver and the H-matrix solver. Both solve the Sommerfeld
    # ground on their fast paths since momwire 0.8.0.
    ("Arr", make_momwire_solver(ArrayBlockSolver, None)),
    ("ACA", make_momwire_solver(HMatrixSolver, None)),
    ("PyNEC", solve_pynec),
]

# Ordered small -> large so the timing matrix reads as a size sweep. Classes:
# single element, small loop, beams, multiband dipoles, large single-wire
# structures, then arrays (where the element-aware ArrayBlock solver pays off).
DESIGNS = [
    ("invvee", InvVeeBuilder, TEN_M_BANDS, TEN_M_WARMUP),
    ("delta_loop", DeltaLoopBuilder, TEN_M_BANDS, TEN_M_WARMUP),
    ("moxon", MoxonBuilder, TEN_M_BANDS, TEN_M_WARMUP),
    ("yagi", YagiBuilder, TEN_M_BANDS, TEN_M_WARMUP),
    ("fandipole", FanBuilder, FAN_BANDS, FAN_WARMUP),
    ("trap_fan_dipole", TrapBuilder, TRAP_BANDS, TRAP_WARMUP),
    ("rhombic", RhombicBuilder, TEN_M_BANDS, TEN_M_WARMUP),
    ("lpda", LpdaBuilder, TEN_M_BANDS, TEN_M_WARMUP),
    ("delta_looparray_1x4", DeltaLoopArray1x4Builder, TEN_M_BANDS, TEN_M_WARMUP),
    ("bowtiearray2x4", BowtieArrayBuilder, TEN_M_BANDS, TEN_M_WARMUP),
]


def time_one(fn, builder_cls, n, f, ground):
    t0 = time.perf_counter()
    fn(builder_cls, n, f, ground)
    return time.perf_counter() - t0


def run_design(
    label, builder_cls, bands, warmup_freq, *, engines, grounds, nsegs, once
):
    print(f"\n########## {label} ##########")
    for g_label in grounds:
        ground = GROUNDS[g_label]
        print(f"\n=== {label} · ground={g_label} ===")
        header = f"{'engine':<6} | " + " | ".join(f"{n:^16}" for n in nsegs)
        print(header)
        print("-" * len(header))
        for name, fn in engines:
            cells = []
            for n in nsegs:
                try:
                    time_one(fn, builder_cls, n, warmup_freq, ground)  # warm-up
                    pts = bands[:1] if once else bands
                    times_ms = [
                        time_one(fn, builder_cls, n, f, ground) * 1e3 for f in pts
                    ]
                except Exception as e:
                    cells.append(f"ERR: {type(e).__name__}")
                    continue
                mean = sum(times_ms) / len(times_ms)
                spread = max(times_ms) - min(times_ms)
                cells.append(f"{mean:7.0f} ms (±{spread / 2:>4.0f})")
            print(f"{name:<6} | " + " | ".join(f"{c:^16}" for c in cells))


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument(
        "--designs",
        help="comma-separated design labels (default: all 10)",
    )
    ap.add_argument(
        "--grounds",
        default=",".join(GROUNDS),
        help=f"comma-separated ground models (default: {','.join(GROUNDS)})",
    )
    ap.add_argument(
        "--engines",
        help="comma-separated engine labels (default: Bs1,Bs2,Sin,Arr,ACA,PyNEC)",
    )
    ap.add_argument(
        "--nsegs",
        default=",".join(map(str, NSEGS)),
        help=f"comma-separated segment counts (default: {','.join(map(str, NSEGS))})",
    )
    ap.add_argument(
        "--once",
        action="store_true",
        help="time a single in-band point instead of averaging the band set",
    )
    args = ap.parse_args()

    grounds = [g.strip() for g in args.grounds.split(",") if g.strip()]
    bad = [g for g in grounds if g not in GROUNDS]
    if bad:
        ap.error(f"unknown ground(s): {bad}; choose from {list(GROUNDS)}")

    nsegs = tuple(int(x) for x in args.nsegs.split(","))

    engines = ENGINES
    if args.engines:
        want = {e.strip() for e in args.engines.split(",")}
        engines = [e for e in ENGINES if e[0] in want]
        if not engines:
            ap.error(
                f"no engines matched {sorted(want)}; choose from "
                f"{[e[0] for e in ENGINES]}"
            )

    designs = DESIGNS
    if args.designs:
        want = {d.strip() for d in args.designs.split(",")}
        designs = [d for d in DESIGNS if d[0] in want]
        if not designs:
            ap.error(
                f"no designs matched {sorted(want)}; choose from "
                f"{[d[0] for d in DESIGNS]}"
            )

    print(
        f"OMP_NUM_THREADS={os.environ['OMP_NUM_THREADS']} "
        f"MKL_NUM_THREADS={os.environ['MKL_NUM_THREADS']} "
        f"OPENBLAS_NUM_THREADS={os.environ['OPENBLAS_NUM_THREADS']} "
        f"OMP_WAIT_POLICY={os.environ['OMP_WAIT_POLICY']} "
        f"GOMP_SPINCOUNT={os.environ['GOMP_SPINCOUNT']}"
    )
    print(
        f"grounds={grounds} nsegs={list(nsegs)} "
        f"engines={[e[0] for e in engines]} "
        f"designs={[d[0] for d in designs]} "
        f"{'single in-band point' if args.once else 'mean over band set'}"
    )

    for label, builder_cls, bands, warmup in designs:
        run_design(
            label,
            builder_cls,
            bands,
            warmup,
            engines=engines,
            grounds=grounds,
            nsegs=nsegs,
            once=args.once,
        )


if __name__ == "__main__":
    main()
