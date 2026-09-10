"""antennaknobs#1369: CW is a NEC-5 card, so the corpus tool translates it.

The tool used to refuse a catenary deck outright ("CW (NEC-4 catenary wire)
has no NEC-5 counterpart"), which is a claim the NEC-5 manual contradicts:
NEC-5 has a CW card in the structure-geometry section.

The mapping is the identity, field for field, because the two dialects spell
the card the same way:

    NEC-4.2   CW ITG NS X1 Y1 Z1 X2 Y2 Z2 RAD ICAT RHM ZM
    NEC-5     CW ITG NS X1 Y1 Z1 X2 Y2 Z2 RAD ICAT RHM ZM
              ^0  ^1 ^2 ^3 ^4 ^5 ^6 ^7 ^8  ^9   ^10 ^11

So the card is passed through with no note, and the ONE field the translator
may touch is NS (field 1) -- the same remesh every GW/GA/GH gets, because a
CW carries segments that EX/LD address by (tag, segment) and NEC-5 puts
sources on knots. ICAT and its two mode arguments RHM / ZM ride along
untouched at fields 9-11, which is what this test pins: a translator that
re-spelled the card, or that fed CW to the mesh by rebuilding the line,
would drop them.
"""

from __future__ import annotations

import importlib.util
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "nec5_corpus" / "nec5_corpus.py"

# The catenary card as 4nec2 writes it on its NEC-4 slot, from
# models/Nec4/Catenary.nec (captured in
# docs/status/2026-08-18-4nec2-subengine-capture.md): 12 fields, ICAT 2.
CW_CARD = "CW 1 39 -19.64 0.0 20. 19.64 0.0 20. 0.001 2 19.64 1"

DECK = f"""CM a hanging catenary wire
CE
{CW_CARD}
GE 0
EX 0 1 20 0 1 0
GN -1
XQ
EN
"""


@pytest.fixture(scope="module")
def tool():
    spec = importlib.util.spec_from_file_location("nec5_corpus_cw_probe", SCRIPT)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def _translate(tool, tmp_path, text: str, name: str = "catenary.nec") -> dict:
    p = tmp_path / name
    p.write_text(text, encoding="utf-8")
    return tool.translate_file(p, name, "exact", False)


def test_a_catenary_deck_translates_instead_of_refusing(tool, tmp_path):
    rec = _translate(tool, tmp_path, DECK)
    assert rec["status"] == "translated", rec.get("reason")
    deck = rec["outputs"][0][1]
    cw = [ln for ln in deck.splitlines() if ln.startswith("CW ")]
    assert len(cw) == 1, deck
    assert cw[0].split()[0] == "CW"


def test_the_cw_fields_stay_in_their_nec5_places(tool, tmp_path):
    """Every field but NS is the one the NEC-4 deck wrote, in its own slot."""
    rec = _translate(tool, tmp_path, DECK)
    f = [ln for ln in rec["outputs"][0][1].splitlines() if ln.startswith("CW ")][
        0
    ].split()[1:]
    assert len(f) == 12, f
    assert f[0] == "1"  # ITG, the tag EX addresses
    # As written: a short token is not reformatted, so `20.` stays `20.`.
    assert f[2:9] == ["-19.64", "0.0", "20.", "19.64", "0.0", "20.", "0.001"]
    assert f[9:] == ["2", "19.64", "1"]  # ICAT RHM ZM -- NEC-4-only slots kept


def test_a_referenced_cw_is_remeshed_so_the_feed_lands_on_a_knot(tool, tmp_path):
    """CW carries segments, so it goes through the mesh like GW.

    The deck feeds segment 20 of 39 -- the middle segment of an odd count,
    where no knot exists. `--offcenter exact` adds one segment (39 -> 40) so
    the wire's centre IS a knot, and the source moves to end 2 of segment 20
    of the new mesh. A CW left out of `Geometry` would leave NS at 39 and
    address a knot that is half a segment away.
    """
    rec = _translate(tool, tmp_path, DECK)
    deck = rec["outputs"][0][1]
    cw = [ln for ln in deck.splitlines() if ln.startswith("CW ")][0]
    assert cw.split()[2] == "40", cw
    ex = [ln for ln in deck.splitlines() if ln.startswith("EX ")][0]
    assert ex.split()[:5] == ["EX", "0", "1", "20", "2"], ex
    assert any("39 -> 40 segments" in n for n in rec["notes"]), rec["notes"]


def test_the_card_itself_earns_no_note(tool, tmp_path):
    """The dialects agree, so there is nothing to tell the reader about CW."""
    rec = _translate(tool, tmp_path, DECK)
    assert rec["status"] == "translated", rec.get("reason")
    assert not [n for n in rec["notes"] if "CW" in n and "segments" not in n], rec[
        "notes"
    ]


def test_a_catenary_only_deck_is_geometry(tool, tmp_path):
    """`CW` alone must not read as a geometry-less deck (nor as a non-deck).

    `_looks_like_deck` gates what `fetch` keeps, so a catenary deck that the
    regex does not recognise never reaches `translate` at all.
    """
    text = DECK.replace("EX 0 1 20 0 1 0\n", "")
    rec = _translate(tool, tmp_path, text)
    assert rec["status"] == "translated", rec.get("reason")
    assert tool._looks_like_deck(text.encode())
