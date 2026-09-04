"""Design-dependent constraint inputs on the served descriptor (#1006 G2-5).

The coupling warnings must be LIVE derived state, recomputed on every design
change — not a one-time check when an engine is picked. The app already has
that mechanism for `requires_backends` (descriptor -> `backendAllowed` ->
`backendDisallowed` -> the solve is withheld), and G2-5 generalises it rather
than running a second path beside it. This file gates the two inputs that
generalisation needs from the server.

`has_stepped_radius_junction` — momwire refuses `extended_kernel=True` on a
deck whose junction joins wires of different radii (momwire#398 D2). Asked of
the DESIGN because that is what the refusal is about; the backend and the
kernel setting are the other two thirds and live on the other side.

`backend_restriction` — the existing allowlist, now carrying the reason for
ITS OWN cause. That retires the frontend's single `RESTRICTED_BACKEND_REASON`,
whose own comment asked to be broadened "if _required_backends ever grows
another cause". It grew one at issue #898 and the copy did not follow, so the
constant is ALREADY false for a vertex-port design — see the test below. This
is a bug fix wearing a refactor's clothes.

Test decks are real catalog designs, found by scanning all 103 rather than
fabricated: `verticals.elt_whip` is the ONLY design in the catalog with a
stepped-radius junction, and it is the telescoping whip the geometry predicts.
"""

from __future__ import annotations

import pytest

import antennaknobs.web.server  # noqa: F401 — resolves the adapter import cycle
from antennaknobs.cli import resolve_class
from antennaknobs.web.adapter import (
    _JUNCTION_PORT_BACKENDS,
    _has_buried_wire,
    _RESTRICTION_REASONS,
    _VERTEX_PORT_BACKENDS,
    _backend_restriction,
    _has_stepped_radius_junction,
)
from antennaknobs.web.examples import REGISTRY

# The one stepped design in the catalog, and two that are not: one WITH
# junctions (so a false positive cannot hide behind "no junctions at all") and
# one with none.
STEPPED = "verticals.elt_whip"
UNIFORM_WITH_JUNCTIONS = "arrays.bowtiearray1x2"
NO_JUNCTIONS = "dipoles.invvee"


def test_the_stepped_design_is_recognised_and_the_uniform_ones_are_not():
    assert _has_stepped_radius_junction(resolve_class(STEPPED)) is True
    assert _has_stepped_radius_junction(resolve_class(UNIFORM_WITH_JUNCTIONS)) is False
    assert _has_stepped_radius_junction(resolve_class(NO_JUNCTIONS)) is False


def test_the_uniform_control_actually_has_junctions():
    """Otherwise the negative case above proves nothing.

    A design with no junctions cannot have a stepped one, so it would answer
    False for a reason that has nothing to do with radii. The control deck has
    to be one where the question is real and the answer is still no.
    """
    from antennaknobs.geometry import flat_wires_to_polylines

    b = resolve_class(UNIFORM_WITH_JUNCTIONS)()
    translated = flat_wires_to_polylines(b.build_wires())
    assert translated["junctions"], f"{UNIFORM_WITH_JUNCTIONS} has no junctions"


def test_exactly_one_catalog_design_is_stepped():
    """Scope, pinned. The whole design-dependent surface of this feature is
    four decks — this one plus the three buried — and that is worth failing on
    if it silently grows, because a fifth would mean a design was added that
    nobody checked against the extended kernel."""
    from antennaknobs.cli import list_builtin_designs

    stepped = [
        n
        for n in list_builtin_designs()
        if _has_stepped_radius_junction(resolve_class(n))
    ]
    assert stepped == [STEPPED], stepped


def test_the_field_reaches_the_registry():
    """The descriptor is built from the registered example, so a helper that
    works but is never wired is the failure this catches."""
    assert REGISTRY[STEPPED].has_stepped_radius_junction is True
    assert REGISTRY[UNIFORM_WITH_JUNCTIONS].has_stepped_radius_junction is False


# --------------------------------------------------------------------------
# The restriction, and the falsehood retiring the frontend constant fixes
# --------------------------------------------------------------------------


def test_each_restriction_cause_carries_ITS_OWN_reason():
    """Two causes, two sentences — the point of serving the reason at all.

    A single sentence per restriction is what the frontend has today, and it
    is wrong for one of the two: the junction-port copy claims "only the
    B-spline and sinusoidal-Galerkin solvers", while a vertex-port design
    allows five backends including NEC-5.
    """
    j = _backend_restriction(_JUNCTION_PORT_BACKENDS)
    v = _backend_restriction(_VERTEX_PORT_BACKENDS)
    assert j["reason"] == _RESTRICTION_REASONS["junction_ports"]
    assert v["reason"] == _RESTRICTION_REASONS["vertex_ports"]
    assert j["reason"] != v["reason"]
    assert _backend_restriction(None) is None


