"""EZNEC's own exports, read the way EZNEC wrote them (AK#1993).

The EZNEC sitting of 2026-10-12 (`scratch/ez-census/compare-1012/REPORT.md`,
"Outside the importer") found three places where AK's NEC reader misread
EZNEC's exports:

1. ``GN 3`` in a NEC-2 format export is NEC-4's Sommerfeld ground, never
   4nec2's MININEC one: 17 % on Basic-NEC5-Dipole;
2. a current source on a VIRTUAL segment is NEC-2's gyrator from a phantom
   wire EZNEC parks 1 λ from its virtual wire, inside the detector's 10 λ:
   Doublet+Feed read 1/Z;
3. the transformer's ``NT`` prints its ideal Y rounded, and the residual
   read as a −37.6 kΩ shunt: 1.4e-3 on 40m-15m.

The decks here are SYNTHETIC: EZNEC's card shapes and header comments, copied
from the sitting's exports, on small geometries of our own (the sitting's files
derive from third-party models and are not committed). Every gate compares
against the same antenna spelled the unambiguous way, and checks that the
branch under test is the one that ran.
"""

from __future__ import annotations

import pytest

from antennaknobs.engines import MomwireEngine
from antennaknobs.file_designs import builder_from_text
from antennaknobs.nec_import import parse_nec
from antennaknobs.network import DrivenCurrent, PortVirtual

STAMP2 = "CM ! Written by EZNEC/Pro+ v. 7.0 in NEC-2 format."
STAMP4 = "CM ! Written by EZNEC/Pro+ v. 7.0 in NEC-4.2 format."

# A 10 m dipole, 10 m up, at 14.15 MHz (λ = 21.19 m). EZNEC parks its circuit
# wires 100 λ out on the diagonal, the virtual wire 1 λ above the phantom.
DIPOLE = "GW 1,21,0.,-5.,10.,0.,5.,10.,.001"
VIRTUAL = "GW 2,5,2118.675,2118.675,2139.861,2118.781,2118.781,2139.967,.0021187"
PHANTOM = "GW 3,3,2118.675,2118.675,2118.675,2118.739,2118.739,2118.739,.0021187"


def _eznec(*lines: str) -> str:
    """A deck in EZNEC's line endings."""
    return "\r\n".join(lines) + "\r\n"


def _z(text: str, dialect: str | None = None) -> complex:
    cls = builder_from_text("eznec.nec", text, dialect=dialect)
    (z,) = MomwireEngine(cls(), ground=cls.file_ground).impedance()
    return complex(z)


def _rel(a: complex, b: complex) -> float:
    return abs(a - b) / abs(b)


# --------------------------------------------------------------------------
# 1. GN 3 in EZNEC's NEC-2 export is NEC-4's Sommerfeld ground
# --------------------------------------------------------------------------
# Basic-NEC5-Dipole's NEC-2 export: the current source as a gyrator from a
# phantom wire onto the real feed segment, and the 'Extended' real ground.
GN3_NEC2 = _eznec(
    "CM Synthetic 20m dipole",
    "CM",
    STAMP2,
    "CM",
    "CM ! Wire #2 for I srcs, shorted/open TL, and/or parallel loads.",
    "CM ! NT #1 is EZNEC current source",
    "CE",
    DIPOLE,
    "GW 2,3,2118.675,2118.675,2118.675,2118.739,2118.739,2118.739,.0021187",
    "GE 1",
    "FR 0,1,0,0,14.15",
    "GN 3,0,0,0,13.,.005",
    "EX 0,2,2,0,0.,1.414214",
    "NT 2,2,1,11,0.,0.,0.,1.,0.,0.",
    "RP 0,91,361,1001,0.,0.,1.,1.,0.",
    "EN",
)
# Its NEC-4.2 export: the same ground card, the source as NEC-4's EX 6.
GN3_NEC4 = _eznec(
    "CM Synthetic 20m dipole",
    "CM",
    STAMP4,
    "CE",
    DIPOLE,
    "GE 1",
    "FR 0,1,0,0,14.15",
    "GN 3,0,0,0,13.,.005",
    "EX 6,1,11,0,1.414214,0.",
    "RP 0,91,361,1001,0.,0.,1.,1.,0.",
    "EN",
)
# A 4nec2 deck: no stamp, so its GN 3 is 4nec2's MININEC ground.
GN3_4NEC2 = """\
CM Synthetic 20m dipole, 4nec2
CE
GW 1 21 0 -5 10 0 5 10 .001
GE 1
GN 3 0 0 0 13 .005
EX 0 1 11 0 1 0
FR 0 1 0 0 14.15 0
EN
"""


