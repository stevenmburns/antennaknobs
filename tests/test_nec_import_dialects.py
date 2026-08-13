"""Dialect tests for nec_import (#824): the NEC-5 edge-source EX form is
recognised precisely — never silently misread as an NEC-2 center-gap
feed — and, since PortAtVertex (#898), imported faithfully through the
network path as the series apex feed."""

from types import MappingProxyType

import pytest

from antennaknobs import AntennaBuilder
from antennaknobs.nec_import import parse_nec
from antennaknobs.network import PortAtVertex


# --------------------------------------------------------------------------
# NEC-5 edge-source EX form (#824)
# --------------------------------------------------------------------------

_EDGE_DECK = """CM nec5 edge source
CE
GW 1 20 0 0 -2.5 0 0 2.5 .001
GE 0
EX 0 1 {seg} {i4} 1 0
FR 0 1 0 0 28.5 0
EN
"""


def test_nec5_edge_source_needs_the_network_path():
    """NEC-5 puts sources at segment ENDS: I4=2 selects end 2 (and is not
    a legal NEC-2 print-flag value, so it is unambiguous). Without the
    network path there is nowhere to host a vertex port, so legacy-mode
    parses refuse with the dialect AND the remedy named — never silently
    shifting the feed half a segment to the NEC-2 center-gap reading."""
    with pytest.raises(ValueError, match="NEC-5 edge-source.*network=True"):
        parse_nec(_EDGE_DECK.format(seg=10, i4=2))
    with pytest.raises(ValueError, match="NEC-5 edge-source.*network=True"):
        parse_nec(_EDGE_DECK.format(seg=-10, i4=0))


def test_nec2_print_flag_i4_still_imports():
    """I4=1 is a legal NEC-2 print-control value (and only ambiguously the
    NEC-5 end-1 form) — it keeps its NEC-2 meaning: the feed imports as the
    ordinary center gap."""
    deck = parse_nec(_EDGE_DECK.format(seg=10, i4=1))
    assert len(deck.feeds) == 1
    assert deck.feeds[0].seg == 10
    assert deck.feeds[0].edge == 0


# --------------------------------------------------------------------------
# the faithful import: edge source → PortAtVertex (#824 closed by #898)
# --------------------------------------------------------------------------

_APEX_DECK = """CM apex vee, NEC-5 edge source
CE
GW 1 16 0. 0. -2.6 0. 0. 0. 0.001
GW 2 16 0. 0. 0. 0. 0. 2.6 0.001
GE 0
FR 0 1 0 0 27.0 0
EX 0 1 16 2 1.0 0.0
EN
"""


def _builder(deck):
    tups = deck.wire_tuples()
    net = deck.network()

    class B(AntennaBuilder):
        default_params = MappingProxyType({"design_freq": 27.0, "freq": 27.0})

        def build_wires(self):
            return tups

        def build_network(self):
            return net

    return B


def test_edge_source_at_a_shared_knot_becomes_a_vertex_port():
    deck = parse_nec(_APEX_DECK, name="apex.nec", network=True)
    net = deck.network()
    (pname, port), *rest = net.ports.items()
    assert not rest
    assert isinstance(port, PortAtVertex)
    assert port.end == "p1"
    assert net.sources[0].port == pname
    # no gap is cut: both arms keep their full segment counts
    assert [t[2] for t in deck.wire_tuples()] == [16, 16]


def test_interior_knot_splits_the_wire():
    """An edge source at an interior knot — e.g. NEC5Engine's own center
    feed spelling, EX at end 2 of the middle segment — splits the wire at
    that knot and apex-feeds the junction: the colinear-identity spelling
    (momwire#300/#305)."""
    deck = parse_nec(
        _APEX_DECK.replace(
            "GW 1 16 0. 0. -2.6 0. 0. 0. 0.001\nGW 2 16 0. 0. 0. 0. 0. 2.6 0.001",
            "GW 1 32 0. 0. -2.6 0. 0. 2.6 0.001",
        ),
        name="c.nec",
        network=True,
    )
    tups = deck.wire_tuples()
    assert [t[2] for t in tups] == [16, 16]
    named = [t[4] for t in tups if len(t) > 4 and t[4]]
    assert named == ["feed"]


@pytest.mark.antenna_computation_check
def test_edge_source_round_trip_matches_the_direct_apex_design():
    """The full circle: a deck authored the NEC-5 way (EX at the shared
    knot) imports and solves on momwire to the SAME impedance as the
    directly-authored PortAtVertex design — and the negative-I3 end-1
    spelling of the same knot agrees exactly."""
    from antennaknobs.engines.momwire import MomwireEngine

    def z(deck_text, name):
        deck = parse_nec(deck_text, name=name, network=True)
        eng = MomwireEngine(_builder(deck)(), ground=None)
        return complex(eng.impedance()[0])

    z_a = z(_APEX_DECK, "a.nec")
    # same knot spelled as end 1 of wire 2's first segment
    z_b = z(_APEX_DECK.replace("EX 0 1 16 2", "EX 0 2 -1 0"), "b.nec")
    assert abs(z_a - z_b) < 1e-9

    import sys

    sys.path.insert(0, "tests")
    from test_port_at_vertex import _ApexDipole

    z_direct = complex(MomwireEngine(_ApexDipole(), ground=None).impedance()[0])
    assert abs(z_a - z_direct) < 1e-6, f"imported {z_a:.4f} vs {z_direct:.4f}"
