"""Issue #1341: currents below the ground plane in the far-field readout.

Both readouts image every segment as if it stood above the plane. For a
current inside the medium that is the wrong problem (the transmitted field,
momwire#570), so: a wholly buried structure's pattern is REFUSED by name; a
mixed deck is served with a note when the pattern barely depends on the
in-medium currents, refused when it does; and a deck with nothing below the
plane is untouched — bit-identical to the readout before this issue.
"""

from __future__ import annotations

import numpy as np
import pytest

from antennaknobs import in_medium
from antennaknobs.engines.momwire import MomwireEngine
from antennaknobs.web.server import (
    _attach_in_medium_assessment,
    _mag2_at_directions,
    _pattern_cuts,
)

SOIL = ("finite", 13.0, 0.005)


# --- the helper on synthetic moment sets ------------------------------------


def _moments(z_list, i_list):
    mid = np.array([[0.0, 0.0, z] for z in z_list], dtype=float)
    dr = np.tile(np.array([0.0, 0.0, 0.01]), (len(z_list), 1))
    i_mid = np.array(i_list, dtype=complex)
    return mid, dr, i_mid


def test_below_surface_mask_uses_a_relative_tolerance():
    mid, _, _ = _moments([1.0, -1e-9, -0.5], [1, 1, 1])
    mask = in_medium.below_surface_mask(mid, 0.0)
    assert mask.tolist() == [False, False, True], "float noise at z=0 is ON the plane"


def test_moment_fraction_is_current_times_length():
    mid, dr, i_mid = _moments([1.0, -1.0], [3.0, 1.0])
    mask = in_medium.below_surface_mask(mid, 0.0)
    assert in_medium.moment_fraction(dr, i_mid, mask) == pytest.approx(0.25)


def test_pattern_delta_ignores_the_nulls():
    full = np.array([1.0, 1e-3, 1e-12])
    above = np.array([1.0, 1e-3, 1e-6])  # a null moved by 60 dB
    assert in_medium.pattern_delta_db(full, above) == pytest.approx(0.0)
    above = np.array([2.0, 1e-3, 1e-12])  # the peak moved by 3.01 dB
    assert in_medium.pattern_delta_db(full, above) == pytest.approx(10 * np.log10(2.0))


def test_assess_wholly_buried_refuses_by_name():
    mid, dr, i_mid = _moments([-0.2, -0.4], [1, 1])
    a = in_medium.assess(mid, dr, i_mid, 0.0, lambda m, d, i: np.ones(4))
    assert not a.served
    assert "momwire#570" in a.refusal
    assert "transmitted" in a.refusal
    assert a.fraction == pytest.approx(1.0)


def test_assess_serves_under_the_bar_and_refuses_over_it():
    mid, dr, i_mid = _moments([1.0, -0.2], [1.0, 0.1])

    def readout_scaled(factor):
        # |M|² proportional to the total moment squared: the buried 10 %
        # moves the pattern by 20·log10(1.1/1.0) ≈ 0.83 dB; scaling the
        # buried current makes it cross the bar.
        def evaluate(m, d, i):
            return np.full(3, (np.sum(np.abs(i)) * factor) ** 2)

        return evaluate

    a = in_medium.assess(mid, dr, i_mid, 0.0, readout_scaled(1.0))
    assert a.served and a.note and "momwire#570" in a.note
    assert a.delta_db == pytest.approx(20 * np.log10(1.1), abs=1e-9)
    mid, dr, i_mid = _moments([1.0, -0.2], [1.0, 1.0])
    a = in_medium.assess(mid, dr, i_mid, 0.0, readout_scaled(1.0))
    assert not a.served and "up to 6.0 dB" in a.refusal


# --- the engine on the catalog ----------------------------------------------


@pytest.mark.antenna_computation_check
def test_buried_dipole_pattern_is_refused_and_impedance_served():
    from antennaknobs.designs.specialty.buried_dipole import Builder

    eng = MomwireEngine(Builder(), ground=SOIL)
    z = eng.impedance()
    assert z[0].real > 0
    with pytest.raises(in_medium.InMediumPatternRefusal) as ei:
        eng.far_field(n_theta=9, n_phi=8, del_theta=10, del_phi=45)
    assert "momwire#570" in str(ei.value)


