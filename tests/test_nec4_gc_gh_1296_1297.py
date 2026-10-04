"""AK#1296 / AK#1297: NEC-4's GH and GC card layouts.

NEC-4 and NEC-5 lay out ``GH`` as ``ITG NS TURNS ZLEN HR1 HR2 WR1 WR2 ISPX``
(NEC-2: ``ITG NS S HL A1 B1 A2 B2 RAD``) and give ``GC``'s first integer a
meaning, ``GC IX 0 RDEL RAD1 RAD2 DEL1 DEL2`` (NEC-2: ``GC 0 0 RDEL RAD1
RAD2``). A deck read as NEC-4 (or NEC-5) takes those layouts; read as NEC-2 it
is refused by name, pointing at the reading that spells it.

The oracle is NEC-4.2's own segmentation table: each printout lists every
segment's centre, length and radius to five decimals, so the geometry built
here must agree to half a unit in the last printed place. The CI gate is our
own probe decks and their printouts (`fixtures/nec4_gc_gh_1296_1297/
README.md`); between them they spell GC 1, GC 2 (with a computed count and a
GM after it), NEC-2's GC in nine fields, and GH helices and log/Archimedes
spirals of either hand. Cebik's NEC-4 tutorial decks, the decks the issues
were filed on, carry no license, so they are checked from the local corpus
against printouts made locally by ``scratch/nec4-gc-gh-cebik/
make_printouts.sh``, and skip where either is absent. Nothing here solves.
"""

import math
import os
import re
from pathlib import Path

import pytest

from antennaknobs.nec_import import GeometryLimits, parse_nec

FIXTURES = Path(__file__).parent / "fixtures" / "nec4_gc_gh_1296_1297"
DECKS = sorted(p.stem for p in FIXTURES.glob("*.nec"))
CEBIK = (
    Path(os.path.expanduser("~/antennas/nec-wild"))
    / "community/cebik-w4rnl/tutorial-models/Tutorial-2"
)
CEBIK_DECKS = {
    "3-1a-nec4": "ch-3",
    "3-1d-nec4": "ch-3",
    "3-2a-nec4": "ch-3",
    "11-11": "ch-11",
    "4-6": "ch-4",
    "4-6a": "ch-4",
    "4-9a": "ch-4",
    "17-11-nec4": "ch-17",
}
CEBIK_PRINTOUTS = Path(__file__).parents[1] / "scratch" / "nec4-gc-gh-cebik"
# Half a unit in the printout's fifth decimal, plus float noise.
PRINTED = 5e-6 + 1e-12
_NUM = re.compile(r"-?\d+\.\d+")


def _printed_segments(out: Path):
    """``[(centre xyz, length, radius)]`` from the printout's SEGMENTATION
    DATA table. Two orientation angles can run together ("0.00000-180.00000"),
    so the numbers are read by pattern, not by column split."""
    text = out.read_text()
    table = text.split("SEGMENTATION DATA")[1].split("INPUT LINE")[0]
    rows = []
    for line in table.splitlines():
        head = line.split()
        nums = _NUM.findall(line)
        if head and head[0].isdigit() and len(nums) >= 7:
            x, y, z, length = map(float, nums[:4])
            rows.append(((x, y, z), length, float(nums[6])))
    return rows


def _built_segments(deck):
    out = []
    for w in deck.wires:
        for k in range(w.n_seg):
            a = [p + (q - p) * k / w.n_seg for p, q in zip(w.p1, w.p2, strict=True)]
            b = [
                p + (q - p) * (k + 1) / w.n_seg for p, q in zip(w.p1, w.p2, strict=True)
            ]
            centre = tuple((u + v) / 2 for u, v in zip(a, b, strict=True))
            out.append((centre, math.dist(a, b), w.radius))
    return out


def _parse(path: Path, dialect):
    return parse_nec(
        path.read_text(errors="replace"), name=path.name, dialect=dialect, network=True
    )


def _read(stem, dialect):
    return _parse(FIXTURES / f"{stem}.nec", dialect)


