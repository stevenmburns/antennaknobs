"""EZNEC's virtual wire imports as virtual circuit nodes (AK#1577).

EZNEC spells a source behind a transformer or a transmission line by parking
one wire ~100 λ away and using its SEGMENTS as circuit nodes: the `NT`/`TL`
cards and the `EX` address those segments, each used segment is pinned open
with `LD 4 … 1.E+10`, and the deck says so (`! *Wire #3 for virtual
segments.`). Modeled as real geometry that wire collides with the network
ports — the source claims a knot and the NT claims the same one-segment piece,
which is the #824 refusal — so the importer recognises the idiom and gives
each referenced segment a `PortVirtual` instead.

The fixtures, their provenance and their NEC-5 numbers are in
`tests/fixtures/eznec_virtual_wire_1577/README.md`. Two of the gates here are
worth naming:

- the CIRCUIT gate (`test_translated_network_reproduces_nec5_at_the_source`)
  drives the imported network with NEC-5's OWN control-deck impedance and
  lands on NEC-5's printed source impedance to 1.8e-05 — no solver involved,
  so it pins the translation itself: ports, pi decomposition, complex-Y line,
  pin admittances and where the drive sits;
- the END-TO-END gate is looser (4.1 % of R) and the residual is NOT this
  translation. AK reads an `NT`/`EX` segment field as a segment and puts the
  port at its CENTRE where NEC-5 addresses a knot; on this 378-segment wire
  that one knot is worth 2.15 % of X, which the transformer and lossy line
  amplify. `test_the_end_to_end_residual_is_the_attachment_knot` measures
  that on the control deck, where no virtual wire is involved at all.
"""

from pathlib import Path

import numpy as np
import pytest

from antennaknobs import AntennaBuilder
from antennaknobs.engines import MomwireEngine, NEC5Engine
from antennaknobs.file_designs import builder_from_file
from antennaknobs.nec_import import parse_nec
from antennaknobs.network import (
    Admittance,
    Driven,
    DrivenCurrent,
    Network,
    PortOnWire,
    PortVirtual,
)
from momwire import BSplineSolver
from momwire.networks import NetworkReducer

from conftest import needs_nec5

FIXTURES = Path(__file__).parent / "fixtures" / "eznec_virtual_wire_1577"

# NEC5CL's own printouts for the three fixture decks (README.md quotes the
# rows). The control is the same antenna and the same LD 0 capacitor with no
# virtual wire and no network, driven straight at the OCF point.
NEC5_SOURCE_Z = complex(48.919, 103.89)  # failEZN5, at the virtual-node source
NEC5_PROBE_I = complex(0.52288, -0.39562)  # failEZN5, the 1e-10 V probe
NEC5_VOLTAGE_SOURCE_Z = complex(49.307, 104.23)  # WA7ARK-OCF-Load-Xfmr-TL
NEC5_CONTROL_Z = complex(275.53, -1441.0)  # WA7ARK-OCF-LoadOnly
FREQ = 1.8
LAMBDA = 299792458.0 / (FREQ * 1e6)


def _deck(name):
    return parse_nec(
        (FIXTURES / name).read_text(encoding="utf-8", errors="replace"),
        name=name,
        network=True,
    )


def _solve(name, engine=MomwireEngine, **kwargs):
    """The deck through the `@file` route the workbench and CLI use — per-wire
    specs, the deck's own segment counts, the deck's ground."""
    cls = builder_from_file(str(FIXTURES / name))
    return engine(cls(), ground=cls.file_ground, **kwargs).impedance()


def _builder(deck, freq):
    """A deck-backed builder, the shape `file_designs` synthesizes: the deck's
    own segment counts and one WireSpec per wire (radius + conductivity)."""

    class B(AntennaBuilder):
        default_params = {"freq": freq}

        def build_wires(self):
            return deck.wire_tuples(specs=True)

        def build_network(self):
            return deck.network()

    return B()


def _one_port(net, drop):
    """`net` with `drop`'s ports, branches and sources removed — used to hand
    the reducer a network whose only REAL port is the antenna attachment, so
    NEC-5's one-port control impedance can stand in for the MoM."""
    return Network(
        ports={k: v for k, v in net.ports.items() if k not in drop},
        branches=[b for b in net.branches if getattr(b, "port", None) not in drop],
        sources=[s for s in net.sources if s.port not in drop],
    )


