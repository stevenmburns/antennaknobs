"""``GX``/``GR`` over the xnec2c example corpus (momwire#415).

Issue #415 opened on a census: intersecting each of the xnec2c project's
example decks with this dialect's refuse-by-name table made ``GR`` the single
largest geometry blocker in the set — bigger than ``TL`` — and ``GX`` the
fourth.  Units 1-3 built both cards, the symmetric cell they declare, and the
cell rule for ``LD``.  This module is the acceptance measurement the issue
asked for, and the numbers below are what it actually reads rather than what
the issue predicted; where the two differ, the difference is recorded here and
in the report, not smoothed over.

Two questions, both over the same corpus:

  1. **Do the decks parse?**  The issue named 18 decks "blocked by nothing
     except ``GX``/``GR``" that "would go straight from refused to accepted".
     Measured, 13 of them do.  The other five are blocked by something the
     census could not see, because the census intersected MNEMONICS with the
     refuse-by-name table and these five refuse by FIELD or by rule:
     ``10-30m-box``, ``10-30m_bipyramid``, ``T12m-H24m`` and ``T20m-H18m``
     each carry a ``GN 0`` with a radial ground SCREEN (a field of the ``GN``
     card, and no screen model exists here); and ``1MHz_tower`` trips unit 3's
     out-of-cell ``LD`` refusal.  ``_EXPECTED`` below records the whole
     36-deck outcome, deck by deck, so a change in any of it is visible.

  2. **Is the expansion exact?**  The transferable property of #415 — "a deck
     using ``GX``/``GR`` must solve identically to the same deck with those
     cards expanded into explicit ``GW`` cards" — rests entirely on the
     expansion being right.  Unit 1 checked that ad hoc against antennaknobs'
     ``nec_import``, an independently written and maintained reader of the
     same cards; ``test_the_expansion_matches_the_reference_bitwise`` makes it
     permanent, over both cards' decks, on tags, segment counts, endpoints and
     radii, BITWISE.

Neither the corpus nor antennaknobs is a momwire dependency, and neither is
present on CI, so the whole module skips when either is missing.  Point
``MOMWIRE_XNEC2C_EXAMPLES`` at a checkout of xnec2c's ``examples/`` directory
to run it.

MOVED HERE from momwire by antennaknobs#1299 — in momwire this skipped on every
CI run (momwire#988), because `antennaknobs.nec_import` is the reference and no
momwire lane installs it.  Moving it does NOT make it run in CI: the xnec2c
corpus is a third-party tree that momwire deliberately does not vendor or pin,
and this repo has no route to it either.  What the move buys is that the test
lives beside the importer it measures, and that its skip is pinned to exactly
that cause by `test_moved_corpus_skips_1299.py` rather than absorbing any
other failure.

TO RUN IT: check out xnec2c at the revision recorded in ``CENSUS_REVISION``
below and point ``MOMWIRE_XNEC2C_EXAMPLES`` at that checkout's ``examples/``
directory.
"""

from __future__ import annotations

import os
import subprocess
from pathlib import Path

import pytest

from momwire.deck import DeckError, parse, tokenize
from momwire.deck._nec2 import _GEOMETRY_CARDS
from momwire.deck._nec2_geometry import build_geometry

from antennaknobs import nec_import

CORPUS_ENV = "MOMWIRE_XNEC2C_EXAMPLES"
CORPUS = Path(
    os.environ.get(CORPUS_ENV) or Path.home() / "antennas" / "xnec2c" / "examples"
)

# The xnec2c revision every count in this module was recorded against.
# momwire does not vendor the corpus and cannot pin it, so the revision is
# recorded rather than enforced — and a checkout at a DIFFERENT revision
# skips with both hashes named instead of failing.
#
# That distinction is the whole reason this constant exists.  A census is a
# statement about one revision of someone else's tree; "your checkout is a
# different revision" is not a defect in momwire, and a lane that goes red
# on arrival for everyone whose clone is newer teaches people to ignore it.
# Drift WITHIN the recorded revision is still a hard failure, which is the
# case the census guard is actually for.
CENSUS_REVISION = "0124325"


