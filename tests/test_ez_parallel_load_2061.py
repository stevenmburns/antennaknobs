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

import math
import struct

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
    engine_block,
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


# --------------------------------------------------------------------------
# A P load on a real wire (the AK#2061 sitting, 2026-10-26: EZNEC 7.0.4's
# NEC-2, NEC-4.2 and NEC-5 exports of its own dipole example, 21 segments,
# fed at 50 %, with 50+j100 ohm loads). EZNEC writes one as a one-port NT from
# its segment to a spare circuit wire, Y11 = 1/Z: across the segment's gap.
# --------------------------------------------------------------------------

NEC5_ENGINE = engine_block(8, "Ext NEC-5")
ZL = 50 + 100j


def _p(pct, z=ZL, wire=1, **kw):
    return {"wire": wire, "pct": pct, "z": (z.real, z.imag), "conn": "P", **kw}


def _nt(imp):
    return [ln.split() for ln in imp.nec_text.splitlines() if ln.startswith("NT ")]


@pytest.mark.parametrize(("blocks", "seg"), [((), "6"), ((NEC5_ENGINE,), "5")])
def test_a_p_load_on_a_real_wire_is_a_one_port_nt_where_eznec_puts_it(blocks, seg):
    """25 % of 21 segments: segment 6's centre under NEC-2, knot 5 (the
    nearest, 23.81 %) under NEC-5, both as EZNEC's exports write it."""
    imp = read_ez(ez_file(DIPOLE, loads=(_p(25.0),), blocks=list(blocks)))
    ((_, wire, s, spare, _, *y),) = _nt(imp)
    assert (wire, s) == ("1", seg)
    assert spare == "2"  # the spare circuit wire after the dipole
    assert complex(float(y[0]), float(y[1])) == pytest.approx(1 / ZL)
    assert not any(ln.startswith("LD 4") for ln in imp.nec_text.splitlines())


@pytest.mark.parametrize("blocks", [(), (NEC5_ENGINE,)])
def test_a_p_load_at_the_feed_shunts_the_source(blocks):
    z0 = _z(_open(ez_file(DIPOLE, blocks=list(blocks))))
    z = _z(_open(ez_file(DIPOLE, loads=(_p(50.0),), blocks=list(blocks))))
    assert z == pytest.approx(1 / (1 / z0 + 1 / ZL), rel=1e-9)


@pytest.mark.parametrize("blocks", [(), (NEC5_ENGINE,)])
def test_off_the_feed_a_p_load_carries_the_wire_current_as_a_series_load_does(blocks):
    """Across a segment's gap with nothing else there, the gap's current is
    the wire's, so 1/Z across it is Z in series; and a series load on the
    same segment adds (the sitting's p6: 20 ohm series beside the P load)."""
    s_load = {"wire": 1, "pct": 25.0, "z": (70.0, 100.0)}
    z_s = _z(_open(ez_file(DIPOLE, loads=(s_load,), blocks=list(blocks))))
    both = (_p(25.0), {"wire": 1, "pct": 25.0, "z": (20.0, 0.0)})
    z_p = _z(_open(ez_file(DIPOLE, loads=both, blocks=list(blocks))))
    assert z_p == pytest.approx(z_s, rel=1e-6)


def test_a_p_load_on_a_free_end_is_refused_under_nec5_and_moved_under_nec2():
    """EZNEC's NEC-5 export refuses the model; its NEC-2 and NEC-4.2 exports
    move the load to the end segment's centre (p3)."""
    raw5 = ez_file(DIPOLE, loads=(_p(0.0),), blocks=[NEC5_ENGINE])
    with pytest.raises(EzUndefined, match="free wire end"):
        read_ez(raw5)
    ((_, wire, s, *_rest),) = _nt(read_ez(ez_file(DIPOLE, loads=(_p(0.0),))))
    assert (wire, s) == ("1", "1")


def test_an_rlc_p_load_follows_frequency_from_its_parts():
    """R 50 ohm in parallel with L 1.137 uH (the sitting's p8b): the NT holds
    1/Z at the model frequency, and the solve takes Z at each frequency."""
    rlc = {"wire": 1, "pct": 50.0, "rlc": ("P", 50.0, 1.137e-6, 0.0, 0.0), "conn": "P"}
    raw = ez_file(DIPOLE, loads=(rlc,), load_type="R")
    z0 = _z(_open(ez_file(DIPOLE)), freq=21.0)
    z = _z(_open(raw), freq=21.0)
    w = 2 * math.pi * 21e6
    l32 = struct.unpack("<f", struct.pack("<f", 1.137e-6))[0]  # .ez stores float32
    zp = 1 / (1 / 50.0 + 1 / (1j * w * l32))
    assert z == pytest.approx(1 / (1 / z0 + 1 / zp), rel=1e-9)


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
