"""momwire#692 probe 2 — re-bank every print through the near-density flip.

Run: prlimit --as=$((8*1024*1024*1024)) .venv/bin/python \
       scratch/692-study/probe2_rebank.py
"""

from __future__ import annotations

import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "momwire" / "tests"))

from momwire.bspline import BSplineSolver  # noqa: E402
from test_crossing_serve_524 import (  # noqa: E402
    crossing_deck,
    fan_rise_deck,
    fan_rise_deck_graded,
    hub_deck,
)

BANKED = {
    "g1": 138.7671 - 102.9889j,
    "g2": 138.7691 - 102.9893j,
    "fan-base-soil": 143.9327 - 26.2135j,
    "fan-n2-soil": 142.1922 - 36.4711j,
    "fan-n3-soil": 142.1918 - 36.4770j,
    "hub-soil": 140.9839 - 43.6025j,
}


def solve(build, tag, banked=None):
    s = BSplineSolver(**build)
    t0 = time.time()
    z, _ = s.compute_impedance()
    dt = time.time() - t0
    note = ""
    if banked is not None:
        note = f"   banked {banked:.4f}  |d| = {abs(z - banked):.4f}"
    print(f"[{tag}] Z = {z:.4f}  ({dt:.1f}s){note}", flush=True)
    return z


def truth_of(build):
    return {
        k: v
        for k, v in build.items()
        if k not in ("ground_z", "ground_eps", "ground_model")
    }


solve(crossing_deck(1), "g1", BANKED["g1"])
solve(crossing_deck(2), "g2", BANKED["g2"])
solve(fan_rise_deck(), "fan-base-soil", BANKED["fan-base-soil"])
solve(fan_rise_deck_graded("n2"), "fan-n2-soil", BANKED["fan-n2-soil"])
solve(fan_rise_deck_graded("n3"), "fan-n3-soil", BANKED["fan-n3-soil"])
solve(hub_deck(), "hub-soil", BANKED["hub-soil"])

for tag, build in (
    ("fan-base", fan_rise_deck(ground_eps=(1.0, 0.0))),
    ("fan-n2", fan_rise_deck_graded("n2", ground_eps=(1.0, 0.0))),
    ("hub", hub_deck(ground_eps=(1.0, 0.0))),
):
    zt = solve(truth_of(build), f"{tag}-eps1-truth")
    z = solve(build, f"{tag}-eps1")
    print(f"[{tag}-eps1-margin] {abs(z - zt):.4f}", flush=True)
