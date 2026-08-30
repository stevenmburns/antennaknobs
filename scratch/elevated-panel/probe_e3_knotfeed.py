"""Elevated-panel probe E3 — the KNOT FEED (split + node_gaps) on the
original E1 family.

The C1-kink study (#449) proved bs2's smooth basis cannot represent the
current's slope kink at a driven point — the split-wire + node-gap
spelling restores the C0 kink at the fed knot and un-stalled the taper
decks. A mis-represented feed-region charge is a parasitic-capacitance
error, i.e. exactly the Z^2-scaled offset E1 measured (-28 ohm at
|Z| ~ 1000). Question: does the knot feed close E1's raw gap?

Spelling per the taper gate (_ward_split_fed): split the vertical AT the
feed arclength (4.3333 from the TOP) into two wires, declare the
2-member junction, drive with node_gaps, feeds=[] EXPLICIT (the #449
trap: a legacy default feed double-drives the deck otherwise).

Run: prlimit --as=$((8*1024*1024*1024)) .venv/bin/python \
       scratch/elevated-panel/probe_e3_knotfeed.py
"""

from __future__ import annotations

import json
import sys  # noqa: F401 — kept: imported for its import-time effect / to document the probe's inputs
import time
from pathlib import Path

import numpy as np

HERE = Path(__file__).resolve().parent
RESULTS = HERE / "results" / "probe-e1.json"

WL7 = 42.827494
FEED_FROM_TOP = 4.3333333333
H = 0.5
RADIAL_DIRS = {
    "ref": [],
    "lone": [(1, 0)],
    "fan": [(1, 0), (0, 1), (-1, 0), (0, -1)],
}


def knot_build(geom, dens=1):
    top = 10.0 + H
    split_z = top - FEED_FROM_TOP
    wires = [
        np.array([(0.0, 0.0, top), (0.0, 0.0, split_z)]),
        np.array([(0.0, 0.0, split_z), (0.0, 0.0, H)]),
    ]
    npe = [[7 * dens], [9 * dens]]
    juncs = [[(0, "end"), (1, "start")]]
    for dx, dy in RADIAL_DIRS[geom]:
        wires.append(np.array([(0.0, 0.0, -0.15), (5.0 * dx, 5.0 * dy, -0.15)]))
        npe.append([10 * dens])
    if geom == "fan":
        juncs.append([(2, "start"), (3, "start"), (4, "start"), (5, "start")])
    return dict(
        wires=wires,
        n_per_edge_per_wire=npe,
        junctions=juncs,
        node_gaps=[(0, "end", 1 + 0j)],
        feeds=[],
        wavelength=WL7,
        wire_radius=0.001,
        ground_z=0.0,
        ground_eps=(13.0, 0.005),
        ground_model="sommerfeld",
    )


def main():
    from momwire.bspline import BSplineSolver

    r = json.loads(RESULTS.read_text())
    out = {}
    print(
        "engine targets (x5): ref "
        + r["nec5 ref h=0.5 x5"]
        + "  lone "
        + r["nec5 lone h=0.5 x5"]
        + "  fan "
        + r["nec5 fan h=0.5 x5"]
    )
    for geom in RADIAL_DIRS:
        for dens in (1, 2):
            t0 = time.time()
            s = BSplineSolver(**knot_build(geom, dens))
            z, _ = s.compute_impedance()
            key = f"momwire-knot {geom} h={H} d{dens}"
            zn = complex(r[f"nec5 {geom} h={H} x5"])
            print(
                f"  {key}: {z:9.4f}   vs engine x5 {zn:9.4f}   "
                f"|gap| = {abs(z - zn):7.3f}  ({time.time() - t0:.0f}s)",
                flush=True,
            )
            out[key] = f"{z:.4f}"

    # Delta instrument under the knot feed.
    for geom in ("lone", "fan"):
        dm = complex(out[f"momwire-knot {geom} h={H} d2"]) - complex(
            out[f"momwire-knot ref h={H} d2"]
        )
        dn = complex(r[f"nec5 {geom} h={H} x5"]) - complex(r["nec5 ref h=0.5 x5"])
        print(
            f"  delta {geom}: momwire-knot {dm:9.4f}   engine {dn:9.4f}   "
            f"|diff| {abs(dm - dn):.4f}"
        )

    old = json.loads(RESULTS.read_text())
    old.update(out)
    RESULTS.write_text(json.dumps(old, indent=1))
    print(f"saved {RESULTS}")


if __name__ == "__main__":
    main()
