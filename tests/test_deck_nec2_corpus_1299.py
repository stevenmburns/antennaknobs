"""Parse agreement: ``momwire.deck``'s nec2 front-end vs antennaknobs.

The nec2 dialect spec (``site/src/content/docs/reference/deck-grammar-nec2.md``,
appendix ``#appendix-differences-from-antennaknobs-importer``) says the two
readers "agree on everything load-bearing for geometry: ``GW``, ``GM``,
``GS``, free-format tolerance, fused mnemonics, ``(tag, segment)`` addressing,
and the connection tolerance and snapping — that code is shared, not merely
equivalent."  This module is the measurement behind that sentence, run over
the 47-deck reference corpus, using antennaknobs' ``nec_import`` — a reader
independently written and maintained outside momwire — as the oracle:

  * the flat NEC wire list after every ``GM``/``GS`` transform and both
    connection passes — tag, segment count, both endpoints, radius;
  * the junction cut set, against antennaknobs' own ``_junction_cuts``;
  * the shattered pieces, against the spans antennaknobs' ``wire_tuples()``
    emits for the same wires;
  * ``(tag, segment)`` resolution, against ``nec_import._locate_segment``;
  * the resolved ``(wire, arclength)`` of every ``EX``/``LD``/``PT`` address
    in the deck, as a POINT IN SPACE — checked against both the flat wire's
    own segment centre and the arclength antennaknobs' polyline translation
    lands the same feed on.  The last comparison is a tolerance rather than a
    bitwise one: the two paths sum a different partition of the same
    polyline, so their arclengths differ by float summation order alone; and
  * GN/GD retention, FR/EX/LD-LD5 semantics, and RLC loading — against the
    portal's own parser and ``antennaknobs.network``'s formulas (momwire#359
    unit C).

This module used to also compare the SOLVE — the same decks built onto a
solver by ``momwire.deck.build_solver`` and by antennaknobs' own portal path,
at the port admittance matrix, bitwise (momwire#359 unit D).  That comparison
ran 41/41 bitwise once (#363) and is recorded history, but phase II of the
portal extraction (#846) rewired antennaknobs' portal onto ``build_solver``
itself, so it had come to compare the pipeline with itself rather than an
independent assembly path.  #373 decided to drop it rather than repair it:
the fixture battery (real nec2c captures) is what now carries solve-level
equivalence, and this module is reduced to what remains two independently
written readers — the parse-agreement subset.

MOVED HERE from momwire by antennaknobs#1299.  In momwire it skipped on every
CI run: antennaknobs is not a momwire dependency and will never be one, so
`importorskip("antennaknobs.nec_import")` meant no lane anywhere executed it
(momwire#988).  Here both packages are installed and it runs on every PR.

The corpus stayed behind, and had to: ten other momwire modules read the same
`tests/fixtures/nec_portal` directory, so it is momwire's, not this test's.
It is reached through the INSTALLED momwire — under this repo's test lane that
is the submodule at the recorded pointer, which is the right contract for an
equivalence test: measure against the corpus CI actually builds with, not a
copy here that would quietly stop covering decks momwire adds.  A wheel-only
momwire has no `tests/` beside the package, so the module skips; that skip is
pinned to exactly this cause by `test_moved_corpus_skips_1299.py`.
"""

from __future__ import annotations

import itertools
import math
import pathlib
from pathlib import Path

import momwire

import pytest

from momwire.deck import parse as momwire_parse
from momwire.deck._cards import parse_card
from momwire.deck._nec2 import _GEOMETRY_CARDS
from momwire.deck._nec2_geometry import build_geometry
from momwire.deck.model import SecondMedium

from antennaknobs import geometry as ak_geometry
from antennaknobs import network as ak_network
from antennaknobs import nec_import

# The portal's own reading of the same deck. It came home in #846 phase III,
# so this is an intra-repo import now rather than an `importorskip` on
# whatever antennaknobs happened to be installed — which matters: once
# antennaknobs deletes its copy (phase IV) an importorskip here would skip
# this module forever, silently, and the deck parser would lose the one
# independent reader it is measured against.
from momwire.portal import _portal as nec_portal  # noqa: E402

