"""Structural gates for the three buried-wire catalog designs.

The value of `verticals.buried_radial_vertical`,
`verticals.elevated_buried_counterpoise` and `specialty.buried_dipole` is
that they sit INSIDE momwire's served scope — the crossing serve
(momwire#524 phase 2) for the bonded screen, the buried serve (momwire#553)
for the two detached ones. The buried-radial vertical's `detached` variant
is the deliberate exception: it sits inside NEC-5's scope and OUTSIDE
momwire's (#567), and its gates pin that mirror in both directions. Scope
is a property of the geometry, so it is checkable without solving, and
these tests check it two ways:

  * directly on `build_wires()` — segment orientation, the right-angle
    rise, the node topology, the feed spelling, and that the knobs move
    the geometry they claim to;
  * through the momwire adapter, by constructing the solver and asking it
    for its own labels (`_wire_media`, `_crossing_junctions`). Those are
    the methods that RAISE the by-name refusals, so a deck that drifts out
    of scope fails here rather than after a multi-minute fill.

Nothing here solves. A buried impedance is a mixed-medium fill measured in
minutes, which is exactly what the suite's ~2 s-per-test rule exists to
keep out; the numbers those solves produce are momwire's to gate, and it
does (`momwire/tests/test_crossing_serve_524.py`,
`test_buried_serve_553.py`).
"""

from __future__ import annotations

import math
import sys

import pytest

from antennaknobs import as_wire, resolve_variant_params
from antennaknobs.designs.specialty.buried_dipole import Builder as BuriedDipole
from antennaknobs.designs.verticals.buried_radial_vertical import (
    Builder as BuriedRadialVertical,
)
from antennaknobs.designs.verticals.elevated_buried_counterpoise import (
    Builder as ElevatedBuriedCounterpoise,
)
from antennaknobs.engines.momwire import MomwireEngine
from antennaknobs.engines.nec5 import NEC5Engine

C_LIGHT = 299792458.0

# The soil the buried anchors were measured over (momwire's SOIL_A):
# eps_r 13, sigma 0.005 S/m. Only the LABELS depend on it here — a wire is
# below the interface or it isn't — but the solver refuses to construct a
# buried deck without a lower medium at all, so it has to be a real one.
SOIL_A = (13.0, 0.005)


def _wires(builder):
    return [as_wire(w) for w in builder.build_wires()]


def _solver(builder):
    """The solver the momwire engine WOULD fill, built and not run.

    Goes through `MomwireEngine` rather than hand-rolling polylines so the
    test sees exactly what a real solve sees: auto_mesh's segment counts,
    the polyline walk's junction derivation, and the Sommerfeld ground
    kwargs the `("finite", ...)` spec resolves to.
    """
    engine = MomwireEngine(builder, ground=("finite",) + SOIL_A, ground_z=0.0)
    return engine, engine._make_solver(wavelength=C_LIGHT / (builder.freq * 1e6))


def _is_vertical(w):
    return w.p0[0] == w.p1[0] and w.p0[1] == w.p1[1] and w.p0[2] != w.p1[2]


def _is_horizontal(w):
    return w.p0[2] == w.p1[2]


# ---------------------------------------------------------------------------
# verticals.buried_radial_vertical — the crossing-serve deck
# ---------------------------------------------------------------------------


def test_brv_every_segment_is_horizontal_or_vertical():
    """The crossing serve's corner regularization is measured for a
    right-angle bend only. A slanted radial-to-rise transition — the
    obvious way to spell "the radial comes up to the feedpoint" — would
    carry current across the interface at an angle with no pinned
    convention, so the H/V purity is a scope requirement, not a style."""
    for w in _wires(BuriedRadialVertical()):
        assert _is_horizontal(w) or _is_vertical(w), w