def test_the_frontends_single_sentence_is_already_false_for_a_real_design():
    """Not hypothetical, and the reason this is a fix rather than a tidy.

    `dipoles.invvee_apex` is restricted by the VERTEX-port cause and allows
    five backends. The frontend's one constant says only two solvers implement
    the thing — a user on that design reads a sentence that contradicts the
    tabs they can see enabled.
    """
    ex = REGISTRY["dipoles.invvee_apex"]
    assert ex.backend_restriction is not None
    assert len(ex.backend_restriction["backends"]) == 5
    assert "nec5" in ex.backend_restriction["backends"]
    assert ex.backend_restriction["reason"] == _RESTRICTION_REASONS["vertex_ports"]
    # The retiring constant's claim, as a string, against what is served:
    assert (
        "only the B-spline and sinusoidal-Galerkin"
        not in (ex.backend_restriction["reason"])
    )


def test_an_unknown_cause_gets_no_reason_rather_than_a_wrong_one():
    """A third cause that forgets a sentence must not inherit another's.

    None lets the gate fall back to generic copy — a worse message, not a
    false one. Inheriting would be the failure this whole change is about.
    """
    got = _backend_restriction(("bspline",))  # neither known tuple
    assert got["backends"] == ["bspline"]
    assert got["reason"] is None


@pytest.mark.parametrize("name", [STEPPED, UNIFORM_WITH_JUNCTIONS, NO_JUNCTIONS])
def test_a_design_that_will_not_build_never_breaks_a_listing(name, monkeypatch):
    """The helper answers False rather than raising, on `_required_backends`'
    precedent: a hint must never be the thing that breaks the design list, and
    a design's real error belongs on the solve path where a user sees it."""
    import antennaknobs.web.adapter as ad

    def boom(*a, **k):
        raise RuntimeError("deliberate")

    monkeypatch.setattr(ad, "_build_builder", boom)
    assert ad._has_stepped_radius_junction(resolve_class(name)) is False


# --------------------------------------------------------------------------
# The buried input (#1006 G2-5), the design side of momwire#553
# --------------------------------------------------------------------------

# The three buried decks, and one that sits ON the interface rather than below
# it — `contact` is a different axis value with different refusals, so a helper
# that treated z == 0 as buried would grey out the extended kernel across every
# ground-plane design in the catalog.
BURIED = [
    "specialty.buried_dipole",
    "verticals.buried_radial_vertical",
    "verticals.elevated_buried_counterpoise",
]


def test_exactly_the_three_buried_decks_are_recognised():
    from antennaknobs.cli import list_builtin_designs

    got = [n for n in list_builtin_designs() if _has_buried_wire(resolve_class(n))]
    assert got == BURIED, got


def test_a_design_on_the_interface_is_not_buried():
    """`contact`, not `buried`. Strictly below, and the negative case has to be
    a deck that actually touches z = 0 — a deck floating above it would answer
    False for a reason that has nothing to do with the boundary."""
    assert _has_buried_wire(resolve_class(STEPPED)) is False
    assert _has_buried_wire(resolve_class(NO_JUNCTIONS)) is False


def test_the_buried_field_reaches_the_registry():
    for name in BURIED:
        assert REGISTRY[name].has_buried_wire is True
    assert REGISTRY[STEPPED].has_buried_wire is False


def test_buried_is_NOT_read_off_the_ground_requirement():
    """They agree on today's catalog, and that agreement is the trap.

    `ground_requirement == "sommerfeld"` is a hand-declared statement in a
    design's `ui_params` about which ground model it needs to mean anything.
    `has_buried_wire` is a measurement of the built geometry. Reading the first
    as if it were the second would make a hand-edited hint decide whether
    momwire's refusal fires — so this asserts the two are computed
    independently, by moving one and requiring the other to stay put.
    """
    sommerfeld = sorted(
        n for n, e in REGISTRY.items() if e.ground_requirement == "sommerfeld"
    )
    assert sommerfeld == BURIED, "the premise moved; re-measure before trusting"

    ex = REGISTRY[BURIED[0]]
    saved = ex.ground_requirement
    try:
        object.__setattr__(ex, "ground_requirement", None)
        assert _has_buried_wire(resolve_class(BURIED[0])) is True
    finally:
        object.__setattr__(ex, "ground_requirement", saved)


@pytest.mark.parametrize("name", BURIED)
def test_a_buried_design_that_will_not_build_never_breaks_a_listing(name, monkeypatch):
    import antennaknobs.web.adapter as ad

    def boom(*a, **k):
        raise RuntimeError("deliberate")

    monkeypatch.setattr(ad, "_build_builder", boom)
    assert ad._has_buried_wire(resolve_class(name)) is False
