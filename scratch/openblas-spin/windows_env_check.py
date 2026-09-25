"""Does setting the thread-pool wait variables from inside Python reach
OpenBLAS / OpenMP on Windows? (antennaknobs#1728, momwire#1203)

On Linux, `os.environ.setdefault(...)` before NumPy loads works exactly like
launch environment (37.6-39.4 against 37.6-39.3 ms per solve on Skylake). On
Windows it might not: NumPy's OpenBLAS is built with MinGW and may read a
different C runtime's copy of the environment than the one Python writes,
and momwire's Windows OpenMP is MSVC's vcomp, not libgomp.

Run it in the Python environment that has antennaknobs and momwire
installed (the same one you launch the workbench from):

    python windows_env_check.py

It runs fresh child processes in three modes, interleaved over three rounds,
each timing repeated free-space solves (N=400, 4 threads) for ~4 s:

  none      nothing set (the library defaults)
  envvar    the three variables in the child's launch environment
  inproc    nothing set at launch; the child sets them with
            os.environ.setdefault before importing NumPy, exactly as the
            momwire#1203 / antennaknobs#1728 blocks do

Works with whatever antennaknobs / momwire is installed, since it tests the
mechanism, not the packages. If inproc matches envvar, the blocks work on
Windows. If inproc matches none, they do not, and the frozen exes need the
variables in their launch environment instead.
"""

from __future__ import annotations

import os
import statistics
import subprocess
import sys

KEYS = ("OMP_WAIT_POLICY", "GOMP_SPINCOUNT", "OPENBLAS_THREAD_TIMEOUT")
VALUES = {
    "OMP_WAIT_POLICY": "PASSIVE",
    "GOMP_SPINCOUNT": "0",
    "OPENBLAS_THREAD_TIMEOUT": "1",
}

CHILD = r"""
import sys, time, warnings
warnings.simplefilter("ignore")
mode = sys.argv[1]
if mode == "inproc":  # exactly what the package blocks do, before NumPy loads
    import os
    for k, v in (("OMP_WAIT_POLICY", "PASSIVE"), ("GOMP_SPINCOUNT", "0"),
                 ("OPENBLAS_THREAD_TIMEOUT", "1")):
        os.environ.setdefault(k, v)
import numpy as np
from momwire.bspline import BSplineSolver
w = [np.array([(0, -5.0, 10.0), (0, 5.0, 10.0)])]
def solve():
    BSplineSolver(wires=w, n_per_edge_per_wire=[[400]], feeds=[(0, 5.0, 1 + 0j)],
                  wavelength=20.0, wire_radius=1e-3, degree=2).compute_impedance()
solve()
ts, end = [], time.perf_counter() + 4.0
while time.perf_counter() < end:
    t = time.perf_counter(); solve(); ts.append(time.perf_counter() - t)
ts = sorted(ts[len(ts) // 2:])
print(1e3 * ts[len(ts) // 2])
"""


def run(mode: str) -> float:
    env = {k: v for k, v in os.environ.items() if k not in KEYS}
    env["OMP_NUM_THREADS"] = env["OPENBLAS_NUM_THREADS"] = "4"
    child_mode = mode
    if mode == "envvar":
        env.update(VALUES)
        child_mode = "none"
    out = subprocess.run(
        [sys.executable, "-c", CHILD, child_mode],
        env=env,
        capture_output=True,
        text=True,
    )
    if out.returncode != 0:
        raise SystemExit(f"{mode} failed:\n{out.stderr[-2000:]}")
    return float(out.stdout.strip().splitlines()[-1])


def main() -> None:
    import importlib.metadata as md

    for pkg in ("antennaknobs", "momwire", "numpy"):
        try:
            print(f"{pkg} {md.version(pkg)}")
        except md.PackageNotFoundError:
            print(f"{pkg} not installed")
    modes = ("none", "envvar", "inproc")
    results: dict[str, list[float]] = {m: [] for m in modes}
    for r in range(3):
        for m in modes:
            ms = run(m)
            results[m].append(ms)
            print(f"round {r + 1}  {m:8} {ms:7.1f} ms/solve", flush=True)
    print("\nmedian ms/solve:")
    for m in modes:
        print(f"  {m:8} {statistics.median(results[m]):7.1f}")


if __name__ == "__main__":
    main()
