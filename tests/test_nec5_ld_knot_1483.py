"""AK#1483: a NEC-5 deck's discrete LD card is ONE load at a knot.

NEC-5 addresses a discrete load (LD 0, 1, 4, 6) as it does a source: I3 is the
segment and I4 its END. The importer read I3..I4 as NEC-2's segment range, so
the catalog's NEC-5 trap dipole, `LD 1 2 1 2` on a 2-segment wire (one trap at
the wire's middle knot), imported as two traps, one per segment, each carrying
the full L and C. A NEC-2 deck keeps the range reading.
"""

from __future__ import annotations

import pytest

from antennaknobs.engines.nec5 import NEC5Engine
from antennaknobs.file_designs import builder_from_file
from antennaknobs.nec_import import parse_nec
from antennaknobs.network import Load, PortAtVertex, PortOnWire

# multiband.trap_dipole (default mesh, free space) as the catalog's NEC-5 deck
# writes it: `EX 0 3 21 2` is end 2 of segment 21, so the deck reads as NEC-5.
TRAP = """\
GW 1 10 -4.026718 0 5 -2.726718 0 5 5E-4
GW 2 2 -2.726718 0 5 -2.676718 0 5 5E-4
GW 3 42 -2.676718 0 5 2.676718 0 5 5E-4
GW 4 2 2.676718 0 5 2.726718 0 5 5E-4
GW 5 10 2.726718 0 5 4.026718 0 5 5E-4
GE 0
LD 1 2 1 2 0 5E-6 6.46181E-12
LD 1 4 1 2 0 5E-6 6.46181E-12
EX 0 3 21 2 1 0
FR 0 1 0 0 28 0
EN
"""


def _named(deck):
    return [(t[2], t[4] if len(t) > 4 else None) for t in deck.wire_tuples()]


def _loads(deck):
    return [(ld.wire, ld.seg, ld.edge) for ld in deck.loads]


def test_each_card_is_one_load_at_its_knot():
    deck = parse_nec(TRAP, name="trap.nec", network=True)
    assert deck.nec5_dialect is True
    assert _loads(deck) == [(1, 1, 2), (3, 1, 2)]
    # Knot 1 of a 2-segment wire is its middle: each trap wire stays whole and
    # carries a plain port.
    assert _named(deck) == [
        (10, None),
        (2, "load1"),
        (42, "feed"),
        (2, "load2"),
        (10, None),
    ]
    net = deck.network()
    assert net.ports["load1"] == PortOnWire("load1")
    loads = [b for b in net.branches if isinstance(b, Load)]
    assert [b.port for b in loads] == ["load1", "load2"]
    assert all(b.parallel and b.l == pytest.approx(5e-6) for b in loads)


def test_a_nec2_deck_keeps_the_segment_range():
    deck = parse_nec(
        TRAP.replace("EX 0 3 21 2", "EX 0 3 21 0"), name="t.nec", network=True
    )
    assert deck.nec5_dialect is False
    assert _loads(deck) == [(1, 1, 0), (1, 2, 0), (3, 1, 0), (3, 2, 0)]


def test_a_declared_deck_reads_end_1():
    """`CM NEC-5` (AK#1476) settles the dialect, so I4 = 1 names end 1."""
    text = "CM NEC-5\n" + TRAP.replace("EX 0 3 21 2", "EX 0 3 21 0").replace(
        "LD 1 2 1 2", "LD 1 2 2 1"
    ).replace("LD 1 4 1 2", "LD 1 4 2 1")
    deck = parse_nec(text, name="t.nec", network=True)
    assert _loads(deck) == [(1, 2, 1), (3, 2, 1)]
    assert _named(deck)[1] == (2, "load1")


def test_a_load_on_the_fed_knot_shares_the_source_port():
    deck = parse_nec(
        TRAP.replace("EX 0 3", "LD 0 3 21 2 50 0 0\nEX 0 3"), name="t.nec", network=True
    )
    net = deck.network()
    assert "load3" not in net.ports
    assert [b.port for b in net.branches if isinstance(b, Load)] == [
        "load1",
        "load2",
        "feed",
    ]


def test_a_load_off_the_middle_knot_is_a_positioned_port():
    text = TRAP.replace("GW 2 2 ", "GW 2 4 ")
    deck = parse_nec(text, name="t.nec", network=True)
    port = deck.network().ports["load1"]
    assert _named(deck)[1] == (4, "load1")
    assert port.at == pytest.approx(1 / 4)


def test_a_load_at_a_wire_end_keeps_the_vertex_spelling():
    deck = parse_nec(
        TRAP.replace("LD 1 2 1 2", "LD 1 2 2 2"), name="t.nec", network=True
    )
    assert _loads(deck)[0] == (1, 2, 2)
    port = deck.network().ports["load1"]
    assert isinstance(port, PortAtVertex)
    assert port.end == "p1"


def test_refinement_keeps_the_knot():
    deck = parse_nec(TRAP, name="trap.nec", network=True).refined(3)
    assert _loads(deck) == [(1, 3, 2), (3, 3, 2)]
    assert _named(deck)[1] == (6, "load1")


def test_the_nec5_deck_round_trips(tmp_path):
    path = tmp_path / "trap.nec"
    path.write_text(TRAP)
    b = builder_from_file(str(path))
    b = b() if isinstance(b, type) else b
    text = NEC5Engine(b, ground=None, require_exe=False).deck([b.freq])
    assert sum(line.startswith("LD 1 ") for line in text.splitlines()) == 2
    back = parse_nec(text, name="back.nec", network=True)
    assert _loads(back) == _loads(parse_nec(TRAP, name="trap.nec", network=True))
