"""SimNEC script forms the import reads, refuses rather than drops, and the
export's buried wire (AK#2195, AK#2196).

AK#2195: three hand-written SimNEC spellings around a NEC2 block were not read.
A source on a port's own nodes with no EX card refused the file as having no
source. Per-wire ``$GW_<tag>.Insulation(...)`` and an inline load expression
were reported "not applied" while the file still solved, which is a
confidently wrong answer. Each now reads, or the file is refused by name.

AK#2196: a design with a buried wire hung the Files view's SimNEC tab. The
exporter built its NEC block through a NEC-2 context, which raised on the
wire below ground, and the route turned that into a 500. The block is NEC-2
card syntax that SimNEC's NEC-5 and NEC-4.2 engines read with the soil
around the wire, so the export now writes it and stops SimNEC's NEC-2 engine
by name.

Every fixture is synthetic, made up for these tests.
"""

from __future__ import annotations

import xml.etree.ElementTree as ET
from types import MappingProxyType

import pytest
from fastapi.testclient import TestClient

from antennaknobs.builder import AntennaBuilder
from antennaknobs.engines.pynec import PyNECEngine
from antennaknobs.network import Driven, Load, Network, PortOnWire, Wire
from antennaknobs.simnec_export import export_ssn
from antennaknobs.simnec_import import parse_ssn
from antennaknobs.wire_catalog import WireSpec

FREQ = 14.0
# A 21-segment, 10.2 m dipole along z: segment 11's centre is 50 %, and
# segment 6's centre is (5.5 / 21) of the wire.
DIPOLE = "GW 1,21,0,0,0,0,0,10.2,.001"
SEG6 = f"{5.5 / 21 * 100:.12g}"


def _ssn(script: str) -> str:
    """A minimal SimNEC circuit around ``script``: an open LOAD, the NETWORK
    element and a GENERATOR at ``FREQ``, the shape the exporter writes."""
    root = ET.Element("SimNEC1p0")
    circuit = ET.SubElement(ET.SubElement(root, "SmithChartCircuit"), "CIRCUIT")

    def element(typ, label, params):
        el = ET.SubElement(circuit, "element")
        ET.SubElement(el, "type").text = typ
        ET.SubElement(el, "sweeperLabel").text = label
        for n, v in params:
            p = ET.SubElement(el, "p")
            ET.SubElement(p, "n").text = n
            ET.SubElement(p, "v").text = v

    element("LOAD", "L", [("ohms", "1000000000")])
    element("NETWORK", "A", [("equ", script)])
    element("GENERATOR", "G", [("MHz", str(FREQ)), ("Zo", "50")])
    return ET.tostring(root, encoding="unicode")


def _script(*after, block=(DIPOLE, "EX 0 1 11 0 1 0"), before=()) -> str:
    return "\n".join(
        [
            "//test",
            "P1 w1 gnd;",
            "P2 w2 gnd;",
            "NECUnits meters;",
            *before,
            "NEC2",
            *block,
            "NECEND",
            "$GW_1.JamSegments(21);",
            *after,
        ]
    )


def _z(text: str) -> complex:
    c = parse_ssn(text, name="t.ssn", network=True)

    class Circuit(AntennaBuilder):
        default_params = MappingProxyType({"freq": FREQ})

        def build_wires(self):
            return c.deck.wire_tuples(specs=True)

        def build_network(self):
            return c.network()

    return complex(PyNECEngine(Circuit(), ground=None).impedance()[0])


# --- AK#2195: the forms read ------------------------------------------------


def test_a_source_on_a_port_s_nodes_is_the_feed():
    """No EX card in the block: SimNEC's feed is the NECSource on a declared
    port's nodes, spelled with a `$` assignment."""
    by_card = _z(_ssn(_script()))
    by_source = _z(
        _ssn(
            _script(
                "$src = NECSource({w2, gnd}, $GW_1, 50);",
                block=(DIPOLE,),
            )
        )
    )
    assert by_source == pytest.approx(by_card, rel=1e-9)


