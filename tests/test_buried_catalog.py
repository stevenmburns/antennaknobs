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
from momwire import _medium_spec

from conftest import needs_nec5
from momwire import RazorSolver

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


def test_brv_radials_run_at_depth_to_a_hub_with_ONE_rise():
    """The hub spelling (issue #1108): N radial runs to a shared hub and a
    SINGLE rise from it to the node. The pre-#1108 default put one rise per
    radial, coincident by construction — that spelling survives as the
    `bundle` variant and is gated separately."""
    b = BuriedRadialVertical()
    b.n_radials = 4
    ws = _wires(b)
    depth = b.depth
    hub = (0.0, 0.0, -depth)
    node = (0.0, 0.0, 0.0)

    runs = ws[0:4]
    (rise,) = ws[4:5]
    assert len(runs) == 4

    for run in runs:
        # The horizontal leg lies wholly at depth and LEAVES the hub —
        # hub-first authoring is load-bearing: it makes the polyline walk
        # start every radial at the hub, which keeps the +/-x and +/-y
        # meshes exact mirror images and the crossing fill's exact-triple
        # memo at its full ~4x dedup (momwire#688's census).
        assert run.p0[2] == -depth and run.p1[2] == -depth
        assert tuple(run.p0) == hub
        # The bend is a right angle: the run has no z component...
        assert run.p0[2] - run.p1[2] == 0.0

    # ...and exactly one rise leaves that same point straight up to the node.
    assert tuple(rise.p0) == hub
    assert tuple(rise.p1) == node
    assert _is_vertical(rise)
    assert rise.p0[0] == rise.p1[0] == 0.0
    assert rise.p0[1] == rise.p1[1] == 0.0
    assert sum(1 for w in ws if tuple(w.p0) == hub and tuple(w.p1) == node) == 1


def test_brv_the_bundle_variant_keeps_the_pre_1108_spelling():
    """The record the `bundle` variant exists to preserve: one rise per
    radial, every one of them coincident. Two structures, not two meshes —
    a bundle of N coincident thin wires is not one wire of the same radius
    (momwire#524's fan widening), so the two are never gated against each
    other."""
    b = BuriedRadialVertical(
        params=resolve_variant_params(BuriedRadialVertical, "bundle")
    )
    ws = _wires(b)
    hub = (0.0, 0.0, -b.depth)
    node = (0.0, 0.0, 0.0)
    rises = [w for w in ws if tuple(w.p0) == hub and tuple(w.p1) == node]
    assert len(rises) == b.n_radials
    assert len(ws) == 2 * b.n_radials + 2


def test_brv_radial_tips_are_free_and_only_the_node_touches_the_plane():
    """Scope: exactly one junction in the plane, radial far ends free, and
    nothing else crossing or lying in z = 0."""
    b = BuriedRadialVertical()
    ws = _wires(b)
    radial = 0.25 * b.design_wavelength * b.length_factor * b.radial_factor

    tips = [w.p1 for w in ws[: b.n_radials]]
    for tip in tips:
        assert tip[2] == -b.depth  # buried, not reaching the plane
        assert math.hypot(tip[0], tip[1]) == pytest.approx(radial)

    at_plane = [w for w in ws if w.p0[2] == 0.0 or w.p1[2] == 0.0]
    # The ONE rise and the driven gap: both end AT the node, and neither
    # lies in the plane (issue #1108 — before it, N rises did).
    assert len(at_plane) == 2
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
    assert len(_wires(base)) == 4 + 1 + 2  # 4 runs + ONE rise + gap + radiator

    more = BuriedRadialVertical()
    more.n_radials = 2
    assert len(_wires(more)) == 2 + 1 + 2

    deeper = BuriedRadialVertical()
    deeper.depth = 0.4
    assert {w.p0[2] for w in _wires(deeper)[:4]} == {-0.4}
    # The rise lengthens with the depth; the radiator does not move.
    assert _wires(deeper)[4].p0[2] == -0.4
    assert _wires(deeper)[-1].p1[2] == _wires(base)[-1].p1[2]

    longer = BuriedRadialVertical()
    longer.radial_factor = 0.5
    tip = _wires(longer)[0].p1
    assert math.hypot(tip[0], tip[1]) == pytest.approx(
        0.5 * 0.25 * longer.design_wavelength
    )


