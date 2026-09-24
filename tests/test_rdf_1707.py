"""The receiving directivity factor, against patterns with a known answer
(AK#1707).

RDF = G(target) - 10*log10((1/4pi) * integral of G over the sphere). The
normalisation is the FULL sphere even over a ground, where the lower
hemisphere simply contributes nothing (EZNEC's average gain, the one the
published W8JI / ON4UN figures subtract). Each case below pins one piece of
that sentence to a closed form:

  * isotropic in free space            D = 1        ->  0 dB
  * short dipole, broadside, free      D = 3/2      ->  1.761 dB
  * short monopole over perfect ground D = 3        ->  4.771 dB, the
    hemisphere integral with the 4pi normalisation (a 2pi one reads 1.761)
  * any uniform loss                   cancels      ->  RDF unchanged

No solve anywhere: the patterns are written down, so a wrong integral or a
wrong normalisation cannot hide behind an engine's own error.
"""

from __future__ import annotations

import math

import numpy as np
import pytest

from antennaknobs.engine import FarField
from antennaknobs.far_field import (
    average_gain,
    pattern_metrics,
    rdf_db,
    refined_pattern_metrics,
)

D_DIPOLE_DB = 10.0 * math.log10(1.5)
D_MONOPOLE_DB = 10.0 * math.log10(3.0)


def _db(lin):
    return 10.0 * np.log10(np.maximum(lin, 1e-30))


def _grid(theta_max, *, closed):
    thetas = np.arange(0.0, theta_max + 0.5, 1.0)
    phis = np.arange(0.0, 361.0 if closed else 360.0, 1.0)
    return thetas, phis


def _dipole_z(thetas, phis, peak_lin):
    """A short z-directed dipole: G = peak * sin^2(theta), any phi."""
    s2 = np.sin(np.radians(thetas)) ** 2
    return _db(peak_lin * s2[:, None] * np.ones(len(phis))[None, :])


@pytest.mark.parametrize("closed", [True, False])
def test_isotropic_free_space_is_zero(closed):
    thetas, phis = _grid(180.0, closed=closed)
    g = np.zeros((thetas.size, phis.size))  # 0 dBi everywhere
    assert average_gain(g, thetas, phis) == pytest.approx(1.0, abs=2e-4)
    assert rdf_db(0.0, g, thetas, phis) == pytest.approx(0.0, abs=1e-3)


def test_short_dipole_broadside_is_its_directivity():
    thetas, phis = _grid(180.0, closed=False)
    g = _dipole_z(thetas, phis, 1.5)
    assert rdf_db(D_DIPOLE_DB, g, thetas, phis) == pytest.approx(D_DIPOLE_DB, abs=1e-3)


def test_hemisphere_over_ground_normalises_by_the_full_sphere():
    """A short monopole over PEC: sin^2 over the upper hemisphere only, peak
    gain 3 (4.77 dBi). The 4pi normalisation gives its directivity, 4.77 dB;
    normalising by the hemisphere's 2pi would give the dipole's 1.76."""
    thetas, phis = _grid(90.0, closed=True)
    g = _dipole_z(thetas, phis, 3.0)
    assert average_gain(g, thetas, phis) == pytest.approx(1.0, abs=2e-4)
    rdf = rdf_db(D_MONOPOLE_DB, g, thetas, phis)
    assert rdf == pytest.approx(D_MONOPOLE_DB, abs=1e-3)
    assert abs(rdf - D_DIPOLE_DB) > 3.0


def test_loss_cancels():
    """A lossy antenna is gain AND average gain scaled together, so the RDF of
    a -15 dB copy is the same number — the property that makes RDF, not
    gain, the Beverage's figure of merit."""
    thetas, phis = _grid(90.0, closed=True)
    g = _dipole_z(thetas, phis, 3.0)
    lossy = g - 15.0
    assert rdf_db(D_MONOPOLE_DB - 15.0, lossy, thetas, phis) == pytest.approx(
        rdf_db(D_MONOPOLE_DB, g, thetas, phis), abs=1e-9
    )