import numpy as np


# The corpus is momwire's, and it stays momwire's: ten other momwire test
# modules read the same directory (portal, deck-cell, SimNEC driver, EZNEC
# printout, roster, differential, buried), so it cannot travel with this test.
#
# So follow the INSTALLED momwire rather than assuming a repo layout. Under
# antennaknobs' test lane momwire is installed editable from the submodule, so
# `momwire.__file__` is `<root>/momwire/src/momwire/__init__.py` and its
# parents[2] is the submodule root — which is the contract this test wants:
# the corpus at the RECORDED POINTER, the same tree CI builds against, rather
# than a copy here that would quietly stop covering decks momwire adds.
#
# Under a wheel install there is no `tests/` beside the package and the corpus
# is simply absent. That is a skip, not a failure, and
# `test_the_skip_reason_is_only_ever_the_missing_corpus` pins it to exactly
# that cause so a renamed directory or a broken import cannot hide in it.
MOMWIRE_TESTS = pathlib.Path(momwire.__file__).resolve().parents[2] / "tests"
CORPUS_DIR = MOMWIRE_TESTS / "fixtures" / "nec_portal"

CORPUS_SKIP_REASON = (
    f"momwire's nec_portal deck corpus is not on disk at {CORPUS_DIR} — this "
    "test reads it from the momwire submodule (editable install), so a "
    "wheel-only momwire cannot run it"
)


def _corpus() -> list[Path]:
    """momwire's reference decks, read from the submodule at the pointer."""
    if not CORPUS_DIR.is_dir():
        return []
    return sorted(CORPUS_DIR.glob("*.deck"))


CORPUS = _corpus()

pytestmark = pytest.mark.skipif(not CORPUS, reason=CORPUS_SKIP_REASON)


class _Where:
    """``nec_import``'s card protocol, reduced to what ``_locate_segment``
    uses: a way to raise with context."""

    def error(self, msg):  # pragma: no cover - only on a mismatch
        return ValueError(msg)


def _cards(text: str):
    """Every card of a deck body, stopping at its terminator."""
    out = []
    for line in text.splitlines():
        card = parse_card(line)
        if card is None:
            continue
        if card.mnemonic in ("NX", "EN"):
            break
        out.append(card)
    return out


def _addresses(cards) -> list[tuple[int, int]]:
    """Every ``(tag, segment)`` the deck addresses, in discovery order.

    ``EX`` names one segment, ``LD``/``IS`` a range, ``PT 0`` a range when it
    carries one.  Duplicates are dropped: antennaknobs refuses a segment
    driven twice, and the union set is what the portal builds anyway.
    """
    seen: list[tuple[int, int]] = []

    def add(tag, seg):
        if (tag, seg) not in seen:
            seen.append((tag, seg))

    for card in cards:
        if card.mnemonic == "EX" and card.i(0) == 0:
            add(card.i(1), max(card.i(2), 1))
        elif card.mnemonic in ("LD", "IS"):
            if card.mnemonic == "LD" and card.i(0) in (-1, 5):
                continue
            first, last = card.i(2), card.i(3)
            if first <= 0 and last <= 0:
                continue
            for seg in range(max(first, 1), max(last, first) + 1):
                add(card.i(1), seg)
        elif card.mnemonic == "PT" and card.i(0) == 0 and (card.i(2) or card.i(3)):
            for seg in range(max(card.i(2), 1), max(card.i(3), card.i(2)) + 1):
                add(card.i(1), seg)
    return seen


def _reference(cards, addresses):
    """antennaknobs' reading of the same geometry.

    A synthesized deck of the geometry cards plus one ``EX`` per address —
    the portal's own ``_synthesize_union_deck`` trick, which reuses that
    repo's only card parser and gives one geometry translation for the whole
    deck.  Each ``EX`` carries its address's index as its voltage, so the
    feeds that come back out of the polyline translation can be matched to
    the address that asked for them.
    """
    lines = [c.raw for c in cards if c.mnemonic in _GEOMETRY_CARDS]
    lines += [f"EX 0 {tag} {seg} 0 {k + 1}." for k, (tag, seg) in enumerate(addresses)]
    return nec_import.parse_nec("\n".join(lines) + "\n", name="equivalence deck")


