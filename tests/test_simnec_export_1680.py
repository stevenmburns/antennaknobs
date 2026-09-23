"""SimNEC export writes the wire conductivity and each wire's mesh (AK#1680).

Before this, ``NECOptions.mhosPerMeter`` was 0 on every export and the deck's
``LD 5`` card was dropped, so every design went to SimNEC as perfect wire, and
AC6LA's own LC1 file (copper wire) round-tripped as conductivity None, moving
the tuner's values (QRZ 1003328 #140-#144). SimNEC also re-meshes a ``GW``
card, which is advisory to it, so the export now names each wire's count with
``$GW_<tag>.JamSegments(N)``, the spelling SimNEC's own files use.

SimNEC's NEC2 reader takes one conductivity for the whole block (it ignores
LD cards), so a design whose wires differ is refused by name.
"""

from __future__ import annotations

import re

import pytest

from antennaknobs.file_designs import builder_from_file
from antennaknobs.simnec_export import (
    SsnUnsupported,
    _conductivity_token,
    build_nec_portal_script,
    export_ssn,
)
from antennaknobs.simnec_import import _RESISTIVITY_OHM_M, parse_ssn
from antennaknobs.wire_catalog import WireSpec, as_wire

COPPER = 1.0 / _RESISTIVITY_OHM_M["copper"]

# AC6LA's snBydipole1-LC1.ssn, the parts this issue is about: his NETWORK
# script verbatim (EZNEC-exported dipole, copper wire, GW 11 jammed to 12) and
# the XMATCH low-pass L tuner in auto mode.
_LC1_EQU = """//per EZNEC
P1 w1 gnd;
P2 w2 gnd;

NECUnits feet, inches;
NECOptions.mhosPerMeter = Conductivities.copper;
NECOptions.fieldStep = 2;
SommerfeldGround(0.0303, 20);

NEC2
CM Back yard dipole
CM
CE
GW 1,11,0.,0.,9.144,0.,10.18946,9.144,.0010262
GE 1
FR 0,1,0,0,14.
GN 2,0,0,0,20.,.0303
EX 0,1,6,0,0.,1.414214
RP 0,181,1,1000,90.,0.,-1.,0.,0.
EN
NECEND
$GW_1.JamSegments(12);"""

_LC1_SSN = f"""<?xml version="1.0" encoding="utf-8"?>
<SimNEC1p0>
    <SmithChartCircuit>
        <CIRCUIT>
            <element>
                <type>LOAD</type>
                <p><n>ohms</n><v>1G</v></p>
            </element>
            <element>
                <type>NETWORK</type>
                <escapeHatch/>
                <p><n>equ</n><v>{_LC1_EQU}</v></p>
            </element>
            <element>
                <type>XMATCH</type>
                <sweeperLabel>LC1</sweeperLabel>
                <p><n>mode</n><v>auto</v></p>
                <p><n>pass</n><v>low</v></p>
                <p><n>R</n><v>0</v></p>
                <p><n>X</n><v>0</v></p>
                <p><n>Qc</n><v>2K</v></p>
                <p><n>Ql</n><v>200</v></p>
                <p><n>MHz</n><v>14.175</v></p>
            </element>
            <element>
                <type>GENERATOR</type>
                <p><n>MHz</n><v>14.175</v></p>
                <p><n>Zo</n><v>50</v></p>
            </element>
        </CIRCUIT>
    </SmithChartCircuit>
</SimNEC1p0>
"""


def _equ(ssn: str) -> str:
    return re.search(r"<n>equ</n><v>(.*?)</v>", ssn, re.S).group(1)


def _gw_counts(script: str) -> dict[int, int]:
    return {
        int(t): int(n) for t, n in re.findall(r"(?m)^GW[ ,]+(\d+)[ ,]+(\d+)", script)
    }


def _jammed(script: str) -> dict[int, int]:
    return {
        int(t): int(n)
        for t, n in re.findall(r"\$GW_(\d+)\.JamSegments\((\d+)\);", script)
    }


def _lc1(tmp_path):
    path = tmp_path / "lc1.ssn"
    path.write_text(_LC1_SSN)
    return builder_from_file(str(path))


def _rebuilt(tmp_path, ssn: str):
    path = tmp_path / "rt.ssn"
    path.write_text(ssn)
    return builder_from_file(str(path))


def _n_segs(builder) -> list[int]:
    return [as_wire(t).n_seg for t in builder.build_wires()]


# --- the round trip of AC6LA's file ------------------------------------------


def test_lc1_writes_copper_and_one_jamsegments_per_wire(tmp_path):
    cls = _lc1(tmp_path)
    script = _equ(export_ssn(cls(), ground=cls.file_ground))
    # Copper by SimNEC's own name, as AC6LA's file spells it.
    assert "NECOptions.mhosPerMeter = Conductivities.copper;" in script
    # One JamSegments per GW card, carrying that card's count (after NECEND,
    # where SimNEC names the block's wires).
    assert _jammed(script) == _gw_counts(script) != {}
    assert script.index("NECEND") < script.index("$GW_1.JamSegments")


