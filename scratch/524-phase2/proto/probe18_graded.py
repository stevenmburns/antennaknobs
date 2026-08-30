"""A-2 session 4, item 4: grade the mesh toward the interface.

Session-4 evidence says the crossing miss is near-interface QUADRATURE
INCONSISTENCY (cut-charge content truncated differently by analytic
moments, Gauss cross tables and the remainder grids), and momwire's Delta
DIVERGES under uniform refinement — the signature of an inconsistent
operator, not of a basis-space limit. The cheap decisive test: geometric
grading of the segments toward z = 0 on the straddle deck (probe17's
single-wire spelling, per-edge subset fill), which is also NEC-4's own
junction prescription. If Delta walks toward the engine limit
(-2.8 - 1.7j) as h(node) shrinks, the production design is graded knots
at the interface; if it stands still, the near-interface cell needs a
designed single-convention quadrature/table.

The mono column is graded IDENTICALLY above the plane so the Delta
instrument keeps cancelling the contact-monopole formulation gap.

Run: prlimit --as=$((8*1024*1024*1024)) .venv/bin/python \
     scratch/524-phase2/proto/probe18_graded.py [level ...]
Levels: 0 = uniform (probe17 regression), 1 = h_node 0.05 m,
        2 = h_node 0.0125 m.
"""

from __future__ import annotations

import json
import sys
import time
from pathlib import Path

import numpy as np

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
sys.path.insert(0, str(Path(__file__).resolve().parents[3] / "momwire" / "tests"))

from momwire.bspline import BSplineSolver  # noqa: E402
from probe17_straddle import seeded_straddle  # noqa: E402
from test_buried_serve_553 import SOIL_A, WL7  # noqa: E402

ENGINE_LIMIT = -2.8200 - 1.6940j  # x5 rung; ladder limit ~ -2.8 - 1.7j

# (below vertices ..., 0), counts; (0, above vertices ...), counts
GRADES = {
    0: dict(
        below=([-2.0], [4]),
        above=([10.0], [15]),
    ),
    1: dict(
        below=([-2.0, -0.5, -0.1], [3, 2, 2]),
        above=([0.1, 0.5, 10.0], [2, 2, 19]),
    ),
    2: dict(
        below=([-2.0, -0.5, -0.1, -0.025], [3, 2, 3, 2]),
        above=([0.025, 0.1, 0.5, 10.0], [2, 3, 2, 19]),
    ),
}


def straddle_graded(level):
    g = GRADES[level]
    zs = g["below"][0] + [0.0] + g["above"][0]
    counts = g["below"][1] + g["above"][1]
    pts = np.array([(0.0, 0.0, z) for z in zs])
    return dict(
        wires=[pts],
        n_per_edge_per_wire=[counts],
        feeds=[(0, 6.3333333333, 1 + 0j)],
        wavelength=WL7,
        wire_radius=0.001,
        ground_z=0.0,
        ground_eps=SOIL_A,
        ground_model="sommerfeld",
    )


def mono_graded(level):
    g = GRADES[level]
    zs = [0.0] + g["above"][0]
    counts = g["above"][1]
    pts = np.array([(0.0, 0.0, z) for z in zs])
    return dict(
        wires=[pts],
        n_per_edge_per_wire=[counts],
        feeds=[(0, 4.3333333333, 1 + 0j)],
        wavelength=WL7,
        wire_radius=0.001,
        ground_z=0.0,
        ground_eps=SOIL_A,
        ground_model="sommerfeld",
    )


def main():
    levels = [int(x) for x in sys.argv[1:]] or [1, 2]
    out = {}
    for lv in levels:
        s = seeded_straddle(straddle_graded(lv))
        geom = s._build_geometry()
        below = s._below_segments(geom)
        h_min = float(geom["h_per_seg"].min())
        print(
            f"level {lv}: {int(below.sum())} below / "
            f"{int((~below).sum())} above, h_node = {h_min:.4f} m",
            flush=True,
        )

        t0 = time.time()
        z, _ = s.compute_impedance()
        tc = time.time() - t0
        t0 = time.time()
        z_mono, _ = BSplineSolver(**mono_graded(lv)).compute_impedance()
        tm = time.time() - t0
        d = z - z_mono
        dist = abs(d - ENGINE_LIMIT)
        out[f"level{lv}"] = dict(
            z=f"{z:.4f}",
            mono=f"{z_mono:.4f}",
            delta=f"{d:.4f}",
            engine_limit=f"{ENGINE_LIMIT:.4f}",
            dist_ohm=round(float(dist), 3),
            h_node=h_min,
            secs=round(tc + tm, 1),
        )
        print(
            f"level {lv}: Z = {z:9.4f}   mono = {z_mono:9.4f}   "
            f"Delta = {d:9.4f}   engine limit = {ENGINE_LIMIT:.4f}   "
            f"dist = {dist:7.3f}   ({tc:.0f}s + {tm:.0f}s)",
            flush=True,
        )

    fp = HERE.parent / "results" / "probe18-graded.json"
    old = json.loads(fp.read_text()) if fp.exists() else {}
    old.update(out)
    fp.write_text(json.dumps(old, indent=1))
    print(f"saved {fp}")


if __name__ == "__main__":
    main()
