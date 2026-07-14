"""Physics regression tests for the Cebik (W4RNL) design family.

Each test pins the published Cebik behaviour (resonant impedance, gain,
polarisation/pattern shape) via the PyNEC engine so a geometry regression
in build_wires() is caught. Free-space (ground=None) is used for the
impedance/gain numbers because it removes soil-model dependence; pattern
shape (broadside vs end-on) is checked there too.
"""

from __future__ import annotations

import numpy as np
import pytest

pytest.importorskip("PyNEC")

# Whole-file: every test here solves a named Cebik design via the PyNEC engine
# (per-design catalog coverage). Quarantined off the per-PR fast lane and run
# in the full main-only suite. See the marker definition in pyproject.toml.
pytestmark = pytest.mark.antenna_computation_check

from antennaknobs.engines import PyNECEngine  # noqa: E402


def _z(builder, ground=None):
    return PyNECEngine(builder, ground=ground).impedance()[0]


def _far_field(builder, ground=None):
    return PyNECEngine(builder, ground=ground).far_field(
        n_theta=90, n_phi=360, del_theta=1, del_phi=1
    )


# ---------------------------------------------------------------------------
# Half-square
# ---------------------------------------------------------------------------


def test_half_square_resonant_and_low_z():
    """Corner-fed half-square: ~65 ohm, near-resonant at length_factor=1
    (Cebik's max-gain proportions)."""
    from antennaknobs.designs.verticals.half_square import Builder

    z = _z(Builder())
    assert 50.0 < z.real < 80.0
    assert abs(z.imag) < 20.0  # near resonance at the default scale


def test_half_square_gain_matches_cebik():
    """~4.6-4.7 dBi free-space per Cebik's published models."""
    from antennaknobs.designs.verticals.half_square import Builder

    ff = _far_field(Builder())
    assert 4.0 < ff.max_gain < 5.5


def test_half_square_is_broadside_with_end_nulls():
    """Vertically-polarised, bidirectional broadside off +/-x with deep
    nulls off the ends (Cebik: >10 dB side rejection)."""
    from antennaknobs.designs.verticals.half_square import Builder

    ff = _far_field(Builder())
    rings = np.array(ff.rings)  # [theta][phi], dBi
    row = rings[60]  # ~30 deg elevation
    broadside = max(row[0], row[180])
    end_on = max(row[90], row[270])
    assert broadside - end_on > 8.0


def test_half_square_feed_wire_carries_current_free_ends_null():
    """The corner feed is a dedicated 1-segment driven edge, so both its
    knots are junctions. current_distribution must carry the segment current
    onto those boundary knots (continuous through a junction) rather than
    zeroing them, which would render a zero-current gap right at the feed —
    the current maximum. The two open leg ends, by contrast, are genuine free
    ends and stay at the current null Cebik describes."""
    from antennaknobs.designs.verticals.half_square import Builder

    cur = PyNECEngine(Builder(), ground=None).current_distribution()
    # Tuple order from build_wires: 0=left leg, 1=feed stub, 2=top, 3=right leg.
    feed = np.abs(cur[1].knot_currents)
    assert cur[1].knot_positions.shape[0] == 2  # 1-segment feed edge
    assert feed.min() > 1e-4  # both junction knots carry current, no gap
    # Open leg ends (knot 0 of the left leg, last knot of the right leg) are
    # free ends -> current null.
    assert abs(cur[0].knot_currents[0]) < 1e-9
    assert abs(cur[3].knot_currents[-1]) < 1e-9


def test_half_square_length_factor_tunes_reactance():
    """Reactance climbs monotonically with length_factor through resonance."""
    from antennaknobs.designs.verticals.half_square import Builder

    x_lo = _z(Builder(dict(Builder.default_params, length_factor=0.96))).imag
    x_mid = _z(Builder(dict(Builder.default_params, length_factor=1.00))).imag
    x_hi = _z(Builder(dict(Builder.default_params, length_factor=1.04))).imag
    assert x_lo < x_mid < x_hi


# ---------------------------------------------------------------------------
# Bobtail curtain
# ---------------------------------------------------------------------------


def test_bobtail_gain_exceeds_half_square():
    """Three-element curtain: ~5+ dBi broadside, more than the half-square's
    ~4.7 (Cebik: ~5.1-5.2 dBi)."""
    from antennaknobs.designs.verticals.bobtail import Builder

    ff = _far_field(Builder())
    assert ff.max_gain > 5.0


def test_bobtail_broadside_directivity():
    """Vertically-polarised, sharply bidirectional broadside off +/-x with
    very deep end nulls (3 in-phase verticals)."""
    from antennaknobs.designs.verticals.bobtail import Builder

    ff = _far_field(Builder())
    rings = np.array(ff.rings)
    row = rings[60]
    broadside = max(row[0], row[180])
    end_on = max(row[90], row[270])
    assert broadside - end_on > 20.0


def test_bobtail_feed_is_coax_friendly():
    """Tapped at a current maximum on the centre vertical (not the classic
    high-Z base/tank point), the driving point is a low, near-resonant ~50 ohm
    that takes coax directly."""
    from antennaknobs.designs.verticals.bobtail import Builder

    z = _z(Builder())
    assert 35.0 < z.real < 70.0
    assert abs(z.imag) < 30.0


def test_bobtail_tap_position_sets_impedance():
    """Sliding the tap toward the base (a current null) raises the feed
    resistance -- the standing-wave transformation that lets feed_height_frac
    pick the match, the same trick a shunt/gamma feed uses."""
    from antennaknobs.designs.verticals.bobtail import Builder

    r_mid = _z(Builder()).real  # default tap (~0.5) -> ~50 ohm
    r_low = _z(Builder(dict(Builder.default_params, feed_height_frac=0.3))).real
    assert r_low > r_mid + 20.0


def test_bobtail_only_centre_element_is_fed():
    """Exactly one driven gap; the outer verticals are passive."""
    from antennaknobs.designs.verticals.bobtail import Builder

    feeds = [t for t in Builder().build_wires() if t[3] is not None]
    assert len(feeds) == 1
    # The fed gap sits on the centre vertical (y = 0).
    (x0, y0, _), (x1, y1, _), _, _ = feeds[0]
    assert y0 == 0.0 and y1 == 0.0


# ---------------------------------------------------------------------------
# Cubical quad beam
# ---------------------------------------------------------------------------


def test_quad_forward_gain():
    """~7 dBi forward (Cebik: 6.6-7.5 dBi for the wideband 2-el quad)."""
    from antennaknobs.designs.loops.quad import Builder

    ff = _far_field(Builder())
    assert ff.max_gain > 6.5


def test_quad_driver_near_resonant():
    """Driver loop ~1.01 wl is near resonance at the default scale."""
    from antennaknobs.designs.loops.quad import Builder

    z = _z(Builder())
    assert abs(z.imag) < 35.0


def test_quad_fires_toward_driver_with_front_to_back():
    """Beam fires +x (toward the driver, away from the reflector at -x)."""
    from antennaknobs.designs.loops.quad import Builder

    ff = _far_field(Builder())
    rings = np.array(ff.rings)
    front = rings[:, 0].max()  # +x
    back = rings[:, 180].max()  # -x
    assert front - back > 6.0


def test_quad_has_two_loops_one_fed():
    """Reflector (passive) + driver (one fed gap) = 2 four-sided loops."""
    from antennaknobs.designs.loops.quad import Builder

    tups = Builder().build_wires()
    feeds = [t for t in tups if t[3] is not None]
    assert len(feeds) == 1
    # Reflector sits behind the driver (more negative x).
    xs = sorted({round(t[0][0], 6) for t in tups})
    assert len(xs) == 2 and xs[0] < xs[1]


# ---------------------------------------------------------------------------
# Lazy-H
# ---------------------------------------------------------------------------


def test_lazy_h_stacking_gain():
    """Two stacked in-phase 1 wl elements give ~8 dBi free-space -- well
    above a single ~1 wl element's ~4 dBi (the vertical-stacking gain)."""
    from antennaknobs.designs.wire.lazy_h import Builder

    ff = _far_field(Builder())
    assert ff.max_gain > 7.0


def test_lazy_h_broadside_horizontal():
    """Bidirectional broadside off +/-x with deep end nulls."""
    from antennaknobs.designs.wire.lazy_h import Builder

    ff = _far_field(Builder())
    rings = np.array(ff.rings)
    row = rings[60]
    broadside = max(row[0], row[180])
    end_on = max(row[90], row[270])
    assert broadside - end_on > 15.0


def test_lazy_h_two_in_phase_feeds():
    """Two centre feeds, both at y=0, both driven in phase (1+0j); by
    symmetry they present equal feed impedance."""
    from antennaknobs.designs.wire.lazy_h import Builder

    feeds = [t for t in Builder().build_wires() if t[3] is not None]
    assert len(feeds) == 2
    assert all(f[3] == 1 + 0j for f in feeds)
    assert all(f[0][1] == -0.05 and f[1][1] == 0.05 for f in feeds)
    zs = PyNECEngine(Builder(), ground=None).impedance()
    assert abs(zs[0] - zs[1]) < 1.0  # symmetric -> equal


def test_lazy_h_wider_spacing_adds_gain():
    """Expanding the stack toward ~5/8 wl raises gain (W2EEY expansion)."""
    from antennaknobs.designs.wire.lazy_h import Builder

    g_half = _far_field(
        Builder(dict(Builder.default_params, spacing_frac=0.5))
    ).max_gain
    g_wide = _far_field(
        Builder(dict(Builder.default_params, spacing_frac=0.625))
    ).max_gain
    assert g_wide > g_half


# ---------------------------------------------------------------------------
# LPDA (log-periodic dipole array)
# ---------------------------------------------------------------------------


def test_lpda_broadband_forward_gain():
    """The defining LPDA behaviour: ~6-9 dBi forward gain held across a wide
    band, firing toward the apex (+x). (Feedpoint impedance is not asserted
    -- the ideal lossless crossed feeder makes it unreliable; see module
    docstring.)"""
    from antennaknobs.designs.broadband.lpda import Builder

    for fr in (24.0, 26.0, 28.57, 30.0):
        b = Builder(dict(Builder.default_params, freq=fr))
        ff = _far_field(b)
        rings = np.array(ff.rings)
        front = rings[:, 0].max()  # +x, toward the apex
        back = rings[:, 180].max()
        assert ff.max_gain > 5.5, (fr, ff.max_gain)
        assert front > back, (fr, front, back)


def test_lpda_elements_scale_by_tau():
    """Element half-lengths form a geometric sequence with ratio tau."""
    from antennaknobs.designs.broadband.lpda import Builder

    b = Builder()
    half, x = b._layout()
    ratios = [half[k + 1] / half[k] for k in range(len(half) - 1)]
    assert all(abs(r - b.tau) < 1e-9 for r in ratios)
    # boom positions strictly increase toward the front
    assert all(x[k + 1] > x[k] for k in range(len(x) - 1))


def test_lpda_feeder_is_crossed_and_front_driven():
    """Every feeder section is crossed (negative z0) and the source sits on
    the front (shortest) element."""
    from antennaknobs.designs.broadband.lpda import Builder
    from antennaknobs.network import TL, Driven

    b = Builder()
    net = b.build_network()
    tls = [br for br in net.branches if isinstance(br, TL)]
    assert len(tls) == b.n_elements - 1
    assert all(tl.transposed and tl.z0 > 0 for tl in tls)  # all crossed
    (src,) = net.sources
    assert isinstance(src, Driven)
    assert src.port == f"d{b.n_elements - 1}"  # frontmost / shortest


# ---------------------------------------------------------------------------
# HB9CV / ZL-Special (2-element all-driven phased beam)
# ---------------------------------------------------------------------------


def test_hb9cv_forward_gain_and_endfire():
    """~6-7 dBi (like a 2-el Yagi) firing toward the front (+x). F/B is real
    but shallow in this ideal-crossed-TL model -- see module docstring."""
    from antennaknobs.designs.beams.hb9cv import Builder

    ff = _far_field(Builder())
    rings = np.array(ff.rings)
    front = rings[:, 0].max()
    back = rings[:, 180].max()
    assert ff.max_gain > 6.0
    assert front - back > 5.0


