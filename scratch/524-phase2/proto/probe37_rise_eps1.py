"""A-2 session 7, probe 37 — the ε̃ = 1 adjudicator for the RISE deck.

probe36 (corner sign fixed to −σσ′·c1·V(a)) gives 358.22−80.46j for the
lone radial respelled with its 15 cm rise — sane reactance, but R = 358
is far from anything banked, and the rise geometry exercises two things
the crossing bank never did: an above wire ENDING at the node
(σ_aσ_b = +1) and a BENT below wire. At ε̃ = 1 the interface vanishes
and the deck is one bent free-space wire (10 m up, 0.15 m down, 5 m
out) the shipped free-space fill solves independently. Agreement =
the composition is right on this geometry class and probe36's number
stands as the deck's exact-EM answer; disagreement localizes a defect.

Run: prlimit --as=$((8*1024*1024*1024)) .venv/bin/python \
       scratch/524-phase2/proto/probe37_rise_eps1.py
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
from probe36_rise_spelling import rise_deck  # noqa: E402
from test_buried_serve_553 import WL7  # noqa: E402


def free_truth():
    # One bent wire, same path as the two-wire rise deck, same knots:
    # walk from the radial tip through the bend and the node up the
    # monopole (the monopole wire is spelled 10 -> 0, so the joined walk
    # reverses it: tip -> bend -> node -> top).
    pts = np.array(
        [(5.0, 0.0, -0.15), (0.0, 0.0, -0.15), (0.0, 0.0, 0.0), (0.0, 0.0, 10.0)]
    )
    # feed at 4.3333 arclength from the TOP of the monopole = arc
    # 5 + 0.15 + (10 - 4.3333) from the wire start.
    feed_arc = 5.0 + 0.15 + 10.0 - 4.3333333333
    return dict(
        wires=[pts],
        n_per_edge_per_wire=[[10, 2, 15]],
        feeds=[(0, feed_arc, 1 + 0j)],
        wavelength=WL7,
        wire_radius=0.001,
    )


def main():
    t0 = time.time()
    z_truth, _ = BSplineSolver(**free_truth()).compute_impedance()
    print(
        f"free-space bent-wire truth = {z_truth:.4f} ({time.time() - t0:.0f}s)",
        flush=True,
    )

    build = rise_deck()
    build["ground_eps"] = (1.0, 0.0)
    s = BSplineSolver(**build)
    t0 = time.time()
    z, _ = s.compute_impedance()
    d = abs(z - z_truth)
    print(f"rise crossing at eps=1     = {z:.4f} ({time.time() - t0:.0f}s)")
    print(f"VERDICT |Z - truth| = {d:.4f} ohm ({d / abs(z_truth) * 100:.3f} %)")

    fp = HERE.parent / "results" / "probe37-rise-eps1.json"
    fp.write_text(
        json.dumps(
            dict(
                truth=f"{z_truth:.4f}",
                crossing_eps1=f"{z:.4f}",
                diff_ohm=round(float(d), 4),
            ),
            indent=1,
        )
    )
    print(f"saved {fp}")


if __name__ == "__main__":
    main()