def test_eznec_gn3_reads_as_nec4_sommerfeld_and_says_why():
    deck = parse_nec(GN3_NEC2)
    assert deck.dialect == "nec4"
    assert deck.dialect_chosen is None
    assert deck.ground_spec == ("finite", 13.0, 0.005)
    assert deck.ground_method == "sommerfeld"
    # The branch that ran: the stamp's reason, not a marker or a buried wire.
    assert deck.dialect_reason.startswith("EZNEC's stamp on line 3 says NEC-2")
    note = deck.dialect_note()
    assert note.startswith("Read as NEC-4")
    assert "EZNEC writes GN 3 only for NEC-4's GN 3" in note
    assert "MININEC ground; read the deck" not in note


def test_eznec_gn3_solves_as_its_nec4_export():
    """The NEC-2 export lands on the NEC-4.2 export, and the same deck with
    its stamp removed (the old reading, MININEC) does not."""
    ref = _z(GN3_NEC4)
    assert parse_nec(GN3_NEC4, network=True).dialect_reason.startswith("EZNEC's stamp")
    assert _rel(_z(GN3_NEC2), ref) < 1e-9
    unstamped = GN3_NEC2.replace(STAMP2, "CM")
    old = parse_nec(unstamped)
    assert old.ground_spec == ("mininec", 13.0, 0.005)
    assert _rel(_z(unstamped), ref) > 1e-2


def test_a_4nec2_gn3_keeps_the_mininec_ground():
    deck = parse_nec(GN3_4NEC2)
    assert deck.dialect == "nec2"
    assert deck.ground_spec == ("mininec", 13.0, 0.005)
    assert deck.dialect_reason == "no NEC-4 or NEC-5 marker found"
    assert "read as 4nec2's MININEC ground" in deck.dialect_note()


def test_prose_naming_eznec_is_no_stamp():
    text = GN3_4NEC2.replace("CE\n", "CM converted from an EZNEC NEC-2 export\nCE\n")
    assert parse_nec(text).ground_spec == ("mininec", 13.0, 0.005)


def test_a_keyed_declaration_still_wins():
    text = GN3_NEC2.replace("CE\r\n", "CM engine=nec2\r\nCE\r\n")
    deck = parse_nec(text)
    assert deck.dialect == "nec2"
    assert deck.ground_spec == ("mininec", 13.0, 0.005)
    assert deck.dialect_reason == "a CM engine=nec2 card on line 7"


def test_a_chosen_dialect_still_wins_and_the_note_says_what_detection_reads():
    deck = parse_nec(GN3_NEC2, dialect="nec2")
    assert deck.dialect == "nec2"
    assert deck.ground_spec == ("mininec", 13.0, 0.005)
    assert deck.dialect_detected == "nec4"
    assert deck.dialect_detected_reason.startswith("EZNEC's stamp on line 3")


def test_an_eznec_nec2_export_on_another_ground_is_unchanged():
    text = GN3_NEC2.replace("GN 3,0,0,0,13.,.005", "GN 2,0,0,0,13.,.005")
    deck = parse_nec(text)
    assert deck.dialect == "nec2"
    assert deck.dialect_reason == "no NEC-4 or NEC-5 marker found"