def test_lc1_round_trips_conductivity_and_segment_counts(tmp_path):
    cls = _lc1(tmp_path)
    ssn = export_ssn(cls(), ground=cls.file_ground)
    # The circuit reads back copper, not None (the reported defect).
    assert parse_ssn(ssn, network=True).conductivity == pytest.approx(COPPER, rel=1e-12)
    # The re-imported design carries it to its wires, and a second export
    # says copper again: the value reached the design, not only the parse.
    rt = _rebuilt(tmp_path, ssn)
    sigmas = [as_wire(t).spec.conductivity for t in rt().build_wires()]
    assert sigmas == pytest.approx([COPPER] * len(sigmas))
    again = _equ(export_ssn(rt(), ground=rt.file_ground))
    assert "NECOptions.mhosPerMeter = Conductivities.copper;" in again
    # Per-wire segment counts: the re-imported design meshes each wire as the
    # exported one did. The importer reads the GW card's count, which the
    # exporter writes equal to the JamSegments beside it; whether the importer
    # APPLIES a JamSegments that differs from its GW card is AK#1679's, and
    # this writer never emits one that differs.
    assert _n_segs(rt()) == _n_segs(cls())
    assert _jammed(again) == _jammed(_equ(ssn))


def test_lc1_keeps_its_xmatch(tmp_path):
    """The tuner (AK#1662) is still SimNEC's XMATCH element."""
    cls = _lc1(tmp_path)
    ssn = export_ssn(cls(), ground=cls.file_ground)
    assert re.findall(r"<type>(\w+)</type>", ssn) == [
        "LOAD",
        "NETWORK",
        "XMATCH",
        "GENERATOR",
    ]


# --- catalog designs ----------------------------------------------------------


def test_a_copper_catalog_design_writes_its_conductivity():
    """pota_invvee's stock wire is 22 AWG PVC-jacketed copper, 5.8e7 S/m
    (the catalog's figure, not SimNEC's 1/1.74e-8), so it is written as the
    number, exactly."""
    from antennaknobs.designs.dipoles.pota_invvee import Builder

    b = Builder()
    assert b.build_wire_material().conductivity == 5.8e7
    script = _equ(export_ssn(b))
    assert "NECOptions.mhosPerMeter = 58000000.0;" in script
    assert _jammed(script) == _gw_counts(script) != {}
    assert parse_ssn(export_ssn(b)).conductivity == 5.8e7


def _lossy_invvee(conductivity):
    from antennaknobs.designs.dipoles.invvee import Builder as InvVee

    class Lossy(InvVee):
        def build_wire_material(self):
            return WireSpec(radius=5e-4, conductivity=conductivity)

    return Lossy()


def test_a_conductivity_on_simnecs_table_is_written_by_name():
    script = _equ(export_ssn(_lossy_invvee(COPPER)))
    assert "NECOptions.mhosPerMeter = Conductivities.copper;" in script


@pytest.mark.parametrize("name, rho", sorted(_RESISTIVITY_OHM_M.items()))
def test_every_name_written_is_the_importers_own(name, rho):
    assert _conductivity_token(1.0 / rho) == f"Conductivities.{name}"


def test_an_off_table_conductivity_round_trips_exactly():
    b = _lossy_invvee(5.7471e7)  # EZNEC's copper figure, not SimNEC's
    ssn = export_ssn(b)
    assert "NECOptions.mhosPerMeter = 57471000.0;" in _equ(ssn)
    assert parse_ssn(ssn).conductivity == 5.7471e7
    assert _conductivity_token(1.25e-3) == "0.00125"
    assert "e+" not in _conductivity_token(1.0e22)


def test_perfect_wire_is_still_zero():
    from antennaknobs.designs.dipoles.invvee import Builder as InvVee

    assert "NECOptions.mhosPerMeter = 0;" in _equ(export_ssn(InvVee()))


def test_seg_per_wl_hands_the_mesh_to_simnec():
    """That knob exists to compare SimNEC's own auto-mesh, so it writes no
    JamSegments."""
    b = _lossy_invvee(COPPER)
    script = build_nec_portal_script(b, freq_mhz=b.freq, seg_per_wl=40)
    assert "NECOptions.segmentsPerWavelength = 40;" in script
    assert "JamSegments" not in script


def test_wires_whose_conductivities_differ_are_refused_by_name():
    from antennaknobs.designs.dipoles.invvee import Builder as InvVee

    class Mixed(InvVee):
        def build_wires(self):
            out = [as_wire(t) for t in super().build_wires()]
            spec = WireSpec(radius=5e-4, conductivity=COPPER)
            out[0] = out[0]._replace(spec=spec)
            return out

    with pytest.raises(
        SsnUnsupported, match=r"conductivities differ \(.* S/m on wire 1; perfect"
    ):
        export_ssn(Mixed())