def _point_on_polyline(polyline, arclength: float):
    """The point ``arclength`` metres along an (M, 3) polyline."""
    remaining = arclength
    for a, b in itertools.pairwise(polyline):
        seg = float(np.linalg.norm(b - a))
        if remaining <= seg:
            return a + (b - a) * (remaining / seg)
        remaining -= seg
    return polyline[-1]


@pytest.mark.parametrize("path", CORPUS, ids=lambda p: p.stem)
def test_geometry_matches_antennaknobs(path: Path):
    text = path.read_text()
    cards = _cards(text)
    geometry_cards = [c for c in cards if c.mnemonic in _GEOMETRY_CARDS]
    addresses = _addresses(cards)
    assert addresses, "every corpus deck addresses at least one segment"

    ours = build_geometry(geometry_cards)
    theirs = _reference(cards, addresses)

    # 1. the flat wire list, bitwise.
    assert len(ours.wires) == len(theirs.wires)
    for mine, ref in zip(ours.wires, theirs.wires, strict=True):
        assert mine.tag == ref.tag
        assert mine.n_seg == ref.n_seg
        assert tuple(mine.p1) == tuple(ref.p1)
        assert tuple(mine.p2) == tuple(ref.p2)
        assert mine.radius == ref.radius

    # 2. the junction cut set, against antennaknobs' own.
    assert ours.cuts == dict(theirs._junction_cuts)

    # 3. the shattered pieces, against the spans wire_tuples() emits. Their
    #    tuples carry the extra splits an EX segment forces (the engine there
    #    feeds a wire at its middle segment); ours carry only the junction
    #    cuts, so each of our pieces must be an exact consecutive RUN of
    #    theirs — same endpoints, same segment total.
    ref_tuples = theirs.wire_tuples()
    cursor = 0
    for wire_index, ref_wire in enumerate(theirs.wires):
        run: list = []
        total = 0
        while total < ref_wire.n_seg:
            run.append(ref_tuples[cursor])
            total += ref_tuples[cursor][2]
            cursor += 1
        assert total == ref_wire.n_seg
        pos = 0
        for piece_index in ours.pieces_of_wire[wire_index]:
            piece = ours.pieces[piece_index]
            covered = 0
            start = pos
            while covered < piece.n_seg:
                covered += run[pos][2]
                pos += 1
            assert covered == piece.n_seg
            assert tuple(run[start][0]) == piece.p1
            assert tuple(run[pos - 1][1]) == piece.p2
        assert pos == len(run)
    assert cursor == len(ref_tuples)

    # 4/5. addressing, and the point every address lands on.
    flat = [[w.tag, w.n_seg, list(w.p1), list(w.p2), w.radius] for w in theirs.wires]
    translated = ak_geometry.flat_wires_to_polylines(ref_tuples)
    # feed voltage k+1 was written by address k.
    ref_feeds = {
        int(round(voltage.real)) - 1: (poly, arclength)
        for poly, arclength, voltage in translated["feeds"]
    }
    assert len(ref_feeds) == len(addresses)

    for k, (tag, seg) in enumerate(addresses):
        ref_wire, ref_local = nec_import._locate_segment(flat, tag, seg, _Where())
        assert ours.locate(tag, seg) == (ref_wire, ref_local)

        wire_index, arclength = ours.resolve(tag, seg)
        model_wire = ours.pieces[wire_index]
        ours_point = tuple(
            a + (b - a) * (arclength / model_wire.length)
            for a, b in zip(model_wire.p1, model_wire.p2, strict=True)
        )

        # (a) the flat wire's own segment centre — NEC's definition.
        w = theirs.wires[ref_wire]
        centre = tuple(
            a + (b - a) * ((ref_local - 0.5) / w.n_seg)
            for a, b in zip(w.p1, w.p2, strict=True)
        )
        assert math.dist(ours_point, centre) <= 1e-12 * (1.0 + w.radius)

        # (b) where antennaknobs' polyline translation puts the same feed.
        poly, ref_arclength = ref_feeds[k]
        ref_point = _point_on_polyline(translated["polylines"][poly], ref_arclength)
        assert math.dist(ours_point, tuple(float(c) for c in ref_point)) <= 1e-9


