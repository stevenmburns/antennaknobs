"""A source at a wire end standing in the ground plane is a ground-contact
feed, not a refusal (AK#1598).

`EX 4,tag,-1` at a wire's base is EZNEC's NEC-5 spelling of a BASE-FED
VERTICAL — the most ordinary ground-mounted antenna there is. Every NEC-5 knot
source used to route through `PortAtVertex` -> momwire's `node_gaps=`, which
needs a two-member junction to put a series EMF in, so a lone base died on

    ValueError: node_gaps[0]: junction 0 has a single member

momwire sorts a knot address THREE ways, not two (`momwire/eznec/_serve.py`,
"Three drive spellings"): a node where two or more wire ends meet takes the
series EMF; a FREE wire end is refused, because there is no through-current
path; and a wire end standing IN THE GROUND PLANE is neither — it is an
ordinary delta gap on the cell it stands in, the drive
`momwire/tests/test_contact_nec5_lane.py` certifies against NEC-5 over five
grounds and five densities. Only the first was reaching momwire from here.

The gate that matters is the DIALECT PAIR. EZNEC wrote Dan AC6LA's Cardioid to
both NEC-4.2 and NEC-5; the two decks are byte-identical apart from their `EX`
cards, so with the loads dropped the only thing left to disagree about is where
the drive lands — and they must agree exactly, not approximately.
"""

import tempfile
from pathlib import Path

import numpy as np
import pytest

from antennaknobs.engines import MomwireEngine
from antennaknobs.file_designs import builder_from_file
from antennaknobs.nec_import import parse_nec
from antennaknobs.network import PortAtVertex, PortOnWire

FIXTURES = Path(__file__).parent / "fixtures" / "eznec_gyrator_1595"
NEC4 = FIXTURES / "Cardioidmodnec4.nec"
NEC5 = FIXTURES / "Cardioidmodnec5.nec"

# One wire, one EX 4 at knot 0, no LD -- so it imports without AK#1599 in the
# way and isolates the END from everything else.
HEAD = "CM ! Written by EZNEC/Pro+ v. 7.0 in NEC-5 format.\nCE\n"
ON_GROUND = (
    "GW 1,6,0.,0.,0.,0.,0.,.242,.000121\nGE 1\nFR 0,1,0,0,299.7925\nGN 1\n"
    "EX 4,1,-1,0,1.,0.\n"
)
FREE_SPACE = (
    "GW 1,6,0.,0.,0.,0.,0.,.242,.000121\nGE 0\nFR 0,1,0,0,299.7925\nEX 4,1,-1,0,1.,0.\n"
)
ELEVATED = (
    "GW 1,6,0.,0.,1.,0.,0.,1.242,.000121\nGE 1\nFR 0,1,0,0,299.7925\nGN 1\n"
    "EX 4,1,-1,0,1.,0.\n"
)
INTERIOR = (
    "GW 1,6,0.,0.,0.,0.,0.,.242,.000121\nGE 1\nFR 0,1,0,0,299.7925\nGN 1\n"
    "EX 4,1,1,0,1.,0.\n"
)


def _deck(body):
    return parse_nec(HEAD + body + "EN\n", name="t.nec", network=True)


def _z(path):
    cls = builder_from_file(str(path))
    return np.asarray(MomwireEngine(cls(), ground=cls.file_ground).impedance())


def test_a_base_fed_vertical_solves():
    """The reporting shape: one wire standing on the plane, fed at its base."""
    deck = _deck(ON_GROUND)
    (src,) = deck.network().sources
    port = deck.network().ports[src.port]
    assert isinstance(port, PortOnWire)
    assert not isinstance(port, PortAtVertex)


def test_the_base_feed_drives_the_cell_it_stands_in():
    """`at` is the CENTRE of the first cell, which is the cell arclength 0
    falls in. A segment gap is `E = V/Delta` over the mesh cell containing the
    feed point, so those are one drive, not two — measured bit-identical on
    momwire's own contact lane. Six segments, so the centre of cell 1 is
    0.5/6."""
    deck = _deck(ON_GROUND)
    (src,) = deck.network().sources
    assert deck.network().ports[src.port].at == pytest.approx(0.5 / 6)


