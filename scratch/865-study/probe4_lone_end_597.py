"""momwire#597: a lone wire end resting in the ground plane.

The issue's claim is that razor infers a grounded end and bspline does not, so
the same undeclared deck is two different antennas with no warning. This
measures the size of that, and whether DECLARING the junction closes it.

A monopole base-fed at z = 0 over PEC and over Sommerfeld ground, handed to
both solvers with and without an explicit grounded junction.
"""

import numpy as np

from momwire.bspline import BSplineSolver
from momwire.razor import RazorSolver

WIRE = np.array([[0.0, 0.0, 0.0], [0.0, 0.0, 10.0]])
COMMON = dict(
    wires=[WIRE],
    n_per_edge_per_wire=[[15]],
    feeds=[(0, 0.5, 1 + 0j)],
    wavelength=42.8,  # 7 MHz
    wire_radius=1e-3,
    ground_z=0.0,
)
SOMM = dict(ground_eps=(13.0, 0.005), ground_model="sommerfeld")
PEC = dict(ground_eps=None)


def solve(cls, ground, junctions):
    kw = dict(COMMON)
    kw.update(ground)
    if junctions is not None:
        kw["junctions"] = junctions
    try:
        z, _ = cls(**kw).compute_impedance()
        return complex(z), None
    except Exception as e:  # noqa: BLE001 - a refusal IS a result here
        return None, f"{type(e).__name__}: {' '.join(str(e).split())[:70]}"


def show(label, ground):
    print(f"\n=== {label} ===")
    for jname, j in (
        ("no junctions= declared", None),
        ("grounded end DECLARED", [[(0, "start")]]),
    ):
        row = []
        for cls in (RazorSolver, BSplineSolver):
            z, err = solve(cls, ground, j)
            row.append(
                f"{cls.__name__:14s} "
                + (f"{z.real:9.3f}{z.imag:+9.3f}j" if z else f"{err[:40]}")
            )
        print(f"  {jname}")
        for r in row:
            print(f"     {r}")


show("PEC ground", PEC)
show("Sommerfeld 13/0.005", SOMM)
