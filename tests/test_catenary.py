"""Tests for the hanging-chain equilibrium solver (``catenary.py``, issue #698).

Every assertion here is checked against an *independently written* closed form
— the textbook catenary relations spelled out fresh in the test — rather than
against whatever the module happened to compute.  The oracles are:

  * symmetric level span: sag ``a·(cosh(d/2a) − 1)``, arc ``2a·sinh(d/2a)``,
    and the tension distribution ``T = w·(z − c)``;
  * an asymmetric span built from hand-picked catenary parameters ``u₀, u₁``;
  * global statics: the two support reactions sum to the chain's weight;
  * the taut-string limit ``sag = w·d²/(8H)`` for the small-sag branch.

One numerical caution worth stating up front: the *oracle* itself has to be
written stably.  ``a·(cosh(u) − 1)`` cancels catastrophically once ``u`` is
tiny (the taut regime), so the taut tests use the algebraically identical
``2a·sinh(u/2)²``, which does not.
"""

import math

import numpy as np
import pytest

import antennaknobs.catenary as catenary
from antennaknobs.catenary import (
    GRAVITY,
    TAUT_D,
    TAUT_SAG_D,
    ChainSegment,
    SegmentMarch,
    chord_sag,
    march_continuous,
    solve_anchored,
    solve_chain,
    solve_tensioned,
    weight_n_per_m,
)

# A 14-awg-ish wire and a heavier halyard, in newtons per metre.
W_WIRE = weight_n_per_m(7.37)
W_ROPE = weight_n_per_m(30.0)


# --------------------------------------------------------------------------
# Closed-form oracles for the marching kernel
# --------------------------------------------------------------------------


def _symmetric_state(a, w, span):
    """Tension state at the LEFT end of a level span of horizontal width
    ``span`` whose catenary parameter is ``a``.

    The vertex sits at mid-span, so the left end is at ``u₀ = −span/2a`` and
    ``V₀ = H·sinh(u₀)``.  Returns ``(H, V0, arc_length)``.
    """
    h = a * w
    u0 = -span / (2.0 * a)
    return h, h * math.sinh(u0), 2.0 * a * math.sinh(span / (2.0 * a))


def test_symmetric_span_matches_textbook_sag_arc_and_tension():
    """Level span: sag, arc length and T = w·(z − c) all reproduced."""
    a, w, span = 40.0, 0.35, 30.0
    h, v0, arc = _symmetric_state(a, w, span)

    # Independent oracles.
    assert arc == pytest.approx(2.0 * a * math.sinh(span / (2.0 * a)), rel=1e-15)
    sag_oracle = a * (math.cosh(span / (2.0 * a)) - 1.0)

    n = 201  # odd, so a sample lands exactly on the vertex
    sol = solve_chain(
        apex=(0.0, 0.0),
        tension=(h, v0),
        segments=(ChainSegment(arc, w, "span"),),
        samples_per_segment=n,
    )

    # The far end is level with the start, one full span away.
    assert sol.end_point[0] == pytest.approx(span, rel=1e-12)
    assert sol.end_point[1] == pytest.approx(0.0, abs=1e-12 * span)

    # Chord is level here, so the perpendicular sag IS the vertical sag.
    assert sol.max_sag_m == pytest.approx(sag_oracle, rel=1e-12)

    # Tension distribution: with z measured from the left end, the directrix
    # sits at c = −a·cosh(u₀), so T(s) = w·(z(s) − c) must equal √(H² + V²).
    c = -a * math.cosh(-span / (2.0 * a))
    pts = sol.segments[0].points
    for i, (_, z) in enumerate(pts):
        s = arc * i / (n - 1)
        assert w * (z - c) == pytest.approx(math.hypot(h, v0 + w * s), rel=1e-12)

    # The vertex (deepest point) is at mid-span and mid-arc.
    lowest = pts[np.argmin(pts[:, 1])]
    assert lowest[0] == pytest.approx(span / 2.0, rel=1e-9)
    assert lowest[1] == pytest.approx(-sag_oracle, rel=1e-9)


