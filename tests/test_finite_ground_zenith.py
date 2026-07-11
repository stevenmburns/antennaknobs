"""Regression: MomwireEngine far-field must not glitch at the zenith over a
finite ground.

The finite-ground far field (``_evaluate_M_perp``) decomposes each
observation ray into vertical/horizontal polarisation to weight the
ground-reflected wave by Fresnel coefficients. That basis is built from the
ray's horizontal projection ``s = sin(theta)``, which vanishes at the zenith
(theta = 0). The original guard replaced ``s`` with 1.0 there, collapsing
BOTH polarisation unit vectors to zero and silently dropping the entire
reflected wave — so the theta = 0 gain sample read ~3 dB low while every
other angle tracked PyNEC within ~0.2 dB.

An elevation pattern is smooth through the zenith: there is no physical
mechanism for a multi-dB cliff between theta = 0 and theta = 1 deg (the 1 deg
sample has s = sin(1 deg) ~ 0.017 > 0, so its basis is well conditioned and
its value is trustworthy). This test pins that continuity for the finite-
ground far field, and confirms the PEC/free paths (which never hit the
decomposition) are unaffected.
"""

from momwire import BSplineSolver

from antennaknobs import resolve_variant_params
from antennaknobs.designs.dipoles.invvee import Builder as InvVee
from antennaknobs.engines import MomwireEngine

FINITE = ("finite", 10.0, 0.002)


def _flat_dipole(height_m):
    params = dict(resolve_variant_params(InvVee, "dipole"))
    params["base"] = height_m
    return InvVee(params)


def _height(frac):
    lam = 299.792458 / 28.47
    return frac * lam


def _zenith_and_1deg_gain(ground):
    """Return (gain at theta=0, gain at theta=1 deg), each the max over the
    azimuth ring so a horizontal dipole's phi variation can't hide the drop."""
    eng = MomwireEngine(_flat_dipole(_height(0.2)), solver=BSplineSolver, ground=ground)
    ff = eng.far_field(n_theta=90, n_phi=360, del_theta=1, del_phi=1)
    assert ff.thetas[0] == 0.0 and ff.thetas[1] == 1.0
    return max(ff.rings[0]), max(ff.rings[1])


def test_finite_ground_zenith_is_continuous():
    """The theta=0 sample must sit within 0.5 dB of the theta=1 deg sample.
    The bug produced a ~3 dB gap; a smooth elevation pattern allows none."""
    g_zenith, g_1deg = _zenith_and_1deg_gain(FINITE)
    assert abs(g_zenith - g_1deg) < 0.5, (
        f"zenith glitch: gain(theta=0)={g_zenith:.2f} dBi vs "
        f"gain(theta=1 deg)={g_1deg:.2f} dBi (gap {abs(g_zenith - g_1deg):.2f} dB)"
    )


def test_pec_ground_zenith_is_continuous():
    """Control: the PEC path skips the Fresnel decomposition entirely, so it
    was never affected. Guards against a fix that regresses the PEC limit."""
    g_zenith, g_1deg = _zenith_and_1deg_gain("pec")
    assert abs(g_zenith - g_1deg) < 0.5