def test_brv_one_radial_is_a_deck_now():
    """The old floor of 2 was never physics. It was the polyline walk: a
    one-radial screen left the node at degree 2, the walk threaded straight
    through it, and momwire received a single polyline crossing the interface
    mid-span. Issue #1109 ends a polyline at every wire end lying in the
    plane, so the node is a declared junction at ANY radial count and the
    clamp is 1."""
    one = BuriedRadialVertical()
    one.n_radials = 1
    assert len(_wires(one)) == 1 + 1 + 2

    _engine, s = _solver(one)
    crossing = s._crossing_junctions()
    assert len(crossing) == 1
    media = s._wire_media()
    members = s.junctions[crossing[0]]
    assert sum(1 for w, _e in members if media[w] == _medium_spec.ABOVE) == 1
    assert sum(1 for w, _e in members if media[w] == _medium_spec.BELOW) == 1


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


def test_brv_nec5_now_takes_the_connected_default_too(monkeypatch):
    """The mirror is gone on this side, and that is issue #1108's point.

    NEC-5 used to refuse the connected spelling — not because of the physics
    but because the DEFAULT was N coincident rises, for which the binary
    silently prints garbage. The hub spelling has one rise and no coincident
    wires, and #1110 expands its graded wires into GW cards, so NEC-5 now
    builds the same conductor momwire does. The `bundle` variant keeps the
    old refusal, with the message that names a way out.
    """
    monkeypatch.setenv("NEC5_EXE", sys.executable)

    b = BuriedRadialVertical()
    engine = NEC5Engine(b, ground=("finite",) + SOIL_A)
    lines = engine.deck([b.freq]).splitlines()
    # Ground flag -1: the deck has buried wires, and burial is what decides
    # the flag (antennaknobs#1025). It was 1 while this wrapper read GE's
    # SECOND field as the buried selector; keyed on burial, this deck's print
    # moves 49.620+20.877j -> 77.805+44.468j and its distance from momwire in
    # R goes 34.58 % -> 2.58 %.
    assert "GE -1 0" in lines
    # the graded rise and radiator became several GW cards, and the deck
    # carries exactly one rise from the hub to the node
    gw = [ln for ln in lines if ln.startswith("GW ")]
    assert len(gw) > len(_wires(b))

    # The detached variant is REFUSED rather than spelled. It has NO rise, so
    # its monopole stands its lower end IN the plane with nothing continuing
    # below, over buried radials: flag -1 leaves that node without a basis
    # function (the deck reads 598.320-54434.000j, an open circuit) and flag 1
    # is documented as not usable with buried wires. There is no spelling to
    # choose between, so it refuses.
    with pytest.raises(NotImplementedError, match="ends ON the ground plane"):
        NEC5Engine(_detached(), ground=("finite",) + SOIL_A)

    with pytest.raises(NotImplementedError, match="detached"):
        NEC5Engine(
            BuriedRadialVertical(
                params=resolve_variant_params(BuriedRadialVertical, "bundle")
            ),
            ground=("finite",) + SOIL_A,
        )