def test_corpus_is_the_whole_reference_set():
    """The gate is the WHOLE corpus, not whatever happened to be on disk.

    45 through #458; 47 since momwire#415 added a ``GX`` and a ``GR`` deck,
    which this module's geometry comparison covers for free — the reference
    importer implements both cards too, and unit 1 ported them from it; 51
    since momwire#456 phase C captured four network decks (a zero-length line,
    an all-zero ``NT``, an ``LD``/``NT`` pair on one segment, and the ``EX 6``
    gyrator idiom) and a fifth, `dipole_nt_after_xq`, for network retention at
    the answer; 59 since momwire#487 captured the seven MININEC-type ground
    idiom decks, which this module covers for free in the half that matters to
    it — ``GN``/``GD`` retention, where the two readers must agree that a
    ``GN`` resets the four second-medium slots a ``GD`` writes; 60 since
    momwire#487 U2 added the cliff-at-zero deck with the serving flip; 65
    since momwire#652 captured the five ``PQ`` charge-report decks (one per
    form the card has, plus the reversed-walk apex)."""
    assert len(CORPUS) == 65


# The corpus is 47 clean exported decks: measured, not one of them has an
# endpoint the connection passes move, or a wire another wire's end lands on
# mid-span. So the two most delicate pieces of shared arithmetic — the
# snapping tolerance and the junction shatter — would go unmeasured on the
# corpus alone. These decks measure them, against the same reference.
_SNAPPING_DECKS = {
    # A corner whose two wires sit 1 nm apart: inside the tolerance, so both
    # readers must fuse it into one node.
    "near_miss_corner": """
GW 1 10 0. 0. 0. 1. 0. 0. 1.E-3
GW 2 10 1.000000001 0. 0. 1. 1. 0. 1.E-3
GE 0
EX 0 1 5 0 1.
""",
    # The same corner 1.5 tolerances apart: outside, so both readers must
    # leave it open. Deliberately gapped geometry is unaffected.
    "wide_gap_corner": """
GW 1 10 0. 0. 0. 1. 0. 0. 1.E-3
GW 2 10 1.00015 0. 0. 1. 1. 0. 1.E-3
GE 0
EX 0 1 5 0 1.
""",
    # A tee: wire 2's end lands on wire 1's interior segment boundary, which
    # becomes a cut so the crossing carries current.
    "mid_wire_tee": """
GW 1 4 0. 0. 0. 1. 0. 0. 1.E-3
GW 2 4 0.5 0. 1.E-7 0.5 1. 0. 1.E-3
GE 0
EX 0 1 3 0 1.
EX 0 2 2 0 1.
""",
    # A tee whose stub is finely meshed: the tolerance is the MINIMUM of the
    # pair's segment lengths, so this one stays open in both readers.
    "mid_wire_tee_fine_stub": """
GW 1 4 0. 0. 0. 1. 0. 0. 1.E-3
GW 2 400 0.5 0. 1.E-4 0.5 1. 0. 1.E-3
GE 0
EX 0 1 3 0 1.
""",
    # A GM-rotated copy: six-significant-digit card coordinates land the
    # replica's corner micrometres off the original's.
    "gm_rotated_polygon": """
GW 1 8 0. 0. 0. 1.000000 0. 0. 1.E-3
GM 1 3 0. 0. 90.000000 1.000000 0. 0. 0
GE 0
EX 0 1 4 0 1.
""",
}