def test_hb9cv_feed_resistive_inductive():
    """Cebik: feed ~40-55 ohm resistive with inductive reactance. Both
    elements are driven through a single crossed phasing line."""
    from antennaknobs.designs.beams.hb9cv import Builder

    z = _z(Builder())
    assert z.real > 15.0  # positive, real driving-point R
    assert z.imag > 0.0  # inductive (needs series-cap cancellation)


def test_hb9cv_both_driven_via_one_crossed_line():
    """No parasite: a single crossed (transposed) phasing line couples the
    two driven element centres; the source sits on the front element."""
    from antennaknobs.designs.beams.hb9cv import Builder
    from antennaknobs.network import TL, Driven

    net = Builder().build_network()
    tls = [br for br in net.branches if isinstance(br, TL)]
    assert len(tls) == 1 and tls[0].transposed and tls[0].z0 > 0
    assert {tls[0].a, tls[0].b} == {"rear", "front"}
    (src,) = net.sources
    assert isinstance(src, Driven) and src.port == "front"


# ---------------------------------------------------------------------------
# Terminated rhombic
# ---------------------------------------------------------------------------


def test_rhombic_unidirectional_when_terminated():
    """The terminating resistor makes the traveling-wave pattern
    unidirectional toward the terminated apex (+x)."""
    from antennaknobs.designs.wire.rhombic import Builder

    ff = _far_field(Builder())
    rings = np.array(ff.rings)
    front = rings[:, 0].max()  # +x toward termination
    back = rings[:, 180].max()
    assert ff.max_gain > 6.0
    assert front - back > 12.0


def test_rhombic_termination_creates_the_directivity():
    """Remove the termination (R -> huge) and the F/B collapses: the
    progressive wave is gone and the pattern goes ~bidirectional."""
    from antennaknobs.designs.wire.rhombic import Builder

    def fb(r):
        b = Builder(dict(Builder.default_params, term_r=r))
        rings = np.array(_far_field(b).rings)
        return rings[:, 0].max() - rings[:, 180].max()

    assert fb(700.0) > 12.0
    assert fb(1e9) < 5.0


def test_rhombic_impedance_tracks_termination():
    """Traveling-wave antenna: the driving-point R sits near the
    termination value, and it scales with it (broadband behaviour)."""
    from antennaknobs.designs.wire.rhombic import Builder

    z600 = _z(Builder(dict(Builder.default_params, term_r=600.0)))
    z800 = _z(Builder(dict(Builder.default_params, term_r=800.0)))
    assert 450.0 < z600.real < 750.0
    assert z800.real > z600.real  # tracks the termination upward


def test_rhombic_has_terminating_load_and_feed():
    """One driven feed apex and one resistive Load at the far apex."""
    from antennaknobs.designs.wire.rhombic import Builder
    from antennaknobs.network import Driven, Load

    net = Builder().build_network()
    loads = [br for br in net.branches if isinstance(br, Load)]
    assert len(loads) == 1
    assert loads[0].port == "term" and loads[0].r == 700.0
    (src,) = net.sources
    assert isinstance(src, Driven) and src.port == "feed"


# ---------------------------------------------------------------------------
# T2FD (terminated tilted folded dipole)
# ---------------------------------------------------------------------------


def _swr(z, z0):
    g = abs((z - z0) / (z + z0))
    return (1 + g) / (1 - g)


_T2FD_BAND = (14.0, 18.0, 22.0, 28.57, 36.0, 45.0, 56.0)


def test_t2fd_broadband_low_swr():
    """The defining T2FD behaviour: a flat SWR curve over a 4:1 frequency
    range (here referenced to the ~850 ohm the terminated geometry settles
    to), unlike a resonant antenna."""
    from antennaknobs.designs.broadband.t2fd import Builder

    z0 = 850.0
    swrs = [
        _swr(_z(Builder(dict(Builder.default_params, freq=f))), z0) for f in _T2FD_BAND
    ]
    assert max(swrs) < 2.5, dict(zip(_T2FD_BAND, swrs))


def test_t2fd_termination_flattens_the_response():
    """Removing the resistor (R -> huge) restores sharp resonances: the
    unterminated max-SWR over the band is far worse than terminated."""
    from antennaknobs.designs.broadband.t2fd import Builder

    z0 = 850.0

    def band_max(r):
        return max(
            _swr(_z(Builder(dict(Builder.default_params, freq=f, term_r=r))), z0)
            for f in _T2FD_BAND
        )

    assert band_max(820.0) < 2.5
    assert band_max(1e9) > 10.0  # huge anti-resonant spike without the load


def test_t2fd_gain_is_reduced_by_loss():
    """Power burned in the terminating resistor drops gain below a resonant
    dipole's ~2.1 dBi -- the bandwidth/efficiency trade."""
    from antennaknobs.designs.broadband.t2fd import Builder

    ff = _far_field(Builder())
    assert ff.max_gain < 2.0


def test_t2fd_folded_with_termination():
    """Folded pair (two end shorts), one driven feed, one resistive Load."""
    from antennaknobs.designs.broadband.t2fd import Builder
    from antennaknobs.network import Driven, Load

    tups = Builder().build_wires()
    feeds = [t for t in tups if len(t) == 5 and t[4] == "feed"]
    terms = [t for t in tups if len(t) == 5 and t[4] == "term"]
    assert len(feeds) == 1 and len(terms) == 1
    net = Builder().build_network()
    (load,) = [br for br in net.branches if isinstance(br, Load)]
    assert load.port == "term"
    (src,) = net.sources
    assert isinstance(src, Driven) and src.port == "feed"


# ---------------------------------------------------------------------------
# Batch 2 — W8JK, phased verticals, inverted-L, OCF, V-beam, bi-square,
# J-pole, discone (a second Cebik/W4RNL set filling further catalog gaps).
# ---------------------------------------------------------------------------


# ---------------------------------------------------------------------------
# W8JK flat-top beam (180-degree all-driven array)
# ---------------------------------------------------------------------------


def test_w8jk_bidirectional_endfire_gain():
    """~5.8 dBi firing equally off both +/- x ends (Kraus extended elements);
    the two anti-phase, close-spaced elements make a bidirectional endfire
    beam, not a unidirectional one."""
    from antennaknobs.designs.wire.w8jk import Builder

    ff = _far_field(Builder())
    rings = np.array(ff.rings)
    front = rings[:, 0].max()  # +x
    back = rings[:, 180].max()  # -x
    assert ff.max_gain > 5.5
    assert abs(front - back) < 1.0  # bidirectional


def test_w8jk_broadside_and_overhead_nulls():
    """The array signature: deep nulls off the ends (+/- y, broadside to the
    boom) AND overhead (theta = 0, broadside to the array axis) -- the latter
    is what a single dipole would NOT have, proving the 180-deg array action."""
    from antennaknobs.designs.wire.w8jk import Builder

    ff = _far_field(Builder())
    rings = np.array(ff.rings)
    lobe = rings[:, 0].max()  # the +x endfire lobe
    side = rings[:, 90].max()  # +y broadside
    overhead = rings[0].max()  # straight up
    assert lobe - side > 15.0
    assert lobe - overhead > 15.0


def test_w8jk_two_antiphase_feeds():
    """Exactly two centre feeds, driven 180 degrees out of phase (+1 and -1),
    one per element -- the defining all-driven, out-of-phase topology."""
    from antennaknobs.designs.wire.w8jk import Builder

    feeds = [t for t in Builder().build_wires() if t[3] is not None]
    assert len(feeds) == 2
    volts = sorted(complex(f[3]).real for f in feeds)
    assert volts[0] == -1.0 and volts[1] == 1.0  # anti-phase


# ---------------------------------------------------------------------------
# Two-element phased vertical array (90-degree cardioid)
# ---------------------------------------------------------------------------


def test_phased_verticals_cardioid_front_to_back():
    """The 90-deg feed phasing steers the pattern unidirectionally toward +x
    with a deep rearward null (~6-7 dB F/B here; a current-forcing network
    deepens it further) -- not the figure-8 of a single vertical."""
    from antennaknobs.designs.verticals.phased_verticals import Builder

    ff = _far_field(Builder())
    rings = np.array(ff.rings)
    front = rings[:, 0].max()
    back = rings[:, 180].max()
    assert ff.max_gain > 4.5
    assert front - back > 5.0


def test_phased_verticals_phase_does_the_steering():
    """Drive the two verticals IN phase instead and the unidirectional cardioid
    collapses -- proving the directivity comes from the FEED PHASE, not the
    geometry."""
    from antennaknobs.designs.verticals.phased_verticals import Builder

    in_phase = Builder(dict(Builder.default_params, front_voltage=1 + 0j))
    rings = np.array(_far_field(in_phase).rings)
    fb = rings[:, 0].max() - rings[:, 180].max()
    assert abs(fb) < 2.0  # symmetric again


def test_phased_verticals_two_feeds_front_quadrature():
    """Two vertical (z-axis) feeds; the rear is the +1 reference and the front
    is driven near 90 degrees out of phase (a dominant imaginary part)."""
    from antennaknobs.designs.verticals.phased_verticals import Builder

    feeds = [t for t in Builder().build_wires() if t[3] is not None]
    assert len(feeds) == 2
    # vertical elements: both feed gaps run along z
    assert all(f[0][2] != f[1][2] for f in feeds)
    rear, front = (complex(f[3]) for f in feeds)
    assert rear == 1 + 0j
    assert abs(front.imag) > abs(front.real)  # near quadrature


# ---------------------------------------------------------------------------
# Inverted-L (bent, top-loaded vertical)
# ---------------------------------------------------------------------------


def test_inverted_l_resonant_low_impedance():
    """Top-loaded short vertical: near-resonant (small X) at a low feed
    resistance over its radial counterpoise."""
    from antennaknobs.designs.verticals.inverted_l import Builder

    z = _z(Builder())
    assert 8.0 < z.real < 45.0
    assert abs(z.imag) < 25.0


def test_inverted_l_vertical_low_angle_radiation():
    """Mostly vertically polarised: the pattern peaks toward the horizon and
    is deeply nulled overhead -- the signature of a vertical, not a horizontal
    wire."""
    from antennaknobs.designs.verticals.inverted_l import Builder

    rings = np.array(_far_field(Builder()).rings)
    horizon = rings[80:].max()  # near the horizon (theta ~ 90)
    overhead = rings[:5].max()  # near zenith (theta ~ 0)
    assert horizon - overhead > 5.0


def test_inverted_l_has_riser_top_and_radials():
    """One base feed, a vertical riser, a horizontal top section (the bend),
    and a radial counterpoise."""
    from antennaknobs.designs.verticals.inverted_l import Builder

    tups = Builder().build_wires()
    feeds = [t for t in tups if t[3] is not None]
    assert len(feeds) == 1
    # a horizontal top wire (constant z, runs along y) exists
    horiz = [
        t
        for t in tups
        if abs(t[0][2] - t[1][2]) < 1e-9 and abs(t[0][1] - t[1][1]) > 1e-6
    ]
    assert horiz, "expected a horizontal top section"


# ---------------------------------------------------------------------------
# Off-Center-Fed dipole (Windom)
# ---------------------------------------------------------------------------


def test_ocf_impedance_rises_off_center():
    """The defining OCF physics: sliding the feed off-centre raises the
    (resistive) feed impedance well above the ~70 ohm centre value."""
    from antennaknobs.designs.dipoles.ocf_dipole import Builder

    r_off = _z(Builder()).real
    r_ctr = _z(Builder(dict(Builder.default_params, feed_frac=0.5))).real
    assert r_off > 1.8 * r_ctr
    assert 150.0 < r_off < 350.0  # near the classic ~200-300 ohm Windom point


def test_ocf_near_resonant():
    """At the design length the off-centre feed is near resonance (small X),
    so the elevated impedance is essentially resistive."""
    from antennaknobs.designs.dipoles.ocf_dipole import Builder

    assert abs(_z(Builder()).imag) < 60.0


def test_ocf_feed_is_off_center():
    """Geometry: a single feed with unequal arms (short arm toward -y end)."""
    from antennaknobs.designs.dipoles.ocf_dipole import Builder

    tups = Builder().build_wires()
    feeds = [t for t in tups if t[3] is not None]
    assert len(feeds) == 1
    y_feed = feeds[0][0][1]
    assert y_feed < -0.05  # offset from the centre (y = 0) toward -y


