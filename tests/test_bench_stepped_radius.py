"""Stepped-radius reference-suspect flag in the corpus bench (issue #885).

The #872 phase-5 movers analysis showed that on decks with stepped/multi-
radius elements the nec2c reference itself carries NEC-2's stepped-diameter
defect: {bs2 + NEC-5} agree with each other against {nec2c + nec2++} on
identical geometry for 44/46 formulation-class movers, all stepped-radius.
The census therefore flags such decks so their ΔΓ-vs-nec2c columns read as
reference-suspect (`d`), and the clean rollup excludes them.
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
from bench_nec_corpus import _stepped_radius, load_deck  # noqa: E402


def _deck(text: str):
    deck, _net, _ignored = load_deck(text, "t.nec")
    return deck


def test_two_radius_deck_is_flagged():
    deck = _deck(
        "GW 1 5 0 0 0 0 0 1 .001\nGW 2 5 0 0 1 0 0 2 .004\nEX 0 1 3 0 1 0\nEN\n"
    )
    assert _stepped_radius(deck) is True


def test_uniform_radius_multiwire_deck_is_not_flagged():
    # Different spellings of the same radius parse to the same float — a
    # multi-wire single-radius yagi-style deck stays unflagged.
    deck = _deck(
        "GW 1 5 0 0 0 0 0 1 .001\n"
        "GW 2 5 0 0 1 0 0 2 1.000E-3\n"
        "GW 3 5 0 1 0 0 1 1 .001\n"
        "EX 0 1 3 0 1 0\nEN\n"
    )
    assert _stepped_radius(deck) is False


def test_single_wire_deck_is_not_flagged():
    deck = _deck("GW 1 9 0 0 -1 0 0 1 .0005\nEX 0 1 5 0 1 0\nEN\n")
    assert _stepped_radius(deck) is False