def _assert_matches(deck, out: Path):
    printed = _printed_segments(out)
    built = _built_segments(deck)
    assert len(built) == len(printed)
    for k, ((c, length, r), (pc, plength, pr)) in enumerate(
        zip(built, printed, strict=True), 1
    ):
        assert all(abs(u - v) <= PRINTED for u, v in zip(c, pc, strict=True)), k
        assert abs(length - plength) <= PRINTED, k
        assert abs(r - pr) <= PRINTED, k


def test_every_fixture_has_its_printout():
    assert len(DECKS) == 11
    for stem in DECKS:
        assert (FIXTURES / f"{stem}.out").is_file(), stem


@pytest.mark.parametrize("dialect", ["nec4", "nec5"])
@pytest.mark.parametrize("stem", DECKS)
def test_the_geometry_is_nec42s_segment_for_segment(stem, dialect):
    """Every segment's centre, length and radius, in NEC-4.2's order. NEC-5's
    manual gives both cards the same layout, so a NEC-5 reading builds the
    same structure."""
    _assert_matches(_read(stem, dialect), FIXTURES / f"{stem}.out")


@pytest.mark.parametrize("stem", sorted(CEBIK_DECKS))
def test_cebiks_decks_are_nec42s_segment_for_segment(stem):
    """The decks #1296/#1297 were filed on, from the local corpus, against a
    local NEC-4.2 printout (the printout's deck has its RP cards removed,
    which leaves the geometry the same)."""
    deck = CEBIK / CEBIK_DECKS[stem] / f"{stem}.nec"
    out = CEBIK_PRINTOUTS / f"{stem}.out"
    if not deck.is_file():
        pytest.skip(f"nec-wild corpus not on this box ({deck})")
    if not out.is_file():
        pytest.skip(f"no local printout; run {CEBIK_PRINTOUTS}/make_printouts.sh")
    _assert_matches(_parse(deck, "nec4"), out)
    # Detection reads them as NEC-4 by the GH/GC card alone (option (b)).
    auto = _parse(deck, None)
    assert (auto.dialect, auto.dialect_detected) == ("nec4", "nec4")
    assert "uses NEC-4's layout" in auto.dialect_reason
    _assert_matches(auto, out)
    with pytest.raises(ValueError, match="read the deck as NEC-4"):
        _parse(deck, "nec2")


def test_gc_2_computes_its_own_segment_count():
    """The GW asks for 10 segments; GC 2 replaces them with the 7 its two
    lengths imply (NEC-4.2 prints the same), which every later (tag, segment)
    address and the GM's copies then count in."""
    tags = {}
    for w in _read("gc2_count_and_gm", "nec4").wires:
        tags[w.tag] = tags.get(w.tag, 0) + w.n_seg
    assert tags == {1: 1, 2: 7, 3: 7, 4: 7, 5: 7}
    first = next(w for w in _read("gc2_count_and_gm", "nec4").wires if w.tag == 2)
    assert math.dist(first.p1, first.p2) == pytest.approx(0.004, abs=1e-12)


def test_gc_1_keeps_the_gw_count_and_its_first_length():
    run = [w for w in _read("gc1_reversed_run", "nec4").wires if w.tag == 1]
    assert len(run) == 9
    assert math.dist(run[0].p1, run[0].p2) == pytest.approx(0.01, abs=1e-12)


def test_nec2s_gc_in_nine_fields_reads_in_every_dialect():
    """``GC 0 0 RDEL RAD1 RAD2 0 0 0 0`` is IX = 0: the same run either way."""
    ref = _built_segments(_read("gc0_nine_fields", "nec4"))
    for dialect in (None, "nec2", "nec5"):
        assert _built_segments(_read("gc0_nine_fields", dialect)) == ref


@pytest.mark.parametrize(
    "stem", ["gc1_reversed_run", "gc2_count_and_gm", "gc2_equal_ends"]
)
def test_a_nec4_gc_read_as_nec2_is_refused_by_name(stem):
    with pytest.raises(ValueError, match="NEC-2's GC has only the ratio form.*NEC-4"):
        _read(stem, "nec2")


@pytest.mark.parametrize(
    "stem", ["gh_right_helix", "gh_left_helix", "gh_flat_log_spiral", "gh_zero_hr2_wr2"]
)
def test_a_nec4_gh_read_as_nec2_is_refused_by_name(stem):
    with pytest.raises(ValueError, match="NEC-4 and NEC-5's GH layout"):
        _read(stem, "nec2")


