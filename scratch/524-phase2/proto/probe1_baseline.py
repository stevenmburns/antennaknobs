"""A-2 task 2: the BASELINE crossing solve — spelling "naive".

Seeded (BELOW, ABOVE) media + declared K=2 junction, reached past the
crossing refusal the G-U5-3 way. The junction at z = 0 classifies as
GROUNDED, so its KCL row is dropped and each arm is an independent
ground-contact end with its own image continuation — the shipped contact
fiction, twice. Nothing is corrected here; this is the number every
crossing spelling is scored against.

Scores against BOTH the x1 engine print (74.761 - 57.730j) and the ladder
limit (~68.9 - 49.7j at x8) — the x1 print is ~6 ohm under-converged, so
the interesting comparison at x1 is print-vs-print at MATCHED mesh.

Run: .venv/bin/python scratch/524-phase2/proto/probe1_baseline.py [mult ...]
"""

from __future__ import annotations

import json
import sys
import time
from pathlib import Path

import numpy as np

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(Path(__file__).resolve().parents[3] / "momwire" / "tests"))

from momwire import _medium_spec  # noqa: E402
from momwire.bspline import BSplineSolver  # noqa: E402
from test_buried_serve_553 import SOIL_A, WL7  # noqa: E402

ANCHOR_X1 = 74.761 - 57.730j
LADDER = {1: 74.76 - 57.73j, 3: 70.86 - 51.68j, 5: 70.04 - 50.72j, 8: 68.88 - 49.73j}


def crossing_deck(mult=1):
    """SPEC.md deck 3 at segment multiplier `mult` (odd keeps the fed
    segment centred: engine EX 4,2,7 = arclength 4.3333 m on the monopole)."""
    return dict(
        wires=[
            np.array([(0.0, 0.0, -2.0), (0.0, 0.0, 0.0)]),
            np.array([(0.0, 0.0, 0.0), (0.0, 0.0, 10.0)]),
        ],
        n_per_edge_per_wire=[[4 * mult], [15 * mult]],
        junctions=[[(0, "end"), (1, "start")]],
        feeds=[(1, 4.3333333333, 1 + 0j)],
        wavelength=WL7,
        wire_radius=0.001,
        ground_z=0.0,
        ground_eps=SOIL_A,
        ground_model="sommerfeld",
    )


def seeded(kw):
    s = BSplineSolver(**kw)
    s._cached_wire_media = (_medium_spec.BELOW, _medium_spec.ABOVE)
    return s


def main():
    mults = [int(m) for m in sys.argv[1:]] or [1]
    out = {}
    for m in mults:
        s = seeded(crossing_deck(m))
        t0 = time.time()
        z, _ = s.compute_impedance()
        secs = time.time() - t0
        ref = LADDER.get(m, ANCHOR_X1)
        miss = abs(z - ref)
        out[f"x{m}"] = dict(
            z=f"{z:.4f}",
            ref=f"{ref:.4f}",
            miss_ohm=round(float(miss), 3),
            secs=round(secs, 1),
        )
        print(
            f"x{m}: Z = {z:9.4f}   engine(x{m}) = {ref:.4f}   "
            f"miss = {miss:7.3f} ohm   ({secs:.0f}s)"
        )
    res = HERE.parent / "results"
    res.mkdir(exist_ok=True)
    (res / "probe1-baseline.json").write_text(json.dumps(out, indent=1))


if __name__ == "__main__":
    main()