@pytest.mark.parametrize("name", sorted(_SNAPPING_DECKS))
def test_connection_passes_match_antennaknobs(name):
    """The connection tolerance and the junction shatter, measured."""
    text = _SNAPPING_DECKS[name]
    cards = _cards(text)
    geometry_cards = [c for c in cards if c.mnemonic in _GEOMETRY_CARDS]
    addresses = _addresses(cards)
    ours = build_geometry(geometry_cards)
    theirs = _reference(cards, addresses)

    for mine, ref in zip(ours.wires, theirs.wires, strict=True):
        assert tuple(mine.p1) == tuple(ref.p1)
        assert tuple(mine.p2) == tuple(ref.p2)
    assert ours.cuts == dict(theirs._junction_cuts)

    flat = [[w.tag, w.n_seg, list(w.p1), list(w.p2), w.radius] for w in theirs.wires]
    for tag, seg in addresses:
        assert ours.locate(tag, seg) == nec_import._locate_segment(
            flat, tag, seg, _Where()
        )


def test_the_synthetic_decks_actually_exercise_both_passes():
    """A guard on the guard: these decks must move an endpoint and cut a
    wire, or they are measuring nothing the corpus did not."""

    def geometry(name):
        return build_geometry(
            [c for c in _cards(_SNAPPING_DECKS[name]) if c.mnemonic in _GEOMETRY_CARDS]
        )

    tee = geometry("mid_wire_tee")
    assert tee.cuts == {0: frozenset({2})}
    assert len(tee.pieces) == 3
    assert geometry("mid_wire_tee_fine_stub").cuts == {}
    corner = geometry("near_miss_corner")
    assert tuple(corner.wires[1].p1) == tuple(corner.wires[0].p2)
    wide = geometry("wide_gap_corner")
    assert tuple(wide.wires[1].p1) != tuple(wide.wires[0].p2)


# ---------------------------------------------------------------------------
# Environment, source and load equivalence (momwire#359 unit C)
#
# The geometry tests above measure GW/GM/GS/connections; this section adds
# GN/GD, FR, EX and LD/LD-5 — the state a deck's execute groups run under.
# The reference for structure/execution is the PORTAL's own nec2 parser,
# ``nec_portal.parse_deck`` — an independently coded retention/arming state
# machine for the FR/EX execute groups, not merely a translation of ours (it
# was antennaknobs' until #846 phase III brought it home). Its GROUND record
# is the one exception: antennaknobs#930 rebuilt ``Ground`` as
# ``Ground.from_model(model.ground)`` rather than a second GN read, so
# assertion 1 below checks that the portal's construction reflects the SAME
# parse this test calls — a wiring check, not a second reader. For
# loading, ``antennaknobs.network``'s RLC formulas fed the raw card fields,
# not momwire's own ``LoadSpec.impedance``. Address resolution reuses this
# module's own ``build_geometry``/``Nec2Structure``, whose bitwise agreement
# with antennaknobs is what the geometry tests above establish; unit C's
# question is retention and card semantics, not geometry a second time.
# ---------------------------------------------------------------------------

# The hand-authored network probes. They carried no DeckModel while the
# dialect refused TL/NT by name (#930), so this module skipped them; since
# momwire#456 phase C they parse, solve, and have exactly the model this test
# compares — so they are IN, and the guard below counts them instead of
# excusing them.
_NETWORK_DECKS = {
    "dipole_nt_network",
    "dipole_tl_network",
    "dipole_tl_shunt_crossed",
    "dipole_tl_zero_length",
    "dipole_nt_all_zero",
    "dipole_ld_nt_colocated",
    "dipole_ex6_gyrator",
    "dipole_nt_after_xq",
}

# The decks refused by FIELD rather than by name, which would carry no
# DeckModel and so cannot be compared reader against reader. There are none:
# `dipole_gd_second_medium` and the three `mininec_*` idiom decks were here
# for #458 — a second medium under a `GN 1` at an execute card that will not
# read it — and momwire#487 retired that refusal, so the whole idiom class
# goes through this module's gates like any other deck. That includes both
# card ORDERS: `mininec_vertical_rp0` leaves the medium in force at the
# execute card and `mininec_gd_reset_by_gn_rp0` clears it, and the two
# readers have to agree about which is which.
_REFUSED_DECKS: set[str] = set()


def _portal_deck(text: str):
    """The same deck body, read by the portal's own nec2 parser."""
    body = text.split("\nNX", 1)[0].split("\nEN", 1)[0]
    return nec_portal.parse_deck(body)