def test_brv_each_radial_runs_at_depth_then_rises_at_a_right_angle():
    b = BuriedRadialVertical()
    b.n_radials = 4
    ws = _wires(b)
    depth = b.depth
    hub = (0.0, 0.0, -depth)
    node = (0.0, 0.0, 0.0)

    # Wire pairs 0..7 are (radial run, its rise); 8/9 are feed gap + radiator.
    runs = ws[0:8:2]
    rises = ws[1:8:2]
    assert len(runs) == len(rises) == 4

    for run, rise in zip(runs, rises):
        # The horizontal leg lies wholly at depth and LEAVES the hub —
        # hub-first authoring is load-bearing: it makes the polyline walk
        # start every radial at the hub, which keeps the +/-x and +/-y
        # meshes exact mirror images and the crossing fill's exact-triple
        # memo at its full ~4x dedup (momwire#688's census).
        assert run.p0[2] == -depth and run.p1[2] == -depth
        assert tuple(run.p0) == hub
        # ...and the rise leaves that same point straight up to the node.
        assert tuple(rise.p0) == hub
        assert tuple(rise.p1) == node
        assert _is_vertical(rise)
        # The bend is a right angle: the run has no z component, the rise
        # no x/y component.
        assert run.p0[2] - run.p1[2] == 0.0
        assert rise.p0[0] == rise.p1[0] == 0.0
        assert rise.p0[1] == rise.p1[1] == 0.0


def test_brv_radial_tips_are_free_and_only_the_node_touches_the_plane():
    """Scope: exactly one junction in the plane, radial far ends free, and
    nothing else crossing or lying in z = 0."""
    b = BuriedRadialVertical()
    ws = _wires(b)
    radial = 0.25 * b.design_wavelength * b.length_factor * b.radial_factor

    tips = [w.p1 for w in ws[0 : 2 * b.n_radials : 2]]
    for tip in tips:
        assert tip[2] == -b.depth  # buried, not reaching the plane
        assert math.hypot(tip[0], tip[1]) == pytest.approx(radial)

    at_plane = [w for w in ws if w.p0[2] == 0.0 or w.p1[2] == 0.0]
    # The N rises, the driven gap: every one of them ends AT the node, and
    # none of them lies in the plane.
    assert len(at_plane) == b.n_radials + 1
    for w in at_plane:
        assert not (w.p0[2] == 0.0 and w.p1[2] == 0.0)


def test_brv_feed_is_a_base_gap_on_the_radiator_not_a_midpoint_excitation():
    """The one feed trap this deck carries.

    `ex=` on a full-length wire places the excitation at that wire's
    MIDPOINT (see `flat_wires_to_polylines`), so driving the whole radiator
    would model a mid-element shunt tap instead of a base feed. The design
    uses the house eps-gap idiom, and the check is on the resolved feed
    ARCLENGTH: it must sit within the gap at the foot of the radiator, not
    halfway up it.
    """
    b = BuriedRadialVertical()
    engine, _ = _solver(b)
    height = 0.25 * b.design_wavelength * b.length_factor

    assert len(engine._feeds) == 1
    pl_idx, arclength, voltage = engine._feeds[0]
    assert voltage == 1 + 0j
    # The feed polyline starts at the node and runs up: the gap is the
    # first 0.05 m of it, so the feed sits at 0.025 m — three orders below
    # the midpoint a whole-wire `ex=` would have produced.
    assert engine._polylines[pl_idx][0].tolist() == [0.0, 0.0, 0.0]
    assert arclength == pytest.approx(0.025)
    assert arclength < 0.01 * height


def test_brv_knobs_move_the_geometry():
    """n_radials and depth are the two knobs the served spelling is most
    sensitive to; pin that they reach the wires."""
    base = BuriedRadialVertical()
    assert len(_wires(base)) == 2 * 4 + 2  # 4 x (run + rise) + gap + radiator

    more = BuriedRadialVertical()
    more.n_radials = 2
    assert len(_wires(more)) == 2 * 2 + 2

    deeper = BuriedRadialVertical()
    deeper.depth = 0.4
    assert {w.p0[2] for w in _wires(deeper)[0:8:2]} == {-0.4}
    # The rise lengthens with the depth; the radiator does not move.
    assert _wires(deeper)[1].p0[2] == -0.4
    assert _wires(deeper)[-1].p1[2] == _wires(base)[-1].p1[2]

    longer = BuriedRadialVertical()
    longer.radial_factor = 0.5
    tip = _wires(longer)[0].p1
    assert math.hypot(tip[0], tip[1]) == pytest.approx(
        0.5 * 0.25 * longer.design_wavelength
    )


