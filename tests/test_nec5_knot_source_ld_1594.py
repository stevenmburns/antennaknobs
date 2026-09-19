"""AK#1594: an `EX 4` knot source at a wire end plus ANY `LD` on the same
wire is refused.

`wire_tuples` cuts a wire into pieces at every claimed knot (issue #824's
rule: a piece can carry at most one attachment). Knot 0 rides the wire's
FIRST piece; every other claimed knot rides the piece ENDING at it. With no
other cut between them, knot 0 and the next claimed knot land on the SAME
first piece and both claim it -- even though nothing downstream of that
piece needs the cut for any other reason. The fix adds one when the next
claimed knot is >= 2 (room for a 1-segment piece between them); when the
next claimed knot is 1, a 1-segment piece has only one interior boundary to
give and the refusal is correct -- there genuinely is no room.

Dan AC6LA's `Cardioidmodnec5.nec` (QRZ 1003328 #107) is the reporting
deck: two lambda/4 verticals over perfect ground, each loaded partway up,
fed in quadrature by EZNEC's NEC-5 `EX 4` (a knot source at end 1 of
segment 1 -- the wire's own base).
"""

from __future__ import annotations

import pytest

from antennaknobs.nec_import import parse_nec

CARDIOID_NEC5 = """CM Cardioid
CM
CM ! Written by EZNEC/Pro+ v. 7.0 in NEC-5 format.
CE
GW 1,6,0.,0.,0.,0.,0.,.242,.000121
GW 2,6,.25,0.,0.,.25,0.,.242,.000121
GE 1
LD 4,1,2,0,18.,0.
LD 4,2,2,0,18.,0.
FR 0,1,0,0,299.7925
GN 1
EX 4,1,-1,0,1.414214,0.
EX 4,2,-1,0,0.,-1.414214
RP 0,1,361,1000,90.,0.,0.,1.,0.
EN
"""


def _named(deck):
    return [(t[2], t[4] if len(t) > 4 else None) for t in deck.wire_tuples(specs=True)]


def test_cardioid_deck_imports_and_wire_tuples_succeeds():
    deck = parse_nec(CARDIOID_NEC5, name="Cardioidmodnec5.nec", network=True)
    named = _named(deck)
    # Each wire cuts into three pieces: the 1-segment knot-0 feed at the
    # base, the 1-segment load at knot 2, and the untouched 4-segment tail.
    assert named == [
        (1, "feed1"),
        (1, "load1"),
        (4, None),
        (1, "feed2"),
        (1, "load2"),
        (4, None),
    ]


def test_ld_moved_further_out_still_imports():
    """The issue's own table: moving the LD to segment 4 (knot 4) still
    collides with knot 0 on the first piece absent the fix, and the cut
    lands wherever the next claimed knot is -- here knot 4, not knot 2."""
    deck = parse_nec(
        CARDIOID_NEC5.replace("LD 4,1,2,0,18.,0.", "LD 4,1,4,0,18.,0."),
        name="t.nec",
        network=True,
    )
    named = _named(deck)
    assert named[0] == (1, "feed1")
    assert named[1] == (3, "load1")  # knot 1..4, the piece ending at knot 4


def test_one_wire_only_still_imports():
    """The issue's table: dropping the second element (GW 2 and its EX/LD)
    reproduces on one wire alone."""
    text = """CE
GW 1,6,0.,0.,0.,0.,0.,.242,.000121
GE 1
LD 4,1,2,0,18.,0.
FR 0,1,0,0,299.7925
GN 1
EX 4,1,-1,0,1.414214,0.
EN
"""
    deck = parse_nec(text, name="t.nec", network=True)
    assert _named(deck) == [(1, "feed"), (1, "load1"), (4, None)]


def test_knot_0_and_knot_1_collision_still_refuses():
    """The genuine no-room case (requirement 2): a knot source at knot 0 and
    a claim at knot 1 -- the wire's only interior knot when it has 2
    segments -- leaves no room to cut between them. A 1-segment piece has
    only one boundary on each side; splitting it further isn't possible, so
    both claims land on the one piece between knots 0 and 1 and the refusal
    is correct, not a bug the fix should have removed."""
    text = """CE
GW 1,2,0,0,0,0,0,1,.001
GE 1
FR 0,1,0,0,10
EX 4,1,-1,0,1,0.
LD 4,1,1,2,18.,0.
EN
"""
    deck = parse_nec(text, name="t.nec", network=True)
    with pytest.raises(ValueError, match="piece between knots 0 and 1"):
        deck.wire_tuples(specs=True)
