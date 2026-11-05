"""A split source inside a wire (the 11-05 EZNEC sitting).

EZNEC moves a split source (W voltage, J current) placed inside a wire to a
knot, the one its NEC-5 export names. Its NEC-2 export then writes a split
voltage as two sources at half the voltage on the segments either side
(TOPBOB40: EX 0 on segments 1 and 2 of a 2-segment wire, .707 V each), and a
split current as the current on the segment meeting the knot (4.6.8c, the
half-squares). Under NEC-5 it is one source at the knot. The import used to
refuse a split anywhere but a wire end.
"""

from __future__ import annotations

import math

import pytest

from antennaknobs.ez_import import read_ez
from test_ez_import_1958 import ez_file

# One straight 10-segment wire.
WIRE = [(0.0, -5.15, 10.0, 0.0, 5.15, 10.0, 0.002, 10)]


def _ex(raw, reading=None):
    imp = read_ez(raw, reading=reading)
    return [l.split() for l in imp.nec_text.splitlines() if l.startswith("EX ")]


def test_a_split_voltage_inside_a_wire_is_two_half_sources_either_side_of_its_knot():
    ex = _ex(ez_file(WIRE, sources=((1, 30.0, 1.0, 0.0, "W"),)))
    # 30 % of 10 segments is knot 3: segments 3 and 4, half of 1 V rms each.
    assert [(e[1], e[2], e[3]) for e in ex] == [("0", "1", "3"), ("0", "1", "4")]
    for e in ex:
        assert float(e[5]) == pytest.approx(math.sqrt(2) / 2)


def test_a_split_current_inside_a_wire_is_one_source_on_the_segment_meeting_its_knot():
    ex = _ex(ez_file(WIRE, sources=((1, 30.0, 1.0, 0.0, "J"),)))
    assert len(ex) == 1
    assert ex[0][2:4] == ["1", "3"]
    assert float(ex[0][5]) == pytest.approx(math.sqrt(2))  # the full current


@pytest.mark.parametrize("kind", ["W", "J"])
def test_under_nec5_it_is_one_source_at_the_knot(kind):
    ex = _ex(ez_file(WIRE, sources=((1, 30.0, 1.0, 0.0, kind),)), reading="nec5")
    assert len(ex) == 1
    assert ex[0][2:4] == ["1", "3"]
    assert float(ex[0][5]) == pytest.approx(math.sqrt(2))


def test_it_solves_as_one_feed_point_would():
    """The two half-voltage sources sit either side of one knot: together
    they drive the antenna as the NEC-5 reading's one source at that knot
    does, to the difference between centre and edge placement."""
    from antennaknobs.file_designs import builder_from_text
    from antennaknobs.engines import MomwireEngine

    raw = ez_file(WIRE, sources=((1, 50.0, 1.0, 0.0, "W"),))
    text = raw.decode("latin-1")
    two = builder_from_text("split.ez", text)
    one = builder_from_text("split.ez", text, dialect="nec5")
    z2 = MomwireEngine(two(), ground=two.file_ground).impedance()
    z1 = complex(MomwireEngine(one(), ground=one.file_ground).impedance()[0])
    # Each half-voltage port sees half the feed impedance, so the two add up
    # to the one source's, to what moving from two segment centres to one
    # segment end costs on a 10-segment wire (2.4 % here).
    assert complex(z2[0]) + complex(z2[1]) == pytest.approx(z1, rel=4e-2)