def test_brv_n_radials_floor_keeps_the_node_a_junction():
    """The floor of 2 is a framework constraint, not a physics one: this
    package derives junctions from endpoint DEGREE, so a one-radial screen
    leaves the node degree-2, the walk threads straight through it, and
    momwire receives a single polyline crossing the interface mid-span.
    The builder clamps rather than emitting that deck."""
    one = BuriedRadialVertical()
    one.n_radials = 1
    assert len(_wires(one)) == 2 * 2 + 2


# ---------------------------------------------------------------------------
# verticals.buried_radial_vertical:detached — the stake-convention mirror
# ---------------------------------------------------------------------------


def _detached():
    return BuriedRadialVertical(
        params=resolve_variant_params(BuriedRadialVertical, "detached")
    )


def test_brv_detached_has_no_rises_and_a_contact_end():
    """The stake convention (momwire#567 anchor class): N radial runs at
    depth joined at a centre point, NO rises, and the monopole's driven
    gap standing its lower end in the plane as a ground CONTACT — the
    exact structural difference from the default, which is what makes the
    two variants two different antennas rather than two meshes."""
    b = _detached()
    ws = _wires(b)
    hub = (0.0, 0.0, -b.depth)

    # n_radials runs + gap + radiator, and nothing else: the rises' absence
    # IS the variant.
    assert len(ws) == b.n_radials + 2

    runs, gap, radiator = ws[: b.n_radials], ws[-2], ws[-1]
    for run in runs:
        assert run.p0[2] == run.p1[2] == -b.depth
        assert tuple(run.p0) == hub
    # The gap contacts the plane from above; only it touches z = 0.
    assert tuple(gap.p0) == (0.0, 0.0, 0.0) and gap.ex == 1 + 0j
    assert gap.p1[2] > 0.0 and radiator.p1[2] > 0.0
    assert [w for w in ws if w.p0[2] == 0.0 or w.p1[2] == 0.0] == [gap]


def test_brv_detached_spells_no_coincident_wires():
    """The default's N-coincident-rise bundle is exactly what the NEC-5
    wrapper refuses by name; the variant must not carry a single duplicated
    endpoint pair, at any radial count."""
    for n in (2, 3, 4):
        b = _detached()
        b.n_radials = n
        keys = [tuple(sorted((tuple(w.p0), tuple(w.p1)))) for w in _wires(b)]
        assert len(keys) == len(set(keys))


def test_brv_detached_same_knobs_move_the_same_geometry():
    """The variant promises the DEFAULT's knobs, unchanged in meaning."""
    fewer = _detached()
    fewer.n_radials = 2
    assert len(_wires(fewer)) == 2 + 2

    deeper = _detached()
    deeper.depth = 0.4
    assert {w.p0[2] for w in _wires(deeper)[:4]} == {-0.4}
    # No rise to lengthen: the radiator still starts at the plane.
    assert _wires(deeper)[-2].p0[2] == 0.0

    longer = _detached()
    longer.radial_factor = 0.5
    tip = _wires(longer)[0].p1
    assert math.hypot(tip[0], tip[1]) == pytest.approx(
        0.5 * 0.25 * longer.design_wavelength
    )


def test_brv_detached_momwire_refuses_by_name():
    """momwire's #567 scope sentence, on the deck the adapter actually
    builds: ground contact plus a buried wire is the combination its
    contact-image fiction cannot serve, and the refusal fires at the
    labeling step — before any fill — pointing back at the connected
    spelling it does serve."""
    _engine, s = _solver(_detached())
    with pytest.raises(ValueError, match="ground CONTACT"):
        s._wire_media()


