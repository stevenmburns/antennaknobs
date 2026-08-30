"""A-2 session 7, probe 36 — P3's OTHER spelling: the radial's RISE.

The engine anchor decks leave the radial DETACHED 15 cm down and let the
stake fiction carry current into the soil. The physical model of a
monopole actually CONNECTED to its radial adds the conductor the deck is
missing: the below wire rises from the radial run to the surface and
junction-joins the monopole there — which is exactly the production
crossing serve (K=2 crossing junction, H/V segments, one radius).

This deck is NOT the engine's deck (it has a 15 cm rise conductor the
engine's does not), so its answer is compared to the anchors only as a
documented convention difference — the interesting question is where it
lands relative to the continuation spelling (probe35's M-only) and to
the shipped contact-mono column.

Run: prlimit --as=$((8*1024*1024*1024)) .venv/bin/python \
       scratch/524-phase2/proto/probe36_rise_spelling.py
"""

from __future__ import annotations

import json
import time
from pathlib import Path
import sys

import numpy as np

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
sys.path.insert(0, str(Path(__file__).resolve().parents[3] / "momwire" / "tests"))

from momwire.bspline import BSplineSolver  # noqa: E402
from test_buried_serve_553 import SOIL_A, WL7  # noqa: E402

ANCHOR_LONE = 92.130 - 70.141j


def rise_deck():
    mono = np.array([(0.0, 0.0, 10.0), (0.0, 0.0, 0.0)])
    rise_radial = np.array([(5.0, 0.0, -0.15), (0.0, 0.0, -0.15), (0.0, 0.0, 0.0)])
    return dict(
        wires=[rise_radial, mono],
        n_per_edge_per_wire=[[10, 2], [15]],
        junctions=[[(0, "end"), (1, "end")]],
        feeds=[(1, 4.3333333333, 1 + 0j)],
        wavelength=WL7,
        wire_radius=0.001,
        ground_z=0.0,
        ground_eps=SOIL_A,
        ground_model="sommerfeld",
    )


def main():
    s = BSplineSolver(**rise_deck())
    print(
        f"media = {s._wire_media()}  crossing = {s._crossing_junctions()}", flush=True
    )
    t0 = time.time()
    z, _ = s.compute_impedance()
    dt = time.time() - t0
    print(
        f"rise spelling Z = {z:.4f}   engine detached-anchor = "
        f"{ANCHOR_LONE:.4f}   |diff| = {abs(z - ANCHOR_LONE):.3f} ohm   "
        f"({dt:.0f}s)"
    )
    fp = HERE.parent / "results" / "probe36-rise-spelling.json"
    old = json.loads(fp.read_text()) if fp.exists() else {}
    old["lone-rise"] = dict(
        z=f"{z:.4f}",
        anchor=f"{ANCHOR_LONE:.4f}",
        diff_ohm=round(float(abs(z - ANCHOR_LONE)), 3),
        secs=round(dt, 1),
    )
    fp.write_text(json.dumps(old, indent=1))
    print(f"saved {fp}")


if __name__ == "__main__":
    main()