@needs_nec5
def test_brv_nec5_solves_the_connected_default_and_banks_its_print(record_property):
    """The record, not a gate on agreement — but the record changed (#1025).

    This used to bank 49.78 + 20.95j and explain the ~30 ohm distance from
    momwire as intrinsic: "NEC-5's interface node is a point electrode and
    momwire's is the crossing fill, so the two answers are ~30 ohm apart by
    construction". That explanation was measured and did not survive. The
    distance was mostly the GROUND FLAG: this wrapper wrote the flag that
    bonds a node at z=0 to ground, which is documented as not usable when
    wires are buried. Keyed on burial instead, the same deck prints
    77.805 + 44.468j and sits 2.58 % from momwire in R rather than 34.58 %.

    So the two engines are NOT ~30 ohm apart by construction on this deck, and
    the interface-node difference — whatever remains of it — is smaller than
    the flag error that was standing in front of it.

    The bar stays deliberately loose (5 ohm) and stays a smoke bound: it
    exists to catch a deck that stopped being this antenna, not to assert
    cross-engine agreement.
    """
    b = BuriedRadialVertical()
    z = NEC5Engine(b, ground=("finite",) + SOIL_A).impedance()
    z = complex(z[0] if isinstance(z, list) else z)
    record_property("nec5_Z", f"{z:.4f}")
    assert abs(z - (77.805 + 44.468j)) < 5.0, z


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

    The hub spelling (issue #1108) makes this the SIMPLEST shape the crossing
    serve has: ONE above member against ONE below member, whatever the radial
    count. Before it, the node carried N coincident rises purely to raise its
    degree, and the serve saw a 1-above x N-below fan.

    What the walk produces here: N radial runs, each its own polyline off the
    degree-(N+1) hub, plus the single rise — N+1 below labels — and the
    radiator above. The hub itself is junction 0, an ordinary wholly-below
    OTHER junction that the scope allows, so the crossing junction is index 1.

    The scope-relevant facts are what this asserts: the grounded junction has
    exactly one above member and one below member, everything else is below,
    and `_crossing_junctions` returns without raising.
    """
    b = BuriedRadialVertical()
    b.n_radials = n_radials
    _engine, s = _solver(b)

    media = s._wire_media()
    assert media == (_medium_spec.BELOW,) * (n_radials + 1) + (_medium_spec.ABOVE,)

    crossing = s._crossing_junctions()
    assert crossing == (1,)

    # The crossing node: ONE rise below, the radiator above.
    members = s.junctions[crossing[0]]
    assert len(members) == 2
    assert sum(1 for w, _e in members if media[w] == _medium_spec.ABOVE) == 1
    assert sum(1 for w, _e in members if media[w] == _medium_spec.BELOW) == 1
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


# ---------------------------------------------------------------------------
# razor-2p on the buried decks — the unit-3 gate, keyed on the capability cell
# ---------------------------------------------------------------------------
#
# momwire#814 (the razor buried arc, unit 3) ends with `razor-2p` serving
# these three decks. Until it does, `RazorSolver.capabilities.buried` is
# False and the constructor refuses each deck by name with the sentence its
# row declares — which is what these pin TODAY. The tests are written
# against the cell rather than against today's answer, so the arc's last
# unit flips them rather than rewriting them: when the cell becomes True
# the same tests demand razor's medium labels agree with bspline's on the
# same deck (which needs razor to expose `_wire_media` /
# `_crossing_junctions` as bspline does — a momwire#813 step-3 item).
# Nothing here solves; construction only, as above.
#
# The cell itself is newer than the last momwire RELEASE (the arc's #651/#812
# work landed after v0.46.0, and the release is held), so on an installed
# momwire that predates it these SKIP with that reason — the dev checkout is
# where they run today, and CI picks them up at the next momwire pin bump.
# A skip, not a fallback: the memory of the deleted `getattr` shrug in
# `engines/momwire.py` is why nothing here reads a missing cell as served.

_HAS_BURIED_CELL = hasattr(RazorSolver.capabilities, "buried")
_needs_buried_cell = pytest.mark.skipif(
    not _HAS_BURIED_CELL,
    reason="installed momwire predates the `buried` capability cell (unreleased)",
)


def _razor_solver(builder):
    engine = MomwireEngine(
        builder,
        solver=RazorSolver,
        solver_kwargs={"nec5_quadrature": True},
        ground=("finite",) + SOIL_A,
        ground_z=0.0,
    )
    return engine, engine._make_solver(wavelength=C_LIGHT / (builder.freq * 1e6))


_RAZOR_BURIED_CASES = (
    # (builder, the refusal cell(s) the deck reaches while `buried` is False)
    # Since #1109 the bonded screen's node is a DECLARED junction, so razor
    # reaches its declared-junction cell (`buried+crossing_junction`,
    # momwire#850) rather than the mid-span `buried+crossing` one; the plain
    # `buried` cell is always in the reached set below.
    pytest.param(
        BuriedRadialVertical, ("buried", "crossing_junction"), id="brv-crossing"
    ),
    pytest.param(ElevatedBuriedCounterpoise, ("buried",), id="ebc-detached-screen"),
    pytest.param(BuriedDipole, ("buried",), id="bd-wholly-below"),
)


@_needs_buried_cell
@pytest.mark.parametrize("cls,cells", _RAZOR_BURIED_CASES)
def test_razor_2p_on_the_buried_decks_follows_its_capability_cell(cls, cells):
    """While razor's `buried` cell is False, each buried deck refuses at
    construction with exactly a sentence the row DECLARES for a cell the
    geometry reaches — `buried` for all three, `buried+crossing_junction`
    too for the bonded screen. Which of the two the bonded screen gets
    depends on the order razor's constructor walks its refusals: before
    momwire#833 it detected the crossing first, since #833 it refuses at the
    `buried` cell unless the node is a declared junction (#1105), and since
    #1109 the node IS declared, so razor reaches its declared-junction cell
    (momwire#850). Both are the declared refusal-by-name this gate is for; an
    undeclared sentence, or none, is the failure. Once the cell is True,
    razor must label the same deck the way bspline does — the crossing
    serve's fan, the detached screens' wholly-below wires — so the flip is
    one line in momwire and this test is the antennaknobs half of
    momwire#814's DoD."""
    b = cls()
    caps = RazorSolver.capabilities
    if not caps.buried:
        reached = {c: caps.refusal(*c) for c in ({("buried",), cells})}
        for c, reason in reached.items():
            assert reason, f"{cls.__name__}: no declared refusal for {c}"
        with pytest.raises(ValueError) as excinfo:
            _razor_solver(b)
        msg = str(excinfo.value)
        hit = [c for c, reason in reached.items() if msg.endswith(reason)]
        assert hit, f"{cls.__name__}: refusal is not a declared sentence: {msg}"
        return

    # The flipped side: razor serves what bspline serves, and says so with
    # the same labels. `_wire_media` / `_crossing_junctions` are bspline's
    # names; the razor twin (momwire#812's medium labels) must spell them
    # the same way for the catalog to read one answer off both.
    _engine, bs = _solver(b)
    _engine, rz = _razor_solver(b)
    assert rz._wire_media() == bs._wire_media()
    assert rz._crossing_junctions() == bs._crossing_junctions()


@_needs_buried_cell
def test_the_razor_buried_gate_does_not_pass_by_accident():
    """The cell-keyed test above has two arms; this pins that the arm it is
    on today is the refusing one, so a momwire pin bump that flips the cell
    is noticed here as a change in which arm runs (and fails until razor
    carries the labels), never as a silently green test."""
    assert RazorSolver.capabilities.buried is False
    for cells in (("buried",), ("buried", "crossing")):
        assert RazorSolver.capabilities.refusal(*cells)


# ---------------------------------------------------------------------------
# The `bundle` variant — a razor refusal the buried flip will NOT retire
# ---------------------------------------------------------------------------
#
# momwire#856 gave razor a name for the bundle instead of a LAPACK death. The
# antennaknobs half of that is here, and it is a different shape from the
# cell-keyed gates above: the coincidence is singular "at any mesh, in free
# space and in soil alike, and whatever the quadrature", so unlike `buried`
# this refusal is permanent and is gated unconditionally.
#
# FREE SPACE on purpose. Razor's `buried` cell is False today, so a buried
# bundle refuses at CONSTRUCTION with the crossing sentence and never reaches
# the coincidence check at all — the bundle sentence is masked. Free space
# reaches it in 0.07 s and pays no buried fill (razor's buried crossing fill
# runs 20-45x bspline's, up to ~405 s on a hub deck, momwire#814).


def _razor_free_space(builder):
    engine = MomwireEngine(
        builder,
        solver=RazorSolver,
        solver_kwargs={"nec5_quadrature": True},
        ground=None,
        ground_z=None,
    )
    return engine, engine._make_solver(wavelength=C_LIGHT / (builder.freq * 1e6))


def _bundle_builder():
    return BuriedRadialVertical(
        params=resolve_variant_params(BuriedRadialVertical, "bundle")
    )


def test_brv_bundle_razor_refuses_the_coincidence_by_declared_name():
    """The declared sentence, read off the PUBLIC row rather than imported
    from `razor._BUNDLE_REFUSAL` — refusal-by-name means the name the row
    publishes, and reaching for the private constant would be a reach-through
    `tests/test_momwire_private_imports.py` exists to discourage.

    Pinned at SOLVE, and construction pinned to SUCCEED, because where this
    check sits is a design decision and not a placement detail (momwire#846):
    momwire#813's collapse adjudicators FILL a coincident deck and compare
    matrices without ever solving it, so moving the refusal earlier — the
    obvious tidy-up — would silently cost #813 its adjudicators. The fill is
    well defined on this deck; it is the SOLVE that has no answer.
    """
    declared = RazorSolver.capabilities.refusals["bundle"]
    assert declared, "razor's row no longer declares a `bundle` sentence"

    _engine, solver = _razor_free_space(_bundle_builder())  # must NOT raise

    with pytest.raises(ValueError) as excinfo:
        solver.compute_impedance()
    msg = str(excinfo.value)
    assert msg.endswith(declared), f"not the declared bundle sentence: {msg}"
    # The prefix is the diagnostic half: WHICH two segments coincide.
    assert "run between the same two points" in msg


def test_the_bundle_axis_is_not_reachable_through_the_refusal_cell_algebra():
    """`refusal("bundle")` answers None — which is how a row spells SERVED —
    on the one solver that cannot solve a bundle at all.

    This is the trap the whole #814 arc is about, in a third place: a
    capability question may only be asked of a row that HAS the field, and
    `bundle` is deliberately not promoted to an axis (momwire#846 leaves it as
    prose, because promoting it means declaring the axis on all eight rows
    against decks nobody has measured). So the declared sentence lives in
    `capabilities.refusals`, and asking the cell algebra instead gets a
    confident wrong answer. Pinned so nobody gates a bundle deck that way.
    """
    caps = RazorSolver.capabilities
    assert caps.refusal("bundle") is None
    assert "bundle" not in caps._fields
    assert caps.refusals["bundle"]


@_needs_buried_cell
def test_brv_bundle_buried_refuses_before_it_can_reach_the_coincidence():
    """Why the gate above is spelled in free space, pinned rather than
    described.

    While `buried` is False the buried refusal fires at construction, so the
    buried bundle never reaches the solve-time coincidence check. Both
    sentences are real and neither is wrong — they are two refusals of one
    deck, and which one you see is an ordering fact.

    That ordering is now expected to hold indefinitely: razor-2p's buried
    serve is SHELVED, not pending (momwire#813's parking comment). razor-2p
    stays the above-ground twin of licensed NEC-5, and bspline is the buried
    engine, because NEC-5's interface node is a known limitation underground
    (measured against Brown-Lewis-Epstein 1937) and razor-2p is first order in
    the far mesh besides (momwire#845). So this test's second arm is not a
    countdown — it is kept because the capability cell stays the single source
    of truth and a decision is not a guarantee.

    Nothing here solves a buried bundle either way: it would pay the 20-45x
    buried fill for a sentence the free-space gate above already holds.
    """
    caps = RazorSolver.capabilities
    b = _bundle_builder()
    if not caps.buried:
        with pytest.raises(ValueError) as excinfo:
            _razor_solver(b)
        msg = str(excinfo.value)
        declared = [s for s in caps.refusals.values() if s and msg.endswith(s)]
        assert declared, f"refusal is not a declared sentence: {msg}"
        return

    # Flipped: construction no longer refuses, and the coincidence is what is
    # left. Not solved here — see the docstring.
    _engine, _solver = _razor_solver(b)
