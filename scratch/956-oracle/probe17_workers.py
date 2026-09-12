"""#956: how many workers, MEASURED rather than assumed.

Haswell here is an i7-4770K: 4 physical cores, 8 logical. The in-medium
quadrature is floating-point bound, so more workers than cores buys the SMT
margin at best and contention at worst — and with inner BLAS/OpenMP threads
unpinned it is oversubscription, every worker trying to take the whole box.

Pinning happens in the ENVIRONMENT before numpy is imported, not after: a
thread pool already built inside numpy does not shrink because an env var
changed later. Hence the assignments above the numpy import.

Each count runs a fixed wall-clock window and reports pairs/second with the
first- and last-fifth throughput beside it. On a thermally limited part a "best
of N short runs" measures turbo headroom rather than the code.
"""

import os
import sys
import time

for _v in (
    "OMP_NUM_THREADS",
    "OPENBLAS_NUM_THREADS",
    "MKL_NUM_THREADS",
    "NUMEXPR_NUM_THREADS",
    "VECLIB_MAXIMUM_THREADS",
):
    os.environ[_v] = "1"
os.environ.setdefault("OPENBLAS_THREAD_TIMEOUT", "1")

import warnings  # noqa: E402
from pathlib import Path  # noqa: E402

import numpy as np  # noqa: E402

warnings.filterwarnings("ignore")
sys.path.insert(0, str(Path(__file__).resolve().parent))

import proj_oracle as PO  # noqa: E402

PO._VERBOSE = False
FREQ = 7.1e6
SOIL_A = (13.0, 0.005)


def sample(n):
    """A representative near-node in-medium batch: shallow below observers on
    the wire surface against below sources along the rise and a radial."""
    rng = np.random.default_rng(7)
    obs = np.column_stack([np.full(n, 5e-4), np.zeros(n), -rng.uniform(0.002, 0.15, n)])
    t_obs = np.tile([0.0, 0.0, 1.0], (n, 1))
    src = np.column_stack([rng.uniform(0.0, 3.0, n), np.zeros(n), np.full(n, -0.15)])
    t_src = np.tile([1.0, 0.0, 0.0], (n, 1))
    return obs, t_obs, src, t_src


def main():
    window = float(sys.argv[1]) if len(sys.argv) > 1 else 30.0
    counts = [int(x) for x in (sys.argv[2:] or ["1", "2", "4", "8"])]
    n = 10
    obs, t_obs, src, t_src = sample(n)
    print(
        f"i7-4770K, 4 cores / 8 threads. batch {n * n} pairs, "
        f"{window:.0f}s window per count, inner threads pinned to 1"
    )
    print(
        f"{'workers':>8} {'batches':>8} {'pairs/s':>10} "
        f"{'first-5th':>10} {'last-5th':>10} {'drift':>7}"
    )
    best = (0.0, None)
    for w in counts:
        proj = PO.make_proj_total_below(FREQ, *SOIL_A, workers=w)
        proj(obs[:2], t_obs[:2], src[:2], t_src[:2])  # warm the pool
        rates = []
        t_end = time.time() + window
        while time.time() < t_end:
            t0 = time.time()
            proj(obs, t_obs, src, t_src)
            rates.append((n * n) / (time.time() - t0))
        r = np.array(rates)
        k = max(1, len(r) // 5)
        f, ll = float(r[:k].mean()), float(r[-k:].mean())
        print(f"{w:8d} {len(r):8d} {r.mean():10.2f} {f:10.2f} {ll:10.2f} {ll / f:7.3f}")
        sys.stdout.flush()
        if r.mean() > best[0]:
            best = (float(r.mean()), w)
    print(f"\nbest: {best[1]} workers at {best[0]:.2f} pairs/s")


if __name__ == "__main__":
    main()