@pytest.mark.antenna_computation_check
def test_buried_radial_vertical_pattern_is_served_with_a_note():
    from antennaknobs.designs.verticals.buried_radial_vertical import Builder

    eng = MomwireEngine(Builder(), ground=SOIL)
    ff = eng.far_field(n_theta=90, n_phi=360, del_theta=1, del_phi=1)
    # Measured 2026-09-09 at the design's defaults: 38 % of Σ|I·dl| below
    # the plane, and the pattern moves 0.46 dB when those segments are
    # dropped — the symmetric screen's currents cancel in the far field.
    assert 0.30 < ff.in_medium_moment_fraction < 0.45
    assert 0.2 < ff.in_medium_pattern_delta_db < 1.0
    assert ff.note and "momwire#570" in ff.note
    # The served readout is the status quo: the peak is what it was before
    # this issue (the same code path, the same numbers).
    assert ff.max_gain == pytest.approx(-2.5851294708057764, abs=1e-6)


def test_free_space_far_field_is_untouched():
    from antennaknobs.designs.dipoles.invvee import Builder

    ff = MomwireEngine(Builder()).far_field(
        n_theta=90, n_phi=360, del_theta=1, del_phi=1
    )
    assert ff.in_medium_moment_fraction == 0.0
    assert ff.in_medium_pattern_delta_db == 0.0
    assert ff.note is None
    assert ff.max_gain == 1.923798486448699  # bit-identical to the pre-#1341 readout


# --- the web readout ---------------------------------------------------------


def _hertzian_response(segments, *, ground=True):
    """A solve-response stand-in: z-directed 1 cm segments at the given
    heights with the given currents, on the web's z = 0 ground plane."""
    wires = [
        {
            "knot_positions": [[0.0, 0.0, z], [0.0, 0.0, z + 0.01]],
            "knot_currents_re": [float(i), float(i)],
            "knot_currents_im": [0.0, 0.0],
        }
        for z, i in segments
    ]
    return {
        "wires": wires,
        "k_meas_m_inv": 2 * np.pi / 20.0,
        "ground": ground,
        "ground_eps_r": 13.0,
        "ground_eps_im": -0.005 / (2 * np.pi * 15e6 * 8.854e-12),
        "directivity_norm": 1.0,
    }


def test_web_wholly_buried_response_refuses_and_withholds_cuts():
    out = _hertzian_response([(-0.5, 1.0)])
    _attach_in_medium_assessment(out)
    assert "momwire#570" in out["pattern_refusal"]
    assert out["in_medium_moment_fraction"] == pytest.approx(1.0)
    assert out["in_medium_pattern_delta_db"] is None
    assert _pattern_cuts(out, 15.0, 0.0) is None


def test_web_small_buried_share_is_served_with_a_note():
    out = _hertzian_response([(1.0, 1.0), (-0.5, 0.05)])
    _attach_in_medium_assessment(out)
    assert "pattern_refusal" not in out
    assert "momwire#570" in out["pattern_note"]
    assert out["in_medium_moment_fraction"] == pytest.approx(0.05 / 1.05)
    assert 0.0 < out["in_medium_pattern_delta_db"] < in_medium.IN_MEDIUM_PATTERN_BAR_DB
    cuts = _pattern_cuts(out, 15.0, 0.0)
    assert cuts is not None and len(cuts["azimuth"]) > 0


def test_web_dominant_buried_share_is_refused():
    out = _hertzian_response([(1.0, 1.0), (-0.5, 1.0)])
    _attach_in_medium_assessment(out)
    assert "up to" in out["pattern_refusal"] and "momwire#570" in out["pattern_refusal"]
    assert _pattern_cuts(out, 15.0, 0.0) is None


def test_web_free_space_and_above_ground_responses_carry_nothing():
    for out in (
        _hertzian_response([(1.0, 1.0)]),
        _hertzian_response([(1.0, 1.0)], ground=False),
    ):
        before = _mag2_at_directions(out, np.array([[0.0, 0.0, 1.0], [1.0, 0.0, 0.0]]))
        _attach_in_medium_assessment(out)
        assert "pattern_refusal" not in out and "pattern_note" not in out
        assert "in_medium_moment_fraction" not in out
        after = _mag2_at_directions(out, np.array([[0.0, 0.0, 1.0], [1.0, 0.0, 0.0]]))
        np.testing.assert_array_equal(before, after)
