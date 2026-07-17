"""Remote TL-anchor wires are virtualized at import time (issue #427).

The classic NEC stub trick parks a 1-segment wire hundreds of wavelengths
away purely so a ``TL`` card has a far-end segment to terminate on. The wire
is designed to be electrically irrelevant, and modeling it as real geometry
either wastes a basis function or (with Sommerfeld ground) hangs momwire's
matrix assembly (momwire#157). ``parse_nec(network=True)`` instead drops the
anchor wire and terminates the TL on a ``PortVirtual`` circuit node — an ideal
open for the zero-far-Y "open stub", or a 1-port ``Admittance`` for the
``1.E+10`` "shorted stub".

The detection is deliberately conservative (``_anchor_wires``): a 1-segment
wire, referenced ONLY as a TL endpoint (not fed, loaded, an NT endpoint, or
sharing a node with another wire), and more than ten wavelengths clear of the
rest of the structure. These tests pin both the structural translation and,
in free space, that the virtualized result matches nec2c's reference for the
same deck (which models the real anchor wire) far better than momwire's own
attempt to mesh the tiny remote wire.
"""

from antennaknobs import AntennaBuilder, WireSpec
from antennaknobs.engines import MomwireEngine
from antennaknobs.nec_import import parse_nec
from antennaknobs.network import (
    Admittance,
    Driven,
    Network,
    PortOnWire,
    PortVirtual,
    TL,
)
from momwire import SinusoidalSolver

# The sinusoidal basis matches NEC's own basis functions, so it is the
# apples-to-apples engine for NEC-fidelity checks (against nec2c/PyNEC).
FREQ = 14.175

# A half-wave dipole (odd segment count, feed at the middle segment) plus a
# 1-segment anchor ~172 λ away, with an open-stub TL from the feed to it.
_DIPOLE = "GW 1,21,-4.87,0.,21.45,4.87,0.,21.45,.0254\n"
_ANCHOR = "GW 2,1,2114.9,2114.9,2114.9,2114.93,2114.93,2114.93,.0021\n"
_HEAD = "CE\n" + _DIPOLE + _ANCHOR + "GE 0\nFR 0,1,0,0,14.175\nEX 0,1,11,0,1.,0.\n"
OPEN_STUB = _HEAD + "TL 1,11,2,1,71.,4.294351,0.,0.,0.,0.\nEN\n"
SHORTED_STUB = _HEAD + "TL 1,11,2,1,50.,4.10505,0.,0.,1.E+10,1.E+10\nEN\n"


def _z(deck, radius=None):
    class B(AntennaBuilder):
        default_params = {"freq": FREQ}

        def build_wires(self):
            return deck.wire_tuples()

        def build_network(self):
            return deck.network()

        def build_wire_material(self):
            return WireSpec(radius=radius or deck.dominant_radius())

    eng = MomwireEngine(B(), solver=SinusoidalSolver, ground=None)
    return eng.impedance()[0]


# --------------------------------------------------------------------------
# detection + structural translation
# --------------------------------------------------------------------------
def test_open_stub_anchor_is_virtualized():
    deck = parse_nec(OPEN_STUB, network=True)
    # Wire index 1 (tag 2) is the anchor.
    assert deck.virtual_anchors == frozenset({1})
    assert deck.virtual_anchor_tags() == (2,)
    # The anchor is gone from the emitted geometry — only the dipole remains
    # (whole, since it is fed at its own middle segment).
    tups = deck.wire_tuples()
    assert len(tups) == 1
    # network(): the TL far end is a PortVirtual, the near end a real port.
    net = deck.network()
    assert isinstance(net.ports["tl1b"], PortVirtual)
    assert isinstance(net.ports["feed"], PortOnWire)
    # Open stub → the virtual node is left an ideal open (no shunt branch).
    kinds = sorted(type(b).__name__ for b in net.branches)
    assert kinds == ["TL"]