def _driven_z(net, z_antenna):
    """The driven-port impedance of `net` with a single real port carrying
    `z_antenna` — the antenna replaced by a measured one-port."""
    real = [n for n, p in net.ports.items() if not isinstance(p, PortVirtual)]
    assert len(real) == 1, real
    idx = {n: i for i, n in enumerate(real)}
    for n in net.ports:
        idx.setdefault(n, len(idx))
    z = NetworkReducer(net, idx, len(idx)).driven_impedance(
        np.array([[1.0 / z_antenna]], dtype=complex), LAMBDA
    )
    return complex(np.atleast_1d(z)[0])


# --------------------------------------------------------------------------
# the idiom, translated
# --------------------------------------------------------------------------
def test_dans_deck_imports_the_virtual_wire_as_nodes():
    deck = _deck("failEZN5.nec")
    # Wire index 2 (tag 3) is EZNEC's virtual wire; it is virtualized under
    # the AK#1577 idiom, not #427's remote TL anchor.
    assert deck.virtual_segment_wires == frozenset({2})
    assert deck.virtual_anchors == frozenset({2})
    # Its geometry is gone: only the two antenna wires are emitted.
    assert len(deck.wire_tuples()) == 2
    net = deck.network()
    # Segment 1 is the transformer's secondary and one end of the line;
    # segment 2 is the line's other end and the source. Two nodes, both
    # virtual; the transformer's antenna end stays a port on a real wire.
    assert isinstance(net.ports["nt1a"], PortVirtual)
    assert isinstance(net.ports["feed1"], PortVirtual)
    assert isinstance(net.ports["nt2a"], PortOnWire)
    # The EX 4 becomes a forced current on the virtual node — which is what
    # momwire's PortVirtual is documented for ("driver feeds that branch out
    # via TLs to real ports").
    (src,) = [s for s in net.sources if isinstance(s, DrivenCurrent)]
    assert (src.port, src.current) == ("feed1", 1.414214 + 0j)
    # The lossy line is the reactive NT's full 2x2 (issue #416) between the
    # two virtual nodes; the transformer is the real-Y pi to the antenna.
    (line,) = [
        b for b in net.branches if isinstance(b, Admittance) and len(b.ports) == 2
    ]
    assert set(line.ports) == {"nt1a", "feed1"}


def test_the_pins_become_ideal_opens_on_their_nodes():
    deck = _deck("failEZN5.nec")
    # One LD 4 1e10 pin per used virtual segment, kept as what it leaves
    # behind once the segment is a node: a 1-port admittance of 1/Z.
    assert [(w, s, z) for w, s, z in deck.virtual_pins] == [
        (2, 1, complex(1e10, 0)),
        (2, 2, complex(1e10, 0)),
    ]
    net = deck.network()
    pins = [b for b in net.branches if isinstance(b, Admittance) and len(b.ports) == 1]
    assert sorted(p.ports[0] for p in pins) == ["feed1", "nt1a"]
    assert all(p.y == ((complex(1e-10, 0),),) for p in pins)
    # They are NOT reported as loads the importer could not express: the deck
    # carries no unexpressed LD at all.
    assert not [m for m, _ in deck.ignored_detail if m == "LD"]


def test_skipped_note_names_the_idiom_and_the_pins():
    note = _deck("failEZN5.nec").skipped_note()
    assert "1 EZNEC virtual wire (tag 3)" in note
    assert "2 virtual circuit nodes" in note
    assert "2 LD 4 open-circuit pins" in note
    # #427's sentence is about a different idiom and must not appear.
    assert "TL-anchor" not in note


