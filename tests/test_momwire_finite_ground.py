"""MomwireEngine finite-ground mapping (momwire >= 0.4.0 ground_eps;
SinusoidalSolver support since momwire 0.5.0).

Since the refl-coef ground landed in momwire (docs/refl-coef-ground-plan.md
there), finite ground specs must reach the impedance solve for solvers that
support it: ("finite", eps_r, sigma) and ("finite-fast", eps_r, sigma) both
map to the solver's ground_eps (momwire's single finite model — NEC gn 0
style reflection-coefficient weighting) on the bspline family and, since
momwire 0.5.0, SinusoidalSolver; TriangularSolver keeps folding to the PEC
image.

The numeric tests cross-check the momwire solves against PyNEC gn 0 — the
oracle the momwire implementations were validated against (dipole 0.1–0.5λ
window: bspline max |ΔZ| ≈ 2.45 Ω with a ~1.4 Ω cross-solver floor;
sinusoidal ≈ 0.11 Ω, at its own ~0.11 Ω floor — same basis as NEC).
"""

import pytest

pytest.importorskip("PyNEC")

from momwire import BSplineSolver, SinusoidalSolver, TriangularSolver  # noqa: E402

from antennaknobs import resolve_variant_params  # noqa: E402
from antennaknobs.designs.dipoles.invvee import Builder as InvVee  # noqa: E402
from antennaknobs.engines import MomwireEngine, PyNECEngine  # noqa: E402

GROUND = ("finite-fast", 10.0, 0.002)


def _flat_dipole(height_m):
    params = dict(resolve_variant_params(InvVee, "dipole"))
    params["base"] = height_m
    return InvVee(params)


def _height(frac):
    lam = 299.792458 / 28.47
    return frac * lam


def test_finite_specs_map_to_ground_eps_for_bspline():
    for spec in (GROUND, ("finite", 13.0, 0.005)):
        eng = MomwireEngine(
            _flat_dipole(_height(0.2)), solver=BSplineSolver, ground=spec
        )
        assert eng._ground_eps == (spec[1], spec[2])


def test_finite_specs_fold_to_pec_for_triangular():
    eng = MomwireEngine(
        _flat_dipole(_height(0.2)), solver=TriangularSolver, ground=GROUND
    )
    assert eng._ground_eps is None


def test_finite_specs_map_to_ground_eps_for_sinusoidal():
    for spec in (GROUND, ("finite", 13.0, 0.005)):
        eng = MomwireEngine(
            _flat_dipole(_height(0.2)), solver=SinusoidalSolver, ground=spec
        )
        assert eng._ground_eps == (spec[1], spec[2])


def test_pec_and_free_never_set_ground_eps():
    assert (
        MomwireEngine(
            _flat_dipole(_height(0.2)), solver=BSplineSolver, ground="pec"
        )._ground_eps
        is None
    )
    assert (
        MomwireEngine(_flat_dipole(_height(0.2)), solver=BSplineSolver)._ground_eps
        is None
    )


def test_momwire_bspline_finite_ground_tracks_nec_gn0():
    """The whole point of the upgrade: at 0.2λ the PEC-image solve is ~18 Ω
    of reactance off NEC's finite ground; the ground_eps solve lands within
    the validated ~2.5 Ω window and strictly beats PEC."""
    builder = _flat_dipole(_height(0.2))
    z_gn0 = PyNECEngine(builder, ground=GROUND).impedance()[0]
    z_mom = MomwireEngine(builder, solver=BSplineSolver, ground=GROUND).impedance()[0]
    z_pec = MomwireEngine(builder, solver=BSplineSolver, ground="pec").impedance()[0]
    assert abs(z_mom - z_gn0) < 2.5
    assert abs(z_mom - z_gn0) < abs(z_pec - z_gn0)
    assert abs(z_pec - z_gn0) > 10.0  # the gap being fixed is real


def test_momwire_sinusoidal_finite_ground_tracks_nec_gn0():
    """SinusoidalSolver shares NEC's basis and weights total image fields,
    so it tracks gn 0 at its own cross-solver floor (~0.11 Ω on the momwire
    validation matrix — see momwire's phase 6 notes). Gate at ~5x that;
    strictly better than the PEC fold this upgrade replaces."""
    builder = _flat_dipole(_height(0.2))
    z_gn0 = PyNECEngine(builder, ground=GROUND).impedance()[0]
    z_mom = MomwireEngine(builder, solver=SinusoidalSolver, ground=GROUND).impedance()[
        0
    ]
    z_pec = MomwireEngine(builder, solver=SinusoidalSolver, ground="pec").impedance()[0]
    assert abs(z_mom - z_gn0) < 0.6
    assert abs(z_mom - z_gn0) < abs(z_pec - z_gn0)
    assert abs(z_pec - z_gn0) > 10.0  # the gap being fixed is real
