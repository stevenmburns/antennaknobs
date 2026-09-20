"""A knot claim is a claim on a NODE, so it need not own the piece that ends
there (AK#1583).

`wire_tuples` cuts a wire into pieces and gives each at most one name, so a
NEC-5 knot attachment has to ride a piece's authored END. It always rode the
piece ENDING at the knot (knot 0 excepted), which collides with the gap port of
a source on that piece's segment -- even though the two are half a segment
apart and the knot is a junction the claim does not need any of that wire for.

The collision is not exotic: it is EZNEC's own instrumentation idiom. A 1e-10 V
`EX` is an ammeter EZNEC drops beside an `LD` to read the current through it
(ROY's probe rule, QRZ 1003328 #98), and the deck says so in its header --
``CM ! 1.E-10 volt sources for recording currents at load locations.`` Every
AutoEZ/EZNEC model that instruments a load sitting at a wire join produces it.
WA7ARK's 40 m choked-coax EFHW with a bonded ground rod is the reporting deck:
``EX 0,2,33,0`` at the CENTRE of segment 33 and ``LD 4,2,33,0`` at KNOT 33,
where wire 3 begins.

The fix gives a crowded-out claim the node's OTHER arm. It is deliberately
narrow, and the two tests that hold it narrow are
`test_a_source_claim_does_not_change_arms` (measured: a source that changes
arms is silently inverted) and
`test_a_junction_of_three_wires_keeps_its_claim_where_the_deck_put_it`.
"""

from __future__ import annotations

from itertools import pairwise
from types import MappingProxyType

import numpy as np
import pytest

from antennaknobs import AntennaBuilder
from antennaknobs.engines import MomwireEngine
from antennaknobs.file_designs import builder_from_file
from antennaknobs.nec_import import parse_nec
from antennaknobs.network import (
    Driven,
    Load,
    Network,
    PortAtVertex,
    PortOnWire,
    Wire,
)

# WA7ARK's shape, reduced to the part that collides: a wire carrying a choke at
# its far end (`LD 4,2,33,0` -- knot 33, the join with wire 3) and EZNEC's
# ammeter beside it (`EX 0,2,33,0` -- the centre of segment 33). The base feed
# is an `EX 4` knot source on the ground contact, which is both an ordinary
# EZNEC drive and what settles the NEC-5 dialect here, exactly as the `EX 4`
# current source does in the reporting deck (that deck carries no "in NEC-5
# format" declaration, and must not: a declared deck reads `EX 0,2,33,0` as a
# knot source, and then there is no probe and no collision).
PROBE_AT_A_JOIN = """CM A choke at a wire join, with EZNEC's current probe beside it
CM
CM EZNEC Pro/2+ v. 7.0.3  2026-09-19 08:20:19
CM
CM ! 1.E-10 volt sources for recording currents at load locations.
CE
GW 1,15,0.,0.,0.,0.,0.,3.,.002794
GW 2,33,0.,0.,3.,0.,0.,10.,.002794
GW 3,3,0.,0.,10.,0.,0.,11.,.002794
GE 1
LD 4,2,33,0,2220.,1650.
FR 0,1,0,0,7.15
GN 1
EX 4,1,1,1,1.,0.
EX 0,2,33,0,1.E-10,0.
EN
"""

# A third arm on the node the load sits on. Nothing else moves.
THIRD_ARM = PROBE_AT_A_JOIN.replace("GE 1", "GW 4,2,0.,0.,10.,1.,0.,10.,.002794\nGE 1")

# The same crowded piece with a SOURCE on the knot instead of a load: `EX 4` at
# knot 33 and the probe at segment 33's centre.
SOURCE_AT_THE_JOIN = PROBE_AT_A_JOIN.replace("LD 4,2,33,0,2220.,1650.\n", "").replace(
    "EX 4,1,1,1,1.,0.", "EX 4,2,33,2,1.,0."
)


def _named(deck):
    return [(t[2], t[4] if len(t) > 4 else None) for t in deck.wire_tuples(specs=True)]


def _worst_rel(a, b):
    """The largest relative disagreement between two current vectors, scaled
    by the vector's own magnitude so the zero at a free end does not dominate.
    Returns ~0 for agreement and ~2 for one being the other's negative."""
    a, b = np.asarray(a), np.asarray(b)
    return float(np.max(np.abs(a - b)) / np.max(np.abs(a)))


def _deck(text, name="probe.nec"):
    return parse_nec(text, name=name, network=True)


