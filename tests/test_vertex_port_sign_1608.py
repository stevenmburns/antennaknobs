"""A vertex port reaches the network in the DECK's sign convention (AK#1608).

`MomwireEngine` resolves a `PortAtVertex` to a momwire `node_gaps` series
feed, whose port current is the one flowing FROM the node INTO the named
wire. Every branch stamped onto that port is authored in the other
convention -- the current ALONG the named wire's own p0->p1 direction. The
two agree at a `p0` and are opposite at a `p1`, so a `p1` port reached
`NetworkReducer` with its row and its column negated.

With one driven port and nothing relating it to another, that is gauge: the
flip cancels between the voltage and the current and the impedance never
moves, which is why it survived `test_vertex_wire_choice_is_immaterial_at_
degree_two` and every network-free deck in momwire's EZNEC corpus. A
TWO-PORT branch is what can see it -- a `TL`, or an `NT` carrying Y12 --
because a relative sign between two ports is a different circuit: the line
comes out silently transposed.

The fix is the congruence issue #580 already applies to gap feeds for the
walk direction, extended to the vertex block of `_contract_y` and to the
voltage that goes in beside it.

The oracle is invariance, and it needs no engine but this one: `2,-1` and
`1,10` are two spellings of ONE node on deck 0011, with both wires running
+y through it, so the port they name is the same port. `momwire.eznec.serve`
answers both with 26.728390 - 11.751671j. Before this fix antennaknobs
answered 26.228536 - 11.652622j for the `p1` spelling and serve's value for the
`p0` one: 1.75e-02 apart on a relabelling that moved no wire.
"""

from __future__ import annotations

from pathlib import Path
from types import MappingProxyType

import numpy as np

from antennaknobs import AntennaBuilder
from antennaknobs.engines import MomwireEngine
from antennaknobs.file_designs import builder_from_file
from antennaknobs.network import (
    TL,
    Driven,
    Network,
    PortAtVertex,
    PortOnWire,
    Wire,
)

# momwire's EZNEC capture of a dipole fed through a coax feedline: one `TL`,
# one source, and both of its ends on wire vertices -- the corpus's minimal
# two-port-branch deck, and the one AK#1608 was filed on.
DECK = Path("momwire/tests/fixtures/eznec/decks/0011_dipole-with-coax-feedline.nec")

# `2,-1` is end 1 of segment 1 of wire 2; `1,10` is end 2 of segment 10 of
# wire 1. Wire 1 runs to (0, -.03048, 9.144) and wire 2 runs on from it, both
# in +y, so the two fields name one node AND one reference direction. Only the
# tag the card uses to reach it differs.
SHIPPED = "TL 2,-1,4,1,50.,13.85023,0.,0.,0.,0."
RESPELLED = "TL 1,10,4,1,50.,13.85023,0.,0.,0.,0."

FREQ = 27.0
ARM = 2.6


def _z(path):
    """The deck through the workbench route, in FREE SPACE.

    Deliberately not `cls.file_ground`: 0011 declares `GN 0`, and a
    Sommerfeld fill costs 4.3 s for the pair against 0.3 s for the same pair
    in free space -- over the issue #393 budget for a test that should run on
    every PR. What is being pinned is which port a card's `(tag, segment)`
    field names, which the ground does not enter: the invariance holds at
    7.3e-14 in free space and 3.7e-14 over the deck's own ground, and the
    defect it catches is large either way -- 5.6e-03 free, 1.75e-02 grounded."""
    cls = builder_from_file(path)
    return complex(MomwireEngine(cls(), ground=None).impedance()[0])


def _engine(end):
    """An apex-fed split dipole with a `TL` off the apex to a parasitic stub,
    the vertex named from the lower arm's `p1` or the upper arm's `p0`.

    Only the port-referenced arm is named: an unreferenced name is an open
    gap by the #578 rule, so the variant renames the other arm rather than
    adding a second name (the idiom `test_port_at_vertex` uses)."""

    class _B(AntennaBuilder):
        default_params = MappingProxyType({"design_freq": FREQ, "freq": FREQ})

        def build_wires(self):
            lower = "apex" if end == "p1" else None
            return [
                Wire((0, 0, -ARM), (0, 0, 0), n_seg=8, name=lower),
                Wire((0, 0, 0), (0, 0, ARM), n_seg=8, name=None if lower else "apex"),
                Wire((1.5, 0, -ARM), (1.5, 0, ARM), n_seg=16, name="stub"),
            ]

        def build_network(self):
            return Network(
                ports={
                    "apex": PortAtVertex("apex", end=end),
                    "stub": PortOnWire("stub"),
                },
                branches=[TL(a="apex", b="stub", z0=50.0, length=3.0)],
                sources=[Driven(port="apex", voltage=1 + 0j)],
            )

    return MomwireEngine(_B(), ground=None)