def test_shorted_stub_anchor_stamps_admittance():
    deck = parse_nec(SHORTED_STUB, network=True)
    assert deck.virtual_anchors == frozenset({1})
    net = deck.network()
    adm = [b for b in net.branches if isinstance(b, Admittance)]
    assert len(adm) == 1
    # 1-port complex admittance on the virtual node carrying the card's full
    # far-end Y = 1e10 + 1e10j (susceptance included — allowed on a virtual
    # end, unlike a real end).
    assert adm[0].ports == ("tl1b",)
    assert adm[0].y == ((complex(1e10, 1e10),),)


def test_virtualize_anchors_off_keeps_the_wire():
    deck = parse_nec(OPEN_STUB, network=True, virtualize_anchors=False)
    assert deck.virtual_anchors == frozenset()
    assert len(deck.wire_tuples()) == 2  # dipole + real anchor wire
    net = deck.network()
    assert isinstance(net.ports["tl1b"], PortOnWire)


def test_skipped_note_reports_virtualized_anchor():
    note = parse_nec(OPEN_STUB, network=True).skipped_note()
    assert "TL-anchor" in note
    assert "tag 2" in note


# --------------------------------------------------------------------------
# negatives — the heuristic must not swallow anything intentional
# --------------------------------------------------------------------------
def test_no_frequency_disables_virtualization():
    # Clearance is measured in wavelengths; with no FR card there is no λ, so
    # the safe default is to model every wire as written.
    text = OPEN_STUB.replace("FR 0,1,0,0,14.175\n", "")
    deck = parse_nec(text, network=True)
    assert deck.virtual_anchors == frozenset()


def test_nearby_tl_terminated_wire_is_not_virtualized():
    # A short TL-terminated wire a fraction of a wavelength away is a real
    # stub, not a remote anchor — clearance gate keeps it.
    near = _ANCHOR.replace(
        "2114.9,2114.9,2114.9,2114.93,2114.93,2114.93", "3.,0.,21.45,3.03,0.,21.45"
    )
    text = (
        "CE\n"
        + _DIPOLE
        + near
        + "GE 0\nFR 0,1,0,0,14.175\nEX 0,1,11,0,1.,0.\n"
        + "TL 1,11,2,1,71.,4.294351,0.,0.,0.,0.\nEN\n"
    )
    deck = parse_nec(text, network=True)
    assert deck.virtual_anchors == frozenset()


def test_fed_remote_wire_is_not_virtualized():
    # A second EX on the remote wire makes it electrically real — not an anchor.
    text = _HEAD + "EX 0,2,1,0,1.,0.\nTL 1,11,2,1,71.,4.294351,0.,0.,0.,0.\nEN\n"
    deck = parse_nec(text, network=True)
    assert deck.virtual_anchors == frozenset()


def test_loaded_remote_wire_is_not_virtualized():
    # An LD lumped load on the remote wire makes it electrically real.
    text = _HEAD + "LD 0,2,1,1,50.,0.,0.\nTL 1,11,2,1,71.,4.294351,0.,0.,0.,0.\nEN\n"
    deck = parse_nec(text, network=True)
    assert deck.virtual_anchors == frozenset()


# --------------------------------------------------------------------------
# equivalence — imported-virtualized must equal a hand-built PortVirtual
# network, in free space (fast, CI-safe)
# --------------------------------------------------------------------------
def test_imported_open_stub_matches_hand_built_virtual_termination():
    deck = parse_nec(OPEN_STUB, network=True)
    radius = 0.0254

    class Hand(AntennaBuilder):
        default_params = {"freq": FREQ}

        def build_wires(self):
            return [((-4.87, 0.0, 21.45), (4.87, 0.0, 21.45), 21, None, "feed")]

        def build_network(self):
            return Network(
                ports={"feed": PortOnWire("feed"), "far": PortVirtual("far")},
                branches=[TL(a="feed", b="far", z0=71.0, length=4.294351)],
                sources=[Driven(port="feed", voltage=1.0)],
            )

        def build_wire_material(self):
            return WireSpec(radius=radius)

    z_import = _z(deck, radius=radius)
    z_hand = MomwireEngine(Hand(), solver=SinusoidalSolver, ground=None).impedance()[0]
    assert abs(z_import - z_hand) < 1e-6