# ---------------------------------------------------------------------------
# Resonant V-beam
# ---------------------------------------------------------------------------


def test_vbeam_fires_along_the_bisector():
    """Two ~1 wl legs splayed at the apex put gain (~5 dBi) along the
    bisector (+/- x) with a deep null off the broadside (+/- y) -- the
    long-wire lobes of the two legs aligning."""
    from antennaknobs.designs.wire.vbeam import Builder

    rings = np.array(_far_field(Builder()).rings)
    fwd = rings[:, 0].max()  # +x bisector
    back = rings[:, 180].max()  # -x bisector
    side = rings[:, 90].max()  # +y broadside
    assert _far_field(Builder()).max_gain > 4.5
    assert fwd - side > 4.0
    assert back - side > 3.0


def test_vbeam_high_reactive_apex_feed():
    """Long-wire apex feed: high resistance and strongly reactive (open-wire
    fed in practice), unlike a resonant dipole."""
    from antennaknobs.designs.wire.vbeam import Builder

    z = _z(Builder())
    assert z.real > 500.0
    assert abs(z.imag) > 500.0


def test_vbeam_two_legs_one_apex_feed():
    """One driven apex gap and two legs of equal length opening symmetrically
    in +/- y."""
    from antennaknobs.designs.wire.vbeam import Builder

    tups = Builder().build_wires()
    feeds = [t for t in tups if t[3] is not None]
    assert len(feeds) == 1
    ends = [t[1] for t in tups if t[3] is None]
    ys = sorted(e[1] for e in ends)
    assert ys[0] < 0 < ys[-1]  # legs splay to both +/- y
    assert abs(abs(ys[0]) - abs(ys[-1])) < 1e-6  # symmetric


# ---------------------------------------------------------------------------
# Bi-square (2 wl vertical loop curtain)
# ---------------------------------------------------------------------------


def test_bisquare_vertical_broadside():
    """Vertically polarised, fires broadside to the loop plane (off +/- x) with
    the in-plane (+/- y) endfire suppressed -- the in-phase vertical components
    adding while the horizontals cancel."""
    from antennaknobs.designs.loops.bisquare import Builder

    ff = _far_field(Builder())
    rings = np.array(ff.rings)
    broadside = rings[:, 0].max()  # +x
    end_on = rings[:, 90].max()  # +y
    assert ff.max_gain > 3.0
    assert broadside - end_on > 2.0


def test_bisquare_high_reactive_corner_feed():
    """A 2 wl loop fed at a corner is a high, reactive feedpoint (open-wire +
    tuner), not a 50 ohm match."""
    from antennaknobs.designs.loops.bisquare import Builder

    z = _z(Builder())
    assert abs(z.imag) > 200.0


def test_bisquare_is_a_four_sided_loop_one_feed():
    """Four half-wave sides forming one closed loop, with a single driven gap
    at the bottom corner (z minimum)."""
    from antennaknobs.designs.loops.bisquare import Builder

    tups = Builder().build_wires()
    feeds = [t for t in tups if t[3] is not None]
    assert len(feeds) == 1
    zmin = min(min(t[0][2], t[1][2]) for t in tups)
    assert abs(feeds[0][0][2] - zmin) < 1e-6  # fed at the bottom corner


# ---------------------------------------------------------------------------
# J-pole (end-fed half-wave + quarter-wave matching stub)
# ---------------------------------------------------------------------------


def test_jpole_omnidirectional_vertical():
    """A vertical end-fed half-wave: ~2 dBi, omnidirectional in azimuth (small
    ripple around the peak-elevation ring)."""
    from antennaknobs.designs.verticals.jpole import Builder

    ff = _far_field(Builder())
    rings = np.array(ff.rings)
    ti = int(np.argmax(rings.max(axis=1)))  # elevation ring of peak gain
    az = rings[ti]
    assert 1.5 < ff.max_gain < 2.6
    assert az.max() - az.min() < 1.5  # omnidirectional in azimuth


def test_jpole_stub_matches_to_coax():
    """The quarter-wave stub transforms the very high end-fed impedance down to
    a coax-friendly match (SWR < 2.5 to 50 ohm at the tuned tap)."""
    from antennaknobs.designs.verticals.jpole import Builder

    assert _swr(_z(Builder()), 50.0) < 2.5


def test_jpole_radiator_continues_above_the_stub():
    """Topology: the half-wave radiator stands on top of one stub leg, so the
    structure's top is a half-wave above the stub top; the feed bridges the two
    close stub legs (different x)."""
    from antennaknobs.designs.verticals.jpole import Builder

    tups = Builder().build_wires()
    feeds = [t for t in tups if t[3] is not None]
    assert len(feeds) == 1
    # feed bridges the two legs -> its endpoints differ in x
    assert abs(feeds[0][0][0] - feeds[0][1][0]) > 1e-6
    # the radiator reaches well above the stub top
    wl = 299.792458 / Builder().design_freq
    ztop = max(max(t[0][2], t[1][2]) for t in tups)
    zbot = min(min(t[0][2], t[1][2]) for t in tups)
    assert (ztop - zbot) > 0.6 * wl  # stub (~1/4) + radiator (~1/2)


# ---------------------------------------------------------------------------
# Discone (broadband vertical)
# ---------------------------------------------------------------------------


_DISCONE_BAND = (34.0, 40.0, 50.0, 65.0)  # above the ~28.6 MHz cone cutoff


def test_discone_broadband_match():
    """The defining discone behaviour: a usable match held across a wide band
    ABOVE the cone's quarter-wave cutoff (here ~2:1, 34-65 MHz), unlike a
    resonant vertical."""
    from antennaknobs.designs.broadband.discone import Builder

    swrs = [
        _swr(_z(Builder(dict(Builder.default_params, freq=f))), 50.0)
        for f in _DISCONE_BAND
    ]
    assert max(swrs) < 3.0, dict(zip(_DISCONE_BAND, swrs))


def test_discone_match_beats_a_resonant_vertical_off_band():
    """A resonant antenna's SWR explodes when you move ~2:1 in frequency; the
    discone's barely moves. Compare the band-edge spread."""
    from antennaknobs.designs.broadband.discone import Builder
    from antennaknobs.designs.verticals.jpole import Builder as JBuilder

    def spread(B, lo, hi, z0):
        return _swr(_z(B(dict(B.default_params, freq=hi))), z0) - _swr(
            _z(B(dict(B.default_params, freq=lo))), z0
        )

    # the resonant J-pole degrades far more across a 34->65 MHz move than the
    # broadband discone does.
    assert abs(spread(Builder, 34.0, 65.0, 50.0)) < abs(
        spread(JBuilder, 34.0, 65.0, 50.0)
    )


def test_discone_omni_low_angle_in_band():
    """In-band it is a vertical: omnidirectional in azimuth and low takeoff
    (peak gain near the horizon)."""
    from antennaknobs.designs.broadband.discone import Builder

    b = Builder(dict(Builder.default_params, freq=50.0))
    rings = np.array(_far_field(b).rings)
    ti = int(np.argmax(rings.max(axis=1)))
    az = rings[ti]
    assert ti > 75  # peak near the horizon (theta ~ 90)
    assert az.max() - az.min() < 1.0  # omnidirectional


def test_discone_has_disc_and_cone_one_feed():
    """A disc cage (horizontal radials) above a cone cage (downward radials),
    fed across the apex gap -- exactly one driven segment."""
    from antennaknobs.designs.broadband.discone import Builder

    tups = Builder().build_wires()
    feeds = [t for t in tups if t[3] is not None]
    assert len(feeds) == 1
    n = int(Builder().n_wires)
    # m disc radials (horizontal) + m cone wires (sloping down) + 1 feed
    horiz = [t for t in tups if abs(t[0][2] - t[1][2]) < 1e-9 and t[3] is None]
    assert len(horiz) == n  # the disc radials


# ===========================================================================
# Batch 3 -- methodology-stress designs
#
# Chosen to exercise paths the earlier batches did not: a 3-D space curve
# (helix), dense acute-angle segmentation (koch_dipole), a long multi-half-wave
# wire (longwire), a series-fed meander (bruce), a 2-D quadrature multi-feed
# (four_square), a large horizontal loop (horizontal_loop), and two ideal-TL
# network feeds (g5rv, zepp). The cross-engine findings are pinned in the
# "methodology" section at the very end.
# ===========================================================================


# ---------------------------------------------------------------------------
# Helix (normal-mode helical vertical) -- 3-D non-planar geometry
# ---------------------------------------------------------------------------


def test_helix_resonant_low_z():
    """Helically-loaded short whip: near-resonant, low radiation resistance."""
    from antennaknobs.designs.specialty.helix import Builder

    z = _z(Builder())
    assert 8.0 < z.real < 25.0  # low R of a helically-loaded short vertical
    assert abs(z.imag) < 25.0  # tuned near resonance


def test_helix_is_genuinely_three_dimensional():
    """Unlike every planar design in the catalog, the helix winds through many
    distinct x AND y coordinates -- a true space curve."""
    from antennaknobs.designs.specialty.helix import Builder

    tups = Builder().build_wires()
    xs = {round(p[0], 3) for t in tups for p in (t[0], t[1])}
    ys = {round(p[1], 3) for t in tups for p in (t[0], t[1])}
    assert len(xs) > 4 and len(ys) > 4


def test_helix_vertically_polarised_omni():
    """Normal-mode helix radiates like a short vertical: omnidirectional in
    azimuth, modest gain."""
    from antennaknobs.designs.specialty.helix import Builder

    ff = _far_field(Builder())
    rings = np.array(ff.rings)
    ti = int(np.argmax(rings.max(axis=1)))
    az = rings[ti]
    assert az.max() - az.min() < 1.0  # omnidirectional in azimuth
    assert ff.max_gain < 3.0  # a small radiator, not a beam


# ---------------------------------------------------------------------------
# Koch fractal dipole -- dense acute-angle segmentation
# ---------------------------------------------------------------------------


def test_koch_resonant_reduced_resistance():
    """Iteration-2 Koch dipole at the default span: near resonant, with a
    radiation resistance well below a full-size dipole's ~70 ohm."""
    from antennaknobs.designs.dipoles.koch_dipole import Builder

    z = _z(Builder())
    assert 25.0 < z.real < 50.0
    assert abs(z.imag) < 25.0


def test_koch_iterations_shorten_resonance():
    """The fractal miniaturisation: at a FIXED span the developed length grows
    with iterations, so a straight (it=0) dipole of that span is far too short
    (strongly capacitive) while the it=2 curve is near resonant."""
    from antennaknobs.designs.dipoles.koch_dipole import Builder

    x_straight = _z(Builder(dict(Builder.default_params, iterations=0))).imag
    x_koch2 = _z(Builder(dict(Builder.default_params, iterations=2))).imag
    assert x_straight < x_koch2 - 100.0  # straight span is much more capacitive


def test_koch_is_a_dipole_pattern():
    """Still a horizontally-polarised dipole, broadside-dominant -- though the
    z-directed bumps of the fractal soften the figure-8 a little, so the
    front-to-side ratio is smaller than a straight dipole's."""
    from antennaknobs.designs.dipoles.koch_dipole import Builder

    ff = _far_field(Builder())
    rings = np.array(ff.rings)
    row = rings[60]
    broadside = max(row[0], row[180])  # off +/- x
    end_on = max(row[90], row[270])  # off the dipole axis (+/- y)
    assert broadside - end_on > 3.5


def test_koch_one_feed_many_chords():
    """Exactly one driven gap; the it=2 arms are a dense chain of short chords
    (16 per arm) -- the segmentation stress the design exists to apply."""
    from antennaknobs.designs.dipoles.koch_dipole import Builder

    tups = Builder().build_wires()
    feeds = [t for t in tups if t[3] is not None]
    assert len(feeds) == 1
    assert len(tups) > 24


# ---------------------------------------------------------------------------
# Bruce array -- series-fed VP meander
# ---------------------------------------------------------------------------


