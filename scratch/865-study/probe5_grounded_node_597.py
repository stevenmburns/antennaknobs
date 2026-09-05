"""momwire#597 probe 5: the case a LONE end cannot show.

Declaring a one-member grounded junction was a bit-identical no-op for both
solvers, which is suspicious rather than reassuring: a junction of one produces
no KCL row, so `_grounded_junctions` (whose whole effect is to DROP that row)
has nothing to act on. The discriminating shape is a grounded node joining
SEVERAL wires -- a vertical meeting radials at z = 0 -- which is also the
"blast radius" #597 names: verticals, radial systems, inverted-L.
"""

import numpy as np

from momwire.bspline import BSplineSolver
from momwire.razor import RazorSolver

MAST = np.array([[0.0, 0.0, 0.0], [0.0, 0.0, 10.0]])


def radials(slope):
    """Radials meeting the mast AT z = 0 and sloping away, so only the shared
    NODE is in the plane. Radials lying IN the plane are refused by #865, which
    is how the two issues interlock: the natural surface-radial deck cannot be
    built at all."""
    return [
        np.array([[0.0, 0.0, 0.0], [10.0 * dx, 10.0 * dy, slope]])
        for dx, dy in ((1, 0), (0, 1), (-1, 0), (0, -1))
    ]


# every wire STARTS at the shared grounded point
JOINT = [[(w, "start") for w in range(5)]]


def solve(cls, junctions, slope):
    wires = [MAST] + radials(slope)
    kw = dict(
        wires=wires,
        n_per_edge_per_wire=[[15]] + [[12]] * (len(wires) - 1),
        feeds=[(0, 0.5, 1 + 0j)],
        wavelength=42.8,
        wire_radius=1e-3,
        ground_z=0.0,
        ground_eps=(13.0, 0.005),
        ground_model="sommerfeld",
    )
    if junctions is not None:
        kw["junctions"] = junctions
    try:
        z, _ = cls(**kw).compute_impedance()
        return complex(z), None
    except Exception as e:  # noqa: BLE001 - a refusal IS a result here
        return None, f"{type(e).__name__}: {' '.join(str(e).split())[:64]}"


for slope, label in (
    (+0.5, "radials sloping UP +0.5 m (elevated)"),
    (-0.5, "radials sloping DOWN -0.5 m (buried)"),
):
    print(f"\n=== mast + 4 radials meeting at z=0, {label} ===")
    for jname, j in (
        ("junctions= NOT declared", None),
        ("joint DECLARED (5 wires)", JOINT),
    ):
        print(f"  {jname}")
        for cls in (RazorSolver, BSplineSolver):
            z, err = solve(cls, j, slope)
            out = f"{z.real:9.3f}{z.imag:+9.3f}j" if z else err
            print(f"     {cls.__name__:14s} {out}")
