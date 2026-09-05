"""momwire#597 probe 9: is the sinusoidal gap about the GROUNDED node, or just
about this deck?

Grading collapsed razor-vs-bspline but left the sinusoidal bases ~10 ohm low,
so that half is not mesh. The control that decides what it IS: lift the same
five-wire junction clear of the interface. If the bases agree once the node is
no longer grounded, the divergence belongs to ground contact; if they still
disagree, it belongs to the junction or the deck and has nothing to do with
#597.
"""

import numpy as np

from momwire.bspline import BSplineSolver
from momwire.razor import RazorSolver
from momwire.sinusoidal import SinusoidalSolver
from momwire.sinusoidal_galerkin import SinusoidalGalerkinSolver

SOLVERS = [RazorSolver, BSplineSolver, SinusoidalSolver, SinusoidalGalerkinSolver]


def deck(node_z):
    """Identical geometry, translated in z. node_z = 0 grounds the junction."""
    wires = [np.array([[0.0, 0.0, node_z], [0.0, 0.0, node_z + 10.0]])]
    counts = [[15]]
    for dx, dy in ((1, 0), (0, 1), (-1, 0), (0, -1)):
        wires.append(
            np.array([[0.0, 0.0, node_z], [10.0 * dx, 10.0 * dy, node_z + 0.5]])
        )
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


for node_z, label in (
    (0.0, "node ON the plane (grounded)"),
    (1.0, "node LIFTED to z = +1 m (same geometry, not grounded)"),
    (3.0, "node LIFTED to z = +3 m"),
):
    print(f"\n=== {label} ===")
    rs = {}
    for cls in SOLVERS:
        try:
            z, _ = cls(**deck(node_z)).compute_impedance()
            rs[cls.__name__] = complex(z)
            print(
                f"   {cls.__name__:26s} {complex(z).real:9.3f}{complex(z).imag:+9.3f}j"
            )
        except Exception as e:  # noqa: BLE001
            print(
                f"   {cls.__name__:26s} {type(e).__name__}: {' '.join(str(e).split())[:50]}"
            )
    if len(rs) > 1:
        R = [v.real for v in rs.values()]
        print(
            f"   spread in R: {max(R) - min(R):6.3f} ohm "
            f"({100 * (max(R) - min(R)) / (sum(R) / len(R)):5.1f} % of mean)"
        )