def test_the_probe_beside_a_load_at_a_join_imports():
    """The reported refusal, on the reported shape. Wire 2 keeps its 33
    authored segments in two pieces -- 32 plain, then segment 33 alone under
    the probe's gap port -- and the choke is not on wire 2 at all."""
    deck = _deck(PROBE_AT_A_JOIN)
    assert _named(deck) == [
        (15, "feed1"),  # the ground-contact base feed, positioned (AK#1598)
        (32, None),
        (1, "feed2"),  # the probe's own segment
        (3, "load1"),  # wire 3, hosting the knot-33 claim at its p0
    ]


def test_the_choke_is_a_port_at_the_join_not_a_gap_on_wire_2():
    """The identity that matters, not merely that nothing raised: `load1` is a
    series node gap at the wire-2/wire-3 node, spelled on wire 3's p0.

    Hosting it there is what keeps the engines' rule -- a wire may be named by
    a gap port or by a vertex port, never both (`wire_catalog.check_network`,
    issues #579, #898). Wire 2 carries only the probe's gap; wire 3 only the
    vertex port."""
    net = _deck(PROBE_AT_A_JOIN).network()
    assert net.ports["load1"] == PortAtVertex("load1", end="p0")
    assert isinstance(net.ports["feed2"], PortOnWire)
    assert net.ports["feed2"].at is None  # the middle of segment 33's own piece
    (load,) = [b for b in net.branches if isinstance(b, Load)]
    assert load.port == "load1" and load.z == 2220 + 1650j


def test_the_hosting_wire_is_where_the_join_is():
    """Node identity is geometric, and it is NOT bitwise: wire 2's last knot
    evaluates to ``3 + (10 - 3) * 33/33``, wire 3 starts at the literal 10.
    The importer's one notion of coincidence is `_junction_cuts`' 1e-9 bucket,
    and the host is found with the same one."""
    tups = _deck(PROBE_AT_A_JOIN).wire_tuples(specs=True)
    (host,) = [t for t in tups if t[4] == "load1"]
    (probe,) = [t for t in tups if t[4] == "feed2"]
    assert np.allclose(host[0], probe[1], rtol=0, atol=1e-9)
    assert np.allclose(host[0], (0.0, 0.0, 10.0), rtol=0, atol=1e-9)


def test_the_deck_keeps_its_own_segmentation_and_boundaries():
    """Re-hosting moves a NAME, never a segment. Each authored wire's pieces
    still sum to its `GW` count and still run end to end, which is the claim
    that the deck is being reproduced rather than approximated."""
    deck = _deck(PROBE_AT_A_JOIN)
    tups = deck.wire_tuples(specs=True)
    assert [w.n_seg for w in deck.wires] == [15, 33, 3]
    # wire 1 whole, wire 2 in two pieces, wire 3 whole
    assert [t[2] for t in tups] == [15, 32, 1, 3]
    for w, pieces in ((deck.wires[0], tups[:1]), (deck.wires[1], tups[1:3])):
        assert sum(p[2] for p in pieces) == w.n_seg
        assert np.allclose(pieces[0][0], w.p1, rtol=0, atol=1e-12)
        assert np.allclose(pieces[-1][1], w.p2, rtol=0, atol=1e-9)
        for lo, hi in pairwise(pieces):
            assert lo[1] == hi[0]  # adjoining pieces meet bitwise


def test_re_hosting_does_not_drag_the_host_wire_into_the_vertex_spelling():
    """The failure mode this change most easily hides: `_vertex_wires` decides
    whether a wire's OTHER attachments get positioned ports (`_site_plan`) or
    the #824 cut, so dragging a wire in would silently move ports that have
    nothing to do with #1583.

    It cannot happen, because a host is only ever a wire the emit loop already
    handles: a `_site_plan` wire is rejected as a candidate outright (its
    pieces carry gap ports, which may not share a wire with a vertex port), and
    a wire with no attachments has no `_site_plan` entry to change."""
    deck = _deck(PROBE_AT_A_JOIN)
    assert deck._vertex_hosts == {(1, 33): (2, 0, "p0")}
    assert deck._vertex_wires == frozenset({1})  # wire 3 is NOT pulled in
    assert set(deck._site_plan) == {0}  # only the ground-contact base feed
    assert deck._site_plan[0]["pieces"] == [(0, 15, "feed1")]


