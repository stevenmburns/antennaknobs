"""A GN 3 deck with a buried wire reads as NEC-4 (AK#1982).

Jeff G8HUL (groups.io antenna-research #1604): a vertical on a ground stake,
`GN 3 0 0 0 13 0.005`, no NEC-4 or NEC-5 marker. Detection read it as NEC-2,
where GN 3 is 4nec2's MININEC ground (AK#1655): perfect for the currents, so
the stake was refused. Only NEC-4's GN 3, the Sommerfeld ground, models a
buried wire, so a buried wire settles which GN 3 the deck means.
"""

from __future__ import annotations

import pytest

from antennaknobs.nec_import import parse_nec

# Jeff's deck as posted, SY symbols and all.
G8HUL = """\
CM
CE
SY Len=20.1
SY Cp=2
GW 1 40 0 0 0 0 0 Len 0.001
GW 2 10 0 0 0 0 0 0-Cp 0.001
GW 99 1 10 10 10 10 10 10.1 0.001
GE -1
GN 3 0 0 0 13 0.005
EK
EX 0 99 1 0 1 0 0 'Source on the dummy line
NT 1 1 99 1 0.2 0 -1.4 0 9.8 0 '49:1 transformer
FR 0 0 0 0 7.2 0
EN
"""

# The same station with the stake lifted clear of the ground.
ABOVE = G8HUL.replace("GW 2 10 0 0 0 0 0 0-Cp 0.001", "GW 2 10 5 0 1 5 0 3 0.001")


def test_a_buried_wire_makes_gn3_nec4s_sommerfeld_ground():
    deck = parse_nec(G8HUL)
    assert deck.dialect == "nec4"
    assert deck.dialect_chosen is None
    assert deck.ground_spec == ("finite", 13.0, 0.005)
    assert deck.ground_method == "sommerfeld"
    note = deck.dialect_note()
    assert note.startswith("Read as NEC-4")
    assert "wire 2 runs below the ground" in note


def test_the_nec4_reading_is_what_choosing_nec4_reads():
    # Detection changes the ground and the EK reading, never the geometry or
    # where the feed lands: the same deck as a reader choosing NEC-4 gets.
    auto, chosen = (
        parse_nec(G8HUL, network=True),
        parse_nec(G8HUL, network=True, dialect="nec4"),
    )
    assert auto.wires == chosen.wires
    assert auto.feeds == chosen.feeds
    assert auto.ground_spec == chosen.ground_spec
    assert auto.extended_kernel == chosen.extended_kernel


def test_a_gn3_deck_with_nothing_buried_keeps_the_mininec_ground():
    deck = parse_nec(ABOVE)
    assert deck.dialect == "nec2"
    assert deck.ground_spec == ("mininec", 13.0, 0.005)
    note = deck.dialect_note()
    assert "no NEC-4 or NEC-5 marker found" in note
    assert "read as 4nec2's MININEC ground" in note
    assert "read the deck as NEC-4" in note


@pytest.mark.parametrize(
    ("dialect", "ground"),
    [("nec2", ("mininec", 13.0, 0.005)), ("nec4", ("finite", 13.0, 0.005))],
)
def test_a_chosen_dialect_still_wins_and_the_note_says_what_detection_reads(
    dialect, ground
):
    deck = parse_nec(G8HUL, dialect=dialect)
    assert deck.dialect == dialect
    assert deck.dialect_chosen == dialect
    assert deck.ground_spec == ground
    assert deck.dialect_detected == "nec4"
    assert "detection reads it as NEC-4" in deck.dialect_note()


def test_a_nec5_marker_still_wins():
    deck = parse_nec("CM NEC-5\n" + G8HUL, network=True)
    assert deck.dialect == "nec5"


def test_other_grounds_are_untouched():
    for card in ("GN 2 0 0 0 13 0.005", "GN 0 0 0 0 13 0.005"):
        deck = parse_nec(G8HUL.replace("GN 3 0 0 0 13 0.005", card))
        assert deck.dialect == "nec2", card