def _corpus_revision() -> str | None:
    """The corpus checkout's short HEAD, or None if it is not a git tree."""
    try:
        out = subprocess.run(
            ["git", "-C", str(CORPUS), "rev-parse", "--short", "HEAD"],
            capture_output=True,
            text=True,
            timeout=10,
        )
    except (OSError, subprocess.SubprocessError):  # pragma: no cover - defensive
        return None
    return out.stdout.strip() or None


CORPUS_REVISION = _corpus_revision() if CORPUS.is_dir() else None

if not CORPUS.is_dir():
    _skip_reason = (
        f"the xnec2c example corpus is not at {CORPUS} — set ${CORPUS_ENV} to a "
        f"checkout's examples/ directory to run these"
    )
elif CORPUS_REVISION is not None and not CENSUS_REVISION.startswith(
    CORPUS_REVISION[:7]
):
    _skip_reason = (
        f"the corpus at {CORPUS} is xnec2c {CORPUS_REVISION}; every count in "
        f"this module was recorded against {CENSUS_REVISION}. Check that "
        f"revision out to run these, or re-record the census against yours "
        f"(the counts are in test_the_corpus_is_the_one_this_module_measures)"
    )
else:
    _skip_reason = ""

pytestmark = pytest.mark.skipif(bool(_skip_reason), reason=_skip_reason)


def _cards(text: str):
    """Every card of a deck, stopping at its terminator."""
    out = []
    for card in tokenize(text):
        if card.mnemonic in ("NX", "EN"):
            break
        out.append(card)
    return out


def _decks() -> tuple[dict[str, list], tuple[str, ...]]:
    """Every corpus deck that writes a ``GX`` or a ``GR``, name -> cards,
    plus the names of any deck that would not tokenize at all.

    The second return value exists because of how this module failed for
    months.  It tokenizes at IMPORT, so a deck the reader cannot even
    tokenize used to raise straight out of collection — and a collection
    error is not a test failure: every test in the file errored at once,
    none of them ran, and the only thing that could have said the corpus had
    drifted (``test_the_corpus_is_the_one_this_module_measures``) was among
    the casualties.  The lane was dark and looked, in a summary line, like
    four errors in someone else's module.

    So an unreadable deck is DATA here, not an exception, and
    ``test_no_corpus_deck_is_unreadable`` turns it into one named failure
    carrying its own remedy.  A dark lane is worse than a red one.
    """
    if not CORPUS.is_dir():
        return {}, ()
    found, unreadable = {}, []
    for path in sorted(CORPUS.glob("*.nec")):
        try:
            cards = _cards(path.read_text())
        except DeckError:
            unreadable.append(path.stem)
            continue
        if any(c.mnemonic in ("GX", "GR") for c in cards):
            found[path.stem] = cards
    return found, tuple(unreadable)


DECKS, UNREADABLE = _decks()
NAMES = tuple(DECKS)


def test_no_corpus_deck_is_unreadable():
    """Every deck in the corpus tokenizes, or this says which does not.

    The known cause is 4nec2's ``SY`` card (symbolic variables): two decks in
    the xnec2c tree write parametric expressions in their fields, which this
    dialect does not read.  antennaknobs' importer does, and exposes
    ``antennaknobs.nec_import.resolve_sy(text)`` — deck text in, plain NEC-2
    card text out — which is how the corpus this census was recorded against
    was translated.  It is exact: full-precision values, not a reformat, so
    an expanded deck is the same antenna to the bit.

    This test runs FIRST in the file on purpose: every count below is taken
    over decks that tokenized, so if some did not, the census failures that
    follow are downstream noise and this is the one to read.
    """
    assert not UNREADABLE, (
        f"{len(UNREADABLE)} corpus deck(s) will not tokenize: "
        f"{', '.join(UNREADABLE)}.\n"
        f"If they carry 4nec2 SY cards, rewrite each in place through "
        f"antennaknobs.nec_import.resolve_sy(path.read_text()); the recorded "
        f"census assumes a corpus that has been through it."
    )


