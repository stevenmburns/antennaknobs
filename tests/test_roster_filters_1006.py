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
`{bspline-d1, razor-nec5}` since #1148, and those two exclusions have two
different NON-AXIS reasons — a deprecated alias and a UI duplicate. No axis
predicate reproduces the set, and inventing one would encode two interface
decisions as if they were engine properties. The list is pinned here with its
reasons instead. The third exclusion, `pulse`, had no reason at all; #1148
closed it, which is what this pin existed to make possible.

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

    TWO exclusions now, each with a STATED non-axis reason: `razor-nec5` is a
    deprecated alias of `razor-2p` (a naming fact — two tabs resolving to the
    identical point in the product space), and `bspline-d1` is the same class
    under a kwarg the bspline panel already exposes (an interface fact, and a
    judgement that belongs to #1006 G2-5 where `degree` becomes a control on
    the bspline tab). A predicate fitted to this set would still encode both
    as engine properties, so the list stays a list.

    The third was `pulse`, which had no reason at all — #1006 called it an
    accident. #1148 measured that nothing about it is unserved and gave it a
    tab, which is what this pin existed to make possible: it fails when the
    set changes, so the accident could be closed deliberately rather than
    drift further. It just was.
    """
    tabs = {b.name for b in _BACKENDS if b.kind == "momwire"}
    assert set(BASES) - tabs == {"bspline-d1", "razor-nec5"}
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


def test_the_pulse_tab_serves_the_basis_momwires_roster_names():
    """#1148: the accident, closed deliberately.

    `pulse` is not a variant of another tab. momwire's roster binds it to
    `HarringtonSolver` — point-matched pulse expansion — and its capability row
    is its own: `basis=('pulse',)`, `testing=('point-matching',)`, all three
    ground models, centre feeds.

    THE CLASS MATTERS AND IS NOT THE OBVIOUS ONE. `momwire.PulseSolver` shares
    the name but cannot take the engine path at all: it refuses the `junctions`
    kwarg the engine passes ("PulseSolver takes no junction spec"). A tab bound
    to it would raise on every deck. `BASES["pulse"]` is the authority on what
    the basis means, and it says Harrington.
    """
    from momwire import HarringtonSolver

    spec = next(b for b in _BACKENDS if b.name == "pulse")
    cls, kw = BASES["pulse"]
    assert spec.solver is cls, (spec.solver, cls)
    assert cls is HarringtonSolver
    assert not kw, "a bound kwarg would make the tab a preset, not the basis"
    axes = cls.capabilities.axes
    assert axes["basis"] == ("pulse",)
    assert axes["testing"] == ("point-matching",)


# The grounds the Pulse tab has to survive, in the order they cost us
# something. FREE SPACE is what #1148's gate checked, and it is why #1255
# happened: `momwire.PulseSolver.__init__` coerced `ground_eps` with
# `complex()` while every other family stores the `(eps_r, sigma)` pair, so
# the tab raised `TypeError: complex() argument must be a string or a number,
# not tuple` on the app's DEFAULT ground and nothing here noticed.
#
# The app's default is a plane, finite, refl-coef, 10 / 0.002 — i.e.
# `("finite-fast", 10.0, 0.002)` — so that spelling is the one a user meets
# first. `("finite", ...)` is the Sommerfeld spelling and reaches a different
# momwire path, so it is not implied by the fast one.
_PULSE_GROUNDS = [
    None,
    "pec",
    ("finite-fast", 10.0, 0.002),
    ("finite", 10.0, 0.002),
]


@pytest.mark.parametrize("ground", _PULSE_GROUNDS, ids=lambda g: str(g))
def test_the_pulse_tab_actually_solves(ground):
    """The substance behind the roster line. A tab that renders and raises on
    every deck would pass every set comparison in this file.

    Parametrised over the grounds rather than run once in free space: free
    space is the ONE case that worked while the tab was broken for every
    finite ground, which is exactly the shape of a gate that cannot fail on
    the thing it exists to catch (#1255).
    """
    import warnings

    from antennaknobs.designs.dipoles.invvee import Builder
    from antennaknobs.engines.momwire import MomwireEngine

    spec = next(b for b in _BACKENDS if b.name == "pulse")
    kwargs = {} if ground is None else {"ground": ground}
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        z = complex(
            MomwireEngine(Builder(), solver=spec.solver, **kwargs).impedance()[0]
        )
    # Point-matched pulse on a coarse mesh is not bspline; it is a real
    # impedance, which is all this gate claims.
    assert 10.0 < z.real < 500.0, z
    assert abs(z.imag) < 500.0, z


def test_a_ground_actually_changes_the_pulse_answer():
    """The parametrised gate above would pass if `ground=` were silently
    ignored — every arm would solve, in free space, four times. So the arms
    are required to DIFFER in the answer, which is the only evidence here
    that the ground reached the solver at all."""
    import warnings

    from antennaknobs.designs.dipoles.invvee import Builder
    from antennaknobs.engines.momwire import MomwireEngine

    spec = next(b for b in _BACKENDS if b.name == "pulse")
    seen = {}
    for ground in _PULSE_GROUNDS:
        kwargs = {} if ground is None else {"ground": ground}
        with warnings.catch_warnings():
            warnings.simplefilter("ignore")
            seen[str(ground)] = complex(
                MomwireEngine(Builder(), solver=spec.solver, **kwargs).impedance()[0]
            )
    free = seen["None"]
    for name, z in seen.items():
        if name == "None":
            continue
        assert abs(z - free) > 1.0, f"{name} answered free space's {free}: {z}"


def test_the_pulse_entry_has_the_shape_every_other_tab_has():
    """The frontend renders tabs from the SERVED roster generically — there is
    no per-backend branch — so a new entry's risk is its shape, not its name.
    Pinned against the other momwire tabs rather than against a literal."""
    momwire_tabs = [b for b in _BACKENDS if b.kind == "momwire"]
    pulse = next(b for b in momwire_tabs if b.name == "pulse")
    for other in momwire_tabs:
        assert type(pulse) is type(other)
    assert pulse.label and isinstance(pulse.label, str)
    assert pulse.solver is not None
    assert isinstance(pulse.model_kwargs, tuple)
