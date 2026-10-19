"""AK#2021: a ``!`` after a card's fields starts a comment to the end of the
line, the trailing-comment form NEC-4 brought in and NEC-5 kept. 4nec2's own
sample set writes it on GW cards (``... ! Drive connection``), which the
importer refused as ``bad number '!'``.

Synthetic decks only. The ``'`` and CM/CE rules are pinned in
``test_nec_import_comments.py`` and must not move.
"""

import pytest

from antennaknobs.file_designs import builder_from_file
from antennaknobs.nec_import import classify_sy, parse_nec, resolve_sy

PLAIN = (
    "CM two-wire test deck\n"
    "CE\n"
    "SY h=5\n"
    "GW 1 11 0 0 0 0 0 h 0.001\n"
    "GW 2 5 0 0 h 0 1 h 0.001\n"
    "GS 0 0 1\n"
    "GE 0\n"
    "LD 4 2 3 3 50 0\n"
    "EX 0 1 6 0 1 0\n"
    "FR 0 1 0 0 14.1 0\n"
    "EN\n"
)

BANGED = (
    "CM two-wire test deck\n"
    "CE\n"
    "SY h=5 ! height in metres\n"
    "GW 1 11 0 0 0 0 0 h 0.001 ! Drive connection, the fed wire\n"
    "GW 2 5 0 0 h 0 1 h 0.001! glued to the radius, no space\n"
    "GS 0 0 1 !scale\n"
    "GE 0 ! free space\n"
    "LD 4 2 3 3 50 0 ! a 50 ohm load\n"
    "EX 0 1 6 0 1 0 ! source\n"
    "FR 0 1 0 0 14.1 0 ! one frequency\n"
    "EN ! end\n"
)


def _geometry(deck):
    return [(w.tag, w.n_seg, w.p1, w.p2, w.radius) for w in deck.wires]


def test_trailing_bang_reads_as_the_same_deck():
    plain = parse_nec(PLAIN, name="plain", network=True)
    banged = parse_nec(BANGED, name="banged", network=True)
    assert _geometry(banged) == _geometry(plain)
    assert banged.feeds == plain.feeds
    assert banged.loads == plain.loads
    assert len(banged.loads) == 1
    assert banged.freq_mhz == plain.freq_mhz
    assert banged.ground == plain.ground


def test_trailing_bang_after_comma_separated_fields():
    deck = parse_nec(
        "CE\nGW,1,11,0,0,0,0,0,5,0.001, ! comma deck\nGE,0\nEX,0,1,6,0,1,0\nEN\n",
        name="t",
    )
    assert deck.wires[0].p2[2] == pytest.approx(5.0)


def test_bang_and_quote_on_one_line():
    deck = parse_nec(
        "CE\nGW 1 11 0 0 0 0 0 5 0.001 ! drive ' and a quote\n"
        "GE 0 ' quote first ! then a bang\nEX 0 1 6 0 1 0\nEN\n",
        name="t",
    )
    assert len(deck.wires) == 1


def test_cm_keeps_its_bang():
    # EZNEC's writer stamp is a CM whose text starts with `!`; CM/CE text is
    # never cut at it.
    deck = parse_nec("CM a ! inside a comment\n" + PLAIN.split("\n", 1)[1], name="t")
    assert "a ! inside a comment" in deck.comments


def test_bang_in_first_column_still_refused():
    # A `!` with no card in front of it is not a trailing comment.
    with pytest.raises(ValueError, match="expected a NEC card mnemonic"):
        parse_nec("CE\n! a whole-line comment\n" + PLAIN.split("CE\n", 1)[1])


def test_resolve_sy_drops_the_bang_comment():
    out = resolve_sy(BANGED, name="t")
    assert "!" not in out
    assert out == resolve_sy(PLAIN, name="t")


def test_classify_sy_reads_through_the_bang():
    (sym,) = classify_sy(BANGED, name="t")
    assert sym.name == "h"
    assert sym.value == pytest.approx(5.0)


def test_no_continuation_onto_a_bang_comment():
    # A wrapped field after a `!` comment would land inside the comment and
    # be dropped with it, so it does not join (the `'` rule, #1295): the
    # orphan line is refused by name rather than silently lost.
    with pytest.raises(ValueError, match="expected a NEC card mnemonic"):
        parse_nec("CE\nGW 1 11 0 0 0 0 0 5 ! wrapped\n0.001\nGE 0\nEN\n")


def test_builder_from_file_imports_a_banged_deck(tmp_path):
    path = tmp_path / "banged.nec"
    path.write_text(BANGED)
    builder_from_file(str(path))
