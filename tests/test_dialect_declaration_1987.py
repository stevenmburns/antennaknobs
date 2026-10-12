"""A keyed dialect declaration: ``CM engine=nec4`` / ``CM dialect=nec4`` (AK#1987).

Maury Markowitz (OpenNEC, groups.io antenna-research #1615) suggested a comment
that programs aware of it write and read to say which engine a deck is for.
antennaknobs already read whole-comment ``CM NEC-4`` / ``CM NEC-5``; this adds
the keyed forms, and a NEC-2 / 4nec2 value, which had no spelling at all.
"""

from __future__ import annotations

import pytest

from antennaknobs.nec_import import parse_nec

# Jeff G8HUL's stake deck (AK#1982): GN 3 with a buried wire.
G8HUL = """\
CM
CE
GW 1 40 0 0 0 0 0 20.1 0.001
GW 2 10 0 0 0 0 0 -2 0.001
GW 99 1 10 10 10 10 10 10.1 0.001
GE -1
GN 3 0 0 0 13 0.005
EX 0 99 1 0 1 0 0
NT 1 1 99 1 0.2 0 -1.4 0 9.8 0
FR 0 0 0 0 7.2 0
EN
"""

DIPOLE = """\
{cm}CE
GW 1 21 -2.5 0 10 2.5 0 10 0.001
GE 0
GN 3 0 0 0 13 0.005
EX 0 1 11 0 1 0
FR 0 1 0 0 28.5 0
EN
"""


@pytest.mark.parametrize(
    ("cm", "dialect"),
    [
        ("CM engine=nec4", "nec4"),
        ("CM dialect=NEC-4.2", "nec4"),
        ("CM ENGINE: nec5", "nec5"),
        ("CM dialect = 4nec2", "nec2"),
        ("CM engine=nec2", "nec2"),
    ],
)
def test_a_keyed_declaration_sets_the_dialect_and_says_why(cm, dialect):
    deck = parse_nec(network=True, text=DIPOLE.format(cm=cm + "\n"))
    assert deck.dialect == dialect
    assert deck.dialect_chosen is None
    assert deck.dialect_detected == dialect
    assert deck.dialect_reason == f"a {cm} card on line 1"
    assert "no NEC-4 or NEC-5 marker found" not in deck.dialect_note()


def test_gn3_follows_the_declared_dialect():
    as4 = parse_nec(network=True, text=DIPOLE.format(cm="CM engine=nec4\n"))
    as2 = parse_nec(network=True, text=DIPOLE.format(cm="CM engine=4nec2\n"))
    assert as4.ground_spec == ("finite", 13.0, 0.005)
    assert as2.ground_spec == ("mininec", 13.0, 0.005)


def test_a_declared_4nec2_deck_is_not_guessed_into_nec4():
    # #1982 reads an undeclared GN 3 deck with a buried wire as NEC-4. A deck
    # that SAYS 4nec2 meant the MININEC ground, which cannot hold a buried
    # wire: it reads as declared, exactly as a reader choosing NEC-2 reads it.
    assert parse_nec(G8HUL).dialect == "nec4"  # undeclared: the #1982 guess
    deck = parse_nec("CM engine=4nec2\n" + G8HUL)
    assert (deck.dialect, deck.dialect_detected) == ("nec2", "nec2")
    assert deck.ground_spec == ("mininec", 13.0, 0.005)
    assert parse_nec("CM engine=nec4\n" + G8HUL).dialect == "nec4"


def test_a_reader_choice_still_wins():
    deck = parse_nec(
        network=True, text=DIPOLE.format(cm="CM engine=nec4\n"), dialect="nec2"
    )
    assert (deck.dialect, deck.dialect_chosen) == ("nec2", "nec2")


@pytest.mark.parametrize(
    "cm",
    ["CM engine=nec4 converted", "CM the engine=nec4 deck", "CM engine=mininec"],
)
def test_prose_and_unknown_values_declare_nothing(cm):
    deck = parse_nec(network=True, text=DIPOLE.format(cm=cm + "\n"))
    assert deck.dialect == "nec2"
    assert deck.dialect_reason == "no NEC-4 or NEC-5 marker found"


@pytest.mark.parametrize(
    "cms",
    [
        "CM engine=nec4\nCM dialect=nec5\n",
        "CM NEC-5\nCM engine=nec4\n",
        "CM engine=4nec2\nCM NEC-4.2\n",
    ],
)
def test_two_declarations_that_disagree_are_refused_by_name(cms):
    with pytest.raises(ValueError, match="declares NEC-.* and line .* declares"):
        parse_nec(network=True, text=DIPOLE.format(cm=cms))


def test_agreeing_declarations_are_fine():
    deck = parse_nec(network=True, text=DIPOLE.format(cm="CM NEC-5\nCM engine=nec5\n"))
    assert deck.dialect == "nec5"
