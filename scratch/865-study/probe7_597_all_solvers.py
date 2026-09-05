"""momwire#597 probe 7: the grounded-node question across the solver set.

Sinusoidal bases are the stated second-solver route for buried work, so their
behaviour at a grounded node matters more than razor's. Two decks, both soils,
declared against undeclared, on every solver that takes the geometry.
"""

import numpy as np

from momwire.bspline import BSplineSolver
from momwire.harrington import HarringtonSolver
from momwire.razor import RazorSolver
from momwire.sinusoidal import SinusoidalSolver
from momwire.sinusoidal_galerkin import SinusoidalGalerkinSolver

SOLVERS = [
    RazorSolver,
    BSplineSolver,
    SinusoidalSolver,
    SinusoidalGalerkinSolver,
    HarringtonSolver,
]

MAST = np.array([[0.0, 0.0, 0.0], [0.0, 0.0, 10.0]])
LONE = dict(wires=[MAST], n_per_edge_per_wire=[[15]])
NODE = dict(
    wires=[MAST]
    + [
        np.array([[0.0, 0.0, 0.0], [10.0 * dx, 10.0 * dy, 0.5]])
        for dx, dy in ((1, 0), (0, 1), (-1, 0), (0, -1))
    ],
    n_per_edge_per_wire=[[15]] + [[12]] * 4,
)
GROUNDS = {
    "PEC": dict(ground_eps=None),
    "Sommerfeld 13/0.005": dict(ground_eps=(13.0, 0.005), ground_model="sommerfeld"),
}


def solve(cls, deck, ground, junctions):
    kw = dict(deck)
    kw.update(ground)
    kw.update(feeds=[(0, 0.5, 1 + 0j)], wavelength=42.8, wire_radius=1e-3, ground_z=0.0)
    if junctions is not None:
        kw["junctions"] = junctions
    try:
        z, _ = cls(**kw).compute_impedance()
        return complex(z), None
    except Exception as e:  # noqa: BLE001 - a refusal IS a result here
        return None, f"{type(e).__name__}: {' '.join(str(e).split())[:52]}"


def fmt(z, err):
    return f"{z.real:9.3f}{z.imag:+9.3f}j" if z is not None else f"  {err[:46]}"


for dname, deck, decl in (
    ("LONE END (monopole base at z=0)", LONE, [[(0, "start")]]),
    (
        "GROUNDED NODE (mast + 4 sloping radials)",
        NODE,
        [[(w, "start") for w in range(5)]],
    ),
):
    for gname, g in GROUNDS.items():
        print(f"\n=== {dname} — {gname} ===")
        print(f"{'solver':26s} {'undeclared':>22s} {'declared':>22s}  same?")
        for cls in SOLVERS:
            zu, eu = solve(cls, deck, g, None)
            zd, ed = solve(cls, deck, g, decl)
            same = (
                "n/a"
                if zu is None or zd is None
                else ("YES" if zu == zd else f"NO d={abs(zu - zd):.3g}")
            )
            print(f"{cls.__name__:26s} {fmt(zu, eu):>22s} {fmt(zd, ed):>22s}  {same}")
