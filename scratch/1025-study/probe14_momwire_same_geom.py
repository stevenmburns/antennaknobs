"""AK#1025 follow-up: momwire on the EXACT hand geometry probe 13 used.

Comparing probe 13's hand decks against catalog momwire numbers would be
comparing different antennas — the hand decks use a 10.35 m mast and a uniform
0.15 m mesh so a boundary lands on the interface. This solves that same
geometry in momwire so the flag question is decided like-for-like.

momwire needs the crossing spelled as two wires meeting at z = 0 with the
junction declared (its served crossing form); the vertical is otherwise
identical.
"""

import math

import numpy as np

from momwire.bspline import BSplineSolver

DEPTH, MAST, RAD_LEN, A, FREQ = 0.15, 10.35, 6.3336, 5.0e-4, 7.1
SEG = 0.15
LAM = 299.792458 / FREQ


def deck(n_rad):
    wires = [
        np.array([[0.0, 0.0, -DEPTH], [0.0, 0.0, 0.0]]),
        np.array([[0.0, 0.0, 0.0], [0.0, 0.0, MAST]]),
    ]
    counts = [[int(round(DEPTH / SEG))], [int(round(MAST / SEG))]]
    for i in range(n_rad):
        th = 2 * math.pi * i / n_rad
        wires.append(
            np.array(
                [
                    [0.0, 0.0, -DEPTH],
                    [RAD_LEN * math.cos(th), RAD_LEN * math.sin(th), -DEPTH],
                ]
            )
        )
        counts.append([54])
    # the rise meets the mast at z=0; every radial meets the rise at the hub
    junctions = [
        [(0, "end"), (1, "start")],
        [(0, "start")] + [(2 + i, "start") for i in range(n_rad)],
    ]
    return dict(
        wires=wires,
        n_per_edge_per_wire=counts,
        junctions=junctions,
        feeds=[(1, SEG / 2, 1 + 0j)],  # first ABOVE-ground segment
        wavelength=LAM,
        wire_radius=A,
        ground_z=0.0,
        ground_eps=(13.0, 0.005),
        ground_model="sommerfeld",
    )


print("momwire (bspline) on probe 13's exact geometry, feed on the first")
print("above-ground segment — the placement probe 13's GE 1 column is stable at.\n")
for n_rad in (4, 12):
    try:
        z, _ = BSplineSolver(**deck(n_rad)).compute_impedance()
        print(
            f"  {n_rad:2d} radials   momwire {complex(z).real:9.3f}{complex(z).imag:+9.3f}j"
        )
    except Exception as e:  # noqa: BLE001
        print(
            f"  {n_rad:2d} radials   {type(e).__name__}: {' '.join(str(e).split())[:80]}"
        )

print("\n  probe 13, same geometry, NEC-5:")
print("     4 radials   GE -1  75.169 +29.173j     GE 1  47.524  +5.692j")
print("    12 radials   GE -1  49.889 +20.984j     GE 1  45.195  +5.204j")