# --------------------------------------------------------------------------
# gate 1 — the deck opens, and the circuit it opens as is NEC-5's
# --------------------------------------------------------------------------
def test_translated_network_reproduces_nec5_at_the_source():
    """The circuit gate: replace the antenna with the one-port NEC-5 itself
    measured (the control deck, same antenna, same capacitor, no virtual
    wire) and the imported network must land on NEC-5's printed source
    impedance. Everything but the MoM is under test — and it agrees to 1.8e-05,
    which is the printout's own precision."""
    net = _one_port(_deck("failEZN5.nec").network(), {"feed2", "load1"})
    z = _driven_z(net, NEC5_CONTROL_Z)
    assert abs(z - NEC5_SOURCE_Z) / abs(NEC5_SOURCE_Z) < 1e-4
    assert z == pytest.approx(complex(48.9173, 103.889), rel=1e-5)


def test_momwire_bspline_solves_dans_deck():
    """End to end on the deck as posted. The tolerance is 5 %, not the 2 %
    AK#1577 asked for, and the gap is measured in
    `test_the_end_to_end_residual_is_the_attachment_knot`: it is the
    segment-centre vs knot attachment, amplified by the transformer and the
    line, not the virtual-wire translation."""
    z_source, z_probe = (
        complex(x) for x in _solve("failEZN5.nec", solver=BSplineSolver)
    )
    assert z_source == pytest.approx(complex(50.928, 105.839), rel=1e-4)
    assert abs(z_source - NEC5_SOURCE_Z) / abs(NEC5_SOURCE_Z) < 0.05
    # The probe: 1e-10 V across the port, so its current is V/Z (NEC-5 prints
    # the current directly).
    i_probe = 1e-10 / z_probe
    assert abs(i_probe - NEC5_PROBE_I) / abs(NEC5_PROBE_I) < 0.05


def test_the_end_to_end_residual_is_the_attachment_knot():
    """Attribution, on the CONTROL deck — no virtual wire, no network, one
    source. AK puts the port at the centre of the deck's segment 378; NEC-5
    addresses the knot at its end. That one knot out of 378 is the whole
    residual: 2.15 % of X here, which the transformer and lossy line turn
    into ~4 % of R at the source."""
    (z,) = (complex(x) for x in _solve("WA7ARK-OCF-LoadOnly.nec", solver=BSplineSolver))
    assert z == pytest.approx(complex(275.111, -1409.989), rel=1e-4)
    assert abs(z.real - NEC5_CONTROL_Z.real) / abs(NEC5_CONTROL_Z.real) < 0.003
    assert 0.02 < abs(z.imag - NEC5_CONTROL_Z.imag) / abs(NEC5_CONTROL_Z.imag) < 0.025
    # And it composes. Push AK's OWN control value through the imported
    # network and it lands on AK's own end-to-end answer for the same model
    # with the virtual wire: the antenna one-port is the only input the
    # translation has, so the residual travels with it and nothing else does.
    net = _one_port(_deck("WA7ARK-OCF-Load-Xfmr-TL.nec").network(), {"load1"})
    (end_to_end,) = (
        complex(x) for x in _solve("WA7ARK-OCF-Load-Xfmr-TL.nec", solver=BSplineSolver)
    )
    assert _driven_z(net, z) == pytest.approx(end_to_end, rel=1e-5)


# --------------------------------------------------------------------------
# gate 2 — the app's NEC-5 engine solves it through the multiport-Y reducer
# --------------------------------------------------------------------------
@needs_nec5
def test_nec5_engine_solves_it_through_the_reducer():
    """A PortVirtual sends the design down `_network_needs_reducer`'s route:
    one deck per driven real port, the circuit reduced onto them. The virtual
    nodes never reach a card, and the 1e-10 V probe is the real port that
    keeps the route legal."""
    z_source, _z_probe = (complex(x) for x in _solve("failEZN5.nec", engine=NEC5Engine))
    assert z_source == pytest.approx(complex(50.680, 105.862), rel=1e-3)
    assert abs(z_source - NEC5_SOURCE_Z) / abs(NEC5_SOURCE_Z) < 0.05


