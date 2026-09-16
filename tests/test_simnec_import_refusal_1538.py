"""What the .ssn importer says when a file carries no deck it can read (#1538).

A SimNEC user's hand-built `Dipole.ssn` landed in the designs folder and the
workbench said only ``no NEC-portal antenna block (a NETWORK element whose
<equ> script carries NEC2 cards)``. Every word of that was true and none of it
told the reader what to do: the file HAS a NETWORK element, and its script IS
an antenna — written in SimNEC's call-style portal language (``NECWire`` /
``NECSource`` against declared variables), which SimNEC evaluates itself and
which leaves no cards in the saved file.

antennaknobs does not evaluate SimNEC's scripting language (#1546, closed
2026-09-16: a scripted circuit is SimNEC's to evaluate). So the fix here is the
REFUSAL — it names the one spelling that is read, and the ways to get one.

The fixture below is a minimal circuit of that shape, written here rather than
copied from anyone's file.
"""

from types import MappingProxyType

import pytest

from antennaknobs.builder import AntennaBuilder
from antennaknobs.network import Wire
from antennaknobs.simnec_export import export_ssn
from antennaknobs.simnec_import import parse_ssn

# The call-style shape: units, declared variables bound from the element's
# numeric params, a ground call, and the antenna built by NECWire/NECSource.
# No NEC2 line, and no cards anywhere in the file.
_CALL_STYLE = """//a scripted dipole
P2 p2a gnd;
NECUnits feet, inches;
length;  height;  dia;
SelectOneOf {Perfect, Sommerfeld} Gtype;
NECGround(Gtype, 0.005, 13) ;
dcl SegmentsPerWavelength = 40;
$w1 = NECWire({0, -length/2, height}, {0, length/2, height}, dia);
dcl src = NECSource({gnd, p2a}, $w1, 50);"""

_NO_ANTENNA = """//just a circuit
P1 p1a gnd;
P2 p2a gnd;"""

_CARDS = """//a dipole as cards
P1 w1 gnd;
P2 w2 gnd;
NECUnits meters, meters;
NEC2
GW 1 11 0 -5 10 0 5 10 0.0005
FR 0 1 0 0 7.1 0
EX 0 1 6 0 1 0
NECEND"""


def _ssn(script: str) -> str:
    return f"""<?xml version="1.0" encoding="utf-8"?>
<SimNEC1p0>
    <SmithChartCircuit>
        <CIRCUIT>
            <element>
                <type>NETWORK</type>
                <escapeHatch/>
                <p><n>equ</n><v>{script}</v></p>
            </element>
            <element>
                <type>GENERATOR</type>
                <p><n>MHz</n><v>7.1</v></p>
                <p><n>Zo</n><v>50</v></p>
            </element>
        </CIRCUIT>
    </SmithChartCircuit>
</SimNEC1p0>
"""


def _refusal(script: str) -> str:
    with pytest.raises(ValueError) as caught:
        parse_ssn(_ssn(script), name="Dipole.ssn")
    return str(caught.value)


def test_a_scripted_antenna_is_named_as_one():
    """Not "no antenna block": the block is there and it IS the antenna."""
    said = _refusal(_CALL_STYLE)
    assert "Dipole.ssn" in said
    assert "script" in said
    # The calls that identify the dialect, so the reader can match the message
    # against what is in front of them.
    assert "NECWire" in said
    assert "NECSource" in said


def test_the_scripted_refusal_names_the_spelling_that_is_read():
    said = _refusal(_CALL_STYLE)
    assert "NEC2" in said and "NECEND" in said


def test_the_scripted_refusal_names_a_way_out():
    """Two routes exist today, and the message carries both."""
    said = _refusal(_CALL_STYLE)
    assert "export" in said  # export a design from antennaknobs to .ssn
    assert "NETWORK" in said  # or put cards in this file's NETWORK script


def test_the_scripted_refusal_promises_no_route_that_does_not_exist():
    """The deck SimNEC generates would be the faithful way in; nothing ships
    that saves it yet, so the message must not read as an instruction."""
    said = _refusal(_CALL_STYLE)
    assert "not available yet" in said


def test_a_circuit_with_no_antenna_at_all_still_says_what_is_read():
    """The generic refusal keeps its name and gains the spelling."""
    said = _refusal(_NO_ANTENNA)
    assert "no NEC-portal antenna block" in said
    assert "NEC2" in said and "NECEND" in said
    # It is NOT the scripted-antenna message: there is no script to name.
    assert "NECWire" not in said


class _Dipole(AntennaBuilder):
    default_params = MappingProxyType({"freq": 14.0, "design_freq": 14.0})

    def build_wires(self):
        return [Wire((0.0, -5.0, 10.0), (0.0, 5.0, 10.0), n_seg=11, ex=1 + 0j)]


def test_the_exporters_own_output_still_imports():
    """The refusal reads the script for a dialect, so it is one edit away from
    rejecting the files antennaknobs itself writes. It does not."""
    circuit = parse_ssn(export_ssn(_Dipole()), name="rt.ssn")
    assert circuit.deck.wires


def test_a_card_block_is_not_mistaken_for_a_script():
    circuit = parse_ssn(_ssn(_CARDS), name="cards.ssn")
    assert len(circuit.deck.wires) == 1