def test_asymmetric_span_matches_hand_computed_catenary():
    """Two points at different heights, built from chosen ``u₀``/``u₁``."""
    a, w = 5.0, 0.3
    h = a * w
    u0, u1 = -0.8, 0.6

    # Hand-computed from z = a·cosh(u) + c, s = a·sinh(u), x = a·u + const.
    dx_oracle = a * (u1 - u0)
    dz_oracle = a * (math.cosh(u1) - math.cosh(u0))
    arc_oracle = a * (math.sinh(u1) - math.sinh(u0))
    v0 = h * math.sinh(u0)

    sol = solve_chain(
        apex=(2.0, 9.0),
        tension=(h, v0),
        segments=(ChainSegment(arc_oracle, w, "span"),),
        samples_per_segment=401,
    )
    assert sol.end_point[0] == pytest.approx(2.0 + dx_oracle, rel=1e-13)
    assert sol.end_point[1] == pytest.approx(9.0 + dz_oracle, rel=1e-13)

    # End tension vector (the far support's pull) is (H, V1) with V1 = H·sinh(u₁).
    assert sol.end_tension_vector[0] == pytest.approx(h, rel=1e-13)
    assert sol.end_tension_vector[1] == pytest.approx(h * math.sinh(u1), rel=1e-12)
    assert sol.end_tension == pytest.approx(h * math.cosh(u1), rel=1e-12)
    assert sol.apex_tension == pytest.approx(h * math.cosh(u0), rel=1e-12)

    # Perpendicular sag, hand-derived: the chord has slope m = Δz/Δx; the
    # tangent matches it at u* = asinh(m); the vertical gap there is
    # a·[cosh u₀ − cosh u* + m·(u* − u₀)], and the perpendicular offset is that
    # gap foreshortened by Δx/‖chord‖.
    m = dz_oracle / dx_oracle
    u_star = math.asinh(m)
    vertical = a * (math.cosh(u0) - math.cosh(u_star) + m * (u_star - u0))
    chord = math.hypot(dx_oracle, dz_oracle)
    assert sol.max_sag_m == pytest.approx(vertical * dx_oracle / chord, rel=1e-11)


def test_steeply_descending_arm_with_negative_v0():
    """An arm that drops steeply (V0 strongly negative) marches correctly."""
    a, w = 3.0, 0.5
    h = a * w
    u0, u1 = -2.5, -1.0
    sol = solve_chain(
        apex=(0.0, 0.0),
        tension=(h, h * math.sinh(u0)),
        segments=(ChainSegment(a * (math.sinh(u1) - math.sinh(u0)), w),),
        samples_per_segment=51,
    )
    # Still descending at the end, so the whole arc is below the start.
    assert sol.end_point[1] < 0.0
    assert sol.end_point[0] == pytest.approx(a * (u1 - u0), rel=1e-13)
    assert sol.end_point[1] == pytest.approx(
        a * (math.cosh(u1) - math.cosh(u0)), rel=1e-13
    )
    # x is strictly increasing along the chain whenever H > 0.
    assert np.all(np.diff(sol.segments[0].points[:, 0]) > 0.0)


def test_massless_segment_marches_straight():
    """``w = 0`` degenerates to a straight line along the tension direction."""
    h, v0, length = 12.0, -5.0, 7.0
    sol = solve_chain(
        apex=(1.0, 4.0),
        tension=(h, v0),
        segments=(ChainSegment(length, 0.0, "halyard"),),
        samples_per_segment=17,
    )
    t = math.hypot(h, v0)
    assert sol.end_point[0] == pytest.approx(1.0 + length * h / t, rel=1e-14)
    assert sol.end_point[1] == pytest.approx(4.0 + length * v0 / t, rel=1e-14)
    assert sol.max_sag_m == 0.0
    # Tension is unchanged along a weightless span.
    assert sol.end_tension == pytest.approx(t, rel=1e-14)
    # Sampled polyline length equals the arc length exactly for a line.
    assert sol.segments[0].polyline_length_m == pytest.approx(length, rel=1e-13)


