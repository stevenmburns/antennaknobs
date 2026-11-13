"""AK#2295: a whole-valued symbol that a real card field also reads is a real
knob, not an integer one.

A symbol that sets a wire's segment count AND one of its coordinates
(``stub*10`` and ``-stub`` on one GW card) is a length. Before the fix it
became an integer knob because its value happened to be whole, so the slider
stepped by 1 and its step could not be changed. A symbol only integer fields
read stays an integer knob (`test_sy_knobs_1705`).
"""

from __future__ import annotations

from test_ssn_parser_2204 import DIPOLE, _ssn

from antennaknobs.nec_import import classify_sy, parse_nec
from antennaknobs.simnec_import import classify_dcl

DECK = """CM synthetic
CE
SY span=6.5
SY stub=3
SY n=15
GW 1 span*10 0 0 9 span 0 9 1.e-3
GW 2 stub*10 0 0 9 -stub 0 9 1.e-3
GW 3 n 0 0 8 span 0 8 1.e-3
GE 0
EX 0 2 1 0 1 0
GN -1
FR 0 1 0 0 14.2 0
EN
"""


def _syms(text):
    return {s.name: s for s in classify_sy(text)}


def test_a_whole_length_that_also_sets_a_segment_count_is_a_real_knob():
    syms = _syms(DECK)
    assert syms["stub"].kind == "knob"
    assert not syms["stub"].integer
    assert isinstance(syms["stub"].default, float) and syms["stub"].default == 3.0
    # Written with a decimal point: still real, the case the report named too.
    assert not _syms(DECK.replace("stub=3", "stub=3.0"))["stub"].integer


def test_a_symbol_only_integer_fields_read_stays_integer():
    n = _syms(DECK)["n"]
    assert n.kind == "knob" and n.integer and n.default == 15


def test_a_fractional_move_equals_the_hand_edit():
    moved = parse_nec(DECK, network=True, sy_overrides={"stub": 3.4})
    edited = parse_nec(DECK.replace("stub=3", "stub=3.4"), network=True)
    assert moved.wires == edited.wires
    # The coordinate moved, so the knob is not rounded to a whole number.
    assert moved.wires != parse_nec(DECK, network=True).wires


def test_the_ssn_reader_uses_the_same_rule():
    text = _ssn("dcl len = 3;").replace(DIPOLE, "GW 1,len*7,0,0,0,0,0,len,.001")
    (sym,) = [s for s in classify_dcl(text, name="t.ssn") if s.name == "len"]
    assert sym.kind == "knob" and not sym.integer
