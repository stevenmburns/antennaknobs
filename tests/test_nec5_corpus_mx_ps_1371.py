"""antennaknobs#1371: NEC-4-only MX and PS are dropped, not passed through.

The translator's emit loop writes any card it has no rule for verbatim, so two
NEC-4.2-only control cards used to reach NEC-5 untouched:

- ``MX`` — NEC-4's matrix memory allocation;
- ``PS`` — NEC-4's print of the electrical lengths of the segments.

NEC-5 has neither, so a deck carrying them reads as an input error there
rather than as the model. They join EK/KH/CP/IS/JN/VC/MP in `_DROP_CARDS`:
removed from the deck, and named in a `CM nec5_corpus:` note so the reader
sees what left.
"""

from __future__ import annotations

import importlib.util
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "nec5_corpus" / "nec5_corpus.py"

DECK = """CM a NEC-4 deck with the two allocation/print cards
CE
GW 1 5 0 0 0 0 0 1 .001
GE 0
MX 200000
PS 0
EX 0 1 3 0 1 0
GN -1
XQ
EN
"""


@pytest.fixture(scope="module")
def tool():
    spec = importlib.util.spec_from_file_location("nec5_corpus_mxps_probe", SCRIPT)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


@pytest.fixture()
def translated(tool, tmp_path):
    p = tmp_path / "nec4.nec"
    p.write_text(DECK, encoding="utf-8")
    rec = tool.translate_file(p, "nec4.nec", "exact", False)
    assert rec["status"] == "translated", rec.get("reason")
    return rec


@pytest.mark.parametrize("mn", ["MX", "PS"])
def test_the_card_does_not_reach_the_translated_deck(translated, mn):
    body = [
        ln
        for ln in translated["outputs"][0][1].splitlines()
        if not ln.startswith("CM") and not ln.startswith("CE")
    ]
    assert not [ln for ln in body if ln.split()[:1] == [mn]], body


@pytest.mark.parametrize("mn", ["MX", "PS"])
def test_the_note_names_the_card_it_dropped(translated, mn):
    notes = [n for n in translated["notes"] if n.startswith(mn + " ")]
    assert len(notes) == 1, translated["notes"]
    assert "dropped: not a NEC-5 command" in notes[0]
    assert f"CM nec5_corpus: {notes[0]}" in translated["outputs"][0][1]


def test_the_rest_of_the_deck_is_untouched(translated):
    """Dropping the two cards is the whole change: the wire and the source
    still translate the way they do without them."""
    lines = [
        ln for ln in translated["outputs"][0][1].splitlines() if not ln.startswith("CM")
    ]
    assert lines == [
        "CE",
        "GW 1 6 0 0 0 0 0 1 .001",
        "GE 0",
        "EX 0 1 3 2 1 0",
        "GN -1",
        "XQ",
        "EN",
    ], lines


@pytest.mark.parametrize("mn", ["MX", "PS"])
def test_the_sentence_matches_the_cards_already_dropped(tool, mn):
    """Same shape as EK/KH/CP/IS/JN/VC, so the notes read as one family."""
    assert tool._DROP_CARDS[mn].startswith(mn + " (NEC-4 ")
    assert tool._DROP_CARDS[mn].endswith("dropped: not a NEC-5 command")