def test_march_rejects_non_positive_horizontal_tension():
    for bad in (0.0, -3.0):
        with pytest.raises(ValueError, match="horizontal tension must be positive"):
            march_continuous((0.0, 0.0), (bad, -1.0), (ChainSegment(5.0, W_WIRE),))


def test_march_rejects_degenerate_sampling_and_empty_chain():
    with pytest.raises(ValueError, match="samples_per_segment"):
        march_continuous((0.0, 0.0), (5.0, -1.0), (ChainSegment(5.0, W_WIRE),), 1)
    with pytest.raises(ValueError, match="at least one segment"):
        march_continuous((0.0, 0.0), (5.0, -1.0), ())


# --------------------------------------------------------------------------
# Taut-limit numerics
# --------------------------------------------------------------------------


def test_taut_limit_solves_without_overflow_and_matches_parabola():
    """H/w ≈ 1e9 × span: the regime where the naive cosh form dies."""
    span, w = 20.0, W_WIRE
    a = 1.0e9 * span
    h, v0, arc = _symmetric_state(a, w, span)
    assert h / w == pytest.approx(a, rel=1e-15)

    sol = solve_chain(
        apex=(0.0, 0.0),
        tension=(h, v0),
        segments=(ChainSegment(arc, w, "taut"),),
        samples_per_segment=101,
    )
    assert np.all(np.isfinite(sol.segments[0].points))
    assert sol.end_point[0] == pytest.approx(span, rel=1e-14)
    assert sol.end_point[1] == pytest.approx(0.0, abs=1e-12)

    # Stable form of a·(cosh(u) − 1); the naive one has already cancelled away
    # every significant digit at u = 5e-10.
    u = span / (2.0 * a)
    sag_oracle = 2.0 * a * math.sinh(u / 2.0) ** 2
    parabolic = w * span**2 / (8.0 * h)
    assert sag_oracle == pytest.approx(parabolic, rel=1e-12)
    assert sol.max_sag_m == pytest.approx(parabolic, rel=1e-9)


def test_offset_branches_agree_across_the_taut_threshold(monkeypatch):
    """The exact and series displacement branches meet seamlessly at TAUT_D."""
    w, length = 0.4, 12.0
    h = w * length / TAUT_D  # exactly on the threshold
    for slope0 in (0.0, -0.7, 1.5, -3.0):
        v0 = slope0 * h
        monkeypatch.setattr(catenary, "TAUT_D", 0.0)  # force exact branch
        exact = catenary._offset(h, v0, w, length)
        monkeypatch.setattr(catenary, "TAUT_D", math.inf)  # force series branch
        series = catenary._offset(h, v0, w, length)
        assert exact[0] == pytest.approx(series[0], rel=1e-11)
        assert exact[1] == pytest.approx(series[1], rel=1e-9, abs=1e-15 * length)


def test_sag_branches_agree_across_the_taut_sag_threshold(monkeypatch):
    """Same seamlessness check for the far touchier perpendicular sag."""
    w, length = 0.4, 12.0
    for d in (TAUT_SAG_D, 10.0 * TAUT_SAG_D, 0.1 * TAUT_SAG_D):
        h = w * length / d
        for slope0 in (0.0, -0.7, 1.5):
            v0 = slope0 * h
            monkeypatch.setattr(catenary, "TAUT_SAG_D", 0.0)
            exact = chord_sag(h, v0, w, length)
            monkeypatch.setattr(catenary, "TAUT_SAG_D", math.inf)
            series = chord_sag(h, v0, w, length)
            assert exact == pytest.approx(series, rel=1e-9)


def test_sag_reduces_to_the_level_span_parabola():
    """``w·d²/(8H)`` for a level span, checked well inside the taut branch."""
    w, span = 0.4, 25.0
    a = 5.0e7 * span
    h, v0, arc = _symmetric_state(a, w, span)
    assert chord_sag(h, v0, w, arc) == pytest.approx(w * span**2 / (8.0 * h), rel=1e-9)


# --------------------------------------------------------------------------
# Sampling consistency
# --------------------------------------------------------------------------


