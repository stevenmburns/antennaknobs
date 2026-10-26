"""The feed marker of a deck driven from a virtual port (EZNEC's and
SimNEC's virtual-segment exports): the source sits on a wire far from the
antenna, read as circuit nodes, and reaches the antenna through a
transformer at a wire END. The marker belongs where that transformer meets
the wire. It used to fall to the first wire's first knot, which on an
end-fed is the far end of the radiator.
"""

import pytest

import antennaknobs.web.server  # noqa: F401 -- resolves the adapter import cycle
from antennaknobs.engines import MomwireEngine
from antennaknobs.file_designs import builder_from_text
from antennaknobs.network import PortVirtual
from antennaknobs.web import adapter

# An end-fed half wave on 20 m: the radiator runs in from x = 10 to the feed
# at the origin, 8 m up, with a short counterpoise sloping down from it. The
# virtual wire 3 is the rig node, and a 1:7 transformer (EZNEC's NT spelling)
# joins it to the radiator's last segment, at the feed corner.
DECK = """CM end-fed through a transformer from a virtual source
CE
GW 1 41 10. 0. 8. 0. 0. 8. .001
GW 2 9 0. 0. 8. -1.5 0. 7. .001
GW 3 2 1000. 1000. 1000. 1000.02 1000.02 1000.02 .001
GE 0
FR 0 1 0 0 14.1 0
EX 4 3 1 0 1. 0.
NT 3 1 1 41 10. 0. -1.428571 0. .2040816 0.
EN
"""


@pytest.fixture(scope="module")
def solved():
    eng = MomwireEngine(builder_from_text("efhw.nec", DECK)())
    return eng, eng.current_distribution()


def test_the_source_is_virtual_and_the_walk_reaches_the_wire(solved):
    eng, _ = solved
    net = eng._network
    assert isinstance(net.ports[net.sources[0].port], PortVirtual)
    assert not isinstance(net.ports[adapter._driven_port_name(net)], PortVirtual)


def test_the_marker_sits_at_the_feed_corner(solved):
    eng, cur = solved
    (marker,) = adapter._feed_positions(eng, cur)
    assert marker["position"] == pytest.approx([0.0, 0.0, 8.0], abs=1e-9)
    wire, knot = adapter._feed_indices(eng, cur)
    assert cur[wire].knot_positions[knot].tolist() == pytest.approx(
        [0.0, 0.0, 8.0], abs=1e-9
    )