def test_brv_detached_nec5_serves_what_the_default_refuses(monkeypatch):
    """The engine mirror, both directions, at construction time: NEC-5
    takes the detached spelling (and rides the buried GE 1 -1 stage), and
    refuses the default's coincident bundle with a message that names this
    variant as the way out."""
    monkeypatch.setenv("NEC5_EXE", sys.executable)

    b = _detached()
    engine = NEC5Engine(b, ground=("finite",) + SOIL_A)
    assert "GE 1 -1" in engine.deck([b.freq]).splitlines()

    with pytest.raises(NotImplementedError, match="detached"):
        NEC5Engine(BuriedRadialVertical(), ground=("finite",) + SOIL_A)


# ---------------------------------------------------------------------------
# verticals.elevated_buried_counterpoise — detached, nothing at the plane
# ---------------------------------------------------------------------------


def test_ebc_radiator_is_wholly_above_and_screen_wholly_below():
    b = ElevatedBuriedCounterpoise()
    ws = _wires(b)
    radiator, screen = ws[:2], ws[2:]

    for w in radiator:
        assert w.p0[2] >= b.base > 0.0
        assert w.p1[2] >= b.base > 0.0
    for w in screen:
        assert w.p0[2] == w.p1[2] == -b.depth < 0.0
    # No conductor anywhere near the interface.
    assert min(w.p0[2] for w in radiator) == pytest.approx(b.base)
    assert all(_is_horizontal(w) for w in screen)


def test_ebc_knobs_move_the_geometry():
    base = ElevatedBuriedCounterpoise()
    assert len(_wires(base)) == 2 + 4

    single = ElevatedBuriedCounterpoise()
    single.n_radials = 1
    assert len(_wires(single)) == 2 + 1

    lifted = ElevatedBuriedCounterpoise()
    lifted.base = 2.0
    assert _wires(lifted)[0].p0 == (0.0, 0.0, 2.0)

    deeper = ElevatedBuriedCounterpoise()
    deeper.depth = 0.35
    assert {w.p0[2] for w in _wires(deeper)[2:]} == {-0.35}


def test_ebc_feed_is_the_house_gap_at_the_radiator_foot():
    b = ElevatedBuriedCounterpoise()
    engine, _ = _solver(b)
    assert len(engine._feeds) == 1
    pl_idx, arclength, voltage = engine._feeds[0]
    assert voltage == 1 + 0j
    assert engine._polylines[pl_idx][0].tolist() == [0.0, 0.0, b.base]
    assert arclength == pytest.approx(0.025)


# ---------------------------------------------------------------------------
# specialty.buried_dipole — the phase-0 wholly-below deck
# ---------------------------------------------------------------------------


def test_bd_is_one_straight_horizontal_wire_strictly_below_the_plane():
    b = BuriedDipole()
    ws = _wires(b)
    assert len(ws) == 3  # arm, driven gap, arm
    for w in ws:
        assert _is_horizontal(w)
        assert w.p0[2] == w.p1[2] == -b.depth < 0.0
        assert w.p0[1] == w.p1[1] == 0.0
    # Collinear along x, end to end, with the gap in the middle.
    assert ws[0].p1 == ws[1].p0
    assert ws[1].p1 == ws[2].p0
    assert ws[1].ex == 1 + 0j
    assert ws[0].ex is None and ws[2].ex is None
    assert ws[0].p0[0] == -ws[2].p1[0]