def test_sampled_polyline_length_converges_to_the_arc_length():
    """Chord-sum length approaches L_i, and the error falls like 1/n²."""
    a, w, span = 12.0, 0.6, 25.0  # deliberately saggy, so the error is visible
    h, v0, arc = _symmetric_state(a, w, span)
    errors = []
    for n in (9, 17, 33, 65, 129):
        sol = solve_chain(
            apex=(0.0, 0.0),
            tension=(h, v0),
            segments=(ChainSegment(arc, w),),
            samples_per_segment=n,
        )
        shape = sol.segments[0]
        assert shape.arc_length_m == pytest.approx(arc, rel=1e-15)
        assert shape.polyline_length_m < arc  # chords cut corners
        errors.append(arc - shape.polyline_length_m)
    for coarse, fine in zip(errors, errors[1:]):
        assert fine < coarse / 3.5  # second-order: each halving gains ~4x
    assert errors[-1] / arc < 1e-5


def test_multi_segment_polyline_is_continuous_at_the_junction():
    sol = solve_anchored(
        apex=(0.0, 12.0),
        segments=(
            ChainSegment(12.0, W_WIRE, "wire"),
            ChainSegment(14.0, W_ROPE, "rope"),
        ),
        anchor=(20.0, 0.0),
        samples_per_segment=25,
    )
    assert len(sol.junctions) == 1
    junction = np.array(sol.junctions[0])
    assert sol.segments[0].points[-1] == pytest.approx(junction, rel=1e-12)
    assert sol.segments[1].points[0] == pytest.approx(junction, rel=1e-12)
    # ``polyline`` drops the duplicated junction sample.
    assert sol.polyline.shape == (25 + 25 - 1, 2)
    assert sol.total_arc_length_m == pytest.approx(26.0, rel=1e-15)


# --------------------------------------------------------------------------
# Model 2 — anchored chain
# --------------------------------------------------------------------------


def _anchored(rope_len, *, samples=101):
    return solve_anchored(
        apex=(0.0, 12.0),
        segments=(
            ChainSegment(12.0, W_WIRE, "wire"),
            ChainSegment(rope_len, W_ROPE, "rope"),
        ),
        anchor=(20.0, 0.0),
        samples_per_segment=samples,
    )


def test_anchored_lands_on_the_anchor():
    sol = _anchored(14.0)
    assert sol.end_point[0] == pytest.approx(20.0, abs=1e-9)
    assert sol.end_point[1] == pytest.approx(0.0, abs=1e-9)
    assert sol.polyline[0] == pytest.approx(np.array([0.0, 12.0]))
    assert sol.polyline[-1] == pytest.approx(np.array([20.0, 0.0]), abs=1e-9)


def test_anchored_support_reactions_sum_to_the_weight():
    """Global statics: F_apex + F_end = (0, Σ Lᵢ·wᵢ), horizontals cancel."""
    for rope_len in (13.0, 16.0, 22.0):
        sol = _anchored(rope_len)
        weight_oracle = 12.0 * W_WIRE + rope_len * W_ROPE
        assert sol.total_weight_n == pytest.approx(weight_oracle, rel=1e-15)
        fx = sol.apex_tension_vector[0] + sol.end_tension_vector[0]
        fz = sol.apex_tension_vector[1] + sol.end_tension_vector[1]
        assert fx == pytest.approx(0.0, abs=1e-12 * weight_oracle)
        assert fz == pytest.approx(weight_oracle, rel=1e-12)
        # Magnitudes agree with the vectors they came from.
        assert sol.apex_tension == pytest.approx(math.hypot(*sol.apex_tension_vector))
        assert sol.end_tension == pytest.approx(math.hypot(*sol.end_tension_vector))
        # The shared H is what both reactions carry horizontally.
        assert abs(sol.apex_tension_vector[0]) == pytest.approx(
            sol.horizontal_tension_n, rel=1e-14
        )


