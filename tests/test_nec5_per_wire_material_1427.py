"""Issue #1427: a design that carries its wire material PER WIRE (a deck loaded
from a file does) must reach the text-deck engines with that material — the
NEC-5 engine and the NEC-2 export were writing LD 5 / LD 2 only from the
design-level `build_wire_material()`, so an imported deck's copper loss
vanished on the NEC-5 tab (AC6LA's Example 2: 68.6-j17.8 against 70.5-j16.2
with the load)."""

from types import MappingProxyType

import pytest

from antennaknobs import AntennaBuilder
from antennaknobs.engines.nec5 import NEC5Engine, probe_nec5
from antennaknobs.file_designs import builder_from_file
from antennaknobs.network import Wire, WireSpec

EXAMPLE2 = """CM Example 2 :	Loaded dipole in free space
CE
SY len=.4836
GW 1 9 0 -len/2 0 0 len/2 0 .0001
GE 0
LD 5 1 0 0 5.8001E7
EX 0 1 5 0 1 0
FR 0 1 0 0 300 0
EN
"""


class TwoWires(AntennaBuilder):
    """Two wires with their OWN specs, different conductivities."""

    default_params = MappingProxyType({"freq": 300.0})

    def build_wires(self):
        return [
            Wire(
                (0.0, -0.24, 0.0),
                (0.0, 0.0, 0.0),
                6,
                spec=WireSpec(radius=1e-4, conductivity=5.8e7),
                ex=1.0,
            ),
            Wire(
                (0.0, 0.0, 0.0),
                (0.0, 0.24, 0.0),
                6,
                spec=WireSpec(radius=2e-4, conductivity=3.5e7),
            ),
        ]


class DesignLevel(AntennaBuilder):
    """No per-wire spec; the design-level material — the pre-#1427 shape."""

    default_params = MappingProxyType({"freq": 300.0})

    def build_wires(self):
        return [((0.0, -0.24, 0.0), (0.0, 0.24, 0.0), 10, 1.0)]

    def build_wire_material(self):
        return WireSpec(radius=1e-4, conductivity=5.8e7)


def _ld_lines(deck):
    return [ln for ln in deck.splitlines() if ln.startswith("LD ")]


def test_per_wire_specs_become_per_tag_ld5_cards():
    deck = NEC5Engine(TwoWires(), ground=None).deck([300.0])
    assert _ld_lines(deck) == [
        "LD 5 1 0 0 5.800000E+07 0. 0.",
        "LD 5 2 0 0 3.500000E+07 0. 0.",
    ]
    # And the radii stayed per wire, as before.
    gws = [ln for ln in deck.splitlines() if ln.startswith("GW ")]
    assert gws[0].endswith("1.000000E-04") and gws[1].endswith("2.000000E-04")


def test_design_level_material_is_the_global_card_as_before():
    deck = NEC5Engine(DesignLevel(), ground=None).deck([300.0])
    assert _ld_lines(deck) == ["LD 5 0 0 0 5.800000E+07 0. 0."]


def test_imported_deck_keeps_its_copper(tmp_path):
    path = tmp_path / "Example2.nec"
    path.write_text(EXAMPLE2)
    b = builder_from_file(str(path))()
    deck = NEC5Engine(b, ground=None).deck([300.0])
    assert "LD 5 1 0 0 5.800100E+07 0. 0." in deck
    assert "LD 5 0 0 0" not in deck


@pytest.mark.skipif(probe_nec5() is None, reason="no NEC-5 binary (NEC5_EXE)")
def test_imported_deck_solves_with_the_load(tmp_path):
    """The number AC6LA should now read on the NEC-5 tab: the 10-segment
    knot-source deck WITH the copper load. Measured on the licensed nec5cl
    2026-09-12 (variant D of #1427); the remaining gap to his 71.86-j19.98 is
    the even-parity / knot-source convention, not the load."""
    path = tmp_path / "Example2.nec"
    path.write_text(EXAMPLE2)
    b = builder_from_file(str(path))()
    z = NEC5Engine(b, ground=None).impedance()[0]
    assert z == pytest.approx(70.509 - 16.164j, abs=0.01)


def test_nec2_export_uses_the_same_per_wire_rule(tmp_path):
    from antennaknobs.nec_export import export_nec

    path = tmp_path / "Example2.nec"
    path.write_text(EXAMPLE2)
    b = builder_from_file(str(path))()
    deck = (
        export_nec(b, ground=None)
        if "ground" in export_nec.__code__.co_varnames
        else export_nec(b)
    )
    lds = [" ".join(ln.split()) for ln in deck.splitlines() if ln.startswith("LD ")]
    assert lds == ["LD 5 1 0 0 5.800100E+07 0. 0."]
    # The NEC-2 deck keeps the deck's own 9 segments and centre-segment source
    # (NEC-2's convention), so this IS the author's deck with its copper.
    assert any(" ".join(ln.split()).startswith("GW 1 9 ") for ln in deck.splitlines())
