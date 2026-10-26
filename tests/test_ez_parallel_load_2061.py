"""A parallel-connected load at a source on a virtual segment (AK#2061).

Mike WA7ARK's EFHW model, converted by Dan AC6LA with EZNEC/Pro+ 7.0 to both
``.ez`` and ``.nec`` (private; not in the repo), carries one ``P`` load. Its
source sits on a virtual segment behind a transformer, and EZNEC's NEC-5
export writes the P load as an ``NT`` from that segment to a second virtual
wire: Y11 = 1/Z, Y12 = Y22 = 0, a shunt across the source's node. That is the
reading `ez_import` already takes for any load on a virtual segment, so a P
load there is served; a P load on a real wire stays refused by name.

The same model's ``.nec`` exposed two gaps on the deck route, both fixed here:

- EZNEC's NEC-5 export words its second circuit wire's legend ``Wire #6 for
  shorted/open trans. lines and/or parallel loads.``, where its NEC-2 export
  says ``for I srcs, shorted/open TL, and/or parallel loads``. Unrecognized,
  the two virtual wires (about 1 lambda apart) failed each other's clearance
  test and were meshed as real wires 100 lambda out.
- With them read as nodes, the one-port NT on the virtual source node was
  emitted as a TWO-port admittance, which held its dead second node and made
  the network singular. A one-port NT is now a one-port admittance.

On Mike's model the two files then agree to 3e-4 ohm once both use one speed
of light (the ``.ez`` route uses 299.792458, the NEC-5 deck route 299.8: a
separate, deliberate choice, AK#1958).
"""

from __future__ import annotations

import pytest

from antennaknobs import network
from antennaknobs.engines import MomwireEngine
from antennaknobs.ez_import import EzUndefined, read_ez
from antennaknobs.file_designs import builder_from_text
from antennaknobs.nec_import import parse_nec
from tests.test_ez_import_1958 import (
    DIPOLE,
    _open,
    _z,
    ez_file,
    transformer_block,
    virtual_block,
)

# The P load: a capacitive -j60 ohm, about Mike's -j60.05.
ZP = -60j


def _virtual_fed(loads=()):
    """The 1958 suite's dipole fed by a current source on virtual segment 7
    through a 1:1 transformer (0.1 ohm series), plus ``loads``."""
    vwire = (100.0, 100.0, 100.0, 100.0, 100.0, 101.0, 0.001, 2)
    return ez_file(
        [*DIPOLE, vwire],
        sources=((2, 25.0, 1.0, 0.0, "I"),),
        loads=loads,
        blocks=[
            transformer_block([((2, 25.0), (1, 50.0), 50.0, 50.0)]),
            virtual_block([7, 3], 2),
        ],
        counts=(1, 0, 0, 2),
    )


def test_a_p_load_at_a_source_on_a_virtual_segment_shunts_the_source():
    p_load = {"wire": 2, "pct": 25.0, "z": (ZP.real, ZP.imag), "conn": "P"}
    raw = _virtual_fed(loads=(p_load,))
    imp = read_ez(raw)
    # EZNEC's own construction, so a fact and not a guess.
    assert not any("virtual segment" in g for g in getattr(imp, "guesses", ()))
    z = _z(_open(raw))
    z_line = _z(_open(_virtual_fed()))  # the dipole + 0.1 ohm, no P load
    assert z == pytest.approx(1 / (1 / z_line + 1 / ZP), rel=1e-9)


def test_a_p_load_on_a_real_wire_is_still_refused_by_name():
    raw = ez_file(
        DIPOLE, loads=({"wire": 1, "pct": 75.0, "z": (5.0, 0.0), "conn": "P"},)
    )
    with pytest.raises(EzUndefined, match="'P' on a real wire's segment"):
        read_ez(raw)


# The deck route: EZNEC's NEC-5 export of the same shape, on a 20-segment
# dipole fed at its centre knot (1,10). Wire 2 is the virtual source wire,
# wire 3 the spare one 21 m below it (about 1 lambda, as EZNEC places them)
# that the one-port NT's dead half lands on. The plain deck carries the same
# stamp, so its ``EX 0,1,10`` is the same centre knot.
_DECK = """CM test
CM ! Written by EZNEC/Pro+ v. 7.0 in NEC-5 format.
CM ! *Wire #2 for virtual segments.
CM ! Wire #3 for shorted/open trans. lines and/or parallel loads.
CE
GW 1,20,0.,-5.15,10.,0.,5.15,10.,.001
GW 2,2,2111.,2111.,2132.,2111.02,2111.02,2132.02,.001
GW 3,2,2111.,2111.,2111.,2111.02,2111.02,2111.02,.001
GE 0
FR 0,1,0,0,14.2
EX 4,2,1,0,1.414214,0.
NT 2,1,3,1,0.,{yp},0.,0.,0.,0.
NT 2,1,1,10,10.,0.,-10.,0.,10.,0.
EN
"""

_PLAIN = """CM test
CM ! Written by EZNEC/Pro+ v. 7.0 in NEC-5 format.
CE
GW 1,20,0.,-5.15,10.,0.,5.15,10.,.001
GE 0
FR 0,1,0,0,14.2
EX 0,1,10,0,1.,0.
EN
"""


def _deck_z(text: str) -> complex:
    cls = builder_from_text("t.nec", text)
    return complex(MomwireEngine(cls(), ground=cls.file_ground).impedance()[0])


def test_eznecs_nec5_legend_names_the_second_circuit_wire():
    deck = parse_nec(_DECK.format(yp=repr((1 / ZP).imag)), name="t.nec", network=True)
    assert deck.virtual_segment_wires == frozenset({1, 2})
    assert len(deck.wire_tuples(specs=True)) == 1


def test_a_one_port_nt_on_a_virtual_node_is_a_one_port_and_solves():
    text = _DECK.format(yp=repr((1 / ZP).imag))
    net = parse_nec(text, name="t.nec", network=True).network()
    ys = [b for b in net.branches if isinstance(b, network.Admittance)]
    assert [len(b.ports) for b in ys] == [1]
    assert isinstance(net.ports[ys[0].ports[0]], network.PortVirtual)
    z_line = _deck_z(_PLAIN) + 0.1  # the 1:1 transformer's series 0.1 ohm
    assert _deck_z(text) == pytest.approx(1 / (1 / z_line + 1 / ZP), rel=1e-9)
