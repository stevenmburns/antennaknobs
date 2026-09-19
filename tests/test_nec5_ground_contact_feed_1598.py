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


def test_the_base_feed_sits_at_the_contact():
    """`at` is 0 — the base itself, which is what the deck names.

    AK#1598 shipped the first cell's CENTRE here, on the argument that a
    segment gap is `E = V/Delta` over the mesh cell containing the feed point,
    so the contact and that centre are one drive. True, and true only under
    `feed_model="segment"`. The default is `"point"` on both `BSplineSolver`
    and `SinusoidalGalerkinSolver` (momwire#654), where the drive is
    `E = V*delta(s - s_f)` and where in the cell the point sits IS the answer:
    36.5032 + 2.1899j at the contact against 36.6245 + 2.8136j at the centre
    on deck 0019, 29 % in X. Corrected in AK#1605."""
    deck = _deck(ON_GROUND)
    (src,) = deck.network().sources
    assert deck.network().ports[src.port].at == 0.0


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


def test_the_two_dialects_put_the_drive_half_a_segment_apart():
    """The dialects do NOT agree here, and AK#1598 asserting that they did was
    an artifact of its own bug.

    EZNEC wrote one antenna to NEC-4.2 (`EX 6,tag,1` — segment-addressed, so
    the drive is the CENTRE of segment 1) and to NEC-5 (`EX 4,tag,-1` —
    knot-addressed, so the drive is the BASE). Those are different points, half
    a segment apart, because NEC-4.2 cannot address a knot: it is EZNEC
    rendering one model into a dialect that has to snap it.

    AK#1598 read them as bit-identical because it snapped the NEC-5 feed to the
    same cell centre NEC-4.2 lands on, so the agreement measured the snap. With
    AK#1605 the NEC-5 deck keeps the feed the deck asks for and the two
    separate — which is the honest answer, and the NEC-5 one is the faithful
    rendering."""
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
    # Same geometry, same loads (none), so the ONLY thing left is the drive
    # position — and it differs, by design.
    spread = abs(z5[0] - z4[0]) / abs(z4[0])
    assert 1e-3 < spread < 0.2, f"{z4[0]!r} vs {z5[0]!r}, rel {spread:.3e}"


def test_each_dialect_lands_where_its_own_card_says():
    """The same difference at the port level, stated as the two addresses.

    Six segments, so the centre of segment 1 is 1/12 and the base is 0. Half a
    segment (1/12) apart, which is exactly the discretisation NEC-4.2 forces
    and NEC-5 does not."""
    p4 = parse_nec(NEC4.read_text(), name="n4", network=True).network()
    p5 = parse_nec(NEC5.read_text(), name="n5", network=True).network()
    at4 = sorted(p4.ports[s.port].at for s in p4.sources)
    at5 = sorted(p5.ports[s.port].at for s in p5.sources)
    assert at4 == [pytest.approx(1 / 12), pytest.approx(1 / 12)]  # segment 1
    assert at5 == [0.0, 0.0]  # the base
    assert at4[0] - at5[0] == pytest.approx(0.5 / 6)  # half a segment


def test_dans_full_nec5_deck_solves():
    """Dan's deck as sent, loads and all — the thing that did not run. The
    loads stay on their knots (that is the NEC-5 reading), so this is NOT
    expected to equal the NEC-4.2 twin; only the drive was ever in question."""
    z = _z(NEC5)
    assert z.shape == (2,)
    assert np.all(np.isfinite(z))
    assert np.all(z.real > 0)