def _expected_port_loads(cards, structure):
    """``LD`` types 0/1/4 as ``(model wire, arclength, kind, r, l, c, x)``,
    reimplemented directly from the raw cards (not momwire's ``_ld``) as an
    independent check.  Every corpus ``LD`` card is a single explicit
    segment (``first == last``, both nonzero) — the assertion below is a
    guard on that assumption, not a corpus fact this helper depends on
    silently."""
    loads = []
    for card in cards:
        if card.mnemonic != "LD":
            continue
        ldtyp = card.i(0)
        if ldtyp == -1:
            loads.clear()
            continue
        if ldtyp not in (0, 1, 4):
            continue  # type 5 is conductivity, checked separately below
        tag, first, last = card.i(1), card.i(2), card.i(3)
        assert first == last and first > 0, (
            "a corpus LD card range grew past a single explicit segment; "
            "_expected_port_loads needs the same range-expansion this "
            "dialect's _ld/ld_segment_range implements"
        )
        wire, arclength = structure.resolve(tag, first)
        if ldtyp in (0, 1):
            r, l, c = card.f(4), card.f(5), card.f(6)
            if r == 0.0 and l == 0.0 and c == 0.0:
                continue
            loads.append(
                (wire, arclength, "series" if ldtyp == 0 else "parallel", r, l, c, 0.0)
            )
        else:
            r, x = card.f(4), card.f(5)
            if r == 0.0 and x == 0.0:
                continue
            loads.append((wire, arclength, "fixed", r, 0.0, 0.0, x))
    return loads


def _expected_conductivity(cards, structure):
    """``LD 5`` as ``{model wire index: conductivity}``, over every touched
    MODEL wire (post-shatter) — the same shape ``DeckWire.material`` uses."""
    global_sigma: float | None = None
    per_flat_wire: dict[int, float] = {}
    for card in cards:
        if card.mnemonic != "LD":
            continue
        ldtyp = card.i(0)
        if ldtyp == -1:
            global_sigma = None
            per_flat_wire = {}
            continue
        if ldtyp != 5:
            continue
        tag, first = card.i(1), card.i(2)
        sigma = card.f(4)
        if tag == 0 and first == 0:
            global_sigma = sigma
            continue
        wire, _ = structure.locate(tag, first)
        per_flat_wire[wire] = sigma
    result = dict(per_flat_wire)
    if global_sigma is not None:
        for i in range(len(structure.wires)):
            result.setdefault(i, global_sigma)
    per_model_wire: dict[int, float] = {}
    for flat_index, sigma in result.items():
        for piece_index in structure.pieces_of_wire[flat_index]:
            per_model_wire[piece_index] = sigma
    return per_model_wire


