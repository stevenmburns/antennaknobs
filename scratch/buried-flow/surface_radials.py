"""Unit 5 scoping: Severns Part 3 surface radials (7.2 MHz, 33 ft radials, 33.5 ft
mast, eps 30 / sigma 0.020 measured) spelled as BURIED at -z and ELEVATED at +z.
Measured Zi: N=4 137+14.9j, N=8 85.5+8.0j, N=16 56.1+6.2j, N=32 42.9+2.1j, N=64 39.7-1.2j."""

import sys
import time

import numpy as np
from momwire.bspline import BSplineSolver

F = 7.2e6
WL = 299792458.0 / F
H = 33.5 * 0.3048
L = 33.0 * 0.3048
A = 0.51e-3  # No.18, shared radius (crossing serve rule)
SOIL = (30.0, 0.020)
MEAS = {
    4: 137 + 14.9j,
    8: 85.5 + 8.0j,
    16: 56.1 + 6.2j,
    32: 42.9 + 2.1j,
    64: 39.7 - 1.2j,
}


def buried(n, depth, n_rad=10, n_far=19):
    ang = 2 * np.pi * np.arange(n) / n
    wires = [
        np.array([(L * np.cos(a), L * np.sin(a), -depth), (0, 0, -depth)]) for a in ang
    ]
    npe = [[n_rad] for _ in ang]
    rise_i = len(wires)
    wires.append(
        np.array([(0, 0, z) for z in (-depth, -depth * 0.33, -depth * 0.08, 0.0)])
    )
    npe.append([1, 1, 1])
    mast_i = rise_i + 1
    wires.append(np.array([(0, 0, z) for z in (H, 0.5, 0.05, 0.0125, 0.0)]))
    npe.append([n_far, 2, 3, 2])
    return BSplineSolver(
        wires=wires,
        n_per_edge_per_wire=npe,
        junctions=[
            [(i, "end") for i in range(n)] + [(rise_i, "start")],
            [(rise_i, "end"), (mast_i, "end")],
        ],
        feeds=[(mast_i, H - 0.05, 1 + 0j)],
        wavelength=WL,
        wire_radius=A,
        ground_z=0.0,
        ground_eps=SOIL,
        ground_model="sommerfeld",
    )


def elevated(n, h, n_rad=10, n_far=19):
    ang = 2 * np.pi * np.arange(n) / n
    wires = [np.array([(L * np.cos(a), L * np.sin(a), h), (0, 0, h)]) for a in ang]
    npe = [[n_rad] for _ in ang]
    mast_i = len(wires)
    wires.append(np.array([(0, 0, z) for z in (H + h, 0.5 + h, 0.05 + h, h)]))
    npe.append([n_far, 2, 3])
    return BSplineSolver(
        wires=wires,
        n_per_edge_per_wire=npe,
        junctions=[[(i, "end") for i in range(n)] + [(mast_i, "end")]],
        feeds=[(mast_i, H - 0.05, 1 + 0j)],
        wavelength=WL,
        wire_radius=A,
        ground_z=0.0,
        ground_eps=SOIL,
        ground_model="sommerfeld",
    )


def solve(s):
    t0 = time.time()
    try:
        z, _ = s.compute_impedance()
        return f"{z.real:7.2f}{z.imag:+7.2f}j ({time.time() - t0:.0f}s)"
    except ValueError as e:
        return "REFUSED: " + str(e).split("\n")[0][:90]


if __name__ == "__main__":
    for n in (int(a) for a in sys.argv[1:] or ["4"]):
        print(f"\n== N={n}  measured {MEAS[n]} ==")
        for d in (0.05, 0.02, 0.01, 0.003):
            print(f"  buried   z=-{d:<6} {solve(buried(n, d))}", flush=True)
        for h in (0.003, 0.01, 0.02, 0.05, 0.15):
            print(f"  elevated z=+{h:<6} {solve(elevated(n, h))}", flush=True)
