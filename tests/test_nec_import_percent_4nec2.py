"""4nec2's percentage positions (AK#1496).

4nec2 (5.7.0 and later) lets EX, LD, TL and NT give a segment as a percentage
of the wire's length, measured from end 1: ``EX 0 2 50% 0 1 0``. AC6LA sent
4nec2's own Example 3 with the centre wire given two segments, where 50% lands
exactly on the joint between them. The importer used to refuse the card
("bad number '50%'").

With ``network=True`` the percentage is the exact position: a port at that
point on the uncut wire, which every engine meshes to carry exactly there
(AK#1469). The path without positioned ports uses the segment whose centre is
nearest, a tie on a boundary going to the lower segment.
"""

from __future__ import annotations

import pytest

from antennaknobs.nec_import import parse_nec
from antennaknobs.network import Load, PortOnWire

EXAMPLE3_2SEG = """\
CM Example 3 :\tInverted-V over ground
CE
SY hgh=20
SY len=20
SY ang=110
SY Z=len*cos(ang/2), X=len*sin(ang/2)
GW\t1\t20\t-X\t0\thgh-Z\t-0.1\t0\thgh\t#12
GW\t2\t2\t-0.1\t0\thgh\t0.1\t0\thgh\t#12
GW\t3\t20\t0.1\t0\thgh\tX\t0\thgh-z\t#12
GE
GN\t2\t0\t0\t0\t14\t.006
EX\t0\t2\t50%\t0\t1\t0
FR\t0\t1\t0\t0\t3.680
EN
"""

LINE10 = "GW 1 10 0 -5 10 0 5 10 0.001\nGE\n{cards}FR 0 1 0 0 14 0\nEN\n"


def _tuples(deck):
    return [(t[2], t[4] if len(t) > 4 else None) for t in deck.wire_tuples()]


def test_daniels_example_3_feeds_the_true_middle_of_the_two_segment_wire():
    deck = parse_nec(EXAMPLE3_2SEG, name="2segCtrExample3.nec", network=True)
    (feed,) = deck.feeds
    assert (feed.wire, feed.seg, feed.at) == (1, 1, 0.5)
    # 50% of the wire is its middle: the wire stays whole with a plain port,
    # and each engine meshes it so the gap sits there.
    assert _tuples(deck) == [(20, None), (2, "feed"), (20, None)]
    assert deck.network().ports["feed"] == PortOnWire("feed")


def test_without_the_network_path_the_nearest_segment_is_used_ties_going_low():
    deck = parse_nec(EXAMPLE3_2SEG, name="2segCtrExample3.nec")
    (feed,) = deck.feeds
    assert (feed.seg, feed.at) == (1, 0.5)


@pytest.mark.parametrize(
    ("pct", "seg", "at"),
    [
        ("30%", 3, 0.3),  # 3.0 segments in: the boundary, so the lower segment
        ("31%", 4, 0.31),
        ("5%", 1, 0.05),
        ("95%", 10, 0.95),
        ("0%", 1, None),  # a gap cannot sit at a wire end
        ("100%", 10, None),
    ],
)
def test_a_percentage_names_its_nearest_segment_and_keeps_its_position(pct, seg, at):
    deck = parse_nec(
        LINE10.format(cards=f"EX 0 1 {pct} 0 1 0\n"), name="p.nec", network=True
    )
    (feed,) = deck.feeds
    assert feed.seg == seg
    assert feed.at == (pytest.approx(at) if at is not None else None)


def test_an_off_middle_percentage_is_a_positioned_port_on_the_whole_wire():
    deck = parse_nec(
        LINE10.format(cards="EX 0 1 31% 0 1 0\n"), name="p.nec", network=True
    )
    assert _tuples(deck) == [(10, "feed")]
    port = deck.network().ports["feed"]
    assert port.at == pytest.approx(0.31)


def test_an_sy_variable_can_carry_the_percentage():
    deck = parse_nec(
        "SY p=25\n" + LINE10.format(cards="EX 0 1 p% 0 1 0\n"),
        name="p.nec",
        network=True,
    )
    assert deck.feeds[0].at == pytest.approx(0.25)


def test_a_load_at_one_percentage_keeps_its_position():
    deck = parse_nec(
        LINE10.format(cards="EX 0 1 5 0 1 0\nLD 0 1 75% 75% 50 0 0\n"),
        name="p.nec",
        network=True,
    )
    (load,) = deck.loads
    assert (load.seg, load.at) == (8, 0.75)
    net = deck.network()
    (branch,) = [b for b in net.branches if isinstance(b, Load)]
    assert net.ports[branch.port].at == pytest.approx(0.75)


def test_a_load_range_in_percentages_expands_over_its_nearest_segments():
    deck = parse_nec(
        LINE10.format(cards="EX 0 1 5 0 1 0\nLD 0 1 20% 40% 5 0 0\n"),
        name="p.nec",
        network=True,
    )
    assert [(ld.seg, ld.at) for ld in deck.loads] == [(2, None), (3, None), (4, None)]


def test_a_transmission_line_end_can_be_a_percentage():
    two = (
        "GW 1 10 0 -5 10 0 5 10 0.001\nGW 2 10 1 -5 10 1 5 10 0.001\nGE\n"
        "EX 0 1 5 0 1 0\nTL 1 50% 2 25% 300 0 0 0 0 0\nFR 0 1 0 0 14 0\nEN\n"
    )
    deck = parse_nec(two, name="tl.nec", network=True)
    (tl,) = deck.tls
    assert (tl.seg_a, tl.at_a, tl.seg_b, tl.at_b) == (5, 0.5, 3, 0.25)
    # Zero length is the distance between the two exact points: 1 m across.
    assert tl.length == pytest.approx((1.0 + 2.5**2) ** 0.5)


@pytest.mark.parametrize(
    ("cards", "message"),
    [
        ("EX 0 1 120% 0 1 0\n", "off the wire"),
        ("EX 0 0 50% 0 1 0\n", "needs a wire tag"),
        ("GW 1 4 0 0 0 0 0 1 1% \n", "only as a position"),
    ],
)
def test_a_percentage_that_names_no_single_place_is_refused_by_name(cards, message):
    text = (
        LINE10.format(cards=cards)
        if cards.startswith("EX")
        else cards + "GE\nEX 0 1 1 0 1 0\nEN\n"
    )
    with pytest.raises(ValueError, match=message):
        parse_nec(text, name="bad.nec", network=True)


def test_a_percentage_on_a_tag_shared_by_two_wires_is_ambiguous():
    text = (
        "GW 1 10 0 -5 10 0 5 10 0.001\nGW 1 10 1 -5 10 1 5 10 0.001\nGE\n"
        "EX 0 1 50% 0 1 0\nFR 0 1 0 0 14 0\nEN\n"
    )
    with pytest.raises(ValueError, match="names 2 wires"):
        parse_nec(text, name="shared.nec", network=True)


def test_two_positions_on_one_segment_are_refused():
    deck = parse_nec(
        LINE10.format(cards="EX 0 1 31% 0 1 0\nLD 0 1 33% 33% 50 0 0\n"),
        name="p.nec",
        network=True,
    )
    with pytest.raises(ValueError, match="fall on one segment"):
        deck.wire_tuples()


def test_a_percentage_is_not_a_nec5_segment_end():
    with pytest.raises(ValueError, match="cannot also name a NEC-5 segment end"):
        parse_nec(LINE10.format(cards="EX 0 1 50% 2 1 0\n"), name="p.nec", network=True)
