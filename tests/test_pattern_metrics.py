"""Tests for antennaknobs.far_field pattern metrics.

The metrics are computed from a `FarField` (rings[θ][φ] in dBi). Tests build
synthetic FarFields with known peaks / lobes so the expected metrics are exact
or analytically known, rather than depending on a solver.
"""

from __future__ import annotations

import numpy as np
import pytest

from antennaknobs.engine import FarField
from antennaknobs.far_field import (
    _beamwidth_linear,
    _beamwidth_wrapped,
    pattern_metrics,
)


def _make_ff(rings):
    rings = np.asarray(rings, float)
    n_theta, n_phi = rings.shape
    thetas = np.arange(n_theta, dtype=float)
    phis = np.arange(n_phi, dtype=float)
    return FarField(
        rings=rings.tolist(),
        max_gain=float(rings.max()),
        min_gain=float(rings.min()),
        thetas=thetas,
        phis=phis,
    )


# --- beamwidth helpers --------------------------------------------------------


def test_wrapped_beamwidth_of_parabolic_lobe():
    # g(φ) = 10 − 0.003333·d², d = circular distance from 0°. g hits 10−3=7 at
    # d = 30°, so the −3 dB width is 60°.
    phis = np.arange(361, dtype=float)
    d = np.minimum(phis, 360.0 - phis)
    g = 10.0 - (3.0 / 900.0) * d**2
    bw = _beamwidth_wrapped(phis, g, peak_idx=0, threshold=7.0)
    assert bw == pytest.approx(60.0, abs=0.5)


def test_wrapped_beamwidth_omnidirectional_is_full_circle():
    phis = np.arange(361, dtype=float)
    g = np.full_like(phis, 5.0)
    assert _beamwidth_wrapped(phis, g, peak_idx=0, threshold=2.0) == 360.0


def test_linear_beamwidth_of_parabolic_lobe():
    # Elevation angles 90..1 (decreasing); lobe peaks at 45° with a 3 dB
    # half-width of 20° → 40° total.
    thetas = np.arange(90, dtype=float)
    el = 90.0 - thetas
    g = 10.0 - (3.0 / 400.0) * (el - 45.0) ** 2
    peak_idx = int(np.argmax(g))
    bw = _beamwidth_linear(el, g, peak_idx, threshold=7.0)
    assert bw == pytest.approx(40.0, abs=1.0)


# --- pattern_metrics ----------------------------------------------------------


def test_peak_takeoff_and_azimuth_locate_the_maximum():
    rings = np.full((90, 361), -50.0)
    rings[75, 0] = 12.0  # θ=75 → elevation 15°, azimuth 0°
    m = pattern_metrics(_make_ff(rings))
    assert m["peak_gain_dbi"] == 12.0
    assert m["takeoff_deg"] == pytest.approx(15.0)
    assert m["azimuth_deg"] == pytest.approx(0.0)


def test_azimuth_reports_zero_when_the_duplicated_endpoint_wins():
    """Issue #958: φ = 0 and φ = 360 are ONE direction, and the grid samples
    both. A peak there is a tie broken at the last bit — on `pota_performer`
    the two copies came out 1.0744769060050083 and 1.074476906005009, so
    `argmax` took φ = 360 and the metric read 360.0 for a bearing of zero.

    Forced here rather than waited for: the φ = 360 column is made the strict
    maximum, which is what a ULP-level tie amounts to for `argmax`. The
    reported azimuth must be the bearing, not the grid coordinate.
    """
    rings = np.full((90, 361), -50.0)
    rings[75, 0] = 12.0
    rings[75, 360] = 12.000000000000002  # the same direction, one ULP up
    m = pattern_metrics(_make_ff(rings))
    assert m["azimuth_deg"] == 0.0, "a bearing of 0 must not report as 360"
    # The rest of the summary must not care which copy won either.
    assert m["takeoff_deg"] == pytest.approx(15.0)
    assert m["front_to_back_db"] == pytest.approx(62.0)


def test_front_to_back_uses_same_elevation_opposite_azimuth():
    rings = np.full((90, 361), -50.0)
    rings[75, 0] = 10.0  # front
    rings[75, 180] = -8.0  # back, same elevation
    m = pattern_metrics(_make_ff(rings))
    assert m["front_to_back_db"] == pytest.approx(18.0)


def test_front_to_back_wraps_when_peak_past_180():
    rings = np.full((90, 361), -40.0)
    rings[60, 300] = 6.0  # peak azimuth 300° → back lobe at 120°
    rings[60, 120] = -4.0
    m = pattern_metrics(_make_ff(rings))
    assert m["azimuth_deg"] == pytest.approx(300.0)
    assert m["front_to_back_db"] == pytest.approx(10.0)


def test_metrics_keys_present():
    rings = np.full((90, 361), -30.0)
    rings[80, 90] = 3.0
    m = pattern_metrics(_make_ff(rings))
    assert set(m) == {
        "peak_gain_dbi",
        "takeoff_deg",
        "azimuth_deg",
        "front_to_back_db",
        "az_beamwidth_deg",
        "el_beamwidth_deg",
    }