@needs_nec5
def test_nec5_engine_reproduces_the_printout_when_the_port_is_a_knot():
    """The other half of the attribution, on the licensed binary itself: spell
    the control deck's source as a knot (`EX 0,1,378,2`) and AK's NEC-5 engine
    returns the printout's 275.53 - 1441.0j to every printed digit. Same
    binary, same mesh, same import — only where the port sits changes."""
    text = (FIXTURES / "WA7ARK-OCF-LoadOnly.nec").read_text(errors="replace")
    knot = text.replace("EX 0,1,378,0,", "EX 0,1,378,2,")
    assert knot != text
    deck = parse_nec(knot, name="knot", network=True)
    (z,) = (
        complex(x) for x in NEC5Engine(_builder(deck, FREQ), ground=None).impedance()
    )
    assert z == pytest.approx(NEC5_CONTROL_Z, rel=1e-6)


# --------------------------------------------------------------------------
# gate 4 — the voltage-source spelling of the same idiom
# --------------------------------------------------------------------------
def test_voltage_source_on_the_virtual_wire_imports_too():
    """Mike's earlier deck: the same model with `EX 0` on the virtual wire and
    no pins. Same idiom, `Driven` instead of `DrivenCurrent`."""
    deck = _deck("WA7ARK-OCF-Load-Xfmr-TL.nec")
    assert deck.virtual_segment_wires == frozenset({2})
    assert deck.virtual_pins == ()  # this vintage writes none
    net = deck.network()
    (src,) = net.sources
    assert isinstance(src, Driven)
    assert (src.port, src.voltage) == ("feed", 1.414214 + 0j)
    assert isinstance(net.ports["feed"], PortVirtual)
    (z,) = (
        complex(x) for x in _solve("WA7ARK-OCF-Load-Xfmr-TL.nec", solver=BSplineSolver)
    )
    assert z == pytest.approx(complex(51.030, 105.903), rel=1e-4)


def test_unpinned_virtual_segments_cost_half_a_percent():
    """Why the pins matter, measured. The same circuit gate as the pinned
    deck's, against ITS printout: without the `LD 4 1.E+10` cards those
    segments still carry their own small admittance in NEC, and the import
    models them as ideal opens. 4.5e-03 — versus 1.8e-05 pinned."""
    net = _one_port(_deck("WA7ARK-OCF-Load-Xfmr-TL.nec").network(), {"load1"})
    z = _driven_z(net, NEC5_CONTROL_Z)
    err = abs(z - NEC5_VOLTAGE_SOURCE_Z) / abs(NEC5_VOLTAGE_SOURCE_Z)
    assert 1e-3 < err < 1e-2


# --------------------------------------------------------------------------
# gate 3 — nothing that imports today changes
# --------------------------------------------------------------------------
_CARD_HEAD = (
    "CM CardTL.ez class: a network to a virtual segment\n"
    "CM ! *Wire #2 for virtual segments.\n"
    "CE\n"
    "GW 1,21,-4.87,0.,21.45,4.87,0.,21.45,.0254\n"
    "GW 2,3,2114.9,2114.9,2114.9,2114.93,2114.93,2114.93,.0021\n"
    "GE 0\nFR 0,1,0,0,14.175\nEX 0,1,11,0,1.,0.\n"
    "LD 4,2,1,0,1.E+10,0.\n"
)
# EZNEC Pro/2+ spells a parallel load as an NT to a virtual segment (its own
# comment: "Wire #N for shorted/open trans. lines and/or parallel loads").
PARALLEL_LOAD = (
    _CARD_HEAD
    + "LD 4,2,2,0,1.E+10,0.\n"
    + "NT 1,11,2,1,.01,0.,0.,0.,0.,0.\n"
    + "NT 1,11,2,2,.005,0.,0.,0.,0.,0.\nEN\n"
)
# An open stub: a TL to the virtual segment and nothing else on that wire.
OPEN_STUB = _CARD_HEAD + "TL 1,11,2,1,71.,4.294351,0.,0.,0.,0.\nEN\n"


def _z_both_ways(text):
    """`[(Z, deck)]` for the deck read with the idiom and without it — the
    after and the before of AK#1577 on one text."""
    out = []
    for virtualize in (True, False):
        deck = parse_nec(text, network=True, virtualize_anchors=virtualize)
        eng = MomwireEngine(_builder(deck, 14.175), solver=BSplineSolver, ground=None)
        out.append((complex(eng.impedance()[0]), deck))
    return out