def test_anchored_tension_is_continuous_across_the_junction():
    """Tension is an output; the wire's end state is the rope's start state."""
    sol = _anchored(14.0)
    wire, rope = sol.segments
    assert wire.end_tension_vector == pytest.approx(rope.start_tension_vector)
    # Vertical tension accumulates exactly the weight hung below it.
    assert rope.end_tension_vector[1] - rope.start_tension_vector[1] == pytest.approx(
        14.0 * W_ROPE, rel=1e-12
    )


def test_anchored_rope_takeup_raises_tension_and_reduces_sag():
    """Winching the rope in (shorter L_r) pulls the chain taut.

    Sag is measured perpendicular to each segment's OWN chord, which is not
    monotone over the whole slack range: a very slack chain swings its wire
    chord toward the vertical, and a near-vertical chord has little
    perpendicular offset no matter how loose the wire is.  The monotone claim
    belongs to the taut half of the range, which is where any real rig lives.
    """
    lengths = [14.0, 13.0, 12.5, 12.0, 11.6, 11.4]
    sols = [_anchored(length) for length in lengths]
    tensions = [s.apex_tension for s in sols]
    h_values = [s.horizontal_tension_n for s in sols]
    wire_sags = [s.segments[0].max_sag_m for s in sols]
    rope_sags = [s.segments[1].max_sag_m for s in sols]

    for prev, nxt in zip(tensions, tensions[1:]):
        assert nxt > prev
    for prev, nxt in zip(h_values, h_values[1:]):
        assert nxt > prev
    for prev, nxt in zip(wire_sags, wire_sags[1:]):
        assert nxt < prev
    for prev, nxt in zip(rope_sags, rope_sags[1:]):
        assert nxt < prev


def test_anchored_rejects_a_rope_too_short_to_reach():
    reach = math.hypot(20.0, 12.0)
    with pytest.raises(ValueError, match="chain cannot reach the anchor"):
        _anchored(reach - 12.0 - 0.5)
    # Exactly straight is rejected too: no equilibrium for an inextensible chain.
    with pytest.raises(ValueError, match="chain cannot reach the anchor"):
        _anchored(reach - 12.0)


def test_anchored_rejects_a_vertical_hanging_chain():
    with pytest.raises(ValueError, match="horizontally beyond the apex"):
        solve_anchored(
            apex=(0.0, 12.0),
            segments=(ChainSegment(14.0, W_WIRE),),
            anchor=(0.0, 0.0),
        )


def test_anchored_rejects_a_weightless_chain():
    with pytest.raises(ValueError, match="weightless chain has no catenary"):
        solve_anchored(
            apex=(0.0, 12.0),
            segments=(ChainSegment(14.0, 0.0), ChainSegment(14.0, 0.0)),
            anchor=(10.0, 0.0),
        )


def test_anchored_rejects_an_empty_chain():
    with pytest.raises(ValueError, match="at least one segment"):
        solve_anchored(apex=(0.0, 0.0), segments=(), anchor=(1.0, -1.0))


# --------------------------------------------------------------------------
# Model 1 — tensioned halyard
# --------------------------------------------------------------------------

APEX = (0.0, 10.0)
STAKE = (9.0, 1.0)
WIRE_LEN = 10.0


def _tensioned(tension, *, stake=STAKE, samples=101):
    return solve_tensioned(
        apex=APEX,
        wire_length_m=WIRE_LEN,
        wire_weight_n_per_m=W_WIRE,
        stake=stake,
        rope_tension_n=tension,
        samples_per_segment=samples,
    )


def test_tensioned_closure_is_satisfied():
    """The end tension vector really is T_rope pointing at the stake."""
    for tension in (2.0, 40.0, 900.0):
        sol = _tensioned(tension)
        ex, ez = sol.end_point
        rx, rz = STAKE[0] - ex, STAKE[1] - ez
        dist = math.hypot(rx, rz)
        assert sol.end_tension_vector[0] == pytest.approx(
            tension * rx / dist, rel=1e-9, abs=1e-9 * tension
        )
        assert sol.end_tension_vector[1] == pytest.approx(
            tension * rz / dist, rel=1e-9, abs=1e-9 * tension
        )
        assert sol.end_tension == pytest.approx(tension, rel=1e-9)