# The 18 decks #415 named as blocked by GX/GR alone.  Quoted verbatim from the
# issue so the reconciliation below is against what was claimed, not against a
# re-derivation of it.
ISSUE_18 = (
    "10-30m-box",
    "10-30m_bipyramid",
    "10-30m_inv_cone",
    "137MHz_turnstile_sloped",
    "137Mhz-QFHA3",
    "137Mhz_xpol_omni",
    "1MHz_tower",
    "2m_1to4l-gp_on_pole",
    "2m_1to4l-horiz_gp_on_pole",
    "2m_5to8l-gp_on_pole",
    "2m_xpol_omni",
    "6-17m_bipyramid",
    "6-20m_fan",
    "6-20m_inv_cone",
    "70cm_collinear",
    "T12m-H24m",
    "T20m-H18m",
    "k9ay_orig",
)

# What each GX/GR deck does through `momwire.deck.parse` today: ``None`` for
# served, otherwise a substring the refusal must name.  Every refusal here is
# for something OTHER than GX/GR — the two cards themselves refuse nothing any
# more, and since momwire#471 neither does the cell rule on this corpus.
#
# ``1MHz_tower`` was that table's one entry about the feature under test, and
# it flipped to served in #471: its four LD cards (tags 3, 6, 9, 12 under a
# GR 3 4) are exactly the replication the in-cell card produces, so the deck
# means precisely what NEC computes and the restatement is dropped rather
# than refused.  The equality is checked per card, not assumed — a copy card
# that DISAGREES with the cell still refuses, which is the silent-wrong class
# the rule exists for.  Gated in `test_deck_nec2_symmetry.py`.
#
# Five decks moved from refused to served in momwire#456 phase C, when the
# dialect learned to read TL: ``2m_Lindenblad`` (four lines), ``40m-moxon``
# (three), and the three stacked arrays (two each).  ``40m-moxon`` is the one
# worth naming — its three TL cards sit under a symmetric cell that is STILL
# LIVE at GE, so it is the wild-corpus witness for the cell-rule exemption
# that the hand-written k9ay probes measure.
_EXPECTED: dict[str, str | None] = {
    "10-30m-box": "radial ground screen",
    "10-30m_bipyramid": "radial ground screen",
    "10-30m_inv_cone": None,
    "10-30m_sphere": "GA (wire arc)",
    "137MHz_turnstile_sloped": None,
    "137Mhz-QFHA1": "GH (helix)",
    "137Mhz-QFHA2": "GH (helix)",
    "137Mhz-QFHA3": None,
    "137Mhz_xpol_omni": None,
    "1MHz_3x_helicone": "GH (helix)",
    "1MHz_3x_helisphere": "GA (wire arc)",
    "1MHz_4x_helisphere": "GA (wire arc)",
    "1MHz_helivert": "GH (helix)",
    "1MHz_tower": None,
    "23cm_helix+radials": "GH (helix)",
    "2m_1to4l-gp_on_pole": None,
    "2m_1to4l-horiz_gp_on_pole": None,
    "2m_5to8l-gp_on_pole": None,
    "2m_Lindenblad": None,
    "2m_bigwheel": "GA (wire arc)",
    "2m_halo_stack": "GA (wire arc)",
    "2m_sqr_halo_stack": None,
    "2m_xpol_omni": None,
    "2m_xpol_omni_stack": None,
    # Served until the 2026-08-22 refresh, and the refusal is not this
    # deck's fault: it carries NE/NH over its GN 2 ground, which this dialect
    # still refuses although the engine has served near fields over every
    # ground since momwire#545.  Recorded as the stale refusal it is, and
    # tracked as momwire#560 — when that lands, this goes back to None.
    "40m-moxon": "NH over a finite ground",
    "6-17m_bipyramid": None,
    "6-20m_fan": None,
    "6-20m_inv_cone": None,
    "6m_big-square_stack": None,
    "6m_bigwheel-stack": "GA (wire arc)",
    "70cm_collinear": None,
    "T12m-H24m": "radial ground screen",
    "T20m-H18m": "radial ground screen",
    "gray_hoverman": "SM (multiple-patch surface)",
    "k9ay_orig": None,
    "satellite": "SP (surface patch)",
}