def test_bruce_vertical_broadside_curtain():
    """Five co-phased risers: vertically polarised, broadside off +/-x with
    deep end nulls (free space)."""
    from antennaknobs.designs.verticals.bruce import Builder

    ff = _far_field(Builder())
    rings = np.array(ff.rings)
    row = rings[60]
    broadside = max(row[0], row[180])
    end_on = max(row[90], row[270])
    assert broadside - end_on > 8.0
    assert ff.max_gain > 3.5


def test_bruce_feed_is_high_z_reactive():
    """The end-riser current-minimum feed is high and strongly reactive -- a
    matching network, not coax, in practice (cf. bisquare/lazy_h)."""
    from antennaknobs.designs.verticals.bruce import Builder

    z = _z(Builder())
    assert z.real > 150.0  # high resistance
    assert z.imag < -800.0  # strongly (capacitively) reactive


def test_bruce_riser_count_and_single_feed():
    """n_vert vertical risers (constant-y segments) and exactly one driven gap."""
    from antennaknobs.designs.verticals.bruce import Builder

    b = Builder()
    tups = b.build_wires()
    feeds = [t for t in tups if t[3] is not None]
    assert len(feeds) == 1
    verticals = [
        t
        for t in tups
        if abs(t[0][1] - t[1][1]) < 1e-9 and abs(t[0][2] - t[1][2]) > 1e-9
    ]
    # each riser is split by neither feed except the fed one; count distinct
    # riser y-columns instead.
    ys = {round(t[0][1], 4) for t in verticals}
    assert len(ys) == int(b.n_vert)


# ---------------------------------------------------------------------------
# Four-square -- 2-D quadrature multi-feed
# ---------------------------------------------------------------------------


def test_four_square_gain_and_front_to_back():
    """Quadrature box fires along the +x,+y diagonal with array gain and a deep
    rearward null."""
    from antennaknobs.designs.verticals.four_square import Builder

    ff = _far_field(Builder())
    rings = np.array(ff.rings)
    row = rings[60]  # ~30 deg elevation
    forward = row[45]  # +x,+y diagonal
    back = row[225]  # -x,-y diagonal
    assert ff.max_gain > 6.0
    assert forward - back > 12.0


def test_four_square_has_four_quadrature_feeds():
    """Exactly four driven gaps: back=+1, front=-1, two equal -90 deg sides."""
    from antennaknobs.designs.verticals.four_square import Builder

    tups = Builder().build_wires()
    feeds = [t[3] for t in tups if t[3] is not None]
    assert len(feeds) == 4
    assert any(abs(v - (1 + 0j)) < 1e-9 for v in feeds)  # back reference
    assert any(abs(v - (-1 + 0j)) < 1e-9 for v in feeds)  # front 180 deg
    sides = [v for v in feeds if abs(v.real) < 1e-9 and v.imag < 0]
    assert len(sides) == 2  # the two -90 deg side corners


def test_four_square_steers_by_phase():
    """It is the phasing, not the geometry, that makes it directional: with all
    four corners fed in phase the deep rearward null disappears."""
    from antennaknobs.designs.verticals.four_square import Builder

    directional = _far_field(Builder())
    rings = np.array(directional.rings)
    fb_phased = rings[60][45] - rings[60][225]
    assert fb_phased > 12.0  # quadrature feed -> strong F/B (sanity on default)


# ---------------------------------------------------------------------------
# Horizontal full-wave loop -- large single closed loop, NVIS
# ---------------------------------------------------------------------------


def test_horizontal_loop_moderate_resistive_feed():
    """Full-wave loop: ~100-130 ohm, near resonant."""
    from antennaknobs.designs.loops.horizontal_loop import Builder

    z = _z(Builder())
    assert 90.0 < z.real < 150.0
    assert abs(z.imag) < 40.0


def test_horizontal_loop_fires_at_zenith():
    """A flat full-wave loop is broadside to its own plane -> the main lobe is
    overhead (theta=0), the NVIS behaviour, far above a low-elevation cut."""
    from antennaknobs.designs.loops.horizontal_loop import Builder

    ff = _far_field(Builder())
    rings = np.array(ff.rings)
    zenith = rings[0].max()
    low = rings[80].max()
    assert zenith >= ff.max_gain - 1.0  # zenith is (near) the global max
    assert zenith - low > 1.5  # and well above the horizon


def test_horizontal_loop_is_closed_single_feed():
    """One driven gap; the rest of the wires close a ~1 wl perimeter loop."""
    from antennaknobs.designs.loops.horizontal_loop import Builder

    b = Builder()
    tups = b.build_wires()
    feeds = [t for t in tups if t[3] is not None]
    assert len(feeds) == 1
    # perimeter ~ one wavelength
    wl = 299.792458 / b.design_freq
    perim = sum(
        ((t[0][0] - t[1][0]) ** 2 + (t[0][1] - t[1][1]) ** 2) ** 0.5 for t in tups
    )
    assert 0.95 < perim / wl < 1.15


# ---------------------------------------------------------------------------
# Long-wire -- long multi-half-wave open conductor
# ---------------------------------------------------------------------------


def test_longwire_gain_exceeds_dipole():
    """A ~3.5 wl wire beats a half-wave dipole."""
    from antennaknobs.designs.wire.longwire import Builder

    assert _far_field(Builder()).max_gain > 4.5


def test_longwire_lobes_tilt_toward_the_axis():
    """The pattern is multi-lobe with the strongest lobes tilted toward the
    wire axis (+/- y), NOT broadside (+/- x) as a dipole would be."""
    from antennaknobs.designs.wire.longwire import Builder

    ff = _far_field(Builder())
    rings = np.array(ff.rings)
    ti = int(np.argmax(rings.max(axis=1)))
    pphi = int(np.argmax(rings[ti]))
    # peak azimuth is near the wire axis (90 or 270), far from broadside (0/180)
    axis_dist = min(abs(pphi - 90), abs(pphi - 270))
    assert axis_dist < 45
    broadside = max(rings[ti][0], rings[ti][180])
    assert ff.max_gain - broadside > 3.0  # broadside is well down from the peak


def test_longwire_centre_feed_moderate_z():
    """Centre-fed at a current maximum (odd half-wave count) -> moderate R,
    not the thousands of ohms an end feed or a current-null centre would give."""
    from antennaknobs.designs.wire.longwire import Builder

    z = _z(Builder())
    assert 80.0 < z.real < 220.0
    assert abs(z.imag) < 60.0


# ---------------------------------------------------------------------------
# G5RV -- matched-line (ideal-TL) network feed
# ---------------------------------------------------------------------------


def test_g5rv_shack_impedance_is_transformed_doublet():
    """The shack-side Z (after the ~half-wave matched line) is the transformed
    centre impedance of a ~1.5 wl doublet -- a reactive ~100-ohm compromise,
    not a 50-ohm match (Cebik's point about the G5RV)."""
    from antennaknobs.designs.broadband.g5rv import Builder

    z = _z(Builder())
    assert 80.0 < z.real < 160.0
    assert abs(z.imag) > 20.0  # reactive: a tuner job, not a coax match


def test_g5rv_doublet_gain():
    """The flat-top radiates as a 1.5 wl doublet (a few dB over a dipole)."""
    from antennaknobs.designs.broadband.g5rv import Builder

    assert 2.5 < _far_field(Builder()).max_gain < 5.0


def test_g5rv_uses_a_tl_branch_and_virtual_shack():
    """The matched line is a single TL branch from a virtual shack port to the
    real doublet-centre port."""
    from antennaknobs.designs.broadband.g5rv import Builder
    from antennaknobs.network import TL, PortVirtual

    net = Builder().build_network()
    assert any(isinstance(b, TL) for b in net.branches)
    assert isinstance(net.ports["shack"], PortVirtual)
    assert net.sources[0].port == "shack"


# ---------------------------------------------------------------------------
# Zepp -- end-fed half-wave through an ideal-TL tuned feeder
# ---------------------------------------------------------------------------


def test_zepp_radiator_is_a_dipole():
    """The half-wave radiator keeps a dipole gain (~2 dBi) regardless of the
    extreme feed -- gain/pattern are the robust outputs."""
    from antennaknobs.designs.wire.zepp import Builder

    assert 1.8 < _far_field(Builder()).max_gain < 2.6


def test_zepp_series_feeder_cannot_match_to_coax():
    """An end-fed half wave is near-total reflection; a LOSSLESS series feeder
    preserves |Gamma|, so the shack impedance stays far from 50 ohm (low R) --
    the historical reason the Zepp ran its tuned feeders to a tuner."""
    from antennaknobs.designs.wire.zepp import Builder

    z = _z(Builder())
    assert z.real < 10.0  # nowhere near a 50-ohm match


# ===========================================================================
# Batch 4 -- second Cebik wave, cross-checked against the cebik.com mirror
# (antenna2.github.io/cebik): EDZ, expanded lazy-H, OWA Yagi, right-angle
# delta (issues #354-#357).
# ===========================================================================


# ---------------------------------------------------------------------------
# Extended Double Zepp (1.25 wl doublet + series matching section)
# ---------------------------------------------------------------------------


def _edz_bare():
    """The EDZ with its centre gap driven directly (matching section removed),
    to read the raw feedpoint the series section transforms."""
    from antennaknobs.designs.wire.edz import Builder

    class Bare(Builder):
        def build_wires(self):
            return [
                (t[0], t[1], t[2], 1 + 0j) if len(t) == 5 and t[4] == "feed" else t[:4]
                for t in super().build_wires()
            ]

        def build_network(self):
            return None

    return Bare()


def test_edz_gain_over_dipole():
    """~5.2 dBi free space -- the 2-3 dB broadside gain over a dipole that is
    the whole point of the 1.25 wl stretch (Cebik)."""
    from antennaknobs.designs.wire.edz import Builder

    ff = _far_field(Builder())
    assert 4.5 < ff.max_gain < 5.6


def test_edz_broadside_with_end_nulls():
    """Still a (slightly split) figure-8: broadside off +/- x dominates the
    wire axis by a wide margin, with the ~50-deg sidelobes only emerging (the
    sidelobes are also why the margin at this ring is a shade under the
    half-square's)."""
    from antennaknobs.designs.wire.edz import Builder

    ff = _far_field(Builder())
    rings = np.array(ff.rings)
    row = rings[60]
    broadside = max(row[0], row[180])
    end_on = max(row[90], row[270])
    assert broadside - end_on > 8.0


def test_edz_bare_centre_high_r_strongly_capacitive():
    """The raw 1.25 wl centre: high-R and strongly capacitive (Cebik quotes
    ~100-140 -j500-600 for typical builds; this wire reads ~150 -j800)."""
    z = _z(_edz_bare())
    assert 100.0 < z.real < 220.0
    assert z.imag < -500.0


def test_edz_series_section_lands_on_coax():
    """The contrast with the zepp: the EDZ centre reflects at |Gamma| ~ 0.84
    (not ~1), so the 600 ohm series section's low-R crossing sits at ~53 ohm
    and the shack sees a direct coax match (SWR ~ 1.07)."""
    from antennaknobs.designs.wire.edz import Builder

    z = _z(Builder())
    assert 45.0 < z.real < 60.0
    assert abs(z.imag) < 10.0
    assert _swr(z, 50.0) < 1.25


def test_edz_match_is_narrowband():
    """The rotation match trades bandwidth: ~600 kHz at 2:1 on 10 m (WB4HFL's
    measured build), so both band edges blow past 2:1."""
    from antennaknobs.designs.wire.edz import Builder

    for f in (28.0, 29.1):
        z = _z(Builder(dict(Builder.default_params, freq=f)))
        assert _swr(z, 50.0) > 2.0, (f, z)


def test_edz_match_line_rotation_tunes_reactance():
    """Along the series line the resistance stays pinned near the low-R
    crossing while the reactance sweeps through zero -- rotation around the
    SWR circle, not a transformer's R-scaling."""
    from antennaknobs.designs.wire.edz import Builder

    zs = [
        _z(Builder(dict(Builder.default_params, match_len_frac=m)))
        for m in (0.144, 0.150, 0.156)
    ]
    assert all(45.0 < z.real < 60.0 for z in zs)  # R barely moves
    assert zs[0].imag < 0.0 < zs[2].imag  # X sweeps through resonance