# --------------------------------------------------------------------------
# 2. a current source on a virtual segment: the gyrator's phantom wire
# --------------------------------------------------------------------------
LEGEND = (
    "CM ! *Wire #2 for virtual segments.",
    "CM ! Wire #3 for I srcs, shorted/open TL, and/or parallel loads.",
)
# Doublet+Feed's NEC-2 export: the source on virtual segment 2/2 through the
# gyrator from phantom 3/2, and a line from there to the feed.
VIRTUAL_I_NEC2 = _eznec(
    "CM Synthetic doublet with feed",
    "CM",
    STAMP2,
    "CM",
    *LEGEND,
    "CM ! NT #1 is EZNEC current source",
    "CE",
    DIPOLE,
    VIRTUAL,
    PHANTOM,
    "GE 0",
    "FR 0,1,0,0,14.15",
    "GN -1",
    "EX 0,3,2,0,0.,1.414214",
    "NT 3,2,2,2,0.,0.,0.,1.,0.,0.",
    "TL 2,2,1,11,300.,3.5,0.,0.,0.,0.",
    "RP 0,181,1,1000,90.,0.,-1.,0.,0.",
    "EN",
)
# The same antenna spelled directly: NEC-4's EX 6 on virtual segment 2/2.
VIRTUAL_I_NEC4 = _eznec(
    "CM Synthetic doublet with feed",
    "CM",
    STAMP4,
    "CM",
    "CM ! *Wire #2 for virtual segments.",
    "CE",
    DIPOLE,
    VIRTUAL,
    "GE 0",
    "FR 0,1,0,0,14.15",
    "GN -1",
    "EX 6,2,2,0,1.414214,0.",
    "TL 2,2,1,11,300.,3.5,0.,0.,0.,0.",
    "RP 0,181,1,1000,90.,0.,-1.,0.,0.",
    "EN",
)


def _gyrators(text: str) -> dict:
    return parse_nec(text, network=True)._network_parts()[3]


def test_the_phantom_and_the_virtual_wire_both_virtualize():
    deck = parse_nec(VIRTUAL_I_NEC2, network=True)
    assert deck.virtual_segment_wires == frozenset({1, 2})
    ports, _branches, sources, gyrators = deck._network_parts()
    # The branch that ran: one gyrator collapsed, from the phantom's node onto
    # a VIRTUAL node, which now carries the forced current.
    ((phantom, target),) = gyrators.items()
    assert phantom not in ports
    assert isinstance(ports[target], PortVirtual)
    (src,) = sources
    assert isinstance(src, DrivenCurrent)
    assert src.port == target
    assert src.current == pytest.approx(1.414214)


def test_the_gyrator_spelling_solves_as_ex6_on_the_virtual_segment():
    ref = _z(VIRTUAL_I_NEC4)
    assert parse_nec(VIRTUAL_I_NEC4, network=True).virtual_segment_wires == {1}
    assert _rel(_z(VIRTUAL_I_NEC2), ref) < 1e-9
    # Before: without the legend neither wire clears the other, both stay
    # real, and the source reads the gyrator's inverted impedance.
    bare = VIRTUAL_I_NEC2
    for line in LEGEND:
        bare = bare.replace(line + "\r\n", "")
    assert parse_nec(bare, network=True).virtual_segment_wires == frozenset()
    assert _gyrators(bare) == {}
    assert _rel(_z(bare), ref) > 0.5


def test_the_legend_needs_the_stamp():
    text = VIRTUAL_I_NEC2.replace(STAMP2 + "\r\n", "")
    assert parse_nec(text, network=True).virtual_segment_wires == frozenset()


def test_a_real_wire_one_wavelength_away_stays_real():
    """The exemption is between the wires the legend names, never from the
    antenna: a real element 1 λ from the virtual wire still keeps it real."""
    near = "GW 4,11,2118.675,2116.,2161.05,2118.675,2121.,2161.05,.001"
    text = VIRTUAL_I_NEC2.replace("GE 0", near + "\r\nGE 0")
    deck = parse_nec(text, network=True)
    assert 1 not in deck.virtual_segment_wires


def test_a_legend_naming_a_missing_wire_names_nothing():
    text = VIRTUAL_I_NEC2.replace("*Wire #2 for", "*Wire #7 for")
    assert parse_nec(text, network=True).virtual_segment_wires == frozenset()