def test_a_free_lone_end_is_still_refused_and_says_why():
    """momwire refuses this row by design, and the deck should say what is
    wrong with IT rather than let `node_gaps[0]` surface as the diagnosis."""
    with pytest.raises(ValueError, match="FREE conductor end"):
        _deck(FREE_SPACE).network()


def test_an_elevated_lone_end_is_still_refused():
    """The ground exists but the end does not stand in it — the same refusal,
    and the message names the height rather than blaming free space."""
    with pytest.raises(ValueError, match=r"stands clear of the ground plane"):
        _deck(ELEVATED).network()


def test_the_ground_is_what_separates_the_two():
    """The three decks above differ ONLY in where the wire stands, which is
    what makes this a measurement: before AK#1598 all three failed alike, so
    the old reading was not about ground at all."""
    assert _deck(ON_GROUND)._ground_contact_knots == frozenset({(0, 0)})
    assert _deck(FREE_SPACE)._ground_contact_knots == frozenset()
    assert _deck(ELEVATED)._ground_contact_knots == frozenset()
    # All three ends are lone; only the standing one is servable.
    for body in (ON_GROUND, FREE_SPACE, ELEVATED):
        assert (0, 0) in _deck(body)._lone_wire_ends


def test_an_interior_knot_source_keeps_the_vertex_spelling():
    """The fix must not move the case that already worked: an interior knot is
    a real through-current path and keeps the series EMF."""
    deck = _deck(INTERIOR)
    (src,) = deck.network().sources
    assert isinstance(deck.network().ports[src.port], PortAtVertex)


def test_the_two_dialects_put_the_drive_in_one_place():
    """THE gate. EZNEC wrote one antenna to NEC-4.2 (`EX 6`, segment-addressed)
    and NEC-5 (`EX 4,tag,-1`, knot-addressed at the base). The decks are
    byte-identical apart from those cards, so once the loads are dropped the
    drive is the only thing left that can differ — and it must not."""
    n4 = "\n".join(
        ln for ln in NEC4.read_text().splitlines() if not ln.startswith("LD ")
    )
    n5 = "\n".join(
        ln for ln in NEC5.read_text().splitlines() if not ln.startswith("LD ")
    )
    with tempfile.TemporaryDirectory() as d:
        a = Path(d) / "n4.nec"
        b = Path(d) / "n5.nec"
        a.write_text(n4 + "\n")
        b.write_text(n5 + "\n")
        z4, z5 = _z(a), _z(b)
    # Not approx: the same drive on the same geometry is the same solve.
    assert z5 == pytest.approx(z4, rel=0, abs=0)


def test_the_nec5_feed_lands_where_the_nec42_writer_put_it():
    """The same claim at the port level, and the reason the solve above agrees:
    EZNEC's NEC-4.2 writer has no knot addressing, so it spells the base feed
    as `EX 6,tag,1` — segment 1 — and the NEC-5 base feed resolves to that same
    cell's centre."""
    p4 = parse_nec(NEC4.read_text(), name="n4", network=True).network()
    p5 = parse_nec(NEC5.read_text(), name="n5", network=True).network()
    at4 = sorted(p4.ports[s.port].at for s in p4.sources)
    at5 = sorted(p5.ports[s.port].at for s in p5.sources)
    assert at4 == at5 == [pytest.approx(1 / 12), pytest.approx(1 / 12)]


def test_dans_full_nec5_deck_solves():
    """Dan's deck as sent, loads and all — the thing that did not run. The
    loads stay on their knots (that is the NEC-5 reading), so this is NOT
    expected to equal the NEC-4.2 twin; only the drive was ever in question."""
    z = _z(NEC5)
    assert z.shape == (2,)
    assert np.all(np.isfinite(z))
    assert np.all(z.real > 0)
