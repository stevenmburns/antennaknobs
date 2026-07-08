"""MomwireEngine finite-ground mapping (momwire >= 0.4.0 ground_eps;
SinusoidalSolver support since 0.5.0; TRUE Sommerfeld since 0.6.0).

Finite ground specs reach the impedance solve for solvers that support
them, and since momwire 0.6.0 the two specs mean different physics:
("finite", eps_r, sigma) drives momwire's Sommerfeld ground
(ground_model="sommerfeld", NEC gn 2 style) on plain BSplineSolver, while
("finite-fast", eps_r, sigma) — and "finite" on the solvers without a
sommerfeld model (HMatrix/ArrayBlock keep their refl-coef fast paths,
SinusoidalSolver is refl-coef only) — maps to the reflection-coefficient
ground_eps solve (NEC gn 0 style).

The refl-coef numeric tests cross-check against PyNEC gn 0 (dipole
0.1–0.5λ window: bspline max |ΔZ| ≈ 2.45 Ω, sinusoidal ≈ 0.11 Ω). The
Sommerfeld numeric tests gate against nec2c-captured gn 2 literals —
PyNEC's own gn 2 solve is order-dependent in-process and numerically
broken below 0.1λ (see momwire scripts/capture_refl_coef_ground_golden.py
for the controls), so it must never be a live oracle at low heights.
"""

import pytest

pytest.importorskip("PyNEC")

from momwire import BSplineSolver, SinusoidalSolver  # noqa: E402

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


def test_ground_model_mapping_per_solver_and_spec():
    """ "finite" → sommerfeld on plain BSplineSolver only; "finite-fast" →
    refl-coef everywhere; solvers without a sommerfeld model keep
    refl-coef for both specs."""
    from momwire import ArrayBlockSolver, HMatrixSolver

    b = _flat_dipole(_height(0.2))

    def model(solver, spec):
        return MomwireEngine(b, solver=solver, ground=spec)._ground_model

    assert model(BSplineSolver, ("finite", 10.0, 0.002)) == "sommerfeld"
    assert model(BSplineSolver, ("finite-fast", 10.0, 0.002)) == "refl-coef"
    for solver in (HMatrixSolver, ArrayBlockSolver, SinusoidalSolver):
        assert model(solver, ("finite", 10.0, 0.002)) == "refl-coef"
        assert model(solver, ("finite-fast", 10.0, 0.002)) == "refl-coef"
    # and the sommerfeld kwarg only reaches solvers that accept it
    eng = MomwireEngine(b, solver=BSplineSolver, ground=("finite", 10.0, 0.002))
    assert eng._ground_solver_kwargs().get("ground_model") == "sommerfeld"
    eng = MomwireEngine(b, solver=SinusoidalSolver, ground=("finite", 10.0, 0.002))
    assert "ground_model" not in eng._ground_solver_kwargs()


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


# nec2c-captured gn 2 oracles (momwire tests/golden_refl_coef_ground.py,
# regenerated 2026-07-06 via the nec2c CLI): flat dipole, (10.0, 0.002).
_GN2_NEC2C = {
    0.05: 68.002 + 1.551j,
    0.02: 95.080 + 32.413j,
}


@pytest.mark.parametrize(
    "frac,gate",
    [(0.05, 2.5), (0.02, 3.0)],  # measured 1.43 / 2.17 through this engine
)
def test_momwire_bspline_sommerfeld_tracks_gn2_at_low_heights(frac, gate):
    """The point of the 0.6.0 upgrade: below 0.1λ the refl-coef model is
    tens of ohms from the true (gn 2) ground; the ("finite", ...) spec on
    BSplineSolver now lands at the cross-solver floor there."""
    builder = _flat_dipole(_height(frac))
    gn2 = _GN2_NEC2C[frac]
    z_somm = MomwireEngine(
        builder, solver=BSplineSolver, ground=("finite", 10.0, 0.002)
    ).impedance()[0]
    z_refl = MomwireEngine(
        builder, solver=BSplineSolver, ground=("finite-fast", 10.0, 0.002)
    ).impedance()[0]
    assert abs(z_somm - gn2) < gate
    assert abs(z_refl - gn2) > 10.0  # the gap sommerfeld closes is real