def test_the_deck_reaches_an_engine(tmp_path):
    """Importing was never the point. The whole route -- named wires, port
    check, mesh coercion, momwire's node gap -- has to accept what comes out,
    and `check_network`'s gap-versus-vertex rule is the one a wrong host would
    trip."""
    path = tmp_path / "probe.nec"
    path.write_text(PROBE_AT_A_JOIN, encoding="utf-8")
    cls = builder_from_file(str(path))
    z = np.asarray(MomwireEngine(cls(), ground=cls.file_ground).impedance())
    assert z.shape == (2,)
    assert np.all(np.isfinite(z))


def test_a_junction_of_three_wires_keeps_its_claim_where_the_deck_put_it():
    """At a node of degree >= 3, WHICH arm the gap separates is part of the
    answer -- that is exactly what NEC-5's tag/segment/end addressing says, and
    what momwire's `PortAtVertex` means by "the current flowing from the node
    INTO the named wire". A third wire at the join therefore leaves the claim
    on wire 2, and the refusal stands with the reason named."""
    deck = _deck(THIRD_ARM, name="three.nec")
    with pytest.raises(ValueError, match="piece between knots 32 and 33") as e:
        deck.wire_tuples(specs=True)
    assert "has degree 3" in str(e.value)


def test_a_wire_that_already_carries_gap_ports_cannot_host_the_claim():
    """The other half of "nothing silently moves".

    Give wire 3 a mid-wire load of its own and it becomes a `_site_plan`
    wire -- its attachments are positioned `PortOnWire` gaps. A wire may be
    named by a gap port or by a vertex port, never both
    (`wire_catalog.check_network`), so hosting the choke there would mean
    re-spelling wire 3's own ports, which is a larger decision than AK#1583's.
    The claim stays put and the refusal says so by name rather than by
    accident."""
    deck = _deck(
        PROBE_AT_A_JOIN.replace(
            "LD 4,2,33,0,2220.,1650.\n",
            "LD 4,2,33,0,2220.,1650.\nLD 4,3,2,0,10.,0.\n",
        ),
        name="busy.nec",
    )
    assert set(deck._site_plan) == {0, 2}
    assert deck._vertex_hosts == {(1, 33): (1, 33, "p1")}  # unmoved
    with pytest.raises(ValueError, match="piece between knots 32 and 33") as e:
        deck.wire_tuples(specs=True)
    assert "carries positioned gap ports of its own" in str(e.value)


def test_a_source_claim_does_not_change_arms():
    """The restriction that keeps this fix honest; the measurement behind it
    is the pair
    `test_a_driven_source_at_a_two_wire_node_is_inverted_by_the_other_arm` and
    `test_a_load_at_a_two_wire_node_is_the_same_circuit_on_either_arm`.

    A source's port has a polarity; a two-terminal load's does not. So a knot
    carrying anything but `LD`s stays where the deck put it and the refusal
    stands -- with the reason, because "it is claimed by more than one
    attachment" alone does not tell anyone what was tried."""
    deck = _deck(SOURCE_AT_THE_JOIN, name="src.nec")
    assert deck._vertex_claims == {(1, 33): ("feed1", False)}
    with pytest.raises(ValueError, match="piece between knots 32 and 33") as e:
        deck.wire_tuples(specs=True)
    assert "source or a TL/NT end" in str(e.value)


def test_the_no_room_refusal_of_1594_still_refuses():
    """AK#1594/#1599 kept the refusal where a 1-segment piece genuinely has no
    room -- knot 0 against knot 1 -- and this change does not widen it there.

    The same wire's other side IS a two-arm alternative and would take the
    load, which is why it is excluded by name in `_vertex_candidates` rather
    than by accident: whether to spend AK#1594's pinned refusal is a separate
    decision from AK#1583's."""
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
    deck = _deck(text, name="noroom.nec")
    with pytest.raises(ValueError, match="piece between knots 0 and 1") as e:
        deck.wire_tuples(specs=True)
    assert "not a wire end this spelling can name" in str(e.value)