def test_tensioned_support_reactions_sum_to_the_weight():
    sol = _tensioned(40.0)
    weight_oracle = WIRE_LEN * W_WIRE
    fx = sol.apex_tension_vector[0] + sol.end_tension_vector[0]
    fz = sol.apex_tension_vector[1] + sol.end_tension_vector[1]
    assert fx == pytest.approx(0.0, abs=1e-12 * weight_oracle)
    assert fz == pytest.approx(weight_oracle, rel=1e-9)


def test_tensioned_taut_limit_approaches_the_straight_chord():
    """T_rope → ∞ converges to the straight arm — the invvee oracle."""
    reach = math.hypot(STAKE[0] - APEX[0], STAKE[1] - APEX[1])
    ux = (STAKE[0] - APEX[0]) / reach
    uz = (STAKE[1] - APEX[1]) / reach
    chord_end = (APEX[0] + WIRE_LEN * ux, APEX[1] + WIRE_LEN * uz)

    previous_miss = math.inf
    for tension in (5.0e2, 5.0e4, 5.0e6, 5.0e8):
        sol = _tensioned(tension)
        miss = math.hypot(
            sol.end_point[0] - chord_end[0], sol.end_point[1] - chord_end[1]
        )
        assert miss < previous_miss / 50.0  # ~1/T convergence, two decades a step
        previous_miss = miss
        # Sag falls off like the taut-string result q·L²/(8·T), where the
        # transverse load q is only the component of the weight perpendicular
        # to this (45°-inclined) arm: q = w·cosθ = w·ux.
        assert sol.max_sag_m == pytest.approx(
            W_WIRE * ux * WIRE_LEN**2 / (8.0 * tension), rel=2e-2
        )
    assert previous_miss < 1e-7
    # And the whole arc, not just its endpoint, has collapsed onto the chord.
    assert _tensioned(5.0e8).max_sag_m < 1e-8


def test_tensioned_more_tension_means_less_sag():
    sags = [_tensioned(t).max_sag_m for t in (5.0, 20.0, 80.0, 320.0)]
    for prev, nxt in zip(sags, sags[1:]):
        assert nxt < prev


def test_tensioned_solves_across_twenty_decades_of_tension():
    """Knob-scrub robustness: nothing in the usable range may throw."""
    for tension in (1e-6, 1e-3, 1e-1, 1e1, 1e3, 1e6, 1e9, 1e12):
        sol = _tensioned(tension, samples=9)
        assert sol.residual < 1e-9
        assert math.isfinite(sol.horizontal_tension_n)
        assert sol.horizontal_tension_n > 0.0


def test_tensioned_rejects_a_stake_not_beyond_the_apex():
    for stake in ((0.0, 1.0), (-4.0, 1.0)):
        with pytest.raises(ValueError, match="horizontally beyond the apex"):
            _tensioned(500.0, stake=stake)


def test_tensioned_rejects_a_stake_the_wire_would_overshoot():
    """A stake nearer than the wire is long has no equilibrium at any tension:
    the taut wire runs past it and the rope would have to pull backwards."""
    near = (4.5, 6.0)
    assert math.hypot(near[0] - APEX[0], near[1] - APEX[1]) < WIRE_LEN
    for tension in (5.0, 50.0, 5000.0):
        with pytest.raises(ValueError, match="no equilibrium found"):
            _tensioned(tension, stake=near)


def test_tensioned_rejects_impossible_inputs():
    with pytest.raises(ValueError, match="rope tension must be positive"):
        _tensioned(0.0)
    with pytest.raises(ValueError, match="rope tension must be positive"):
        _tensioned(-5.0)
    with pytest.raises(ValueError, match="weightless wire has no catenary"):
        solve_tensioned(
            apex=APEX,
            wire_length_m=WIRE_LEN,
            wire_weight_n_per_m=0.0,
            stake=STAKE,
            rope_tension_n=50.0,
        )
    with pytest.raises(ValueError, match="wire length must be positive"):
        solve_tensioned(
            apex=APEX,
            wire_length_m=0.0,
            wire_weight_n_per_m=W_WIRE,
            stake=STAKE,
            rope_tension_n=50.0,
        )