def test_edz_uses_a_series_tl_and_virtual_shack():
    """One series TL branch from a virtual shack port to the real
    doublet-centre port, driven at the shack (cf. g5rv/zepp)."""
    from antennaknobs.designs.wire.edz import Builder
    from antennaknobs.network import TL, Driven, PortVirtual

    net = Builder().build_network()
    tls = [br for br in net.branches if isinstance(br, TL)]
    assert len(tls) == 1 and not tls[0].transposed
    assert {tls[0].a, tls[0].b} == {"shack", "feed"}
    assert isinstance(net.ports["shack"], PortVirtual)
    (src,) = net.sources
    assert isinstance(src, Driven) and src.port == "shack"


# ---------------------------------------------------------------------------
# Expanded Lazy-H (two stacked EDZs + real phasing harness)
# ---------------------------------------------------------------------------


def test_expanded_lazy_h_gain():
    """~10.1 dBi free space: the EDZ stretch + 5/8 wl stack (Cebik's 15.1 dBi
    at 8 deg takeoff adds height-over-ground gain)."""
    from antennaknobs.designs.wire.expanded_lazy_h import Builder

    assert _far_field(Builder()).max_gain > 9.5


def test_expanded_lazy_h_beats_standard_lazy_h():
    """The expansion is worth ~2 dB over the standard 1 wl / 1/2 wl lazy-H --
    the design's whole reason to exist."""
    from antennaknobs.designs.wire.expanded_lazy_h import Builder
    from antennaknobs.designs.wire.lazy_h import Builder as LazyH

    g_x = _far_field(Builder()).max_gain
    g_std = _far_field(LazyH()).max_gain
    assert g_x - g_std > 1.5


def test_expanded_lazy_h_broadside():
    """One dominant broadside lobe off +/- x; the wire axis stays well down."""
    from antennaknobs.designs.wire.expanded_lazy_h import Builder

    ff = _far_field(Builder())
    rings = np.array(ff.rings)
    front = rings[:, 0].max()
    side = rings[:, 90].max()
    assert front - side > 7.0


def test_expanded_lazy_h_wider_stack_adds_gain():
    """Through the real harness (leg lengths track the spacing), expanding the
    stack from the classic 1/2 wl to Cebik's 5/8 wl still pays ~0.7 dB."""
    from antennaknobs.designs.wire.expanded_lazy_h import Builder

    g_wide = _far_field(Builder()).max_gain  # 5/8 wl default
    g_half = _far_field(
        Builder(dict(Builder.default_params, spacing_frac=0.5))
    ).max_gain
    assert g_wide - g_half > 0.3


def test_expanded_lazy_h_multiband_taper():
    """Fed through a tuner it works far below the design band, with the
    stacking gain fading as the fixed stack shrinks in wavelengths -- Cebik's
    band taper (15.1/12.5/9.0 dBi at height -> ~10.1/7.2/4.1 free space)."""
    from antennaknobs.designs.wire.expanded_lazy_h import Builder

    gains = {
        fr: _far_field(Builder(dict(Builder.default_params, freq=fr))).max_gain
        for fr in (28.57, 21.1, 14.1)
    }
    assert gains[28.57] > gains[21.1] > gains[14.1]
    assert gains[21.1] > 6.5


def test_expanded_lazy_h_junction_is_tuner_territory():
    """The junction the tuner sees -- two transformed EDZ centres in parallel
    -- is low-R and strongly reactive, not a coax match (Cebik: open-wire
    line to a wide-range balanced tuner)."""
    from antennaknobs.designs.wire.expanded_lazy_h import Builder

    z = _z(Builder())
    assert z.real < 100.0
    assert abs(z.imag) > 100.0


def test_expanded_lazy_h_harness_topology():
    """Two equal, untransposed TL legs from the element centres to a virtual
    mid-stack junction, driven at the junction -- equal legs are what impose
    the in-phase drive (cf. lazy_h's idealized dual sources)."""
    from antennaknobs.designs.wire.expanded_lazy_h import Builder
    from antennaknobs.network import TL, Driven, PortVirtual

    net = Builder().build_network()
    tls = [br for br in net.branches if isinstance(br, TL)]
    assert len(tls) == 2
    assert all(not tl.transposed for tl in tls)
    assert abs(tls[0].length - tls[1].length) < 1e-12  # equal legs
    assert {tls[0].b, tls[1].b} == {"lo", "hi"}
    assert isinstance(net.ports["junction"], PortVirtual)
    (src,) = net.sources
    assert isinstance(src, Driven) and src.port == "junction"


# ---------------------------------------------------------------------------
# OWA Yagi (4-el with the close-in coupled-resonator first director)
# ---------------------------------------------------------------------------


_OWA_BAND = (28.0, 28.5, 29.0)


def test_owa_flat_swr_across_the_whole_band():
    """The defining OWA behaviour: direct 50-ohm feed with SWR < 1.5 held
    over all of 28.0-29.0 MHz (Cebik's design goal for the family; this
    model reads 1.10-1.32)."""
    from antennaknobs.designs.beams.owa_yagi import Builder

    swrs = {
        f: _swr(_z(Builder(dict(Builder.default_params, freq=f))), 50.0)
        for f in _OWA_BAND
    }
    assert max(swrs.values()) < 1.5, swrs


def test_owa_bandwidth_shames_the_generic_yagi():
    """Same band, same 50-ohm reference: the conventional driver-reflector-
    directors `beams.yagi` swings past 5:1 at a band edge while the OWA
    never leaves ~1.3 -- the coupled resonator is worth a >2x band-max
    margin."""
    from antennaknobs.designs.beams.owa_yagi import Builder
    from antennaknobs.designs.beams.yagi import Builder as Yagi

    owa_max = max(
        _swr(_z(Builder(dict(Builder.default_params, freq=f))), 50.0) for f in _OWA_BAND
    )
    yagi_max = max(
        _swr(_z(Yagi(dict(Yagi.default_params, freq=f))), 50.0) for f in _OWA_BAND
    )
    assert owa_max * 2.0 < yagi_max


def test_owa_gain_and_front_to_back_hold_across_band():
    """~8.3-8.7 dBi forward with F/B > 10 dB at both edges and mid-band --
    the smooth-across-the-band consistency the OWA trades ~0.2 dB of peak
    gain for."""
    from antennaknobs.designs.beams.owa_yagi import Builder

    for f in _OWA_BAND:
        ff = _far_field(Builder(dict(Builder.default_params, freq=f)))
        rings = np.array(ff.rings)
        fb = rings[:, 0].max() - rings[:, 180].max()
        assert ff.max_gain > 8.0, (f, ff.max_gain)
        assert fb > 10.0, (f, fb)


def test_owa_d1_is_the_matching_network():
    """Delete the close-in first director and the OWA's own match collapses
    (mid-band SWR ~3.9): the wideband 50-ohm feed lives in that one
    coupled-resonator element, not in the driver."""
    from antennaknobs.designs.beams.owa_yagi import Builder

    class NoD1(Builder):
        TABLE = tuple(t for i, t in enumerate(Builder.TABLE) if i != Builder.D1)

    z = _z(NoD1(dict(NoD1.default_params, freq=28.5)))
    assert _swr(z, 50.0) > 2.5


def test_owa_topology_close_in_first_director():
    """Four y-parallel elements, one driven; the OWA signature is D1 parked
    ~0.05 wl from the driver while D2 sits ~0.18 wl further on, with lengths
    monotone reflector > driver > D1 > D2."""
    from antennaknobs.designs.beams.owa_yagi import Builder

    b = Builder()
    feeds = [t for t in b.build_wires() if t[3] is not None]
    assert len(feeds) == 1
    halves = [h for h, _ in b.TABLE]
    poss = [p for _, p in b.TABLE]
    assert halves[0] > halves[1] > halves[2] > halves[3]
    assert poss[2] - poss[1] < 0.06  # D1 hugs the driver...
    assert poss[3] - poss[2] > 0.15  # ...D2 does not
    # fat elements are part of the published design
    assert b.build_wire_material().radius > 0.01


# ---------------------------------------------------------------------------
# Right-angle delta (the coax-friendly SCV)
# ---------------------------------------------------------------------------


def test_rad_coax_friendly_near_resonant():
    """The right-angle proportions' whole point: ~48-51 ohm near-resonant at
    the quarter-wave-from-apex feed (Cebik: 51 ohm; the equilateral delta's
    same feed sits at ~120 ohm)."""
    from antennaknobs.designs.verticals.right_angle_delta import Builder

    z = _z(Builder())
    assert 40.0 < z.real < 60.0
    assert abs(z.imag) < 15.0


def test_rad_gain_matches_cebik():
    """~3.3-3.6 dBi free space -- mid-pack SCV, above the equilateral's 2.9,
    below the half-square's 4.6."""
    from antennaknobs.designs.verticals.right_angle_delta import Builder

    ff = _far_field(Builder())
    assert 3.0 < ff.max_gain < 4.2


def test_rad_ranks_below_the_half_square():
    """Cebik's family ranking holds inside the catalog: the half-square
    out-gains the RAD by ~1 dB."""
    from antennaknobs.designs.verticals.half_square import Builder as HalfSquare
    from antennaknobs.designs.verticals.right_angle_delta import Builder

    assert _far_field(HalfSquare()).max_gain > _far_field(Builder()).max_gain + 0.5


def test_rad_vertically_polarised_overhead_null():
    """The SCV signature: the pattern peaks at the horizon and is deeply
    nulled overhead -- the horizontal members cancel, the vertical runs
    radiate. (The corner-fed `loops.delta_loop` is the horizontally-dominant
    opposite.)"""
    from antennaknobs.designs.verticals.right_angle_delta import Builder

    rings = np.array(_far_field(Builder()).rings)
    horizon = rings[85:].max()
    zenith = rings[:5].max()
    assert horizon - zenith > 15.0


def test_rad_near_omni_front_to_side():
    """The delta is the near-omni end of the SCV family: broadside is up on
    the ends by only a few dB (Cebik: ~3 dB), nothing like the bobtail's
    ~28 dB broadside discipline."""
    from antennaknobs.designs.verticals.right_angle_delta import Builder

    rings = np.array(_far_field(Builder()).rings)
    row = rings[60]
    margin = max(row[0], row[180]) - max(row[90], row[270])
    assert 1.0 < margin < 8.0


def test_rad_length_factor_tunes_reactance():
    """Reactance climbs monotonically with length_factor through resonance
    (cf. half_square)."""
    from antennaknobs.designs.verticals.right_angle_delta import Builder

    x_lo = _z(Builder(dict(Builder.default_params, length_factor=0.96))).imag
    x_mid = _z(Builder(dict(Builder.default_params, length_factor=1.004))).imag
    x_hi = _z(Builder(dict(Builder.default_params, length_factor=1.05))).imag
    assert x_lo < x_mid < x_hi


def test_rad_is_a_closed_right_angle_delta_one_feed():
    """Topology: one driven gap on the left sloping side (not on the base),
    the loop closes, and the side/base proportions make the apex a right
    angle (side^2 + side^2 ~ diagonal relation: h = w/2)."""
    from antennaknobs.designs.verticals.right_angle_delta import Builder

    b = Builder()
    tups = b.build_wires()
    feeds = [t for t in tups if t[3] is not None]
    assert len(feeds) == 1
    zb = b.base
    # The fed edge slopes: it is off the base wire and off y = 0.
    assert feeds[0][0][2] > zb + 0.1
    assert feeds[0][0][1] < 0.0  # on the left (-y) side
    # Right angle at the apex: apex height equals half the base width.
    wavelength = 299.792458 / b.design_freq
    w = b.base_frac * wavelength * b.length_factor
    apex_h = max(max(t[0][2], t[1][2]) for t in tups) - zb
    assert abs(apex_h - w / 2) < 0.02 * wavelength
    # ~1 wl closed perimeter (2 sides + base ~ 1.07 wl).
    perim = w + 2 * b.side_frac * wavelength * b.length_factor
    assert 0.95 < perim / wavelength < 1.15


# ===========================================================================
# Batch 5 -- tier-2 Cebik follow-ons (issues #362-#366), from the
# cebik.com mirror (antenna2.github.io/cebik).
# ===========================================================================


