"""momwire#597 probe 8: does grading the node collapse the spread for EVERY
basis, or only for the razor/bspline pair?

The ungraded Sommerfeld node spreads 30.5-47.8 ohm across four bases. The
engine's CoarseCrossingNode advisory says that node is worth ~4.5 ohm at the
default quadrature, and grading collapsed razor-vs-bspline from 5.02 to 0.75.
If grading pulls the sinusoidal bases in too, the spread is mesh; if it does
not, something basis-specific is happening at a grounded node.
"""

import numpy as np

from momwire.bspline import BSplineSolver
from momwire.razor import RazorSolver
from momwire.sinusoidal import SinusoidalSolver
from momwire.sinusoidal_galerkin import SinusoidalGalerkinSolver

SOLVERS = [RazorSolver, BSplineSolver, SinusoidalSolver, SinusoidalGalerkinSolver]


def graded(p0, p1, n_fine=6, n_coarse=10, fine_frac=0.256):
    p0, p1 = np.asarray(p0, float), np.asarray(p1, float)
    ts, t = [0.0], fine_frac / (2 ** (n_fine - 1))
    for _ in range(n_fine):
        ts.append(t)
        t *= 2
    ts += list(np.linspace(ts[-1], 1.0, n_coarse + 1)[1:])
    return np.array([p0 + (p1 - p0) * s for s in ts]), [1] * n_fine + [2] * n_coarse


def deck(grade):
    wires, counts = [], []
    ends = [((0, 0, 0), (0, 0, 10.0), 15)] + [
        ((0, 0, 0), (10.0 * dx, 10.0 * dy, 0.5), 12)
        for dx, dy in ((1, 0), (0, 1), (-1, 0), (0, -1))
    ]
    for p0, p1, n in ends:
        if grade:
            pts, c = graded(p0, p1)
            wires.append(pts)
            counts.append(c)
        else:
            wires.append(np.array([p0, p1], dtype=float))
            counts.append([n])
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


for grade, label in (
    (False, "UNGRADED node"),
    (True, "GRADED node (80 mm finest panel)"),
):
    print(f"\n=== {label}, Sommerfeld 13/0.005 ===")
    rs = {}
    for cls in SOLVERS:
        try:
            z, _ = cls(**deck(grade)).compute_impedance()
            rs[cls.__name__] = complex(z)
            print(
                f"   {cls.__name__:26s} {complex(z).real:9.3f}{complex(z).imag:+9.3f}j"
            )
        except Exception as e:  # noqa: BLE001
            print(
                f"   {cls.__name__:26s} {type(e).__name__}: {' '.join(str(e).split())[:52]}"
            )
    if len(rs) > 1:
        R = [v.real for v in rs.values()]
        print(
            f"   spread in R: {max(R) - min(R):6.3f} ohm "
            f"({100 * (max(R) - min(R)) / (sum(R) / len(R)):5.1f} % of mean)"
        )
