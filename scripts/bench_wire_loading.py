"""Runtime cost of distributed wire loading (momwire#131 / issues #316-#318).

Question (NEXT_ARC_PLAN item 1): is lossy wire cheap enough to enable by
default? For each design in a small->large matrix this times, with a fresh
builder+engine per call (the web server's per-tick pattern):

  single — engine.impedance() at the design's default freq
  swept  — engine.impedance_sweep() over 41 points, +/-3 % around freq

for three wire variants:

  ideal — wire_type=None (PEC, the classic path; the control)
  bare  — "18-awg" (conductivity only -> skin-effect R')
  pvc   — "18-awg-pvc" (conductivity + insulation L')

Besides wall-clock, the loading entry points in momwire's BSpline family
(_loading_gram build, _apply_loading, HMatrix zblock's _loading_block) are
wrapped to report the *loading-attributable* seconds and the cache
behaviour (gram builds should be 1/instance; the per-omega CSR cache in
_loading_block should miss once per k, never within a k).

Prediction to verify: loading build is O(N) numpy with no kernel evals;
expect the loading share <1 % of the solve. See the recommendation memo in
docs/status/ for the captured run and the default-on decision.
"""

from __future__ import annotations

# Mirror the UI backend's threading setup (web/server.py) BEFORE numpy/scipy
# import — each library snapshots the env at its own import time.
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

import numpy as np  # noqa: E402

from antennaknobs.designs.arrays.bowtiearray2x4 import (  # noqa: E402
    Builder as BowtieArrayBuilder,
)
from antennaknobs.designs.dipoles.invvee import Builder as InvVeeBuilder  # noqa: E402
from antennaknobs.designs.dipoles.invvee_coax_station import (  # noqa: E402
    Builder as StationBuilder,
)
from antennaknobs.designs.dipoles.pota_invvee import (  # noqa: E402
    Builder as PotaBuilder,
)
from antennaknobs.designs.specialty.hentenna import (  # noqa: E402
    Builder as HentennaBuilder,
)
from antennaknobs.designs.wire.rhombic import Builder as RhombicBuilder  # noqa: E402
from antennaknobs.engines.momwire import MomwireEngine  # noqa: E402
from momwire import ArrayBlockSolver, BSplineSolver, HMatrixSolver  # noqa: E402
from momwire.bspline import BSplineSolver as _Base  # noqa: E402


# ---------------------------------------------------------------------------
# Instrumentation: accumulate loading-attributable seconds + cache stats.
# Patched on the BSpline base so HMatrix/ArrayBlock subclasses inherit it.
# ---------------------------------------------------------------------------

STATS = {
    "gram_builds": 0,
    "gram_s": 0.0,
    "apply_calls": 0,
    "apply_s": 0.0,
    "block_calls": 0,
    "block_s": 0.0,
    "csr_misses": 0,
}


def _reset_stats():
    for k in STATS:
        STATS[k] = 0 if isinstance(STATS[k], int) else 0.0


_orig_gram = _Base._loading_gram
_orig_apply = _Base._apply_loading
_orig_block = _Base._loading_block


def _timed_gram(self):
    fresh = self._cached_loading_gram is None
    t0 = time.perf_counter()
    out = _orig_gram(self)
    dt = time.perf_counter() - t0
    if fresh:
        STATS["gram_builds"] += 1
        STATS["gram_s"] += dt
    return out


def _timed_apply(self, Z, omega=None):
    t0 = time.perf_counter()
    out = _orig_apply(self, Z, omega=omega)
    STATS["apply_calls"] += 1
    STATS["apply_s"] += time.perf_counter() - t0
    return out


def _timed_block(self, I, J, omega=None):
    key = omega if omega is not None else self.omega
    cache = getattr(self, "_loading_csr_cache", None)
    if cache is None or cache[0] != key:
        STATS["csr_misses"] += 1
    t0 = time.perf_counter()
    out = _orig_block(self, I, J, omega=omega)
    STATS["block_calls"] += 1
    STATS["block_s"] += time.perf_counter() - t0
    return out


_Base._loading_gram = _timed_gram
_Base._apply_loading = _timed_apply
_Base._loading_block = _timed_block


# ---------------------------------------------------------------------------
# Benchmark matrix
# ---------------------------------------------------------------------------

VARIANTS = (("ideal", None), ("bare", "18-awg"), ("pvc", "18-awg-pvc"))