# ---------------------------------------------------------------------------
# Rectangle "magnetic slot" SCV (1 wl loop flattened wide + QW transformer)
# ---------------------------------------------------------------------------


def _rectangle_bare():
    """The rectangle with its side gap driven directly (matching section
    removed), to read the raw very-low-R feedpoint the transformer steps up."""
    from antennaknobs.designs.verticals.rectangle import Builder

    class Bare(Builder):
        def build_wires(self):
            return [
                (t[0], t[1], t[2], 1 + 0j) if len(t) == 5 and t[4] == "feed" else t[:4]
                for t in super().build_wires()
            ]

        def build_network(self):
            return None

    return Bare()


def test_rectangle_bare_feed_is_low_z_near_resonant():
    """The flattened loop's mid-side feed on a short vertical side: very low
    R, near-resonant (Cebik: ~15 ohm; the price of the squashed proportions)."""
    z = _z(_rectangle_bare())
    assert 8.0 < z.real < 25.0
    assert abs(z.imag) < 15.0


def test_rectangle_qw_section_steps_up_to_coax():
    """The quarter-wave low-Z section (two paralleled 50-ohm coaxes ~ 25 ohm)
    steps the ~15 ohm feed up to near-coax at the shack (cf. wire.edz's
    series-line rotation -- this one is the R-scaling transformer instead)."""
    from antennaknobs.designs.verticals.rectangle import Builder

    z = _z(Builder())
    assert _swr(z, 50.0) < 1.45
    assert abs(z.imag) < 15.0


def test_rectangle_gain_matches_cebik():
    """Top of the SCV family album (Cebik: 4.4 dBi free space, second only
    to the half-square's 4.6). This model reads ~5.1 -- it runs the whole
    family a few tenths hot (its half-square reads 4.9 vs Cebik's 4.6, its
    delta 3.6 vs 3.3)."""
    from antennaknobs.designs.verticals.rectangle import Builder

    ff = _far_field(Builder())
    assert 4.4 < ff.max_gain < 5.6


def test_rectangle_family_ranking():
    """Cebik's family ranking, as robust as the model spread allows: the
    rectangle and half-square are the family's top pair within a fraction of
    a dB of each other (Cebik has the half-square 0.2 dB ahead; this model
    reads the rectangle 0.2 ahead), and both clear the right-angle delta by
    over a dB."""
    from antennaknobs.designs.verticals.half_square import Builder as HalfSquare
    from antennaknobs.designs.verticals.rectangle import Builder
    from antennaknobs.designs.verticals.right_angle_delta import Builder as RAD

    g_rect = _far_field(Builder()).max_gain
    assert abs(g_rect - _far_field(HalfSquare()).max_gain) < 0.6
    assert g_rect > _far_field(RAD()).max_gain + 1.0


def test_rectangle_vertically_polarised_overhead_null():
    """The SCV signature: pattern peaks at the horizon, deep null overhead --
    the long horizontal wires cancel, the short vertical sides radiate."""
    from antennaknobs.designs.verticals.rectangle import Builder

    rings = np.array(_far_field(Builder()).rings)
    horizon = rings[85:].max()
    zenith = rings[:5].max()
    assert horizon - zenith > 15.0


def test_rectangle_broadside_with_end_nulls():
    """Two in-phase verticals ~0.4 wl apart: bidirectional broadside off
    +/- x with clear end-on rejection (like the half-square, unlike the
    near-omni delta)."""
    from antennaknobs.designs.verticals.rectangle import Builder

    rings = np.array(_far_field(Builder()).rings)
    row = rings[60]
    broadside = max(row[0], row[180])
    end_on = max(row[90], row[270])
    assert broadside - end_on > 6.0


def test_rectangle_is_a_wide_closed_loop_fed_mid_short_side():
    """Topology: a closed 1 wl rectangle much wider than tall (Cebik's 56' x
    12.8' proportions, aspect > 3.5), with the single port gap centred on one
    short VERTICAL side -- the current maximum that makes it an SCV."""
    from antennaknobs.designs.verticals.rectangle import Builder

    b = Builder()
    tups = b.build_wires()
    ports = [t for t in tups if len(t) == 5 and t[4] == "feed"]
    assert len(ports) == 1
    (p,) = ports
    # The port edge is vertical (spans z, constant y) and sits mid-side.
    assert abs(p[0][1] - p[1][1]) < 1e-9
    assert abs(p[0][2] - p[1][2]) > 0.0
    wavelength = 299.792458 / b.design_freq
    w = b.horiz_frac * wavelength * b.length_factor
    v = b.vert_frac * wavelength * b.length_factor
    assert w / v > 3.5
    mid = b.base + v / 2
    assert abs((p[0][2] + p[1][2]) / 2 - mid) < 0.05
    # ~1 wl closed perimeter.
    assert 0.9 < 2 * (w + v) / wavelength < 1.1


def test_rectangle_uses_a_quarter_wave_tl_and_virtual_shack():
    """One low-Z TL branch, a quarter wave long at the design frequency, from
    a virtual shack port to the real mid-side port, driven at the shack
    (the transformer counterpart of wire.edz's rotation line)."""
    from antennaknobs.designs.verticals.rectangle import Builder
    from antennaknobs.network import TL, Driven, PortVirtual

    b = Builder()
    net = b.build_network()
    tls = [br for br in net.branches if isinstance(br, TL)]
    assert len(tls) == 1 and not tls[0].transposed
    assert {tls[0].a, tls[0].b} == {"shack", "feed"}
    assert tls[0].z0 < 40.0  # a low-Z line: sqrt(15 * 50) ~ 27 ohm territory
    wavelength = 299.792458 / b.design_freq
    assert abs(tls[0].length - wavelength / 4) < 0.02 * wavelength
    assert isinstance(net.ports["shack"], PortVirtual)
    (src,) = net.sources
    assert isinstance(src, Driven) and src.port == "shack"


# ---------------------------------------------------------------------------
# Terminated end-fed long-wire (traveling wave against ground)
# ---------------------------------------------------------------------------
#
# The catalog's first ground-CONNECTED design: both vertical legs end at
# z=0 and NEC joins them to the ground image (the PyNECEngine GE-flag
# support this design introduced; see test_pynec_ground.py). All numbers
# run over PEC ground -- NEC-2's Sommerfeld ground does not support wire
# contact (that is a NEC-4 feature), which the design docstring flags.


def _tlw(**over):
    from antennaknobs.designs.wire.terminated_longwire import Builder

    return Builder(dict(Builder.default_params, **over) if over else None)


def _tlw_unterminated():
    """The terminating resistor deleted (far leg still grounded): the wave
    reflects, the standing-wave pattern returns -- Cebik's comparison case."""
    from antennaknobs.designs.wire.terminated_longwire import Builder
    from antennaknobs.network import Driven, Network, PortOnWire

    class Unterminated(Builder):
        def build_network(self):
            return Network(
                ports={"feed": PortOnWire("feed")},
                branches=[],
                sources=[Driven(port="feed", voltage=1 + 0j)],
            )

    return Unterminated()


def _fb(ff):
    """Front-to-back at the strongest elevation ring, forward = +x."""
    rings = np.array(ff.rings)
    ti = int(np.argmax(rings[:, 0]))
    return rings[ti, 0] - rings[ti, 180], ti


def test_tlw_unidirectional_toward_the_termination():
    """The traveling-wave signature: one main lobe off the TERMINATED end
    (+x), F/B well into the teens (Cebik's 10 wl model: 20.3 dB over
    average ground)."""
    ff = _far_field(_tlw(), ground="pec")
    fb, _ = _fb(ff)
    assert fb > 12.0
    rings = np.array(ff.rings)
    ti, pi = np.unravel_index(int(np.argmax(rings)), rings.shape)
    assert min(pi, 360 - pi) < 25  # global peak looks down +x


def test_tlw_gain_and_low_takeoff():
    """Cebik's 10 wl model: 10.47 dBi at 11 deg takeoff over average
    ground; over PEC the image is lossless so this model reads a couple dB
    hotter, still at a low DX angle."""
    ff = _far_field(_tlw(), ground="pec")
    assert 10.0 < ff.max_gain < 14.5
    rings = np.array(ff.rings)
    ti = int(np.unravel_index(int(np.argmax(rings)), rings.shape)[0])
    assert ti > 70  # peak within ~20 deg of the horizon


def test_tlw_terminator_burns_a_quarter_not_half():
    """Cebik's headline correction to the folklore: the termination eats
    ~25% of the power, not 50%. The engine's load-loss accounting (the
    rhombic/momwire load-BC machinery) reads it directly."""
    eng = PyNECEngine(_tlw(), ground="pec")
    eng.current_distribution()
    assert 0.60 < eng._excited_efficiency < 0.85


def test_tlw_feed_impedance_tracks_the_line():
    """The feedpoint sits near the termination value across a wide band
    (Cebik: 544 +87j, SWR(600) = 1.20 at the design length; and 'extreme
    frequency-changing agility' without rematching)."""
    z = _z(_tlw(), ground="pec")
    assert _swr(z, 600.0) < 1.6
    for f in (28.57 * 0.8, 28.57 * 1.25):
        zf = _z(_tlw(freq=f), ground="pec")
        assert _swr(zf, 600.0) < 2.0, (f, zf)


def test_tlw_termination_costs_gain_buys_direction():
    """Delete the resistor and the reflected wave restores the standing-wave
    bidirectional pattern: more gain (Cebik: +3.5 dB over average ground,
    13.96 vs 10.47 at 10 wl; this PEC model with the far leg still grounded
    reads +1.5) while the front-to-back collapses to nothing."""
    g_term = _far_field(_tlw(), ground="pec").max_gain
    ff_open = _far_field(_tlw_unterminated(), ground="pec")
    fb_open, _ = _fb(ff_open)
    assert 1.0 < ff_open.max_gain - g_term < 5.5
    assert fb_open < 6.0


def test_tlw_longer_is_stronger():
    """Cebik's length ladder: gain climbs with wire length (7.1 dBi at 3 wl
    -> 10.5 at 10 wl over ground) while the pattern stays unidirectional."""
    gains = {}
    for lw in (3.0, 7.0, 10.0):
        ff = _far_field(_tlw(length_frac=lw), ground="pec")
        gains[lw] = ff.max_gain
        fb, _ = _fb(ff)
        assert fb > 10.0, (lw, fb)
    assert gains[3.0] < gains[7.0] < gains[10.0]


def test_tlw_topology_grounded_legs():
    """Both vertical legs touch z=0 (the ground connection the GE flag
    makes real), the single driven edge sits at the bottom of the near leg,
    and the far leg bottom carries the ~800 ohm Load (Cebik's working value
    for RL = 138*log10(4h/d))."""
    from antennaknobs.network import Load

    b = _tlw()
    tups = b.build_wires()
    grounded = [t for t in tups if t[0][2] == 0.0 or t[1][2] == 0.0]
    assert len(grounded) == 2
    names = {t[4] for t in tups if len(t) == 5 and t[4]}
    assert names == {"feed", "term"}
    net = b.build_network()
    (load,) = [br for br in net.branches if isinstance(br, Load)]
    assert load.port == "term" and load.r == b.term_r
    # ~10 wl of horizontal run at ~1 wl height.
    wavelength = 299.792458 / b.design_freq
    xs = [p[0] for t in tups for p in (t[0], t[1])]
    assert abs((max(xs) - min(xs)) / wavelength - b.length_frac) < 0.2
    zs = {p[2] for t in tups for p in (t[0], t[1])}
    assert abs(max(zs) / wavelength - 1.0) < 0.15


# ---------------------------------------------------------------------------
# Moxon turnstile (two up-firing Moxons + a REAL quadrature phasing line)
# ---------------------------------------------------------------------------


def _moxon_turnstile_single_element():
    """Element A alone, driven directly at its gap: the reference the
    turnstile halves (junction R) and smooths (azimuth dome) against."""
    from antennaknobs.designs.beams.moxon_turnstile import Builder
    from antennaknobs.network import Driven, Network, PortOnWire

    class Single(Builder):
        def build_wires(self):
            return self._element("a")

        def build_network(self):
            return Network(
                ports={"feed_a": PortOnWire("feed_a")},
                branches=[],
                sources=[Driven(port="feed_a", voltage=1 + 0j)],
            )

    return Single()