# The 11 decks whose geometry section also carries a ``GA`` or a ``GH``.  Both
# are refused by name, so neither reader has the arc or the helix to build on,
# and for six of them the remaining cards do not stand on their own: a later
# ``GM`` addresses a tag only the missing card would have created.  The other
# five reduce to a self-consistent geometry and are compared like any other.
_ARC_OR_HELIX_DECKS = frozenset(
    {
        "10-30m_sphere",
        "137Mhz-QFHA1",
        "137Mhz-QFHA2",
        "1MHz_3x_helicone",
        "1MHz_3x_helisphere",
        "1MHz_4x_helisphere",
        "1MHz_helivert",
        "23cm_helix+radials",
        "2m_bigwheel",
        "2m_halo_stack",
        "6m_bigwheel-stack",
    }
)

# The four decks that reach ``GE`` with a symmetric cell still live — #415's
# own "Scope" table, remeasured.  Two carry an ``LD`` and two do not.
_LIVE_AT_GE = ("1MHz_tower", "40m-moxon", "70cm_collinear", "k9ay_orig")
_LIVE_WITH_LD = ("1MHz_tower", "k9ay_orig")


def geometry_cards(name: str) -> list:
    return [c for c in DECKS[name] if c.mnemonic in _GEOMETRY_CARDS]


# ---------------------------------------------------------------------------
# the corpus itself
# ---------------------------------------------------------------------------


def test_the_corpus_is_the_one_this_module_measures():
    """A guard on the guard: the counts below are of a fixed corpus, so a
    checkout that grew or lost a deck must say so here rather than quietly
    change what every other test in this file means.

    xnec2c ``0124325``: 82 decks, of which 36 write a ``GX`` or a ``GR``.
    Re-recorded 2026-08-22
    against a refreshed checkout (it had been 75 and 36; #415's original census
    reported 82 and 34).  The seven decks the refresh brought write neither
    card, so the GX/GR slice and every expectation in ``_EXPECTED`` came
    through unchanged except ``40m-moxon`` — see its entry.

    This test could not fail for the whole period the counts were wrong: two
    corpus decks carry 4nec2 ``SY`` cards, ``_decks()`` tokenizes at import,
    and the resulting ``DeckError`` was a COLLECTION error, so every test in
    this module errored and none of them ran.  The decks are expanded now
    (antennaknobs' ``nec_import.resolve_sy``); the lesson is that a census
    guard behind an import-time parse guards nothing.
    """
    assert len(list(CORPUS.glob("*.nec"))) == 82
    assert len(NAMES) == 36
    assert set(NAMES) == set(_EXPECTED)


def test_gr_is_the_bigger_of_the_two_blockers():
    """The census finding that opened #415, remeasured on this checkout."""
    users = {
        m: sum(1 for cards in DECKS.values() if any(c.mnemonic == m for c in cards))
        for m in ("GX", "GR")
    }
    assert users == {"GX": 7, "GR": 29}


