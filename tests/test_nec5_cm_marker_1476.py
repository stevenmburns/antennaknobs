"""AK#1476: a `CM NEC-5` card declares a deck NEC-5.

NEC-2 and NEC-5 read the same `EX` card differently. In NEC-5, per its manual,
`I4 = 0` puts the source at a segment END: end 2 for a positive segment, end 1
for a negative one. NEC-2 reads the card as the segment's CENTRE. The importer
reads NEC-5 only when a deck shows it, so AC6LA's hand-written deck, with no
`NOFILE` and no end field, split around segment 10. A deck can now say so.
"""

import pytest

from antennaknobs.nec_import import parse_nec

# AC6LA's deck (QRZ, 2026-09-12), GW and EX as he wrote them.
DAN = "SY len=.4836\nGW 1 20 0 -len/2 0 0 len/2 0 .0001\nEX 0 1 10 0 1 0\n"


def _wires(text):
    deck = parse_nec(text, name="dan2.nec", network=True)
    return deck, [(w.n_seg, w.name) for w in deck.wire_tuples(specs=True)]


def test_without_the_card_the_deck_still_reads_as_nec2():
    """NEC-2 reads EX segment 10 as the centre of segment 10: a port at 19/40
    of the whole wire (AK#1469 part B), not the wire's middle."""
    deck, wires = _wires(DAN)
    assert deck.nec5_dialect is False
    assert wires == [(20, "feed")]
    assert deck.network().ports["feed"].at == pytest.approx(19 / 40)


@pytest.mark.parametrize("card", ["CM NEC-5", "CM nec-5", "CM NEC5", "cm  NEC-5  "])
def test_the_card_makes_the_centre_source_a_whole_wire(card):
    deck, wires = _wires(f"{card}\n{DAN}")
    assert deck.nec5_dialect is True
    assert wires == [(20, "feed")]
    (feed,) = deck.feeds
    assert (feed.seg, feed.edge) == (10, 2)
    assert getattr(deck.network().ports["feed"], "at", None) is None


@pytest.mark.parametrize(
    "card", ["CM converted from a NEC-5 deck", "CM NEC-5 corpus", "CM NEC-2"]
)
def test_a_comment_that_only_mentions_nec5_declares_nothing(card):
    deck, wires = _wires(f"{card}\n{DAN}")
    assert deck.nec5_dialect is False
    assert deck.network().ports["feed"].at == pytest.approx(19 / 40)


@pytest.mark.parametrize(
    "ex, edge",
    [
        ("EX 0 1 -10 0 1 0", 1),  # I4 = 0, negative segment: end 1
        ("EX 0 1 10 1 1 0", 1),  # I4 = 1 names end 1 once the deck is NEC-5
        ("EX 0 1 10 2 1 0", 2),
    ],
)
def test_a_declared_deck_takes_the_manuals_full_end_rule(ex, edge):
    deck = parse_nec(
        "CM NEC-5\n" + DAN.replace("EX 0 1 10 0 1 0", ex), name="d.nec", network=True
    )
    (feed,) = deck.feeds
    assert (feed.seg, feed.edge) == (10, edge)


def test_end_1_of_segment_10_is_an_off_centre_knot_on_the_whole_wire():
    deck, wires = _wires(
        "CM NEC-5\n" + DAN.replace("EX 0 1 10 0 1 0", "EX 0 1 10 1 1 0")
    )
    assert wires == [(20, "feed")]
    assert deck.network().ports["feed"].at == pytest.approx(9 / 20)


def test_a_declared_decks_gn_0_is_sommerfeld():
    deck = parse_nec(
        "CM NEC-5\n" + DAN + "GN 0 0 0 0 13 .005\n", name="d.nec", network=True
    )
    assert deck.ground_method == "sommerfeld"
    assert deck.ground_spec == ("finite", 13.0, 0.005)


def test_a_declared_deck_still_needs_the_network_path():
    with pytest.raises(ValueError, match="network=True"):
        parse_nec("CM NEC-5\n" + DAN, name="d.nec")