def test_the_spelling_of_a_network_end_does_not_move_the_answer(tmp_path):
    """THE gate, on a shipping deck, with no second engine in it.

    Both cards name the wire-1/wire-2 junction and both wires run +y through
    it, so the port is the same port and the antenna is the same antenna. The
    bar is 1e-12: nine orders under the 5.6e-03 the missing congruence costs
    here, and well above the assembly-order noise two different wire orderings
    carry (measured 7.3e-14). Over the deck's own ground the same two
    spellings were 1.75e-02 apart, which is the 0011 number AK#1608 reports."""
    text = DECK.read_text(errors="replace")
    assert SHIPPED in text, "fixture moved: the TL card this test respells is gone"
    shipped = tmp_path / "shipped.nec"
    respelled = tmp_path / "respelled.nec"
    shipped.write_text(text)
    respelled.write_text(text.replace(SHIPPED, RESPELLED))

    a, b = _z(shipped), _z(respelled)
    rel = abs(a - b) / abs(a)
    assert rel < 1e-12, f"{SHIPPED} -> {a!r}, {RESPELLED} -> {b!r}, rel {rel:.3e}"


def test_two_spellings_of_one_vertex_agree_through_a_transmission_line():
    """The same statement without a deck, and the reason the existing
    degree-two test did not catch this.

    `test_vertex_wire_choice_is_immaterial_at_degree_two` drives the vertex
    and nothing else, where the wire choice is gauge and the impedance was
    already immaterial. Hang a `TL` off the same vertex and the choice stops
    being gauge: the line sees the port's reference direction, and naming the
    other arm transposed it."""
    p1 = complex(_engine("p1").impedance()[0])
    p0 = complex(_engine("p0").impedance()[0])
    rel = abs(p1 - p0) / abs(p0)
    assert rel < 1e-12, f"p1 {p1!r} vs p0 {p0!r}, rel {rel:.3e}"


def test_the_swept_path_carries_the_same_sign():
    """`_contract_y` has two branches — one matrix, and a swept (n_k, n, n)
    stack through `np.einsum` — and a congruence applied to only one of them
    would make `impedance_sweep` disagree with `impedance` at the same
    frequency. Same invariance, same bar, through the stack."""
    a = np.asarray(_engine("p1").impedance_sweep([26.0, 27.0, 28.0]))
    b = np.asarray(_engine("p0").impedance_sweep([26.0, 27.0, 28.0]))
    worst = float(np.max(np.abs(a - b) / np.abs(b)))
    assert worst < 1e-12, f"p1 {a.ravel()} vs p0 {b.ravel()}, worst {worst:.3e}"


def test_the_fast_path_is_taken_exactly_when_there_is_nothing_to_sign():
    """The congruence must reach vertex ports and stop there.

    Both halves matter and each pins the other's boundary. A design whose
    vertex ports all sit at `p0` has nothing to normalize, and `_contract_y`
    must hand its Y back UNTOUCHED rather than round-trip it through a
    multiply -- that identity is why every network-free deck in momwire's
    EZNEC corpus is bit-identical across this change, and why `PortAtEnd`
    rows still ride the fast path (a KCL row's outflow convention is
    geometric and both conventions already agree on it).

    Name the same vertex from the other arm and the port is a `p1`: its row
    and column carry the -1, so the off-diagonal that couples it to the
    `stub` gap port comes back negated. Before the fix the `p1` design took
    the fast path too, which is the whole defect in one line."""
    probe = np.array([[1.0 + 0j, 2.0 + 3.0j], [2.0 + 3.0j, 4.0 + 0j]])

    untouched = _engine("p0")._contract_y(probe)
    assert untouched is probe

    signed = _engine("p1")._contract_y(probe)
    assert signed is not probe
    # feeds first, then vertex ports: the gap port on `stub` is row 0 and the
    # apex vertex is row 1 (momwire's [feeds..., junction_ports..., node
    # gaps...] Y ordering).
    assert signed[0, 0] == probe[0, 0] and signed[1, 1] == probe[1, 1]
    assert signed[0, 1] == -probe[0, 1] and signed[1, 0] == -probe[1, 0]
