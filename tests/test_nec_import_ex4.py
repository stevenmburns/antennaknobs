"""EX 4 — NEC-5's current source (issue #1243).

NEC-5 reuses NEC-2's type number 4 for a segment current source in amps
(F1/F2), placed at a segment END like every NEC-5 source; NEC-2's type 4
is an elementary current source at a point in space with no segment
addressed. EZNEC's NEC-5 export writes ``EX 4`` routinely (√2 A = 1 W
into 1 Ω), which is how the form arrived: AC6LA's deck from the QRZ
slope thread, imported here as the fixture.

Deck-level contract: ``EX 4`` parses in network mode into a ``NecFeed``
with ``current=True`` at the decoded END (a ``PortAtVertex`` source),
using NEC-5's full end rule since type 4 pins the dialect. Without the
network path it refuses with the same sentence shape type 6 uses. NEC-2's
blank-segment type 4 refuses by name. Physics oracle: a one-port's Z is
independent of the ideal-source kind, so the deck with ``EX 4`` and the
same deck with ``EX 0`` at the same end must report identical Z.
"""

import pytest

from antennaknobs import AntennaBuilder, WireSpec
from antennaknobs.engines import MomwireEngine
from antennaknobs.nec_import import parse_nec
from antennaknobs.network import Driven, DrivenCurrent, PortAtVertex

# AC6LA's "Vertical on 45 deg slope" (EZNEC Pro+ 7.0, NEC-5 format), as
# posted: a 45° sloping wire on a plumb hub with four radials 1 in above
# the soil, fed at end 1 of segment 1 with √2 A.
AC6LA_DECK = """CM Vertical on 45 deg slope
CM
CM ! Written by EZNEC Pro+ v. 7.0 in NEC-5 format.
CE
GW 1,11,0.,0.,.0254,-7.134,0.,7.1594,.001
GW 2,5,0.,0.,.0254,10.55607,0.,.0254,.001
GW 3,5,0.,0.,.0254,0.,10.55607,.0254,.001
GW 4,5,0.,0.,.0254,-10.55607,0.,.0254,.001
GW 5,5,0.,0.,.0254,0.,-10.55607,.0254,.001
GE 1
LD 5,0,1,31,5.7471E+7,1.
FR 0,1,0,0,7.1
GN 0,0,0,0,13.,.005,1.,0.
EX {ex}
RP 0,181,1,1000,90.,0.,-1.,0.,0.
EN
"""

EX4_AS_POSTED = "4,1,-1,0,1.414214,0."
EX0_SAME_END = "0,1,-1,0,1.,0."

DIPOLE = "GW 1 11 0 -5 10 0 5 10 0.001\nGE\nEX {ex}\nEN\n"


def _deck_builder(deck, freq=7.1):
    class B(AntennaBuilder):
        default_params = {"freq": freq}

        def build_wires(self):
            return deck.wire_tuples()

        def build_network(self):
            return deck.network()

        def build_wire_material(self):
            return WireSpec(radius=deck.dominant_radius())

    return B()


def test_ex4_parses_to_a_current_source_at_the_end():
    deck = parse_nec(AC6LA_DECK.format(ex=EX4_AS_POSTED), name="dan", network=True)
    (feed,) = deck.feeds
    assert feed.current is True
    assert feed.voltage == pytest.approx(1.414214 + 0j)  # amps for EX 4
    assert (feed.wire, feed.seg, feed.edge) == (0, 1, 1)  # -1 → end 1
    net = deck.network()
    (src,) = net.sources
    assert isinstance(src, DrivenCurrent)
    assert src.current == pytest.approx(1.414214 + 0j)
    assert isinstance(net.ports[src.port], PortAtVertex)


def test_ex4_needs_the_network_path():
    with pytest.raises(ValueError, match="NEC-5's current-source.*network=True"):
        parse_nec(AC6LA_DECK.format(ex=EX4_AS_POSTED), name="dan")


@pytest.mark.parametrize(
    ("ex", "edge"),
    [
        ("4 1 6 1 1 0", 1),  # I4 names end 1
        ("4 1 6 2 1 0", 2),  # I4 names end 2
        ("4 1 6 0 1 0", 2),  # I4 = 0, positive I3 → end 2 (NEC-5's rule)
        ("4 1 -6 0 1 0", 1),  # I4 = 0, negative I3 → end 1
    ],
)
def test_ex4_takes_nec5_full_end_rule(ex, edge):
    """Type 4 pins the dialect, so the one spelling the voltage form has to
    keep as an ambiguous NEC-2 center gap (I4 = 0, positive segment) reads
    as NEC-5 means it: end 2. There is no center source in NEC-5."""
    deck = parse_nec(DIPOLE.format(ex=ex), name="t", network=True)
    (feed,) = deck.feeds
    assert feed.current is True
    assert (feed.seg, feed.edge) == (6, edge)


def test_nec2_elementary_current_source_is_refused_by_name():
    """NEC-2's EX 4: I2/I3 blank, a point source in space. Not a feed."""
    with pytest.raises(ValueError, match="elementary current source"):
        parse_nec(DIPOLE.format(ex="4 0 0 0 0 0 5 90 0 1"), name="t", network=True)


def test_ex6_at_a_segment_end_imports_too():
    """The current-source-at-an-end refusal (#824) predates the vertex
    port; a 4nec2 EX 6 at an end now takes the same route as EX 4."""
    deck = parse_nec(DIPOLE.format(ex="6 1 -6 0 1 0"), name="t", network=True)
    (feed,) = deck.feeds
    assert (feed.current, feed.seg, feed.edge) == (True, 6, 1)
    (src,) = deck.network().sources
    assert isinstance(src, DrivenCurrent)


def test_ex4_impedance_matches_the_voltage_edge_import():
    """The gate from #1243: AC6LA's deck as posted (EX 4) and the same deck
    with a voltage source at the same end (EX 0,1,-1) solve to the same Z
    on momwire over the deck's soil — the source type does not move Z."""
    deck_i = parse_nec(AC6LA_DECK.format(ex=EX4_AS_POSTED), name="i", network=True)
    deck_v = parse_nec(AC6LA_DECK.format(ex=EX0_SAME_END), name="v", network=True)
    assert isinstance(deck_v.network().sources[0], Driven)
    ground = ("finite", 13.0, 0.005)
    z_i = MomwireEngine(_deck_builder(deck_i), ground=ground).impedance()[0]
    z_v = MomwireEngine(_deck_builder(deck_v), ground=ground).impedance()[0]
    assert z_i == pytest.approx(z_v, rel=1e-9)
    assert z_i.real > 10  # solved something real, not a degenerate port
