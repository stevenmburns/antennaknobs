"""antennaknobs#1391: a token that is not a number must not reach the deck.

Two ways the same thing went wrong, and the second was found by measuring the
first.

1. An UNRESOLVED SY SYMBOL. `normalize` kept any token substitution could not
   resolve, because a `GN` card's ground-screen file name looks like a symbol.
   So `GW 1 5 0 0 0 0 0 nosuch .001` translated, the deck was written with
   `nosuch` still in it, the report said `translated`, and the failure arrived at
   the engine as an engine error that was ours.

2. A TRAILING `!` COMMENT. `'` was stripped; `!` was not, and 60 decks in the
   public corpus use it. `4nec2-models/Objects/747plane.nec` came out of 1.6 with
   every one of its 423 GW cards carrying 13 to 15 fields instead of 9 — the
   comment prose read as geometry — and reported `translated`.

The fix keeps the WORD fields NEC actually has (file names on GN / GF / WG / PL)
and refuses anything else, naming the token. Getting that list right is not a
detail: with only GN exempt, 30 decks this tool refuses BY NAME for GF/WG read
"unreadable" instead, and two Cebik tutorial decks that translate fine stopped.
"""

from __future__ import annotations

import importlib.util
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "nec5_corpus" / "nec5_corpus.py"

HEAD = "CM x\nCE\n"
TAIL = "GE 0\nEX 0 1 3 0 1 0\nXQ\nEN\n"


@pytest.fixture(scope="module")
def tool():
    spec = importlib.util.spec_from_file_location("nec5_corpus_sym_probe", SCRIPT)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def _translate(tool, tmp_path, text):
    p = tmp_path / "d.nec"
    p.write_text(text, encoding="utf-8")
    return tool.translate_file(p, "d.nec", "exact", False)


def test_an_unresolved_symbol_makes_the_deck_unreadable(tool, tmp_path):
    """The issue's own example."""
    rec = _translate(tool, tmp_path, HEAD + "GW 1 5 0 0 0 0 0 nosuch .001\n" + TAIL)
    assert rec["status"] == "unreadable", rec
    assert "'nosuch'" in rec["reason"], rec["reason"]
    assert "GW field 8" in rec["reason"], rec["reason"]


def test_the_symbol_is_never_written_into_a_deck(tool, tmp_path):
    """The property that matters: not merely a better status, but that no output
    deck carries the token. A `translated` deck with `nosuch` in it is our bug
    delivered as the engine's error message."""
    rec = _translate(tool, tmp_path, HEAD + "GW 1 5 0 0 0 0 0 nosuch .001\n" + TAIL)
    assert not rec["outputs"], rec["outputs"]


@pytest.mark.parametrize(
    ("card", "what"),
    [
        ("GN 2 0 0 0 13 .005 1 0 NOFILE", "GN's NOFILE sentinel"),
        ("GN 2 0 0 0 13 .005 1 0 screen.dat", "a GN screen file name"),
        ("GF 0 RADIAL8.NGF", "a GF Green's-function file"),
        ("WG 0 R2-H18-V14.WGF", "a WG Green's-function file"),
        ("PL 2 3 0 m20-12-currents.dat", "a PL plot file"),
    ],
)
def test_the_word_fields_nec_actually_has_are_kept(tool, tmp_path, card, what):
    """Each of these is a FILE NAME, and each was found in the public corpus.
    Whole cards are exempt rather than one position, because a name's index moves
    with the card's optional fields."""
    rec = _translate(
        tool, tmp_path, HEAD + "GW 1 5 0 0 0 0 0 1 .001\n" + card + "\n" + TAIL
    )
    assert rec["status"] != "unreadable", (what, rec.get("reason"))


def test_a_trailing_bang_comment_is_stripped_not_read_as_geometry(tool, tmp_path):
    """747plane's shape. Through 1.6 the prose became extra GW fields."""
    deck = (
        HEAD + "GW 1 5 0 0 0 0 0 1 .001 ! Drive connection 118.35 23.67 4.73\n" + TAIL
    )
    rec = _translate(tool, tmp_path, deck)
    assert rec["status"] == "translated", rec.get("reason")
    gw = [ln for ln in rec["outputs"][0][1].splitlines() if ln.startswith("GW ")]
    assert len(gw) == 1, gw
    assert "!" not in gw[0] and "Drive" not in gw[0], gw[0]
    # GW takes exactly nine fields; 1.6 wrote thirteen here.
    assert len(gw[0].split()) - 1 == 9, gw[0]


def test_a_single_quote_comment_still_works(tool, tmp_path):
    """The marker that was always stripped, so the new loop cannot have lost it."""
    deck = HEAD + "GW 1 5 0 0 0 0 0 1 .001 ' a note\n" + TAIL
    rec = _translate(tool, tmp_path, deck)
    assert rec["status"] == "translated", rec.get("reason")
    gw = [ln for ln in rec["outputs"][0][1].splitlines() if ln.startswith("GW ")][0]
    assert len(gw.split()) - 1 == 9, gw


def test_a_comment_marker_inside_a_CM_line_is_left_alone(tool, tmp_path):
    """CM text is taken before the field split, so a `!` in prose is prose."""
    rec = _translate(
        tool, tmp_path, "CM 747! needs nec2d1k9\nCE\nGW 1 5 0 0 0 0 0 1 .001\n" + TAIL
    )
    assert rec["status"] == "translated", rec.get("reason")
    assert "747! needs nec2d1k9" in rec["outputs"][0][1]


def test_a_good_deck_is_untouched(tool, tmp_path):
    rec = _translate(tool, tmp_path, HEAD + "GW 1 5 0 0 0 0 0 1 .001\n" + TAIL)
    assert rec["status"] == "translated", rec.get("reason")