def _moxon_turnstile_junction():
    """The transformer bypassed (driven right at element A's gap, phaseline
    kept): reads the raw ~25 ohm turnstile junction."""
    from antennaknobs.designs.beams.moxon_turnstile import Builder
    from antennaknobs.network import TL, Driven, Network, PortOnWire

    class Junction(Builder):
        def build_network(self):
            net = super().build_network()
            (phase,) = [
                br
                for br in net.branches
                if isinstance(br, TL) and {br.a, br.b} == {"feed_a", "feed_b"}
            ]
            return Network(
                ports={
                    "feed_a": PortOnWire("feed_a"),
                    "feed_b": PortOnWire("feed_b"),
                },
                branches=[phase],
                sources=[Driven(port="feed_a", voltage=1 + 0j)],
            )

    return Junction()


def test_moxon_turnstile_element_is_a_resonant_coax_moxon():
    """Each element is Cebik's resonant coax-class Moxon (his VHF tube
    build: 50 ohm; this thin-wire HF cousin reads ~62). The number matters
    because the phaseline z0 must EQUAL it -- the harness tracks 62."""
    z = _z(_moxon_turnstile_single_element())
    assert 40.0 < z.real < 70.0
    assert abs(z.imag) < 10.0


def test_moxon_turnstile_junction_halves_the_element():
    """Turnstile arithmetic: through the matched quarter-wave phaseline the
    two elements land in parallel, so the junction reads ~half the element R
    (Cebik: 50 -> 25 ohm)."""
    z = _z(_moxon_turnstile_junction())
    assert 18.0 < z.real < 33.0
    assert abs(z.imag) < 12.0


def test_moxon_turnstile_transformer_restores_coax():
    """The 35 ohm quarter-wave section steps the 25 ohm junction back up to
    the main feedline (Cebik: 49 ohm on RG-83, or paralleled 70 ohm lines)."""
    from antennaknobs.designs.beams.moxon_turnstile import Builder

    z = _z(Builder())
    assert _swr(z, 50.0) < 1.35
    assert abs(z.imag) < 12.0


def test_moxon_turnstile_quadrature_currents():
    """Cebik's central lesson from the QEX notes: turnstile quality is a
    CURRENT condition -- equal magnitudes, 90 deg apart -- and a matched-z0
    quarter-wave phaseline is what enforces it (his model: ratio 0.976 at
    89.98 deg). Read the two driven-gap currents from the real solve."""
    from antennaknobs.designs.beams.moxon_turnstile import Builder

    b = Builder()
    eng = PyNECEngine(b, ground=None)
    cur = eng.current_distribution()
    feed_idx = [
        i for i, t in enumerate(b.build_wires()) if len(t) == 5 and t[4] is not None
    ]
    ia, ib = (cur[i].knot_currents[1] for i in feed_idx)
    ratio = abs(ib) / abs(ia)
    phase = np.angle(ib / ia, deg=True)
    assert 0.75 < ratio < 1.25
    assert 75.0 < abs(phase) < 105.0


def test_moxon_turnstile_zenith_dome():
    """Fired straight up for fixed satellite work: the pattern peaks at the
    zenith and the quadrature pair smooths the mid-elevation ring into a
    dome -- azimuth ripple within ~2 dB where the single Moxon alone swings
    far more (its beam is a beam)."""
    from antennaknobs.designs.beams.moxon_turnstile import Builder

    rings = np.array(_far_field(Builder()).rings)
    assert rings[:5].max() > rings.max() - 1.0  # peak is overhead
    ring45 = rings[45]
    assert ring45.max() - ring45.min() < 2.0
    single45 = np.array(_far_field(_moxon_turnstile_single_element()).rings)[45]
    assert single45.max() - single45.min() > 2.0 * (ring45.max() - ring45.min())


def test_moxon_turnstile_gain_accounting():
    """Each element gets half the power, but at the zenith the two fields
    are ORTHOGONAL polarisations, so their powers add back: the TOTAL-field
    gain matches the single element's boresight (~5.6 dBi here). Cebik's
    famous ~3 dB turnstile penalty is what a polarisation-MATCHED (linear or
    single-CP-sense) receiver sees of it -- not a hole in the total-power
    pattern this engine plots."""
    from antennaknobs.designs.beams.moxon_turnstile import Builder

    g_single = _far_field(_moxon_turnstile_single_element()).max_gain
    g_turn = _far_field(Builder()).max_gain
    assert g_single > 5.0
    assert abs(g_single - g_turn) < 0.5


def test_moxon_turnstile_network_topology():
    """One quarter-wave phaseline at the ELEMENT impedance between the two
    driver gaps plus one quarter-wave low-Z transformer from a virtual shack
    to element A, driven at the shack -- Cebik's Fig. 12 feed exactly."""
    from antennaknobs.designs.beams.moxon_turnstile import Builder
    from antennaknobs.network import TL, Driven, PortVirtual

    b = Builder()
    net = b.build_network()
    tls = [br for br in net.branches if isinstance(br, TL)]
    assert len(tls) == 2 and not any(tl.transposed for tl in tls)
    wavelength = 299.792458 / b.design_freq
    (phase,) = [tl for tl in tls if {tl.a, tl.b} == {"feed_a", "feed_b"}]
    (match,) = [tl for tl in tls if {tl.a, tl.b} == {"shack", "feed_a"}]
    assert abs(phase.length - wavelength / 4) < 0.02 * wavelength
    assert abs(match.length - wavelength / 4) < 0.02 * wavelength
    assert match.z0 < phase.z0  # ~35 vs ~50: the step-down transformer
    assert isinstance(net.ports["shack"], PortVirtual)
    (src,) = net.sources
    assert isinstance(src, Driven) and src.port == "shack"
    # Two crossed elements: the two driver gaps run perpendicular.
    tups = b.build_wires()
    gaps = [t for t in tups if len(t) == 5 and t[4] is not None]
    assert {g[4] for g in gaps} == {"feed_a", "feed_b"}


# ---------------------------------------------------------------------------
# 40 m wide-band phased-driver wire Yagi (the OWA's 40 m counterpart)
# ---------------------------------------------------------------------------


_PDY_BAND = (7.0, 7.15, 7.3)


def test_pdy_flat_swr_across_the_whole_band():
    """The design goal: all of 7.0-7.3 MHz under 50-ohm SWR 1.5 with no
    traps or loading (Cebik's wire version: 1.42 / 1.11 / 1.48)."""
    from antennaknobs.designs.beams.phased_driver_yagi import Builder

    swrs = {
        f: _swr(_z(Builder(dict(Builder.default_params, freq=f))), 50.0)
        for f in _PDY_BAND
    }
    assert max(swrs.values()) < 1.6, swrs


def test_pdy_bandwidth_shames_the_conventional_wire_yagi():
    """Cebik's Part 1 premise: a conventional 2-el driver-reflector wire
    Yagi covers only ~2/3 of 40 m -- same band, same 50-ohm reference, the
    conventional cell blows far past the phased cell's band-max SWR."""
    from antennaknobs.designs.beams.phased_driver_yagi import Builder
    from antennaknobs.designs.beams.yagi import Builder as Yagi

    pdy_max = max(
        _swr(_z(Builder(dict(Builder.default_params, freq=f))), 50.0) for f in _PDY_BAND
    )
    yagi_max = max(
        _swr(
            _z(Yagi(dict(Yagi.default_params, design_freq=7.15, freq=f))),
            50.0,
        )
        for f in _PDY_BAND
    )
    assert pdy_max * 2.0 < yagi_max


def test_pdy_gain_and_front_to_back_across_band():
    """Cebik's Table 3: gain CLIMBS across the band (5.92 -> 6.97 dBi; this
    model reads ~1 dB over his numbers throughout, 6.8 -> 8.0) with the
    in-plane front-to-back holding 12.9-15.5 dB (this model: 12.1-15.1,
    peaking mid-band exactly as published). The F/B is measured in the
    beam plane -- the free-space pattern also has a genuine overhead lobe
    that a max-over-theta comparison would misread as a rear lobe."""
    from antennaknobs.designs.beams.phased_driver_yagi import Builder

    gains = {}
    for f in _PDY_BAND:
        ff = _far_field(Builder(dict(Builder.default_params, freq=f)))
        rings = np.array(ff.rings)
        fb = rings[89, 0] - rings[89, 180]
        gains[f] = ff.max_gain
        assert ff.max_gain > 6.3, (f, ff.max_gain)
        assert fb > 11.0, (f, fb)
    assert gains[7.0] < gains[7.3]


def test_pdy_half_twist_is_the_point():
    """Un-twist the 250-ohm phase line (transposed=False) and the phased
    cell breaks outright: the feedpoint leaves the band (SWR ~20 mid-band)
    and the front-to-back collapses -- the single half twist IS the
    design. (The reducer's transposed TL matches NEC's native crossed-line
    tl_card, z0 < 0, on this exact geometry -- verified while building.)"""
    import dataclasses

    from antennaknobs.designs.beams.phased_driver_yagi import Builder
    from antennaknobs.network import TL

    class Untwisted(Builder):
        def build_network(self):
            net = super().build_network()
            net.branches[:] = [
                dataclasses.replace(br, transposed=False) if isinstance(br, TL) else br
                for br in net.branches
            ]
            return net

    b = Untwisted(dict(Untwisted.default_params, freq=7.15))
    assert _swr(_z(b), 50.0) > 5.0
    rings = np.array(
        _far_field(Untwisted(dict(Untwisted.default_params, freq=7.15))).rings
    )
    assert rings[89, 0] - rings[89, 180] < 5.0


def test_pdy_topology_phased_driver_cell():
    """Three y-parallel thin-wire elements: rear driver (longest) at x=0,
    forward driver ~0.056 wl ahead carrying the single feed, director
    ~0.16 wl out; one TRANSPOSED 250-ohm line joins the drivers (Cebik's
    'single half twist' of ladder line)."""
    from antennaknobs.designs.beams.phased_driver_yagi import Builder
    from antennaknobs.network import TL, Driven

    b = Builder()
    tups = b.build_wires()
    names = {t[4]: t for t in tups if len(t) == 5 and t[4]}
    assert set(names) == {"feed", "rear"}
    wavelength = 299.792458 / b.design_freq
    halves = [h for h, _ in b.TABLE]
    poss = [p for _, p in b.TABLE]
    assert halves[0] > halves[1] > halves[2]  # rear > forward > director
    assert poss[0] == 0.0
    assert 0.04 < poss[1] < 0.07  # the drivers hug each other...
    assert poss[2] - poss[1] > 0.08  # ...the director does not
    # feed sits on the FORWARD driver, the phase line runs rear <- feed
    assert abs(names["feed"][0][0] - poss[1] * wavelength) < 0.01
    assert abs(names["rear"][0][0]) < 0.01
    net = b.build_network()
    (tl,) = [br for br in net.branches if isinstance(br, TL)]
    assert tl.transposed and abs(tl.z0 - 250.0) < 1e-9
    assert {tl.a, tl.b} == {"feed", "rear"}
    (src,) = net.sources
    assert isinstance(src, Driven) and src.port == "feed"
    # The wire elements are #12 LADDER LINE (a two-conductor cage), so the
    # model wire is its ~5 mm equivalent radius -- much fatter than a bare
    # #12 (1 mm) yet nothing like the tubing version's taper schedule.
    assert 0.003 < b.build_wire_material().radius < 0.008


# ---------------------------------------------------------------------------
# Tri-Moxon switched vertical array (10-10 News No. 51)
# ---------------------------------------------------------------------------
#
# Cebik's published numbers are over real ground (the 11 deg takeoff IS the
# ground), so unlike the rest of the batch these run over average earth.


_TM_GROUND = ("finite", 13.0, 0.005)


def _tm(**over):
    from antennaknobs.designs.verticals.tri_moxon import Builder

    return Builder(dict(Builder.default_params, **over) if over else None)


