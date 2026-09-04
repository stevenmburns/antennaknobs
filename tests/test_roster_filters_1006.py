"""The rosters as statements over the product space (issue #1006 G2-4 a+c).

An engine is identified by a name in three places that do not agree — momwire's
`deck.BASES`, its `deck.NEC2_BASES`, and antennaknobs' `_BACKENDS`. #1006 asks
that each host's subset become a STATEMENT over the axes rather than an
accident. Measured, the three are three different things:

  * `NEC2_BASES` is ALREADY derived from an axis. momwire wrote it as
    `{name: e for name, e in BASES.items() if e[0].capabilities.centre_feeds}`,
    so #1006's thesis has a pre-existing example rather than one this unit
    created. What is gated is that it STAYS derived.
  * The EZNEC/NEC-5 seam is not a roster at all — see below.
  * antennaknobs' tabs are not a statement and cannot be made one — see below.

THE MIRROR, which is the one measured pair here. The nec2 dialect addresses
segment CENTRES; a node-addressing dialect addresses KNOTS. Those are the two
feed-grid cells momwire#611 and momwire#673 added, and the rows that miss each
grid are disjoint:

    centre_feeds=False  ->  {razor-2p, razor-nec5}   dropped by NEC2_BASES
    knot_feeds=False    ->  {pulse, sinusoidal}      refused by the node dialect

Neither set contains the other and neither is empty: a family that snaps to one
grid answers half a cell away on the other, in silence, which is why both cells
exist rather than one. These are declared per-row facts, so comparing them is a
measurement rather than a restatement.

MUTATE THE DATA A GATE READS, NOT THE CODE THAT READS IT. Written down because
three gates written today were vacuous and all three failed the same way: the
mutation chosen could not change the thing being measured. This file's first
version asserted `NEC2_BASES == {b : centre_feeds}` and survived flipping
razor's `centre_feeds` — because that moved BOTH sides together, the roster
being derived from the cell. The sibling cases were a `re.I` message filter
that ignores a case change, and an identity check "defeated" by `str(s)`, which
returns the same object. A gate is only proven by a mutation that could
plausibly reach it from the direction a real change would come.

WHAT THE SEAM IS NOT. #1006's "Related" section says the EZNEC/NEC-5 seam
"serves a different subset again". It does not: `eznec/_serve.py` takes any
name in `BASES` the deck's geometry can host, and filters PER DECK on
`knot_feeds` when the deck has feeds. That is a refusal, not a roster, and the
distinction matters because a roster is a list someone chose while a per-deck
refusal is a property of the deck in front of you.

AND ONE ROSTER IS NOT A STATEMENT. antennaknobs' tabs are `BASES` minus
`{bspline-d1, pulse, razor-nec5}`, and those three exclusions have three
different NON-AXIS reasons — a deprecated alias, a UI duplicate, and an
accident. No axis predicate reproduces the set, and inventing one would encode
two interface decisions and an oversight as if they were engine properties.
The list is pinned here with its reasons instead, and the gap is filed.

RESOLUTION STABILITY (#1006 point 1). "Names stay as aliases/presets so
nothing breaks and no URL or saved session changes meaning." There is no URL
or saved-session carrier for the backend name today — no router, no query
param, no permalink — so the round-trip fixture that phrasing implies has no
surface to run on. What underwrites the promise instead is that a NAME
RESOLVES TO A FIXED POINT in the space: every roster name resolves, aliases
resolve identically to what they alias, and antennaknobs' names agree with the
momwire names they bind. That is the invariant a rename would break, and it is
the precondition for a URL round trip rather than a substitute for one — if a
URL surface appears, this gate is what makes the round trip meaningful.
"""

from __future__ import annotations

import pytest

import antennaknobs.web.server  # noqa: F401 — resolves the adapter import cycle
from antennaknobs.web.adapter import _BACKENDS
from momwire.deck._solver import BASES, NEC2_BASES

_HAS_AXES = "axes" in getattr(BASES["bspline"][0].capabilities, "_fields", ())
pytestmark = pytest.mark.skipif(
    not _HAS_AXES, reason="momwire predates #1006 G2-1 (no `axes` capability cell)"
)


def _caps(name):
    return BASES[name][0].capabilities


# --------------------------------------------------------------------------
# (a) The mirror
# --------------------------------------------------------------------------


