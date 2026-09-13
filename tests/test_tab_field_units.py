"""A number and its unit in one TAB-delimited 4nec2 card field is one value.

4nec2 decks write card fields like `-68 ft` or `60.7 uh`: a number, a space and
a unit symbol, inside a single TAB-delimited field. The SY evaluator already
reads `SY X=135 ft` as a product. But both card-field splitters, antennaknobs'
importer (`nec_import._split_card_fields`) and the corpus tool
(`nec5_corpus._split_fields`), split the field on the space. Every later column
then shifted by one.

The corpus had five such decks. `2lsloper` (twice) is a 2-element 80 m sloper
wholly above ground, read as wires running 68 m underground, which made it a
phantom buried deck in two censuses. `G5RV` (twice) had its wire misplaced.
`Vehicle`'s `LD` card read `60.7 uh` as two fields. The raw GW lines below are
those decks' own spelling.
"""

from __future__ import annotations

import importlib.util
from pathlib import Path

import pytest

from antennaknobs.nec_import import _split_card_fields, parse_nec

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "nec5_corpus" / "nec5_corpus.py"

SLOPER_GW = "GW\t1\t11\t0\t-68 ft \tX\tY\t-68 ft\tZ\t#12"
G5RV_GW = "GW\t1\t31\t0\t-51 ft\t0\t0\t51 ft\t0\t#12"
VEHICLE_LD = "LD\t1\t4\t1\t0\t0\t60.7 uh\t0"


@pytest.fixture(scope="module")
def tool():
    spec = importlib.util.spec_from_file_location("nec5_corpus_units_probe", SCRIPT)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def _splitters(tool):
    return [("nec_import", _split_card_fields), ("nec5_corpus", tool._split_fields)]


@pytest.mark.parametrize(
    "line, want",
    [
        (SLOPER_GW, ["GW", "1", "11", "0", "-68ft", "X", "Y", "-68ft", "Z", "#12"]),
        (G5RV_GW, ["GW", "1", "31", "0", "-51ft", "0", "0", "51ft", "0", "#12"]),
        (VEHICLE_LD, ["LD", "1", "4", "1", "0", "0", "60.7uh", "0"]),
    ],
)
def test_a_number_and_its_unit_stay_one_field(tool, line, want):
    for name, split in _splitters(tool):
        assert split(line) == want, name


@pytest.mark.parametrize(
    "line, want",
    [
        # a number followed by a gauge or another number: separate fields
        (
            "GW\t1\t5\t0\t0\t0\t0\t0\t10\t4.0  #12",
            ["GW", "1", "5", "0", "0", "0", "0", "0", "10", "4.0", "#12"],
        ),
        ("GW\t1 2\t0", ["GW", "1", "2", "0"]),
        # the #1273 operator rejoin still works
        ("GM\t0\t0\t0\tFz + 0.24529\t1", ["GM", "0", "0", "0", "Fz+0.24529", "1"]),
    ],
)
def test_other_tab_field_shapes_are_unchanged(tool, line, want):
    for name, split in _splitters(tool):
        assert split(line) == want, name


SLOPER_DECK = (
    "CM K6NA - 2 Element 80m Sloper\nCE\nSY X=135 ft\nSY Y=64 ft\nSY Z=26 ft\n"
    f"{SLOPER_GW}\nGW\t2\t11\t0\t68 ft\tX\tY\t68 ft\tZ\t#12\nGE\t1\n"
    "EX\t0\t1\t6\t00\t1.0\t0.0\nGN\t2\t0\t0\t0\t13\t.005\nFR\t0\t1\t0\t0\t 3.8\nEN\n"
)


def test_the_sloper_imports_as_a_sloper_above_ground():
    deck = parse_nec(SLOPER_DECK, name="2lsloper", network=True)
    ft = 0.3048
    w = deck.wires[0]
    assert w.p1 == pytest.approx((0.0, -68 * ft, 135 * ft))
    assert w.p2 == pytest.approx((64 * ft, -68 * ft, 26 * ft))
    assert min(w.p1[2], w.p2[2]) > 0.0  # wholly above ground, not buried
    assert w.radius == pytest.approx(0.0010262, rel=1e-3)  # #12 AWG, not 1 ft


def test_the_sloper_translates_to_legal_gw_cards(tool, tmp_path):
    p = tmp_path / "2lsloper.nec"
    p.write_text(SLOPER_DECK, encoding="utf-8")
    rec = tool.translate_file(p, "2lsloper.nec", "double", False)
    assert rec["status"] == "translated", rec.get("reason")
    deck = rec["outputs"][0][1]
    gws = [ln.split() for ln in deck.splitlines() if ln.split()[:1] == ["GW"]]
    # each card: GW, tag, segment count, six coordinates, radius
    assert gws and all(len(g) == 10 for g in gws), gws
    z1, z2 = float(gws[0][5]), float(gws[0][8])
    assert z1 == pytest.approx(135 * 0.3048) and z2 == pytest.approx(26 * 0.3048)


def test_the_vehicle_load_reads_its_inductance(tool):
    fields = tool._split_fields(VEHICLE_LD)
    assert tool._value(fields[6], "LD", {}) == pytest.approx(60.7e-6)
