"""Is the buried-fed drift the feed gap? Hold the FED segment fixed and refine
everything else (A); then hold everything else and shrink only the fed segment (B).
bvd1 geometry: 1 m vertical dipole, top 0.15 m down, a = 1 mm, soil A, 7 MHz."""

import sys

import numpy as np

sys.path.insert(0, "/home/smburns/antennas/antennaknobs/momwire/tests")
from momwire.bspline import BSplineSolver
from test_buried_serve_553 import SOIL_A, WL7

Z_TOP, L = -0.15, 1.0


def deck(n_side, gap, free=False, degree=2):
    zc = Z_TOP - L / 2
    pts = np.array(
        [(0, 0, Z_TOP - L), (0, 0, zc - gap / 2), (0, 0, zc + gap / 2), (0, 0, Z_TOP)],
        float,
    )
    ground = (
        {} if free else dict(ground_z=0.0, ground_eps=SOIL_A, ground_model="sommerfeld")
    )
    return BSplineSolver(
        wires=[pts],
        n_per_edge_per_wire=[[n_side, 1, n_side]],
        feeds=[(0, L / 2, 1 + 0j)],
        wavelength=WL7,
        wire_radius=0.001,
        degree=degree,
        **ground,
    )


def z(*a, **k):
    return deck(*a, **k).compute_impedance()[0]


G0 = L / 11  # bvd1's fed segment length
for free in (False, True):
    tag = "FREE " if free else "SOIL "
    print(f"\n== (A) {tag} fed segment FIXED at {G0:.4f} m, sides refined ==")
    prev = None
    for k in (1, 3, 5, 9, 15):
        zz = z(5 * k, G0, free)
        print(
            f"  n_side={5 * k:3d}  {zz:.4f}"
            + ("" if prev is None else f"  d={abs(zz - prev):.4f}")
        )
        prev = zz
    print(f"== (B) {tag} sides FIXED at 45 segs, fed segment shrinks ==")
    prev = None
    for div in (1, 3, 9, 27, 81):
        g = G0 / div
        zz = z(45, g, free)
        print(
            f"  gap={g:.5f} m (Δ/a={g / 0.001:6.1f})  {zz:.4f}"
            + (
                ""
                if prev is None
                else f"  d={abs(zz - prev):.4f}  d/ln3={abs(zz - prev) / np.log(3):.4f}"
            )
        )
        prev = zz