# ---------------------------------------------------------------------------
# 1. the decks parse
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("name", NAMES)
def test_every_gx_gr_deck_is_served_or_refuses_for_a_recorded_reason(name):
    """No ``GX``/``GR`` deck may refuse for an unrecorded reason.

    The point of the table is that it is exhaustive: a deck that starts
    refusing, stops refusing, or refuses for a DIFFERENT reason all fail here,
    which is the only way a regression in either card is caught over decks
    nobody hand-wrote.
    """
    expected = _EXPECTED[name]
    text = (CORPUS / f"{name}.nec").read_text()
    if expected is None:
        model = parse(text)
        assert model.wires, f"{name}: served but built no wires"
        return
    with pytest.raises(DeckError) as exc:
        parse(text)
    assert expected in str(exc.value), f"{name}: refused for {exc.value}"


def test_fourteen_of_the_issues_eighteen_go_from_refused_to_accepted():
    """The reconciliation against #415's own claim, stated as a number.

    The issue said all 18 "would go straight from refused to accepted".  Four
    do not, and none of the four is about ``GX``/``GR``: each carries a ``GN
    0`` radial ground SCREEN, which the census's mnemonic intersection could
    not see because the screen is a FIELD of a served card.

    Was THIRTEEN until momwire#471.  ``1MHz_tower`` was the fourteenth and
    the only one held back by ``GX``/``GR`` itself — unit 3's out-of-cell
    ``LD`` refusal — and #471 served it by recognising that its three
    copy-addressed cards restate the in-cell card's replication exactly.  So
    the remaining shortfall is now entirely the ground screen, which is the
    honest reading of what #415 got wrong.
    """
    assert set(ISSUE_18) <= set(NAMES)
    served = [n for n in ISSUE_18 if _EXPECTED[n] is None]
    assert len(served) == 14
    blocked = {n: _EXPECTED[n] for n in ISSUE_18 if _EXPECTED[n] is not None}
    assert blocked == {
        "10-30m-box": "radial ground screen",
        "10-30m_bipyramid": "radial ground screen",
        "T12m-H24m": "radial ground screen",
        "T20m-H18m": "radial ground screen",
    }


# ---------------------------------------------------------------------------
# 2. the expansion is exact
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("name", NAMES)
def test_the_expansion_matches_the_reference_bitwise(name):
    """momwire's expanded wire list against antennaknobs', bitwise.

    The reference is fed the SAME cards this dialect reads — the geometry
    section with ``GA``/``GH`` dropped, since both readers refuse those by
    name — so the comparison is of two independent implementations of the same
    input rather than of two different decks.  Six decks do not survive that
    reduction (a later ``GM`` addresses a tag the arc or helix would have
    created); both readers say so, in the same words, which is asserted rather
    than skipped.
    """
    cards = geometry_cards(name)
    body = "\n".join(c.raw for c in cards) + "\n"

    ours = theirs = None
    ours_error = theirs_error = None
    try:
        ours = build_geometry(cards)
    except DeckError as exc:
        ours_error = str(exc)
    try:
        theirs = nec_import.parse_nec(body, name=name)
    except ValueError as exc:
        theirs_error = str(exc)

    if ours_error is not None:
        assert name in _ARC_OR_HELIX_DECKS, (
            f"{name}: geometry refused with no arc or helix to blame: {ours_error}"
        )
        assert theirs_error is not None, f"{name}: only we refused: {ours_error}"
        # Both name the same dangling tag; the reference prefixes its own
        # deck name and card position, so the tail is what is comparable.
        assert theirs_error.endswith(ours_error), f"{ours_error!r} / {theirs_error!r}"
        return

    assert theirs_error is None, f"{name}: only the reference refused: {theirs_error}"
    assert len(ours.wires) == len(theirs.wires), (
        f"{name}: {len(ours.wires)} wires against the reference's {len(theirs.wires)}"
    )
    for i, (mine, ref) in enumerate(zip(ours.wires, theirs.wires, strict=True)):
        where = f"{name} wire {i}"
        assert mine.tag == ref.tag, where
        assert mine.n_seg == ref.n_seg, where
        assert tuple(mine.p1) == tuple(ref.p1), where
        assert tuple(mine.p2) == tuple(ref.p2), where
        assert mine.radius == ref.radius, where


