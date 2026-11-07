"""Several EX cards on one NEC-5 knot add, as NEC-5 reads them (AK#2205).

Measured on the licensed NEC-5 (numbers only) on the dipole below at 14 MHz:
1 V and 0.5 V on knot 10 carry 1.7724e-2 + j9.0041e-3 A, exactly the current
of one 1.5 V source there (67.269 - j34.173 ohm), whether the two cards name
the knot as end 2 of segment 10 or as end 1 of segment 11. SimNEC's port
measurement deck has this shape: two loads at one wire end become two cards
on one knot, and the import used to refuse it.

Every deck here is synthetic.
"""

from __future__ import annotations

from types import MappingProxyType

import pytest

from antennaknobs.builder import AntennaBuilder
from antennaknobs.cli import make_engine_factory
from antennaknobs.nec_import import parse_nec

FREQ = 14.0


def _deck(*ex: str, xq_more: tuple[str, ...] = ()) -> str:
    more = "".join(f"{c}\n" for c in xq_more)
    return (
        "CM synthetic\nCE\nGW 1 21 0 0 -5.1 0 0 5.1 .001\nGE 0\n"
        + "".join(f"{c}\n" for c in ex)
        + f"FR 0 1 0 0 {FREQ} 0\nXQ\n"
        + more
        + "EN\n"
    )


def _z(text: str) -> complex:
    deck = parse_nec(text, network=True, dialect="nec5")

    class Deck(AntennaBuilder):
        default_params = MappingProxyType({"freq": FREQ})

        def build_wires(self):
            return deck.wire_tuples(specs=True)

        def build_network(self):
            return deck.network()

    return complex(make_engine_factory("momwire:razor-2p", None)(Deck()).impedance()[0])


def test_two_sources_on_one_knot_are_one_source_of_their_sum():
    two = _z(_deck("EX 0 1 10 2 1.0 0", "EX 0 1 10 2 0.5 0"))
    one = _z(_deck("EX 0 1 10 2 1.5 0"))
    assert two == pytest.approx(one, rel=1e-12)


def test_the_two_ends_that_meet_at_a_knot_are_the_same_knot():
    spelled = _z(_deck("EX 0 1 10 2 1.0 0", "EX 0 1 11 1 0.5 0"))
    one = _z(_deck("EX 0 1 10 2 1.5 0"))
    assert spelled == pytest.approx(one, rel=1e-12)


def test_the_deck_says_it_added_them():
    deck = parse_nec(
        _deck("EX 0 1 10 2 1.0 0", "EX 0 1 11 1 0.5 0"), network=True, dialect="nec5"
    )
    (feed,) = deck.feeds
    assert feed.voltage == 1.5
    assert deck.summed_knot_sources == ((0, 10, 2),)
    assert "2 EX cards on knot 10 of wire 1" in deck.skipped_note()


def test_a_port_measurement_deck_opens():
    """SimNEC's shape: one run per port, the driven port at 1 V and the others
    at 1e-10 V, two of them on one knot. The first run reads; the shared knot
    carries 2e-10 V, a short to the printed digits, so the driven port reads
    as the deck with that knot simply closed."""
    probes = _z(
        _deck(
            "EX 0 1 11 1 1.0 0",
            "EX 0 1 4 2 1.0E-10 0",
            "EX 0 1 4 2 1.0E-10 0",
            xq_more=("EX 0 1 11 1 1.0E-10 0", "EX 0 1 4 2 1.0 0", "XQ"),
        )
    )
    alone = _z(_deck("EX 0 1 11 1 1.0 0"))
    assert probes == pytest.approx(alone, rel=1e-6)


def test_a_segment_centre_duplicate_still_refuses():
    """NEC-2's centre sources are not covered: that reading is unchecked."""
    deck = parse_nec(
        _deck("EX 0 1 11 0 1.0 0", "EX 0 1 11 0 0.5 0"), network=True, dialect="nec2"
    )
    with pytest.raises(ValueError, match="more than one EX card"):
        deck.network()