def test_tensioned_keeps_the_cut_length_fixed_as_tension_changes():
    """The electrical knob must not move when the mechanical one does."""
    for tension in (3.0, 300.0, 30000.0):
        sol = _tensioned(tension, samples=401)
        assert sol.segments[0].arc_length_m == WIRE_LEN
        assert sol.segments[0].polyline_length_m == pytest.approx(WIRE_LEN, rel=1e-6)


# --------------------------------------------------------------------------
# Segment validation and the kernel seam
# --------------------------------------------------------------------------


def test_chain_segment_validates_its_inputs():
    with pytest.raises(ValueError, match="arc length must be positive"):
        ChainSegment(0.0, W_WIRE)
    with pytest.raises(ValueError, match="arc length must be positive"):
        ChainSegment(-2.0, W_WIRE)
    with pytest.raises(ValueError, match="weight per metre must be non-negative"):
        ChainSegment(5.0, -1.0, "rope")


def test_weight_conversion_uses_standard_gravity():
    assert weight_n_per_m(1000.0) == pytest.approx(GRAVITY)
    assert weight_n_per_m(7.37) == pytest.approx(7.37e-3 * 9.80665)


def test_solvers_accept_an_alternative_marching_kernel():
    """The kernel is a seam: any callable with the signature can stand in.

    This stands in for the discrete funicular kernel that will land later —
    here a thin wrapper that just counts calls, proving the shooting wrappers
    route every march through the injected kernel and nothing else.
    """
    calls = []

    def counting_kernel(start, tension, segments, samples_per_segment=33):
        calls.append(samples_per_segment)
        return march_continuous(start, tension, segments, samples_per_segment)

    sol = solve_tensioned(
        apex=APEX,
        wire_length_m=WIRE_LEN,
        wire_weight_n_per_m=W_WIRE,
        stake=STAKE,
        rope_tension_n=100.0,
        samples_per_segment=64,
        kernel=counting_kernel,
    )
    assert calls  # every march went through the injected kernel
    assert calls[-1] == 64  # the final, full-resolution march
    assert set(calls[:-1]) == {2}  # residual evaluations sample only endpoints
    assert sol.segments[0].points.shape == (64, 2)

    calls.clear()
    anchored = solve_anchored(
        apex=(0.0, 12.0),
        segments=(ChainSegment(12.0, W_WIRE), ChainSegment(14.0, W_ROPE)),
        anchor=(20.0, 0.0),
        samples_per_segment=48,
        kernel=counting_kernel,
    )
    assert calls[-1] == 48
    assert anchored.polyline.shape == (48 + 48 - 1, 2)


def test_segment_march_carries_the_raw_kernel_contract():
    marched = march_continuous(
        (0.0, 0.0), (5.0, -2.0), (ChainSegment(4.0, 0.5), ChainSegment(3.0, 0.9)), 11
    )
    assert len(marched) == 2
    for m in marched:
        assert isinstance(m, SegmentMarch)
        assert m.points.shape == (11, 2)
        assert m.end_point == pytest.approx(tuple(m.points[-1]))
    # H is shared; V accumulates the weight of each span in turn.
    assert marched[0].end_tension[0] == 5.0
    assert marched[1].end_tension[0] == 5.0
    assert marched[0].end_tension[1] == pytest.approx(-2.0 + 4.0 * 0.5)
    assert marched[1].end_tension[1] == pytest.approx(-2.0 + 4.0 * 0.5 + 3.0 * 0.9)
    # Segment 2 starts where segment 1 ended.
    assert marched[1].points[0] == pytest.approx(np.array(marched[0].end_point))


def test_chain_solution_reports_the_worst_segment_sag():
    sol = _anchored(20.0)
    assert sol.max_sag_m == max(s.max_sag_m for s in sol.segments)
    assert sol.segments[1].max_sag_m > sol.segments[0].max_sag_m
    assert sol.segments[0].chord_length_m < sol.segments[0].arc_length_m
