"""AK#2241: the end-to-end engine comparison the test suite cannot afford.

A 7.1 MHz dipole behind a 1000-section RLCG ladder (4002 MNA unknowns),
through `make_engine_factory("momwire:bspline", None)`: `.impedance()` and a
three-point `impedance_sweep` on the sparse path (the default), then the same
engine forced dense. Dense is ~1 GB and seconds per frequency here; run under
`prlimit --as=6G`. The builder is `tests/test_sparse_mna_2241.py`'s own.

Usage: python e2e_dense_1000.py [N_SECTIONS]
"""

import resource
import sys
import time
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "tests"))
import test_sparse_mna_2241 as t  # noqa: E402

n = int(sys.argv[1]) if len(sys.argv) > 1 else 1000
freqs = [6.9, 7.1, 7.3]
e = t._engine(n)
for path in ("sparse", "dense"):
    with t.forced(path):
        t0 = time.perf_counter()
        z = complex(np.atleast_1d(e.impedance())[0])
        t1 = time.perf_counter()
        zs = np.asarray(e.impedance_sweep(freqs))[:, 0]
        t2 = time.perf_counter()
    rss = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss / 1024
    print(
        f"{path:6s} Z {z:.10f}  impedance {t1 - t0:.2f} s  sweep(3) {t2 - t1:.2f} s  peak RSS {rss:.0f} MB"
    )
    if path == "sparse":
        z_s, zs_s = z, zs
    else:
        print(
            f"|dZ|/|Z| {abs(z_s - z) / abs(z):.2e}  sweep worst {np.max(np.abs(zs_s - zs) / np.abs(zs)):.2e}"
        )
