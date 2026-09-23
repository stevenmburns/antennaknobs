"""The 3-D max samples the horizon and the lower hemisphere, and refines the
peak off the 1° grid (AK#1669).

NEC's far-field grid runs θ 0..89°: elevation 1-90° only. AC6LA's Cardioid
peaks AT the horizon (EZNEC: 6.78 dBi @ 0°), so the readout said el 1°; a
free-space lobe pointing down was never seen at all; and the peak was the best
1° × 1° sample rather than the lobe's own maximum.

The synthetic cases give `refined_pattern_metrics` a gain function with a
known answer. The Cardioid case runs the real endpoint body and checks it
against the drawn cut through the same direction, which is what the #1632 aim
puts on screen.
"""

from __future__ import annotations

from pathlib import Path

import numpy as np
import pytest

import antennaknobs.web.examples  # noqa: F401  registration order
from antennaknobs.engine import FarField
from antennaknobs.far_field import pattern_metrics, refined_pattern_metrics
from antennaknobs.file_designs import builder_from_file
from antennaknobs.web import server
from antennaknobs.web.adapter import _make_example
from antennaknobs.web.server import _pattern_cuts

CARDIOID = (
    Path(__file__).parent / "fixtures" / "eznec_gyrator_1595" / "Cardioidmodnec5.nec"
)


class _Lobe:
    """Gain = peak − (angle from the lobe axis / w)² dB: a lobe whose 3-dB
    full width is 2·w·√3, at a direction off every 1° sample."""

    def __init__(self, theta0, phi0, *, peak=10.0, w=10.0, has_ground=True):
        t, p = np.radians(theta0), np.radians(phi0)
        self.axis = np.array([np.sin(t) * np.cos(p), np.sin(t) * np.sin(p), np.cos(t)])
        self.peak, self.w, self.has_ground = peak, w, has_ground

    def __call__(self, theta_deg, phi_deg):
        t = np.radians(np.asarray(theta_deg, float))[:, None]
        p = np.radians(np.asarray(phi_deg, float))[None, :]
        r = np.stack(
            np.broadcast_arrays(
                np.sin(t) * np.cos(p), np.sin(t) * np.sin(p), np.cos(t)
            ),
            axis=-1,
        )
        ang = np.degrees(np.arccos(np.clip(r @ self.axis, -1.0, 1.0)))
        return self.peak - (ang / self.w) ** 2


def _nec_grid(gain):
    """What the endpoint summarised before: NEC's θ 0..89 × closed φ ring."""
    thetas, phis = np.arange(90.0), np.arange(361.0)
    rings = gain(thetas, phis)
    return FarField(rings.tolist(), rings.max(), rings.min(), thetas, phis)


def test_an_off_grid_lobe_is_found_at_its_own_direction_and_gain():
    lobe = _Lobe(62.37, 123.61, w=2.0)
    m = refined_pattern_metrics(lobe)
    assert m["peak_gain_dbi"] == pytest.approx(10.0, abs=1e-3)
    assert m["takeoff_deg"] == pytest.approx(90.0 - 62.37, abs=0.01)
    assert m["azimuth_deg"] == pytest.approx(123.61, abs=0.01)
    # The grid's best sample is 0.37° / 0.39° off the axis in each angle.
    old = pattern_metrics(_nec_grid(lobe))
    assert old["peak_gain_dbi"] < 10.0 - 0.02
    assert old["takeoff_deg"] == 28.0


def test_a_lobe_at_the_horizon_reads_elevation_zero():
    m = refined_pattern_metrics(_Lobe(90.0, 30.0))
    assert m["takeoff_deg"] == pytest.approx(0.0, abs=1e-9)
    assert m["peak_gain_dbi"] == pytest.approx(10.0, abs=1e-9)
    assert pattern_metrics(_nec_grid(_Lobe(90.0, 30.0)))["takeoff_deg"] == 1.0


def test_in_free_space_a_downward_lobe_is_found():
    lobe = _Lobe(130.0, 200.0, has_ground=False)
    m = refined_pattern_metrics(lobe)
    assert m["takeoff_deg"] == pytest.approx(-40.0, abs=0.01)
    assert m["peak_gain_dbi"] == pytest.approx(10.0, abs=1e-6)


def test_over_a_ground_the_lower_hemisphere_is_not_searched():
    m = refined_pattern_metrics(_Lobe(130.0, 200.0, has_ground=True))
    assert m["takeoff_deg"] == pytest.approx(0.0, abs=1e-9)
    assert m["peak_gain_dbi"] == pytest.approx(10.0 - (40.0 / 10.0) ** 2)


def test_the_elevation_width_runs_through_the_horizon_in_free_space():
    # 3-dB full width 2·10·√3 = 34.64°, centred on the horizon: the NEC grid
    # saw only its upper half.
    m = refined_pattern_metrics(_Lobe(90.0, 0.0, has_ground=False))
    assert m["el_beamwidth_deg"] == pytest.approx(34.64, abs=0.05)
    assert m["az_beamwidth_deg"] == pytest.approx(34.64, abs=0.05)
    assert pattern_metrics(_nec_grid(_Lobe(90.0, 0.0)))["el_beamwidth_deg"] < 18.0


class _Ring:
    """A pattern that depends on θ alone: every azimuth ties."""

    has_ground = False

    def __init__(self, f):
        self.f = f

    def __call__(self, theta_deg, phi_deg):
        t = np.asarray(theta_deg, float)[:, None]
        return np.broadcast_to(self.f(t), (t.shape[0], np.size(phi_deg))).copy()


def test_ties_resolve_to_one_direction_by_rule():
    # An omnidirectional horizon ring: azimuth 0, not whichever bit won.
    m = refined_pattern_metrics(_Ring(lambda t: 2.0 - ((t - 90.0) / 20.0) ** 2))
    assert m["azimuth_deg"] == 0.0
    assert m["takeoff_deg"] == pytest.approx(0.0, abs=1e-9)
    assert m["az_beamwidth_deg"] == 360.0
    # Twin lobes mirrored about the horizon: the upper one.
    twin = _Ring(lambda t: 2.0 - ((np.abs(t - 90.0) - 30.0) / 10.0) ** 2)
    assert refined_pattern_metrics(twin)["takeoff_deg"] == pytest.approx(30.0, abs=1e-9)


def test_the_cardioid_peaks_at_the_horizon_and_matches_the_drawn_cut():
    cls = builder_from_file(str(CARDIOID))
    ex = _make_example("Cardioidmodnec5", cls)
    f = cls().freq
    req = {
        "measurement_freq_mhz": f,
        "design_freq_mhz": f,
        "ground": True,
        "ground_model": "pec",
    }
    m = ex.far_field_metrics(req)
    # EZNEC puts this cardioid's peak AT the horizon, 6.78 dBi.
    assert m["takeoff_deg"] == 0.0
    assert m["peak_gain_dbi"] == pytest.approx(6.78, abs=0.2)

    # The aim (#1632) puts the azimuth cut at the peak's elevation and the
    # elevation cut at its bearing; both must pass through the same maximum.
    out = ex.momwire_solve(req)
    server._attach_derived_em_fields(out)
    server._attach_gain_norm(out)
    cuts = _pattern_cuts(out, m["takeoff_deg"], m["azimuth_deg"])
    for trace in (cuts["azimuth"], cuts["elevation"]):
        # The cuts are rounded to 1e-3 dB on the wire.
        assert max(trace) <= m["peak_gain_dbi"] + 1e-3
        assert max(trace) == pytest.approx(m["peak_gain_dbi"], abs=0.01)