def test_parallel_load_deck_solves_to_the_same_answer_virtualized():
    """The shape that appears in the wild: the far wire stops being geometry
    and the answer does not move at all (the NT's far half is all zeros, so
    the node was never carrying anything)."""
    (z_new, deck_new), (z_old, deck_old) = _z_both_ways(PARALLEL_LOAD)
    assert deck_new.virtual_segment_wires == frozenset({1})
    assert deck_old.virtual_segment_wires == frozenset()
    assert len(deck_new.wire_tuples()) == 1 and len(deck_old.wire_tuples()) == 2
    assert z_new == pytest.approx(z_old, rel=1e-12)


def test_a_tl_only_virtual_segment_is_left_exactly_as_it_was():
    """Dan's CardTL.ez class. A wire that only TERMINATES TL cards imports and
    solves today, so AK#1577 does not touch it — the idiom's reading would
    move that answer by 0.53 % (an ideal open against the pinned segment's own
    admittance), which is a change for an issue that asks for one."""
    (z_new, deck_new), (z_old, deck_old) = _z_both_ways(OPEN_STUB)
    assert deck_new.virtual_anchors == frozenset()
    assert deck_new.wire_tuples() == deck_old.wire_tuples()
    assert z_new == z_old


# --------------------------------------------------------------------------
# gate 5 — the #824 refusal still fires on a REAL wire
# --------------------------------------------------------------------------
REAL_WIRE_COLLISION = (
    "CM a knot source and a network port on one piece of a REAL wire\n"
    "CE\n"
    "GW 1,21,-4.87,0.,21.45,4.87,0.,21.45,.0254\n"
    "GW 2,3,2114.9,2114.9,2114.9,2114.93,2114.93,2114.93,.0021\n"
    "GE 0\nFR 0,1,0,0,14.175\n"
    "LD 4,2,1,0,1.E+10,0.\n"
    "EX 4,1,11,2,1.414214,0.\n"  # knot 11 of wire 1 — a current source
    "NT 1,11,2,1,.01,0.,0.,0.,0.,0.\n"  # ... and an NT on segment 11
    "EN\n"
)


def test_824_refusal_still_fires_for_a_real_wire():
    """Wire 1 is the antenna: a knot source there needs its own wire end, and
    the NT claims the same one-segment piece. Virtualizing wire 2 (which IS
    the idiom) does not make that collision legal."""
    deck = parse_nec(REAL_WIRE_COLLISION, network=True)
    assert deck.virtual_segment_wires == frozenset({1})
    with pytest.raises(ValueError, match="claimed by more than one attachment"):
        deck.wire_tuples()


# --------------------------------------------------------------------------
# negatives — the detector must not swallow anything intentional
# --------------------------------------------------------------------------
def _remote(deck_text, **kw):
    return parse_nec(deck_text, network=True, **kw).virtual_segment_wires


def test_a_real_load_on_the_remote_wire_disqualifies_it():
    text = PARALLEL_LOAD.replace("LD 4,2,1,0,1.E+10,0.\n", "LD 0,2,1,1,50.,0.,0.\n")
    assert _remote(text) == frozenset()


def test_a_nearby_wire_is_not_virtualized():
    text = PARALLEL_LOAD.replace(
        "2114.9,2114.9,2114.9,2114.93,2114.93,2114.93", "3.,0.,21.45,3.03,0.,21.45"
    )
    assert _remote(text) == frozenset()


def test_a_remote_wire_that_is_electrically_big_is_not_virtualized():
    """Clearance alone is not enough: a remote wire a sizable fraction of a
    wavelength long is an antenna in a coupling study, not a node holder."""
    text = PARALLEL_LOAD.replace(
        "2114.9,2114.9,2114.9,2114.93,2114.93,2114.93",
        "2114.9,2114.9,2114.9,2120.,2120.,2120.",
    )
    assert _remote(text) == frozenset()


def test_no_frequency_disables_virtualization():
    text = PARALLEL_LOAD.replace("FR 0,1,0,0,14.175\n", "")
    assert _remote(text) == frozenset()


def test_virtualize_anchors_off_keeps_the_wire():
    assert _remote(PARALLEL_LOAD, virtualize_anchors=False) == frozenset()