def test_the_nec2_roster_is_ALREADY_derived_from_the_axis_not_curated():
    """`NEC2_BASES` needs no filter written for it — momwire built it as one.

    NOT `assert NEC2_BASES == {b : centre_feeds}`. That was this file's first
    version and it is a TAUTOLOGY: `deck/_solver.py` defines the roster as

        NEC2_BASES = {name: e for name, e in BASES.items()
                      if e[0].capabilities.centre_feeds}

    so the assertion compares a value against its own derivation and cannot
    fail. Mutation-checked: flipping razor's `centre_feeds` moved BOTH sides
    together and the test stayed green, which is how it was caught.

    What is worth pinning is the structural fact — that this roster is
    derived at all — because that is what makes it a statement over the
    product space rather than a list someone maintains. If it ever became a
    hand-written literal, #1006's thesis would have lost its one existing
    example and nobody would notice from the names.
    """
    import inspect

    from momwire.deck import _solver

    src = inspect.getsource(_solver)
    # Anchor on the ASSIGNMENT, not the first mention — the name appears in
    # prose above it, and a window from there measures the wrong text.
    i = src.index("NEC2_BASES = ")
    assert "capabilities.centre_feeds" in src[i : i + 400], (
        "NEC2_BASES is no longer derived from the axis — it has become a "
        "curated list, which is the thing #1006 wants rosters to stop being"
    )


def test_the_node_dialect_filter_is_knot_feeds_and_the_two_are_mirrors():
    """The other half of the mirror, and the reason both cells exist.

    A node-addressing dialect refuses the rows that snap to centres; the nec2
    dialect drops the rows that snap to knots. The two excluded sets are
    disjoint and non-empty, which is what makes them mirrors rather than one
    cell wearing two names.
    """
    no_knot = {n for n in BASES if not _caps(n).knot_feeds}
    no_centre = {n for n in BASES if not _caps(n).centre_feeds}
    assert no_knot == {"pulse", "sinusoidal"}
    assert no_centre == {"razor-2p", "razor-nec5"}
    assert not (no_knot & no_centre), "a family that misses BOTH grids"
    # ...and the nec2 roster drops exactly the centre-missers, not the others.
    assert set(BASES) - set(NEC2_BASES) == no_centre


def test_the_seam_is_a_per_deck_refusal_not_a_roster():
    """#1006 says the EZNEC/NEC-5 seam serves "a different subset again"; it
    does not, and the correction is recorded on the issue.

    The seam accepts any name in `BASES` the deck can host. If it were a
    roster it would be a named subset somewhere — it is not, and the
    knot-missing rows are still perfectly reachable through it for a deck
    with no feeds to place.
    """
    from momwire.eznec import _serve

    assert not any(
        isinstance(getattr(_serve, n, None), (set, frozenset, tuple, dict))
        and n.isupper()
        and n.endswith("BASES")
        for n in dir(_serve)
    ), "the seam has grown a roster — this test's premise needs re-measuring"


def test_the_antennaknobs_tab_list_has_no_axis_predicate():
    """Pinned as a LIST with its reasons, because it is not a statement.

    Three exclusions, three non-axis reasons: `razor-nec5` is a deprecated
    alias of `razor-2p` (a naming fact), `bspline-d1` is the same class under
    a kwarg the bspline panel already exposes (an interface fact), and `pulse`
    never got a tab (an accident — #1006's own words). A predicate fitted to
    this set would encode two of those as engine properties.

    This test exists to notice when the set changes, so the accident can be
    closed deliberately rather than drift further.
    """
    tabs = {b.name for b in _BACKENDS if b.kind == "momwire"}
    assert set(BASES) - tabs == {"bspline-d1", "pulse", "razor-nec5"}
    assert tabs < set(BASES), "a tab that momwire's roster does not name"


# --------------------------------------------------------------------------
# (c) Resolution stability — the gate #1006 point 1 actually needs
# --------------------------------------------------------------------------


def test_every_roster_name_resolves_to_a_point_in_the_space():
    """A preset that does not resolve is a name with no meaning to keep."""
    from momwire._capabilities import axes_for

    for name in BASES:
        got = axes_for(_caps(name))
        assert got.get("basis"), f"{name}: no basis"
        assert got.get("solve_strategy"), f"{name}: no solve strategy"


def test_a_deprecated_alias_resolves_IDENTICALLY_to_what_it_aliases():
    """`razor-nec5` is the retired spelling of `razor-2p` — one class, one
    bound kwarg, two names. If a rename ever made them resolve differently,
    an old URL or saved session would silently mean a different engine, which
    is precisely what #1006 point 1 promises will not happen."""
    from momwire._capabilities import axes_for

    old_cls, old_kw = BASES["razor-nec5"]
    new_cls, new_kw = BASES["razor-2p"]
    assert old_cls is new_cls and old_kw == new_kw
    assert axes_for(old_cls.capabilities) == axes_for(new_cls.capabilities)


def test_antennaknobs_names_agree_with_the_momwire_names_they_bind():
    """The two rosters may differ in WHICH names they carry; they must not
    differ in what a shared name MEANS. A tab resolving to a different point
    than momwire's entry of the same name is the drift that would make a
    saved session ambiguous the moment a URL surface exists."""
    from momwire._capabilities import axes_for

    for b in _BACKENDS:
        if b.kind != "momwire" or b.name not in BASES:
            continue
        assert axes_for(b.solver.capabilities) == axes_for(_caps(b.name)), b.name
