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
    with pytest.raises(ValueError, match="read the deck as NEC-4"):
        _parse(deck, None)


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
        _read(stem, None)
    with pytest.raises(ValueError, match="read the deck as NEC-4"):
        _read(stem, "nec2")


@pytest.mark.parametrize(
    "stem", ["gh_right_helix", "gh_left_helix", "gh_flat_log_spiral", "gh_zero_hr2_wr2"]
)
def test_a_nec4_gh_read_as_nec2_is_refused_by_name(stem):
    with pytest.raises(ValueError, match="NEC-4 and NEC-5's GH layout"):
        _read(stem, None)


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