# (label, builder_cls, solver_cls, nominal_nsegs)
CASES = (
    ("invvee N=21", InvVeeBuilder, BSplineSolver, 21),
    ("invvee N=81", InvVeeBuilder, BSplineSolver, 81),
    ("hentenna N=21", HentennaBuilder, BSplineSolver, 21),
    ("pota_invvee N=21", PotaBuilder, BSplineSolver, 21),
    ("invvee_coax_station N=21", StationBuilder, BSplineSolver, 21),
    ("rhombic N=21", RhombicBuilder, BSplineSolver, 21),
    ("rhombic N=81", RhombicBuilder, BSplineSolver, 81),
    ("bowtiearray2x4 N=21 Arr", BowtieArrayBuilder, ArrayBlockSolver, 21),
    ("bowtiearray2x4 N=21 ACA", BowtieArrayBuilder, HMatrixSolver, 21),
)

N_SINGLE = 3  # timed repeats for the single solve
N_SWEEP_PTS = 41


def _make_engine(builder_cls, solver_cls, nsegs, wire_type):
    b = builder_cls()
    b.nominal_nsegs = nsegs
    # Always assign: None must override a design's own default (pota_invvee
    # defaults to "22-awg-pvc") so the ideal row is truly ideal.
    b.wire_type = wire_type
    return MomwireEngine(b, solver=solver_cls)


def _time_single(builder_cls, solver_cls, nsegs, wire_type):
    """Fresh engine per call (the per-tick pattern); returns (mean_s, stats)."""
    _make_engine(builder_cls, solver_cls, nsegs, wire_type).impedance()  # warm-up
    _reset_stats()
    times = []
    for _ in range(N_SINGLE):
        eng = _make_engine(builder_cls, solver_cls, nsegs, wire_type)
        t0 = time.perf_counter()
        eng.impedance()
        times.append(time.perf_counter() - t0)
    return float(np.mean(times)), dict(STATS)


def _time_sweep(builder_cls, solver_cls, nsegs, wire_type):
    eng = _make_engine(builder_cls, solver_cls, nsegs, wire_type)
    freqs = eng.builder.freq * np.linspace(0.97, 1.03, N_SWEEP_PTS)
    _reset_stats()
    t0 = time.perf_counter()
    eng.impedance_sweep(freqs)
    return time.perf_counter() - t0, dict(STATS)


def _fmt_loading(stats, total_s, n_calls):
    load_s = (stats["gram_s"] + stats["apply_s"] + stats["block_s"]) / n_calls
    share = 100.0 * load_s / total_s if total_s > 0 else 0.0
    return load_s * 1e3, share


def main():
    import sys

    # Optional argv substring filters: run only matching case labels.
    filters = sys.argv[1:]
    cases = [c for c in CASES if not filters or any(f in c[0] for f in filters)]
    print(
        f"OMP_NUM_THREADS={os.environ['OMP_NUM_THREADS']} "
        f"OPENBLAS_NUM_THREADS={os.environ['OPENBLAS_NUM_THREADS']}"
    )
    print(
        f"\nsingle = mean of {N_SINGLE} fresh-engine impedance() calls; "
        f"swept = one impedance_sweep({N_SWEEP_PTS} pts).\n"
        "loading = ms spent in _loading_gram/_apply_loading/_loading_block "
        "(per solve), and its share of wall-clock."
    )
    for label, builder_cls, solver_cls, nsegs in cases:
        print(f"\n=== {label} [{solver_cls.__name__}] ===")
        hdr = (
            f"{'variant':<6} | {'single':>10} | {'loading':>16} | "
            f"{'swept':>10} | {'loading':>16} | {'csr miss':>8}"
        )
        print(hdr)
        print("-" * len(hdr))
        for vname, wtype in VARIANTS:
            s_mean, s_stats = _time_single(builder_cls, solver_cls, nsegs, wtype)
            s_load_ms, s_share = _fmt_loading(s_stats, s_mean, N_SINGLE)
            w_s, w_stats = _time_sweep(builder_cls, solver_cls, nsegs, wtype)
            w_load_ms, w_share = _fmt_loading(w_stats, w_s, 1)
            print(
                f"{vname:<6} | {s_mean * 1e3:8.1f} ms | "
                f"{s_load_ms:7.2f} ms {s_share:4.1f}% | "
                f"{w_s * 1e3:8.0f} ms | "
                f"{w_load_ms:7.2f} ms {w_share:4.1f}% | "
                f"{w_stats['csr_misses']:>8}"
            )


if __name__ == "__main__":
    main()