def test_a_nec2_gh_short_of_its_radius_keeps_the_plain_refusal():
    """Seven fields is a NEC-2 card missing its radius, not NEC-4's layout
    (opensource/arcanum/helix-axial.nec)."""
    deck = "GH 1 40 0.25 1.25 0.15915 0.15915 0.001\nGE 0\nEN\n"
    with pytest.raises(ValueError, match="wire radius must be > 0"):
        parse_nec(deck)


def test_a_nec2_gc_and_gh_are_unchanged_under_a_nec2_reading():
    """The absence check: NEC-2's spellings still read as NEC-2."""
    gh = "GH 1 8 0.3 0.9 0.1 0.1 0.1 0.1 0.001\nGE 0\nEN\n"
    deck = parse_nec(gh)
    assert len(deck.wires) == 8 and {w.radius for w in deck.wires} == {0.001}
    gc = "GW 1 4 0 0 0 0 0 1 0\nGC 0 0 1.2 .001 .002\nGE 0\nEN\n"
    assert len(parse_nec(gc).wires) == 4


@pytest.mark.parametrize(
    ("cards", "match"),
    [
        ("GW 1 4 0 0 0 0 0 1 0\nGC 3 0 0 .001 .001 .1 .1", "IX must be 0"),
        ("GW 1 4 0 0 0 0 0 1 0\nGC 2 0 0 .001 .001 0 .1", "DEL1 must be"),
        ("GW 1 4 0 0 0 0 0 1 0\nGC 2 0 0 .001 .001 .1 1.5", "DEL2 must be"),
        ("GW 1 4 0 0 0 0 0 1 0\nGC 1 0 0 .001 .001 1.0", "DEL1 must be"),
        ("GH 1 10 2 1 1 1 0 0 0", "wire radii must be > 0"),
        ("GH 1 10 2 1 1 1 .001 .001 2", "ISPX must be 0"),
        ("GH 1 10 2 1 0 1 .001 .001 0", "log spiral needs both radii"),
    ],
)
def test_malformed_nec4_cards_are_refused_by_name(cards, match):
    with pytest.raises(ValueError, match=match):
        parse_nec(f"{cards}\nGE 0\nEN\n", dialect="nec4")


def test_the_limits_see_the_count_gc_2_computes():
    """A GC 2 whose lengths imply a huge count is refused BEFORE the run is
    built, from the computed count rather than the GW's NS."""
    limits = GeometryLimits(max_segments=100, max_wires=100)
    deck = "GW 1 4 0 0 0 0 0 1 0\nGC 2 0 0 .001 .001 1e-9 1e-9\nGE 0\nEN\n"
    with pytest.raises(ValueError, match="segments"):
        parse_nec(deck, dialect="nec4", limits=limits)


# --- detection: a NEC-4 layout leans NEC-4 (option (b), 2026-10-04) --------
# A GH or GC only the NEC-4/NEC-5 layout spells rules NEC-2 out and leans
# NEC-4; an unambiguous NEC-5 marker still wins, and the card outranks NOFILE.

HELIX = "GH 1 60 3 .9144 .099 .099 .001 .001 0"
GC1 = "GW 1 9 0 0 0 0 0 1 0\nGC 1 0 0 .001 .001 .05"
GC2 = "GW 1 9 0 0 0 0 0 1 0\nGC 2 0 0 .001 .001 .05 .2"


def _lean_note(mnemonic, line):
    return (
        "Read as NEC-4 (sources and loads at segment centres): the "
        f"{mnemonic} card on line {line} uses NEC-4's layout, which NEC-5 "
        "shares, and nothing else in the deck says which — choose Read as "
        "NEC-5 if it came from a NEC-5 program."
    )


def _probe(geometry, *, ex="EX 0 1 5 0 1 0", before="", after=""):
    text = f"{before}CE\n{geometry}\nGE 0\n{after}{ex}\nFR 0 1 0 0 30 0\nEN\n"
    return parse_nec(text, network=True)


