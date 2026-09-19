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

AK#1598 then narrowed WHERE that cut is reached from. A knot-0 source on a
wire END standing alone in the GROUND PLANE is a ground-contact feed now, not
a series EMF: the wire is not cut at all and both attachments become
positioned ports at their exact places, which is strictly better than cutting
and is what makes Dan's deck actually SOLVE rather than merely import. So the
cut this module gates is now reached at a knot 0 that is a JUNCTION -- the
remaining way a wire end carries a series EMF -- and both worlds are covered
below.
"""

from __future__ import annotations

import numpy as np
import pytest

from antennaknobs.engines import MomwireEngine
from antennaknobs.file_designs import builder_from_file
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

# The same collision with knot 0 at a JUNCTION instead of on the ground: a
# second wire ends at the fed knot, so the source is a series EMF through that
# node and `wire_tuples` must still cut around it (AK#1594's own case, in the
# shape AK#1598 leaves it in). Elevated, so nothing here is a ground contact.
JUNCTION_KNOT0 = """CM ! Written by EZNEC/Pro+ v. 7.0 in NEC-5 format.
CE
GW 1,6,0.,0.,1.,0.,0.,1.242,.000121
GW 2,4,0.,0.,1.,.3,0.,1.,.000121
GE 1
LD 4,1,2,0,18.,0.
FR 0,1,0,0,299.7925
GN 1
EX 4,1,-1,0,1.414214,0.
EN
"""


def _named(deck):
    return [(t[2], t[4] if len(t) > 4 else None) for t in deck.wire_tuples(specs=True)]


def _solve(text, tmp_path, name="deck.nec"):
    path = tmp_path / name
    path.write_text(text, encoding="utf-8")
    cls = builder_from_file(str(path))
    return np.asarray(MomwireEngine(cls(), ground=cls.file_ground).impedance())


def test_cardioid_deck_imports_and_wire_tuples_succeeds():
    """The reporting deck opens. Its verticals STAND on the ground plane, so
    since AK#1598 each base is a ground-contact feed and the wire keeps its
    authored six segments uncut -- the feed and the load ride it as positioned
    ports instead of each needing a piece of their own."""
    deck = parse_nec(CARDIOID_NEC5, name="Cardioidmodnec5.nec", network=True)
    assert _named(deck) == [(6, "w1"), (6, "w2")]
    net = deck.network()
    # Feed at the centre of cell 1 (the cell the base stands in), load on its
    # own knot 2 -- both exact, neither snapped onto the other.
    assert net.ports["feed1"].at == pytest.approx(0.5 / 6)
    assert net.ports["load1"].at == pytest.approx(2 / 6)


def test_the_cardioid_deck_solves(tmp_path):
    """The gate AK#1594 could not carry: importing was never the point, and
    before AK#1598 this deck imported and then died in momwire on
    `node_gaps[0]: junction 0 has a single member`."""
    z = _solve(CARDIOID_NEC5, tmp_path, "cardioid.nec")
    assert z.shape == (2,)
    assert np.all(np.isfinite(z)) and np.all(z.real > 0)


def test_a_knot_0_source_at_a_JUNCTION_still_gets_its_own_piece():
    """AK#1594's cut, in the place it is still reached: knot 0 is a junction
    (wire 2 ends there), so the source is a series EMF and knot 0 collides
    with the knot-2 load on the first piece unless a cut at knot 1 separates
    them. Ten segments of room is not the question -- having any cut is."""
    deck = parse_nec(JUNCTION_KNOT0, name="j.nec", network=True)
    assert deck._ground_contact_knots == frozenset()  # elevated: no contact
    assert _named(deck)[:3] == [(1, "feed"), (1, "load1"), (4, None)]


def test_ld_moved_further_out_still_imports():
    """The issue's own table: the cut lands wherever the next claimed knot is
    -- here knot 4, not knot 2 -- so the load piece is three segments."""
    deck = parse_nec(
        JUNCTION_KNOT0.replace("LD 4,1,2,0,18.,0.", "LD 4,1,4,0,18.,0."),
        name="t.nec",
        network=True,
    )
    named = _named(deck)
    assert named[0] == (1, "feed")
    assert named[1] == (3, "load1")  # knot 1..4, the piece ending at knot 4


def test_one_wire_only_still_imports():
    """The issue's table: one vertical alone on the ground reproduces the
    original report, and since AK#1598 it needs no cut at all."""
    text = """CM ! Written by EZNEC/Pro+ v. 7.0 in NEC-5 format.
CE
GW 1,6,0.,0.,0.,0.,0.,.242,.000121
GE 1
LD 4,1,2,0,18.,0.
FR 0,1,0,0,299.7925
GN 1
EX 4,1,-1,0,1.414214,0.
EN
"""
    deck = parse_nec(text, name="t.nec", network=True)
    assert _named(deck) == [(6, "w1")]
    net = deck.network()
    assert net.ports["feed"].at == pytest.approx(0.5 / 6)
    assert net.ports["load1"].at == pytest.approx(2 / 6)


def test_knot_0_and_knot_1_collision_still_refuses():
    """The genuine no-room case (requirement 2), at a junction so it is still
    a series EMF: a source at knot 0 and a claim at knot 1 on a 2-segment wire
    leave no room to cut between them. A 1-segment piece has only one boundary
    on each side, so both claims land on the one piece and the refusal is
    correct, not a bug the fix should have removed."""
    text = """CM ! Written by EZNEC/Pro+ v. 7.0 in NEC-5 format.
CE
GW 1,2,0,0,1,0,0,2,.001
GW 2,2,0,0,1,.3,0,1,.001
GE 1
FR 0,1,0,0,10
GN 1
EX 4,1,-1,0,1,0.
LD 4,1,1,2,18.,0.
EN
"""
    deck = parse_nec(text, name="t.nec", network=True)
    assert deck._ground_contact_knots == frozenset()
    with pytest.raises(ValueError, match="piece between knots 0 and 1"):
        deck.wire_tuples(specs=True)