def test_a_driven_source_at_a_two_wire_node_is_the_same_circuit_either_arm():
    """AMENDED for AK#1608. This test used to assert the OPPOSITE, and the
    change of verdict is the point.

    momwire resolves a `PortAtVertex` to "the current flowing from the node
    INTO the named wire", so at momwire's own boundary naming the other arm
    of a two-wire node reverses the port's reference direction, and a driven
    source's currents come back NEGATED. That reading is still true OF
    MOMWIRE, and it was measured here (impedance agreeing to 6.1e-15, currents
    negated to 6.0e-15).

    It is no longer true at AK's boundary. AK#1608 found that the engine was
    stamping deck-convention network branches onto momwire-convention ports
    and applying no congruence between them -- worth up to 16 % on any deck
    carrying a TL or NT, and decided against AK by the engine's own printouts
    (0012 and 0016 print byte-identical; serve preserved that to 1e-15, AK
    broke it by 7.2 %). `_contract_y` now signs the vertex block, so a port's
    reported current means "current in the +wire direction" whichever arm
    names it, and the two spellings are ONE circuit.

    That has to be so for decks: `TL 2,-1,4,1` and `TL 1,10,4,1` are two
    spellings of one node, and the author's arbitrary tag choice cannot pick
    the answer. It is the same port type for hand-authored designs, so it is
    one convention for both.

    What this costs AK#1583: `_vertex_candidates`' refusal on a source claim
    is now CONSERVATIVE rather than necessary -- its stated reason (a
    reference direction that reverses) no longer holds at this boundary. The
    refusal is unchanged and still correct to keep; widening it is a separate
    decision with its own measurement, not a free consequence of this one.

    The bar is 1e-10 -- four orders above the assembly-order noise the two
    spellings legitimately carry, and ten below the factor of two that a
    regression to the old convention would show, which the second assertion
    pins from the other side."""
    arm, freq = 2.6, 27.0

    def run(end):
        class _B(AntennaBuilder):
            default_params = MappingProxyType({"design_freq": freq, "freq": freq})

            def build_wires(self):
                lower = "p" if end == "p1" else None
                return [
                    Wire((0, 0, -arm), (0, 0, 0), n_seg=8, name=lower),
                    Wire((0, 0, 0), (0, 0, arm), n_seg=8, name=None if lower else "p"),
                ]

            def build_network(self):
                return Network(
                    ports={"p": PortAtVertex("p", end=end)},
                    branches=[],
                    sources=[Driven(port="p", voltage=1 + 0j)],
                )

        eng = MomwireEngine(_B(), ground=None)
        (z,) = eng.impedance()
        return z, np.asarray(eng.current_distribution()[0].knot_currents)

    p1, p0 = run("p1"), run("p0")
    assert p1[0] == pytest.approx(p0[0], rel=1e-10)
    # SAME, not negated -- the congruence normalizes the arm away.
    assert _worst_rel(p1[1], p0[1]) < 1e-10
    # And pinned from the other side: a regression to the raw momwire
    # convention would make these differ by a factor of two.
    assert _worst_rel(p1[1], -p0[1]) > 1.0


def test_a_load_at_a_two_wire_node_is_the_same_circuit_on_either_arm():
    """The load half of the measurement above, on its own so a regression says
    which half moved. Same geometry, same gap feed, only the arm the choke's
    port names -- and every knot current comes back the SAME (1.3e-13
    relative, assembly-order noise), not negated. A two-terminal impedance has
    no polarity: V = I*Z survives both signs flipping. That is what makes
    AK#1583's re-hosting a spelling change and not a model change, and it is
    the only claim allowed to move."""
    arm, freq = 2.6, 27.0

    def run(end):
        class _B(AntennaBuilder):
            default_params = MappingProxyType({"design_freq": freq, "freq": freq})

            def build_wires(self):
                lower = "ld" if end == "p1" else None
                return [
                    Wire((0, 0, -arm), (0, 0, -arm + 0.3), n_seg=1, name="feed"),
                    Wire((0, 0, -arm + 0.3), (0, 0, 0), n_seg=7, name=lower),
                    Wire((0, 0, 0), (0, 0, arm), n_seg=8, name=None if lower else "ld"),
                ]

            def build_network(self):
                return Network(
                    ports={
                        "feed": PortOnWire("feed"),
                        "ld": PortAtVertex("ld", end=end),
                    },
                    branches=[Load(port="ld", r=2220.0, l=1650e-9)],
                    sources=[Driven(port="feed", voltage=1 + 0j)],
                )

        eng = MomwireEngine(_B(), ground=None)
        (z,) = eng.impedance()
        return z, np.asarray(eng.current_distribution()[1].knot_currents)

    p1, p0 = run("p1"), run("p0")
    assert p1[0] == pytest.approx(p0[0], rel=1e-10)
    assert _worst_rel(p1[1], p0[1]) < 1e-10
    assert _worst_rel(p1[1], -p0[1]) > 1.0
