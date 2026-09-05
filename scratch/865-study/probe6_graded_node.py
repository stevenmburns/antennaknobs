"""momwire#597 probe 6: is the razor/bspline gap grounding semantics, or mesh?

Probe 5 measured 5.02 ohm between the two solvers on a 5-wire grounded node.
But the engine's own CoarseCrossingNode advisory fired on that deck and put the
node's worth at "~4.5 ohm" -- almost exactly the gap. Before reporting a
solver disagreement, grade the node as the advisory prescribes and see whether
the gap survives. If it collapses, the disagreement was mesh.
"""

import numpy as np

from momwire.bspline import BSplineSolver
from momwire.razor import RazorSolver


def graded(p0, p1, n_fine=6, n_coarse=10, fine_frac=0.256):
    """Polyline with extra VERTICES bunched toward p0, so grading cannot change
    junction topology (the advisory's own instruction)."""
    p0, p1 = np.asarray(p0, float), np.asarray(p1, float)
    ts = [0.0]
    t = fine_frac / (2 ** (n_fine - 1))
    for _ in range(n_fine):
        ts.append(t)
        t *= 2
    ts += list(np.linspace(ts[-1], 1.0, n_coarse + 1)[1:])
    pts = np.array([p0 + (p1 - p0) * s for s in ts])
    return pts, [1] * n_fine + [2] * n_coarse


def deck(grade):
    wires, counts = [], []
    if grade:
        pts, c = graded((0, 0, 0), (0, 0, 10.0))
        wires.append(pts)
        counts.append(c)
        for dx, dy in ((1, 0), (0, 1), (-1, 0), (0, -1)):
            pts, c = graded((0, 0, 0), (10.0 * dx, 10.0 * dy, 0.5))
            wires.append(pts)
            counts.append(c)
    else:
        wires.append(np.array([[0.0, 0.0, 0.0], [0.0, 0.0, 10.0]]))
        counts.append([15])
        for dx, dy in ((1, 0), (0, 1), (-1, 0), (0, -1)):
            wires.append(np.array([[0.0, 0.0, 0.0], [10.0 * dx, 10.0 * dy, 0.5]]))
            counts.append([12])
    return dict(
        wires=wires,
        n_per_edge_per_wire=counts,
        feeds=[(0, 0.5, 1 + 0j)],
        wavelength=42.8,
        wire_radius=1e-3,
        ground_z=0.0,
        ground_eps=(13.0, 0.005),
        ground_model="sommerfeld",
    )


# 5 % slope means z = 0.05*s, so the #865 floor h >= 2a = 2 mm forbids any
# node panel shorter than 40 mm -- while the crossing-node advisory asks for
# ~6 mm. The two constraints are in direct conflict here; 80 mm is the finest
# panel that clears the floor with margin (z = 4 mm, h/a = 8).
for grade, label in (
    (False, "ungraded node (probe 5's deck)"),
    (True, "GRADED node, 80 mm finest panel (floor-limited)"),
):
    print(f"\n=== {label} ===")
    zs = {}
    for cls in (RazorSolver, BSplineSolver):
        try:
            z, _ = cls(**deck(grade)).compute_impedance()
            zs[cls.__name__] = complex(z)
            print(
                f"   {cls.__name__:14s} {complex(z).real:9.3f}{complex(z).imag:+9.3f}j"
            )
        except Exception as e:  # noqa: BLE001
            print(
                f"   {cls.__name__:14s} {type(e).__name__}: {' '.join(str(e).split())[:60]}"
            )
    if len(zs) == 2:
        a, b = zs["RazorSolver"], zs["BSplineSolver"]
        print(
            f"   gap dR = {abs(a.real - b.real):6.3f} ohm "
            f"({100 * abs(a.real - b.real) / abs(b.real):5.2f} %)   "
            f"dX = {abs(a.imag - b.imag):6.3f} ohm"
        )
