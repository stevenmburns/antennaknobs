"""Solve the knob box on a grid, for the R and X heatmaps + contours."""

import json
import sys
import time
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent))

from harness import Deck

HERE = Path(__file__).resolve().parent

kind, n = sys.argv[1], int(sys.argv[2])
d = Deck(kind)
(a0, a1), (b0, b1) = d.box
A = np.linspace(a0, a1, n)
B = np.linspace(b0, b1, n)
R = np.zeros((n, n))
X = np.zeros((n, n))
t0 = time.perf_counter()
for j, bv in enumerate(B):
    for i, av in enumerate(A):
        z = d.z((av, bv))
        R[j, i], X[j, i] = z.real, z.imag
    d.flush()
    print(f"  row {j + 1}/{n}  {time.perf_counter() - t0:6.1f} s", flush=True)
d.flush()
out = Path(__file__).resolve().parent / f"grid_{kind}.json"
out.write_text(
    json.dumps(
        {
            "knobs": d.knobs,
            "A": A.tolist(),
            "B": B.tolist(),
            "R": R.tolist(),
            "X": X.tolist(),
            "z0": d.z0,
        }
    )
)
print(f"{kind}: {n}x{n} in {time.perf_counter() - t0:.1f} s -> {out.name}")
print(
    f"  R range {R.min():.1f} .. {R.max():.1f}   X range {X.min():.1f} .. {X.max():.1f}"
)