@pytest.mark.parametrize("path", CORPUS, ids=lambda p: p.stem)
def test_environment_source_and_load_semantics_match_antennaknobs(path: Path):
    """GN/GD, FR, EX retention and LD/LD-5, against antennaknobs' own nec2
    parser and RLC formulas — momwire#359 unit C."""
    if path.stem in _REFUSED_DECKS:
        pytest.skip("refused by this dialect; see the geometry test")

    text = path.read_text()
    ours = momwire_parse(text)
    portal = _portal_deck(text)
    cards = _cards(text)
    geometry_cards = [c for c in cards if c.mnemonic in _GEOMETRY_CARDS]
    structure = build_geometry(geometry_cards)

    # 0. every card this dialect reads has real semantics now (unit C): a
    #    fully-populated model defers nothing.
    assert ours.deferred == ()

    # 1. ground mapping: type, constants, the second medium, and the GE flag.
    #    (a wiring check, not a second GN read — see the section note above)
    assert portal.ground == nec_portal.Ground.from_model(ours.ground)
    assert ours.ground_plane_flag == portal.ground_plane_flag
    if portal.second_medium is None:
        assert ours.second_medium is None
    else:
        assert ours.second_medium == SecondMedium(
            portal.second_medium.eps_r2,
            portal.second_medium.sigma2,
            portal.second_medium.edge_distance,
            portal.second_medium.height,
        )

    # 2. one entry per execute card, in the same positions None (a no-op
    #    XQ) falls in, and the same frequency list per group that ran.
    assert len(ours.groups) == len(portal.groups)
    for mine, ref in zip(ours.groups, portal.groups, strict=True):
        if ref is None:
            assert mine is None
            continue
        assert mine is not None
        assert mine.frequencies == pytest.approx(ref.freqs_mhz)

    # 3. the union feed set (spec #one-geometry-one-port-set), rebuilt here
    #    from the portal's OWN retained `sources` — an independent
    #    retention trace — and resolved through our own structure.
    order: list[tuple[int, int]] = []
    position: dict[tuple[int, int], int] = {}
    expected_volts: list[complex] = []
    for ref in portal.groups:
        if ref is None:
            continue
        for tag, seg, volts in ref.sources:
            key = (tag, seg)
            if key not in position:
                position[key] = len(order)
                order.append(key)
                expected_volts.append(volts)
    expected_feeds = [structure.resolve(tag, seg) for tag, seg in order]
    assert len(ours.feeds) == len(expected_feeds)
    for (wire, arclength, volts), (e_wire, e_arclength), e_volts in zip(
        ours.feeds, expected_feeds, expected_volts, strict=True
    ):
        assert wire == e_wire
        assert arclength == pytest.approx(e_arclength, abs=1e-12)
        assert volts == e_volts

    for mine, ref in zip(ours.groups, portal.groups, strict=True):
        if ref is None:
            continue
        expected_voltages = [0j] * len(order)
        for tag, seg, volts in ref.sources:
            expected_voltages[position[(tag, seg)]] = volts
        assert mine.voltages == tuple(expected_voltages)

    # 4. LD 0/1/4 impedances at every frequency the deck actually runs,
    #    against antennaknobs.network's RLC formulas fed the SAME raw
    #    fields — a genuinely different implementation of the same physics.
    expected_loads = _expected_port_loads(cards, structure)
    assert len(ours.loads) == len(expected_loads)
    all_freqs_mhz = sorted({f for g in ours.groups if g for f in g.frequencies})
    for (wire, arclength, spec), (e_wire, e_arclength, kind, r, l, c, x) in zip(
        ours.loads, expected_loads, strict=True
    ):
        assert wire == e_wire
        assert arclength == pytest.approx(e_arclength, abs=1e-12)
        assert spec.kind == kind
        for freq_mhz in all_freqs_mhz:
            omega = 2.0 * math.pi * freq_mhz * 1e6
            ours_z = spec.impedance(freq_mhz * 1e6)
            if kind == "fixed":
                ref_z = complex(r, x)
            elif kind == "series":
                ref_z = ak_network._series_rlc_impedance(
                    r or None, l or None, c or None, omega
                )
            else:
                ref_z = 1.0 / ak_network._parallel_rlc_admittance(
                    r or None, l or None, c or None, omega
                )
            assert ours_z == pytest.approx(ref_z, rel=1e-9)

    # 5. LD 5 conductivity, whole-structure and per-wire, against the raw
    #    card values directly.
    expected_conductivity = _expected_conductivity(cards, structure)
    for wire_index, expected in expected_conductivity.items():
        material = ours.wires[wire_index].material
        assert material is not None
        assert material.conductivity == expected


def test_every_network_deck_carries_the_cards_it_states():
    """The network decks are compared like every other deck now, so what is
    left to guard is that they are actually IN the comparison: a deck whose
    ``TL``/``NT`` silently failed to parse would have an empty ``networks``
    tuple and would sail through every assertion above.

    The set is written out for the same reason the differential suite's count
    is — a corpus deck that quietly stops carrying a network shows up here.
    """
    on_disk = {p.stem for p in CORPUS}
    assert _NETWORK_DECKS <= on_disk
    for stem in sorted(_NETWORK_DECKS):
        path = next(p for p in CORPUS if p.stem == stem)
        text = path.read_text()
        stated = sum(
            1 for line in text.splitlines() if line.split()[:1] in (["TL"], ["NT"])
        )
        assert stated, f"{stem} states no network card"
        assert len(momwire_parse(text).networks) == stated, stem