def test_bd_velocity_factor_sizes_the_wire_to_a_medium_half_wave():
    """The design's whole point: the wire is cut to a half-wave IN THE
    SOIL, so the free-space geometry is ~1/sqrt(eps_r) of a free-space
    half-wave. Both sizing knobs must reach the ends."""
    b = BuriedDipole()
    half = 0.25 * b.design_wavelength * b.velocity_factor * b.length_factor
    assert _wires(b)[2].p1[0] == pytest.approx(half)

    free = BuriedDipole()
    free.velocity_factor = 1.0
    assert _wires(free)[2].p1[0] == pytest.approx(0.25 * free.design_wavelength)

    scaled = BuriedDipole()
    scaled.length_factor = 0.5
    assert _wires(scaled)[2].p1[0] == pytest.approx(0.5 * half)

    deeper = BuriedDipole()
    deeper.depth = 0.3
    assert {w.p0[2] for w in _wires(deeper)} == {-0.3}


# ---------------------------------------------------------------------------
# momwire scope labeling — constructed, never solved
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("n_radials", [2, 3, 4])
def test_brv_labels_as_the_crossing_serve(n_radials):
    """The fan widening's labeling shape, read off the deck the adapter
    actually builds: N below members meeting ONE above member at a
    crossing junction in the plane.

    Two things differ from momwire's own `fan_rise_deck` fixture, both
    consequences of this package deriving polylines from wire endpoints
    rather than authoring them:

      * momwire spells each radial as one polyline that runs at depth and
        then rises; here the shared hub at (0, 0, -depth) is a degree-2N
        node, so the walk splits every radial into a run and a rise. The
        media tuple is therefore 2N below labels, not N.
      * that same hub becomes junction 0 (an ordinary wholly-below OTHER
        junction, which the scope allows), so the crossing junction is
        index 1, not 0.

    The scope-relevant facts are unchanged and are what this asserts: the
    grounded junction has exactly one above member, everything else is
    below, and `_crossing_junctions` returns without raising.
    """
    from momwire import _medium_spec

    b = BuriedRadialVertical()
    b.n_radials = n_radials
    _engine, s = _solver(b)

    media = s._wire_media()
    assert media == (_medium_spec.BELOW,) * (2 * n_radials) + (_medium_spec.ABOVE,)

    crossing = s._crossing_junctions()
    assert crossing == (1,)

    # The crossing node: N rises below, the radiator above — the 1-above x
    # N-below fan the serve is scoped to.
    members = s.junctions[crossing[0]]
    assert sum(1 for w, _e in members if media[w] == _medium_spec.ABOVE) == 1
    assert sum(1 for w, _e in members if media[w] == _medium_spec.BELOW) == n_radials
    # ...and the hub is the allowed below-side other junction.
    assert all(media[w] == _medium_spec.BELOW for w, _e in s.junctions[0])


@pytest.mark.parametrize("n_radials", [1, 2, 4])
def test_ebc_labels_with_no_crossing_junction(n_radials):
    from momwire import _medium_spec

    b = ElevatedBuriedCounterpoise()
    b.n_radials = n_radials
    _engine, s = _solver(b)

    media = s._wire_media()
    # Polyline 0 is the radiator (feed gap + shaft merge into one walk);
    # the rest is screen. Two radials merge through their degree-2 hub
    # into a single straight polyline, which is why the below count is not
    # simply n_radials.
    assert media[0] == _medium_spec.ABOVE
    assert set(media[1:]) == {_medium_spec.BELOW}
    assert s._crossing_junctions() == ()


def test_bd_labels_as_a_wholly_buried_deck():
    from momwire import _medium_spec

    _engine, s = _solver(BuriedDipole())
    assert s._wire_media() == (_medium_spec.BELOW,)
    assert s._crossing_junctions() == ()


def test_buried_decks_stay_inside_the_one_radius_rule():
    """The crossing serve refuses a per-wire radius by name. None of the
    three designs overrides `build_wire_material` or carries a per-wire
    `spec`, so the whole deck solves at one radius — pinned here because a
    future per-wire tweak would break the bonded design at fill time, not
    at build time."""
    for cls in (BuriedRadialVertical, ElevatedBuriedCounterpoise, BuriedDipole):
        b = cls()
        assert b.build_wire_material() is None, cls
        assert all(w.spec is None for w in _wires(b)), cls
