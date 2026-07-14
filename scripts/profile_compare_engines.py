"""Side-by-side solve-time comparison across 7 engines × 3 N values over a
range of antenna designs spanning the solver-selection space (single elements,
beams, multiband dipoles, large single-wire structures, and arrays).

Engines compared:
  Bs1   — momwire BSplineSolver(degree=1) (the tent basis; the retired
          TriangularSolver was the same scheme to roundoff)
  Bs2   — momwire BSplineSolver(degree=2)
  Sin   — momwire SinusoidalSolver
  Arr   — momwire ArrayBlockSolver (element-aware block-low-rank)
  ACA   — momwire HMatrixSolver (hierarchical matrix / adaptive cross approx)
  PyNEC — antennaknobs.engines.pynec.PyNECEngine (ground="free")

Each cell is the mean wall-clock of impedance() across the design's
target bands, with an off-band warm-up call beforehand. Geometry/Z size
is identical across band frequencies for a given (design, N), so the
per-call cost is essentially N-and-solver-only and averaging hides
one-shot jitter.

See docs/status/2026-06-25-solver-selection-benchmark.md for a captured run
and the by-antenna-class solver-selection guide derived from it.
"""

from __future__ import annotations

# Mirror the UI backend's threading setup (web/server.py) BEFORE numpy/scipy/
# PyNEC import — each library snapshots the env at its own import time. Keep
# this in sync with web/server.py's thread policy: physical-core count for
# both OMP and OpenBLAS (fill and LU are sequential phases), OMP workers
# parked between regions. Env vars work here because they are set before the
# first numpy/scipy/PyNEC import — the server itself must use threadpoolctl
# at runtime instead (see issue #377).
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
os.environ.setdefault("OPENBLAS_NUM_THREADS", _NPROC)
os.environ.setdefault("OMP_NUM_THREADS", _NPROC)
os.environ.setdefault("OMP_WAIT_POLICY", "PASSIVE")
os.environ.setdefault("GOMP_SPINCOUNT", "0")

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
from antennaknobs.engines.pynec import PyNECEngine  # noqa: E402
from antennaknobs.engines.momwire import MomwireEngine  # noqa: E402
from momwire import (  # noqa: E402
    ArrayBlockSolver,
    BSplineSolver,
    HMatrixSolver,
    SinusoidalSolver,
)


NSEGS = (21, 41, 81)

# trap_fan_dipole target bands (17m / 15m / 12m / 10m measurement freqs)
TRAP_BANDS = (18.1575, 21.383, 24.97, 28.47)
TRAP_WARMUP = 17.0

# fandipole target bands (20m / 17m / 15m / 12m / 10m)
FAN_BANDS = (14.300, 18.1575, 21.383, 24.97, 28.47)
FAN_WARMUP = 13.0

# Single-band 10m designs (moxon, bowtiearray2x4, delta_loop). Geometry/Z size
# is fixed by (design, N), so these in-band points only average solve jitter.
TEN_M_BANDS = (28.0, 28.3, 28.57, 28.85)
TEN_M_WARMUP = 27.0


def make_momwire_solver(solver_cls, solver_kwargs):
    def solve(builder_cls, n, f):
        b = builder_cls()
        b.nominal_nsegs = n
        b.freq = f
        MomwireEngine(b, solver=solver_cls, solver_kwargs=solver_kwargs).impedance()

    return solve


def solve_pynec(builder_cls, n, f):
    b = builder_cls()
    b.nominal_nsegs = n
    b.freq = f
    PyNECEngine(b, ground="free").impedance()


ENGINES = [
    ("Bs1", make_momwire_solver(BSplineSolver, {"degree": 1})),
    ("Bs2", make_momwire_solver(BSplineSolver, {"degree": 2})),
    ("Sin", make_momwire_solver(SinusoidalSolver, None)),
    # ACA-accelerated B-spline solvers (degree=2 basis): the H-matrix solver
    # and the element-aware array-block solver. Built to beat the dense path on
    # large/array geometries; on small designs the ACA setup is pure overhead.
    ("Arr", make_momwire_solver(ArrayBlockSolver, None)),
    ("ACA", make_momwire_solver(HMatrixSolver, None)),
    ("PyNEC", solve_pynec),
]


def time_one(fn, builder_cls, n, f):
    t0 = time.perf_counter()
    fn(builder_cls, n, f)
    return time.perf_counter() - t0


def run_design(label, builder_cls, bands, warmup_freq):
    print(f"\n=== {label} ===")
    header = f"{'engine':<6} | " + " | ".join(f"{n:^16}" for n in NSEGS)
    print(header)
    print("-" * len(header))
    for name, fn in ENGINES:
        cells = []
        for n in NSEGS:
            try:
                time_one(fn, builder_cls, n, warmup_freq)  # warm-up
                times_ms = [time_one(fn, builder_cls, n, f) * 1e3 for f in bands]
            except Exception as e:
                cells.append(f"ERR: {type(e).__name__}")
                continue
            mean = sum(times_ms) / len(times_ms)
            spread = max(times_ms) - min(times_ms)
            cells.append(f"{mean:7.0f} ms (±{spread / 2:>4.0f})")
        print(f"{name:<6} | " + " | ".join(f"{c:^16}" for c in cells))


def main():
    print(
        f"OMP_NUM_THREADS={os.environ['OMP_NUM_THREADS']} "
        f"OPENBLAS_NUM_THREADS={os.environ['OPENBLAS_NUM_THREADS']} "
        f"OMP_WAIT_POLICY={os.environ['OMP_WAIT_POLICY']} "
        f"GOMP_SPINCOUNT={os.environ['GOMP_SPINCOUNT']}"
    )
    # Ordered small -> large so the timing matrix reads as a size sweep. Classes:
    # single element, small loop, beams, multiband dipoles, large single-wire
    # structures, then arrays (where the element-aware ArrayBlock solver pays off).
    run_design("invvee", InvVeeBuilder, TEN_M_BANDS, TEN_M_WARMUP)
    run_design("delta_loop", DeltaLoopBuilder, TEN_M_BANDS, TEN_M_WARMUP)
    run_design("moxon", MoxonBuilder, TEN_M_BANDS, TEN_M_WARMUP)
    run_design("yagi", YagiBuilder, TEN_M_BANDS, TEN_M_WARMUP)
    run_design("fandipole", FanBuilder, FAN_BANDS, FAN_WARMUP)
    run_design("trap_fan_dipole", TrapBuilder, TRAP_BANDS, TRAP_WARMUP)
    run_design("rhombic", RhombicBuilder, TEN_M_BANDS, TEN_M_WARMUP)
    run_design("lpda", LpdaBuilder, TEN_M_BANDS, TEN_M_WARMUP)
    run_design(
        "delta_looparray_1x4", DeltaLoopArray1x4Builder, TEN_M_BANDS, TEN_M_WARMUP
    )
    run_design("bowtiearray2x4", BowtieArrayBuilder, TEN_M_BANDS, TEN_M_WARMUP)


if __name__ == "__main__":
    main()