def test_an_inline_load_reads_as_the_two_node_spelling():
    inline = _z(
        _ssn(_script(f"$ld = NECSource(R(1k) ||| L(2u) ||| C(30p), $GW_1, {SEG6});"))
    )
    two_node = _z(
        _ssn(
            _script(
                "R1 (1000 ||| L(2e-06) ||| C(3e-11)) n1 n2;",
                f"dcl ld = NECSource({{n1,n2}}, $GW_1, {SEG6});",
            )
        )
    )
    bare = _z(_ssn(_script()))
    assert inline == pytest.approx(two_node, rel=1e-9)
    assert abs(inline - bare) > 1.0  # the load is really there


def test_per_wire_insulation_is_that_wire_s_jacket():
    per_wire = parse_ssn(_ssn(_script("$GW_1.Insulation(1m, 3.0, 0);")), name="t.ssn")
    default = parse_ssn(
        _ssn(_script(before=('NECOptions.Insulation("W7EL", 0.001, 3.0, 0);',))),
        name="t.ssn",
    )
    assert per_wire.deck.wire_insulation == default.deck.wire_insulation
    ((i, (b, eps_r)),) = per_wire.deck.wire_insulation
    assert i == 0
    assert b == pytest.approx(0.002)
    assert eps_r == 3.0


# --- AK#2195: refused, not dropped -------------------------------------------


@pytest.mark.parametrize(
    "stmt",
    [
        # A value the import cannot read (a variable).
        "$ld = NECSource(R(rv) ||| L(2u), $GW_1, 50);",
        # A wire no GW card declares.
        "$GW_7.Insulation(1m, 3.0, 0);",
        # An R component nothing attaches.
        "R1 (1000) n1 n2;",
    ],
)
def test_a_model_statement_left_unread_refuses_the_file(stmt):
    with pytest.raises(ValueError, match="could not be read"):
        _z(_ssn(_script(stmt)))


def test_a_load_and_a_source_at_wire_ends_sit_at_the_knot_exactly():
    """100 % is the wire's end, 0 % its start: knots, which NEC-2 cards cannot
    spell, so they go on the deck as a NEC-5 deck's end field does."""
    c = parse_ssn(
        _ssn(
            _script(
                "$src = NECSource({w2, gnd}, $GW_1, 0);",
                "$a = NECSource(R(1k) ||| L(2u), $GW_1, 100);",
                "$b = NECSource(R(500) ||| L(1u), $GW_1, 100);",
                block=(DIPOLE,),
            )
        ),
        name="t.ssn",
        network=True,
    )
    ((feed),) = c.deck.feeds
    assert (feed.wire, feed.seg, feed.edge) == (0, 1, 1)
    assert [(ld.wire, ld.seg, ld.edge, ld.r) for ld in c.deck.loads] == [
        (0, 21, 2, 1000.0),
        (0, 21, 2, 500.0),
    ]


def test_a_knot_between_segments_matches_the_nec5_deck_of_it():
    """Between segments 10 and 11 is a knot: the same place NEC-5's `EX 0 1 10
    2` names, so the import and that deck solve alike on a knot engine."""
    from antennaknobs.cli import make_engine_factory
    from antennaknobs.nec_import import parse_nec

    pct = f"{10 / 21 * 100:.12g}"
    ssn = parse_ssn(
        _ssn(_script(f"$src = NECSource({{w2, gnd}}, $GW_1, {pct});", block=(DIPOLE,))),
        name="t.ssn",
        network=True,
    )
    nec5 = parse_nec(
        f"CM\nCE\n{DIPOLE}\nGE 0\nEX 0 1 10 2 1 0\nFR 0 1 0 0 {FREQ} 0\nXQ\nEN\n",
        network=True,
        dialect="nec5",
    )

    def z(deck):
        class Deck(AntennaBuilder):
            default_params = MappingProxyType({"freq": FREQ})

            def build_wires(self):
                return deck.wire_tuples(specs=True)

            def build_network(self):
                return deck.network()

        return complex(
            make_engine_factory("momwire:razor-2p", None)(Deck()).impedance()[0]
        )

    assert z(ssn.deck) == pytest.approx(z(nec5), rel=1e-9)