@pytest.mark.parametrize(
    ("geometry", "mnemonic", "line"),
    [(HELIX, "GH", 2), (GC1, "GC", 3), (GC2, "GC", 3)],
)
def test_a_nec4_layout_alone_reads_as_nec4_at_the_centre(geometry, mnemonic, line):
    deck = _probe(geometry)
    assert (deck.dialect, deck.dialect_detected) == ("nec4", "nec4")
    assert deck.dialect_note() == _lean_note(mnemonic, line)
    (feed,) = deck.feeds
    assert (feed.seg, feed.edge) == (1, 0)  # a segment centre, not a knot


@pytest.mark.parametrize(
    ("geometry", "mnemonic"),
    [
        ("GH,1,60,3,.9144,.099,.099,.001,.001,0", "GH"),
        ("GW,1,9,0,0,0,0,0,1,0\nGC,2,0,0,.001,.001,.05,.2", "GC"),
        ("GH1,60,3,.9144,.099,.099,.001,.001,0", "GH"),
    ],
)
def test_the_comma_spelling_leans_too(geometry, mnemonic):
    deck = _probe(geometry)
    assert deck.dialect == "nec4"
    assert f"the {mnemonic} card on line" in deck.dialect_reason


@pytest.mark.parametrize("geometry", [HELIX, GC2])
def test_the_layout_outranks_nofile(geometry):
    deck = _probe(geometry, after="GN 2 0 0 0 13 .005 NOFILE\n")
    assert deck.dialect == "nec4"
    assert "uses NEC-4's layout" in deck.dialect_reason
    assert deck.feeds[0].edge == 0


@pytest.mark.parametrize("geometry", [HELIX, GC2])
@pytest.mark.parametrize("ex", ["EX 0 1 5 2 1 0", "EX 4 1 5 2 1 0", "EX 0 1 -5 0 1 0"])
def test_a_nec5_segment_end_source_still_reads_nec5(geometry, ex):
    """The layout is NEC-5's too, so the card reads either way; the EX says
    which."""
    deck = _probe(geometry, ex=ex)
    assert (deck.dialect, deck.dialect_detected) == ("nec5", "nec5")
    assert "segment-end form" in deck.dialect_reason
    assert deck.feeds[0].edge in (1, 2)


@pytest.mark.parametrize("geometry", [HELIX, GC1])
def test_a_cm_nec5_still_reads_nec5(geometry):
    deck = _probe(geometry, before="CM NEC-5\n")
    assert deck.dialect == "nec5"
    assert deck.dialect_reason == "a CM NEC-5 card on line 1"


def test_a_cm_nec4_is_the_reason_over_the_lean():
    deck = _probe(HELIX, before="CM NEC-4.2\n")
    assert deck.dialect == "nec4"
    assert deck.dialect_reason == "a CM NEC-4.2 card on line 1"


def test_a_source_before_the_card_is_read_the_nec4_way():
    """Decided ahead of the card loop: an EX read before the GH still sits
    at its segment centre."""
    text = (
        "CE\nGW 2 9 1 0 0 1 0 1 .001\nEX 0 2 5 0 1 0\n"
        f"{HELIX}\nGE 0\nFR 0 1 0 0 30 0\nEN\n"
    )
    deck = parse_nec(text, network=True)
    assert deck.dialect == "nec4" and deck.feeds[0].edge == 0


def test_a_chosen_dialect_reports_what_detection_would_do():
    text = f"CE\n{HELIX}\nGE 0\nEX 0 1 30 0 1 0\nFR 0 1 0 0 30 0\nEN\n"
    deck = parse_nec(text, network=True, dialect="nec5")
    assert deck.dialect == "nec5" and deck.dialect_detected == "nec4"
    assert "detection reads it as NEC-4 (the GH card on line 2" in deck.dialect_note()


def test_ispx_1_and_plain_nec2_cards_do_not_lean():
    """ISPX = 1 reads in NEC-2 as a 1 m wire radius, so it is no tell, and a
    NEC-2 GH or GC is no tell either."""
    for geometry in (
        "GH 1 60 3 .9144 .099 .099 .001 .001 1",
        "GH 1 8 0.3 0.9 0.1 0.1 0.1 0.1 0.001",
        "GW 1 9 0 0 0 0 0 1 0\nGC 0 0 1.2 .001 .002",
    ):
        assert _probe(geometry).dialect == "nec2", geometry