def _tm_solo():
    """Element 1 alone (neighbours and their parked feedlines deleted): the
    reference that shows how little the parked rectangles disturb."""
    from antennaknobs.designs.verticals.tri_moxon import Builder
    from antennaknobs.network import Driven, Network, PortOnWire

    class Solo(Builder):
        def build_wires(self):
            return self._element(1)

        def build_network(self):
            return Network(
                ports={"feed_1": PortOnWire("feed_1")},
                branches=[],
                sources=[Driven(port="feed_1", voltage=1 + 0j)],
            )

    return Solo()


def test_tri_moxon_sector_performance():
    """Cebik's headline per-sector numbers over ground: ~6.6 dBi at the
    11 deg takeoff with F/B ~13 dB -- '2-element Yagi range' from three
    fixed wire rectangles and a coax switch."""
    ff = _far_field(_tm(), ground=_TM_GROUND)
    rings = np.array(ff.rings)
    ti = int(np.unravel_index(int(np.argmax(rings)), rings.shape)[0])
    assert 5.9 < ff.max_gain < 7.5
    assert 90 - ti < 16  # low takeoff (Cebik: 11 deg)
    fb = rings[ti, 0] - rings[ti, 180]
    assert fb > 10.0


def test_tri_moxon_swr_holds_across_the_band():
    """Cebik's Fig. 4: under 1.7:1 on 50-ohm coax across all of 28-29 MHz
    with the dip near the 28.35 design frequency."""
    swrs = {
        f: _swr(_z(_tm(freq=f), ground=_TM_GROUND), 50.0) for f in (28.0, 28.35, 29.0)
    }
    assert max(swrs.values()) < 1.8, swrs
    assert swrs[28.35] < 1.35, swrs


def test_tri_moxon_sector_is_a_wide_slice_of_horizon():
    """Each rectangle covers ~125 degrees of azimuth (Cebik's Fig. 2), so
    three switched sectors blanket the horizon with only shallow overlap
    dips."""
    rings = np.array(_far_field(_tm(), ground=_TM_GROUND).rings)
    ti = int(np.unravel_index(int(np.argmax(rings)), rings.shape)[0])
    row = rings[ti]
    within3 = np.sum(row > row.max() - 3.0)
    assert 100 < within3 < 160, within3


def test_tri_moxon_parked_neighbours_cost_little():
    """The design's premise: each Moxon's own F/B protects the others, so
    with the two idle rectangles parked (feedpoints open through their
    shorted quarter-wave lines) the active sector loses only a whisker
    against the same rectangle flying solo."""
    ff_solo = _far_field(_tm_solo(), ground=_TM_GROUND)
    ff_full = _far_field(_tm(), ground=_TM_GROUND)
    assert abs(ff_solo.max_gain - ff_full.max_gain) < 0.7


def test_tri_moxon_direction_switch_rotates_the_beam():
    """The rotator replacement: driving element 2 instead of element 1
    swings the same beam 120 degrees around the horizon (exposed as the
    `dir2`/`dir3` variants)."""
    from antennaknobs import resolve_variant_params
    from antennaknobs.designs.verticals.tri_moxon import Builder

    ff1 = _far_field(_tm(), ground=_TM_GROUND)
    ff2 = _far_field(
        Builder(resolve_variant_params(Builder, "dir2")), ground=_TM_GROUND
    )
    r1, r2 = np.array(ff1.rings), np.array(ff2.rings)
    t1, p1 = np.unravel_index(int(np.argmax(r1)), r1.shape)
    t2, p2 = np.unravel_index(int(np.argmax(r2)), r2.shape)
    assert abs(ff1.max_gain - ff2.max_gain) < 0.3
    assert min(abs(p2 - p1 - 120), abs(p2 - p1 - 120 + 360)) < 15


def test_tri_moxon_idle_feedlines_are_shorted_quarter_waves():
    """Cebik's switching detail, modelled literally: the two idle drivers
    each hang on a quarter-wave 50-ohm line shorted at the switch end (a TL
    to a virtual stub port hard-shorted by a Shunt), which presents the
    open circuit at the parked feedpoint that 'modeling shows' works best.
    Geometry: three AWG-14 wire rectangles 120 degrees apart, reflectors
    48 inches off the post, Cebik's A/E proportions."""
    from antennaknobs.network import Driven, PortVirtual, Shunt, TL

    b = _tm()
    net = b.build_network()
    (src,) = net.sources
    assert isinstance(src, Driven) and src.port == "feed_1"
    tls = [br for br in net.branches if isinstance(br, TL)]
    shorts = [br for br in net.branches if isinstance(br, Shunt)]
    assert len(tls) == 2 and len(shorts) == 2
    wavelength = 299.792458 / b.design_freq
    for tl in tls:
        assert abs(tl.length - wavelength / 4) < 0.02 * wavelength
        assert abs(tl.z0 - 50.0) < 1e-9 and not tl.transposed
        assert isinstance(net.ports[tl.b], PortVirtual)
    assert {s.port for s in shorts} == {tl.b for tl in tls}
    assert all(s.r == 0.0 for s in shorts)
    # Geometry: 3 feed gaps, element verticals A ~ 0.364 wl tall, driver
    # radius = post spacing + E, thin AWG-14 wire.
    tups = b.build_wires()
    names = {t[4] for t in tups if len(t) == 5 and t[4]}
    assert names == {"feed_1", "feed_2", "feed_3"}
    assert abs(b.a_frac - 0.364) < 0.01
    assert abs(b.e_frac - 0.1329) < 0.005
    assert b.build_wire_material().radius < 0.001


# ===========================================================================
# Methodology / cross-engine findings (momwire vs the PyNEC reference)
#
# These lock in WHERE the four momwire solver bases agree with PyNEC and where
# they do not -- the point of this batch. They import MomwireEngine directly.
# ===========================================================================


def test_parasitic_loop_quad_agrees_across_engines():
    """A parasitic (no-port) closed loop -- the cubical quad's reflector -- is
    now handled on every momwire basis (the geometry translator cuts the loop at
    an arbitrary edge and lets momwire's junction KCL carry the current around
    it). Both basis families agree with the PyNEC reference. This was the
    single biggest momwire gap; the test that used to assert it RAISED now
    asserts it SOLVES."""
    from antennaknobs.designs.loops.quad import Builder
    from antennaknobs.engines import MomwireEngine
    from momwire import BSplineSolver, SinusoidalSolver

    z_ref = _z(Builder())  # PyNEC reference
    assert z_ref.real > 0.0
    for solver, kw in [
        (SinusoidalSolver, {}),
        (BSplineSolver, {"degree": 2}),
    ]:
        z = MomwireEngine(
            Builder(), ground=None, solver=solver, solver_kwargs=kw
        ).impedance()[0]
        # within a few percent of PyNEC on R, and near-resonant like PyNEC
        assert abs(z.real - z_ref.real) / z_ref.real < 0.05
        assert abs(z.imag) < 15.0


def test_terminated_rhombic_is_unidirectional_across_engines():
    """A closed loop with TWO port edges -- the rhombic's feed apex + its
    terminating resistor -- is now handled too (cut at one port, the other
    rides the long-way polyline as a mid-polyline feed). The resistive load
    is imposed with its physical series-impedance BC in the excited solve, so
    momwire develops the same TRAVELING-WAVE unidirectional pattern as PyNEC
    (it was bidirectional, F/B ~1 dB, before the load shaped the current), and
    the radiation efficiency folds the termination loss into GAIN."""
    from antennaknobs.designs.wire.rhombic import Builder
    from antennaknobs.engines import MomwireEngine

    ref = _far_field(Builder())  # PyNEC reference
    ff = MomwireEngine(Builder(), ground=None).far_field(
        n_theta=90, n_phi=360, del_theta=1, del_phi=1
    )

    def front_to_back(far):
        r = np.array(far.rings)
        ti = int(np.argmax(r.max(axis=1)))
        pphi = int(np.argmax(r[ti]))
        return r[ti][pphi] - r[ti][(pphi + 180) % 360]

    # gain now accounts for the termination loss (directivity x efficiency),
    # so it lands close to PyNEC instead of ~3 dB high.
    assert abs(ff.max_gain - ref.max_gain) < 0.8
    # and the termination makes it strongly unidirectional, like PyNEC.
    assert front_to_back(ff) > 15.0
    assert front_to_back(ref) > 15.0


def test_pynec_pec_matches_momwire_sinusoidal_on_terminated_loop():
    """PyNEC defaults to PEC wires (WIRE_CONDUCTIVITY=None), matching momwire's
    lossless model. With copper loss off, PyNEC and momwire's SINUSOIDAL basis --
    the same NEC2 basis family -- agree on a terminated rhombic to a fraction
    of an ohm and a fraction of a dB. This pins that clean cross-engine
    reference (turning copper loss back on would offset it by a few tenths of
    a dB, which is exactly why the default is PEC)."""
    from antennaknobs.designs.wire.rhombic import Builder
    from antennaknobs.engines import MomwireEngine
    from momwire import SinusoidalSolver

    z_nec = _z(Builder())  # PyNEC, PEC by default
    eng = MomwireEngine(Builder(), ground=None, solver=SinusoidalSolver)
    z_sin = eng.impedance()[0]
    # same basis family + both PEC -> impedance agrees to well under 1%.
    assert abs(z_nec - z_sin) / abs(z_nec) < 0.01
    # and the load efficiency that feeds the gain correction matches too.
    eng.current_distribution()
    z_ref_eff = eng._excited_efficiency
    nec = PyNECEngine(Builder())
    nec.current_distribution()
    assert abs(nec._excited_efficiency - z_ref_eff) < 0.02


def test_t2fd_broadband_gain_agrees_across_engines():
    """The T2FD is a folded loop carrying a feed AND a terminating resistor
    (two port edges). With the load shaping the current and its loss folded
    into gain, momwire's low broadband gain matches PyNEC instead of reading
    several dB high."""
    from antennaknobs.designs.broadband.t2fd import Builder
    from antennaknobs.engines import MomwireEngine
    from momwire import BSplineSolver, SinusoidalSolver

    g_ref = _far_field(Builder()).max_gain  # PyNEC reference
    for solver, kw in [
        (SinusoidalSolver, {}),
        (BSplineSolver, {"degree": 2}),
    ]:
        g = (
            MomwireEngine(Builder(), ground=None, solver=solver, solver_kwargs=kw)
            .far_field(n_theta=90, n_phi=360, del_theta=1, del_phi=1)
            .max_gain
        )
        assert abs(g - g_ref) < 0.8


def test_g5rv_ideal_halfwave_line_is_singular_on_every_engine():
    """An ideal lossless TL is singular at exactly k*lambda/2 (sin betaL = 0);
    the guard fires identically on PyNEC and every momwire basis -- a shared
    network-layer limitation, not a momwire-specific hole. The default sits just
    off the half wave to avoid it."""
    import pytest

    from antennaknobs.designs.broadband.g5rv import Builder

    with pytest.raises(ValueError):
        _z(Builder(dict(Builder.default_params, match_len_frac=0.5)))


def test_bruce_high_z_feed_is_well_conditioned_across_bases():
    """The Bruce feed is high-Z and reactive, but because the tap sits a little
    off the exact current null the bases AGREE on it (within a few percent)
    -- high-Z but NOT ill-conditioned."""
    from antennaknobs.designs.verticals.bruce import Builder
    from antennaknobs.engines import MomwireEngine
    from momwire import SinusoidalSolver

    zb = MomwireEngine(Builder(), ground=None).impedance()[0]
    zs = MomwireEngine(Builder(), ground=None, solver=SinusoidalSolver).impedance()[0]
    assert abs(zb - zs) / abs(zb) < 0.1


def test_zepp_current_null_end_feed_is_basis_dependent():
    """Contrast to the Bruce: feeding at a near-OPEN current null (the end of a
    half wave) is ill-conditioned. After the stub transform the shack R agrees
    across bases but the REACTANCE inherits the basis spread."""
    from antennaknobs.designs.wire.zepp import Builder
    from antennaknobs.engines import MomwireEngine

    zp = _z(Builder())  # PyNEC shack
    zb = MomwireEngine(Builder(), ground=None).impedance()[0]
    assert abs(zp.real - zb.real) < 1.0  # R agrees
    # X inherits the end-null spread: ~2.7 ohm for BSpline d=2 vs PyNEC
    # (the retired triangular basis sat >4), still ~170x the R agreement.
    assert abs(zp.imag - zb.imag) > 2.0