def test_a_place_that_is_neither_centre_nor_knot_is_refused_not_moved():
    with pytest.raises(ValueError, match="neither a segment centre nor a knot"):
        _z(_ssn(_script("$ld = NECSource(R(1k) ||| L(2u), $GW_1, 40);")))


# --- AK#2196: a buried wire exports --------------------------------------------

SOIL = ("finite", 13.0, 0.005)
JACKET = WireSpec(radius=1e-3, insulation_radius=1.5e-3, insulation_eps_r=3.0)


class _RodVertical(AntennaBuilder):
    """A 5 m vertical fed at its foot, 0.1 m up, over a 1 m rod in the soil."""

    default_params = MappingProxyType({"freq": FREQ, "design_freq": FREQ})

    def build_wires(self):
        return [
            Wire((0, 0, 5.1), (0, 0, 0.11), 20, spec=JACKET),
            Wire((0, 0, 0.11), (0, 0, 0.1), 1, name="feed", spec=JACKET),
            Wire((0, 0, 0.1), (0, 0, 0.0), 2),
            Wire((0, 0, 0.0), (0, 0, -1.0), 4),
        ]

    def build_network(self):
        return Network(
            ports={"feed": PortOnWire("feed")},
            branches=[],
            sources=[Driven(port="feed", voltage=1 + 0j)],
        )


class _RodVerticalLoaded(_RodVertical):
    def build_wires(self):
        w = super().build_wires()
        return [*w[:2], Wire((0, 0, 0.1), (0, 0, 0.0), 1, name="ld"), w[3]]

    def build_network(self):
        net = super().build_network()
        return Network(
            ports={"feed": PortOnWire("feed"), "ld": PortOnWire("ld")},
            branches=[Load("ld", r=50.0)],
            sources=net.sources,
        )


def _equ(text: str) -> str:
    for el in ET.fromstring(text).iter("element"):
        if el.findtext("type") == "NETWORK":
            for p in el.findall("p"):
                if p.findtext("n") == "equ":
                    return p.findtext("v")
    raise AssertionError("no NETWORK script")


def test_a_buried_wire_exports_with_a_guard_for_nec2():
    text = export_ssn(_RodVerticalLoaded(), ground=SOIL, freq_mhz=FREQ)
    equ = _equ(text)
    assert "SommerfeldGround(0.005, 13);" in equ
    assert "if (NECOptions.Engine == 2)" in equ
    assert "NOT USING NEC-5 OR NEC-4.2: wire 4 is buried" in equ
    # The jacket goes per wire, the form SimNEC's NEC-5 engine runs; the
    # W7EL form needs SimNEC's NEC-2 engine.
    assert "W7EL" not in equ
    assert "$GW_1.Insulation(0.0005, 3, 0);" in equ
    assert "$GW_2.Insulation(0.0005, 3, 0);" in equ
    # It reads back: the rod is still in the soil, and the jackets are on.
    c = parse_ssn(text, name="rt.ssn", network=True)
    assert min(min(w.p1[2], w.p2[2]) for w in c.deck.wires) == pytest.approx(-1.0)
    assert {i for i, _ in c.deck.wire_insulation} == {0, 1}
    assert c.ground == SOIL


def test_the_route_answers_any_exporter_failure(monkeypatch):
    """A 500 left the Files pane on "Writing the SimNEC circuit…" for good."""
    import dataclasses

    import antennaknobs.web.server as server

    def boom(req):
        raise RuntimeError("GEOMETRY DATA ERROR--SEGMENT 9 EXTENDS BELOW GROUND")

    real = server.example_for
    monkeypatch.setattr(
        server,
        "example_for",
        lambda g: dataclasses.replace(real(g), ssn_export=boom),
    )
    r = TestClient(server.app).post("/design_ssn", json={"geometry": "dipoles.invvee"})
    assert r.status_code == 200
    got = r.json()
    assert got["available"] is False
    assert "EXTENDS BELOW GROUND" in got["reason"]