def test_a_partial_ring_is_refused():
    thetas = np.arange(0.0, 91.0, 1.0)
    phis = np.arange(0.0, 181.0, 1.0)
    with pytest.raises(ValueError, match="whole ring"):
        average_gain(np.zeros((thetas.size, phis.size)), thetas, phis)


def _ff(thetas, phis, g):
    return FarField(
        rings=g.tolist(),
        max_gain=float(g.max()),
        min_gain=float(g.min()),
        thetas=thetas,
        phis=phis,
    )


def test_pattern_metrics_rdf_needs_to_know_the_lower_hemisphere():
    """A NEC-convention grid (theta 0..89) is the whole integral only over a
    ground. Without `has_ground` there is no average gain to take, and the
    metric says so rather than reading a free-space pattern as half of
    itself.

    The pattern is 6*cos^2(theta) over the upper hemisphere — average gain
    exactly 1, directivity 6 (7.78 dB) at the zenith — chosen because it is
    NULL at the horizon: the grid's missing 89..90 deg strip then costs
    nothing, which is also the case that matters (over lossy ground every
    pattern is null there). A horizon-peaked pattern loses that strip, 2.6 %
    of a sin^2 monopole's integral (0.11 dB), the same grid clipping
    `radiated_fraction` documents."""
    thetas = np.arange(0.0, 90.0, 1.0)
    phis = np.arange(0.0, 361.0, 1.0)
    c2 = np.cos(np.radians(thetas)) ** 2
    g = _db(6.0 * c2[:, None] * np.ones(phis.size)[None, :])
    assert pattern_metrics(_ff(thetas, phis, g))["rdf_db"] is None
    rdf = pattern_metrics(_ff(thetas, phis, g), has_ground=True)["rdf_db"]
    assert rdf == pytest.approx(10.0 * math.log10(6.0), abs=2e-3)


def _evaluator(fn, has_ground):
    def gain(theta_deg, phi_deg):
        t = np.radians(np.atleast_1d(np.asarray(theta_deg, float)))
        p = np.radians(np.atleast_1d(np.asarray(phi_deg, float)))
        return fn(t[:, None], p[None, :])

    gain.has_ground = has_ground
    return gain


def test_refined_metrics_carry_the_rdf_free_and_over_ground():
    dipole = _evaluator(
        lambda t, p: _db(1.5 * np.sin(t) ** 2 * np.ones_like(p)), has_ground=False
    )
    assert refined_pattern_metrics(dipole)["rdf_db"] == pytest.approx(
        D_DIPOLE_DB, abs=1e-3
    )
    monopole = _evaluator(
        lambda t, p: _db(3.0 * np.sin(t) ** 2 * np.ones_like(p)), has_ground=True
    )
    assert refined_pattern_metrics(monopole)["rdf_db"] == pytest.approx(
        D_MONOPOLE_DB, abs=1e-3
    )


def test_a_directional_pattern_has_the_directivity_of_its_beam():
    """A cardioid-squared azimuth pattern over a sin^2 elevation, over
    ground, peak 1: the average is (1/4pi) * (2pi * 3/8) * (2/3) = 1/8, so
    the RDF is 9.03 dB. Pins the refined path's peak AND its use of the
    1-degree grid for the average, off the axis of symmetry the other cases
    share."""

    def cardioid(t, p):
        return _db(((1.0 + np.cos(p)) / 2.0) ** 2 * np.sin(t) ** 2)

    m = refined_pattern_metrics(_evaluator(cardioid, has_ground=True))
    assert m["rdf_db"] == pytest.approx(10.0 * math.log10(8.0), abs=2e-3)
    assert m["azimuth_deg"] == pytest.approx(0.0, abs=0.05)