def test_the_expansion_is_measured_on_thirty_of_the_thirty_six():
    """The score, written out: 30 decks compared bitwise, 6 refused by both.

    Written as a test rather than a comment because the interesting failure is
    the silent one — a change that makes more decks unbuildable would still
    leave every parametrisation above green while measuring less.
    """
    unbuildable = []
    for name in NAMES:
        try:
            build_geometry(geometry_cards(name))
        except DeckError:
            unbuildable.append(name)
    assert len(NAMES) - len(unbuildable) == 30
    assert set(unbuildable) < _ARC_OR_HELIX_DECKS
    assert len(unbuildable) == 6


# ---------------------------------------------------------------------------
# 3. the symmetric cell, over the corpus
# ---------------------------------------------------------------------------


def test_only_four_decks_reach_ge_with_a_live_cell():
    """#415's "Scope" table: the typical real deck builds a symmetric
    sub-assembly and then adds a feed wire or a mast, which collapses the
    symmetry and restores ordinary per-tag addressing.  Of the 30 decks whose
    geometry this dialect can build, 26 never see the cell rule at all."""
    live = []
    for name in NAMES:
        try:
            built = build_geometry(geometry_cards(name))
        except DeckError:
            continue  # the six with a dangling arc/helix tag
        if built.symmetry is not None:
            live.append(name)
    assert tuple(sorted(live)) == _LIVE_AT_GE


@pytest.mark.parametrize("name", _LIVE_AT_GE)
def test_the_live_cell_decks_split_into_two_with_a_load_and_two_without(name):
    """The pair that matters is the one carrying an ``LD``: only there does
    the cell rule change an answer.  ``k9ay_orig`` and ``1MHz_tower`` are the
    two, which is why they are this arc's named regression fixtures
    (``test_deck_nec2_cell_fixtures.py``)."""
    has_ld = any(c.mnemonic == "LD" and c.i(0) != 5 for c in DECKS[name])
    assert has_ld == (name in _LIVE_WITH_LD)


def test_40m_moxon_is_the_wild_witness_for_the_network_cell_exemption():
    """momwire#456 phase C, on a deck nobody wrote for the purpose.

    ``40m-moxon`` reaches ``GE`` with a symmetric cell still live AND carries
    three ``TL`` cards, which is the exact combination the hand-written
    ``k9ay_{nt,tl}_*`` probes were built to measure.  It is served — one
    network record per card, no replication onto the copies, no cell-rule
    refusal — which is what says the exemption holds outside the probes.

    It is also the only deck in this 36-deck slice where the two rules meet,
    so if the exemption were wrong this is where the corpus would say so.

    The deck also carries ``NE``/``NH`` over its ``GN 2`` ground, which this
    dialect refuses although the engine has served near fields over every
    ground since momwire#545 (tracked as momwire#560).  That is about the two
    OBSERVATION cards and touches nothing this test measures, so they are
    dropped here rather than losing the only wild witness there is — and the
    drop is GATED below, so the day #560 lands this test fails and says to
    stop trimming."""
    text = (CORPUS / "40m-moxon.nec").read_text()
    with pytest.raises(DeckError, match="NH over a finite ground"):
        parse(text)
    trimmed = "\n".join(
        line for line in text.splitlines() if line.split()[:1] not in (["NE"], ["NH"])
    )
    model = parse(trimmed)
    built = build_geometry(geometry_cards("40m-moxon"))
    assert built.symmetry is not None, "the premise: the cell must still be live"
    assert [c.kind for c in model.networks] == ["TL", "TL", "TL"]
    # Every endpoint resolves onto a real wire of the generated structure.
    for card in model.networks:
        for wire, arclength in (card.end_a, card.end_b):
            assert 0 <= wire < len(model.wires)
            assert 0.0 < arclength < model.wires[wire].length
