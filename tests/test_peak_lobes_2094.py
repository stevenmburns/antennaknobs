"""Every lobe of a pattern's maximum, for the workbench's 3-D max (AK#2094).

AC6LA (QRZ 1003328 #214) read "@ az 8°" and "@ az 6°" for one maximum of
SP3L's turnstile. Its ring is within 0.005 dB of the peak across 4-10° and
again across 184-190°: the antenna is the same after a half turn, so the twin
lobes are equal however it is tuned, and a first-found rule names either. A
vertical on three radials has three such lobes; on four or more it is round
to 0.0005 dB. `far_field.azimuth_lobes` lists every lobe within 0.01 dB (NEC's
printed resolution), and an empty list says the ring is round. The pattern
metrics stay scalars (the metrics table's contract, AK#1828); the web layer
attaches the lobes (`ring_lobes`).
"""

from __future__ import annotations

import numpy as np
import pytest

from antennaknobs.designs.verticals.vertical import Builder as Vertical
from antennaknobs.engines.momwire import MomwireEngine
from antennaknobs.far_field import (
    PEAK_LOBE_TOL_DB,
    azimuth_lobes,
    pattern_metrics,
    refined_pattern_metrics,
    ring_lobes,
)

AZ = np.arange(0.0, 360.0, 1.0)


def _lobes(f):
    return azimuth_lobes(AZ, f(np.radians(AZ)))[0]


def test_one_lobe_twins_three_and_round():
    assert _lobes(lambda a: 5 * np.cos(a - np.radians(40))) == [40.0]
    assert _lobes(lambda a: 0.5 * np.cos(2 * (a - np.radians(7)))) == [7.0, 187.0]
    assert _lobes(lambda a: 0.25 * np.cos(3 * (a - np.radians(60)))) == [
        60.0,
        180.0,
        300.0,
    ]
    assert _lobes(lambda a: 0.4 + 0.004 * np.cos(a)) == []


def test_a_flat_top_reads_at_its_centre_and_a_run_across_zero_is_one_lobe():
    flat = np.where((AZ >= 4) & (AZ <= 10), 4.566, 4.0)
    assert azimuth_lobes(AZ, flat)[0] == [7.0]
    across = np.where((AZ >= 356) | (AZ <= 4), 3.0, 0.0)
    assert azimuth_lobes(AZ, across)[0] == [0.0]


def test_the_tolerance_is_from_the_given_peak_and_the_ripple_is_the_rings():
    ring = 0.25 * np.cos(3 * np.radians(AZ))
    lobes, ripple = azimuth_lobes(AZ, ring, peak_dbi=0.25)
    assert lobes == [0.0, 120.0, 240.0]
    assert ripple == pytest.approx(0.5)
    assert PEAK_LOBE_TOL_DB == 0.01


@pytest.fixture(scope="module")
def three_radials():
    b = Vertical(params={**Vertical.default_params, "n_radials": 3})
    return MomwireEngine(b, ground=("finite", 13.0, 0.005))


def test_three_radials_have_three_lobes_and_their_ripple_is_the_front_to_back(
    three_radials,
):
    """Measured 2026-10-28: lobes at 60/180/300°, ripple 0.25 dB; the back of
    a lobe falls between the other two, so F/B is that ripple, not 0."""
    gain = three_radials.gain_evaluator()
    m = refined_pattern_metrics(gain)
    out = ring_lobes(gain, m)
    assert out["azimuth_lobes_deg"] == pytest.approx([60.0, 180.0, 300.0], abs=1.0)
    assert out["azimuth_ripple_db"] == pytest.approx(m["front_to_back_db"], abs=0.01)
    assert "azimuth_lobes_deg" not in m


def test_a_grid_source_reads_the_same_ring(three_radials):
    """`ring_lobes` off a 1-degree grid, as the card-deck engines serve it."""
    ff = three_radials.far_field(n_theta=90, n_phi=360, del_theta=1, del_phi=1)
    rings = np.asarray(ff.rings, float)
    thetas = np.asarray(ff.thetas, float)
    phis = np.asarray(ff.phis, float)

    def grid_gain(th, ph):
        ti = [int(np.flatnonzero(np.isclose(thetas, t))[0]) for t in th]
        pi = [int(np.flatnonzero(np.isclose(phis, p % 360.0))[0]) for p in ph]
        return rings[np.ix_(ti, pi)]

    m = pattern_metrics(ff, has_ground=True)
    out = ring_lobes(grid_gain, m)
    assert out["azimuth_lobes_deg"] == pytest.approx([60.0, 180.0, 300.0], abs=1.0)
