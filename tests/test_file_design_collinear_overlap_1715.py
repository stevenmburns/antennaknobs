"""AK#1715: a file design's knob may not stack one wire on another.

The topology freeze (AK#1705, AK#1714) compared end contacts, the ground
plane and where feeds, loads and lines land. Two wires moved onto one line
and overlapping meet at no end, so none of those changed and the value was
accepted: on AC6LA's 3-el 20 m Yagi ``dcl_ddis = 0`` puts the director on the
driven element, and the solve that followed was of two conductors in one
place. It is refused by name now, for ``.ssn`` constants and ``.nec`` SY
symbols alike, and the same sentence reaches the web error panel.
"""

from __future__ import annotations

import importlib
from collections import namedtuple
from pathlib import Path

import pytest

from antennaknobs.file_designs import _overlaps, builder_from_file

YAGI = Path(__file__).parent / "fixtures" / "ssn_dcl_knobs_1714" / "3el-20m-yagi-sy.ssn"

REFUSAL = (
    "3el-20m-yagi-sy: dcl_ddis = 0 (the file has 2.7432) is refused: "
    "wire 1 (tag 1) would lie on top of wire 2 (tag 2): the two run along the "
    "same line and share 9.664 m of it; the file's topology is frozen at its "
    "own values"
)

_W = namedtuple("_W", "p1 p2")


def _pairs(*wires):
    return _overlaps([_W(*w) for w in wires])


def test_the_acceptance_case_is_refused_by_name():
    """The triage's case, the whole sentence: which knob, the value and the
    file's own, which two wires, and how much of the line they share."""
    cls = builder_from_file(str(YAGI))
    with pytest.raises(ValueError) as exc:
        cls(dict(cls.default_params, dcl_ddis=0.0)).build_wires()
    assert str(exc.value) == REFUSAL


def test_the_design_keeps_working_either_side_of_the_refused_value():
    cls = builder_from_file(str(YAGI))
    assert len(cls().build_wires()) == 3
    assert len(cls(dict(cls.default_params, dcl_ddis=0.5)).build_wires()) == 3
    # The director moved behind the driven element onto the reflector's line.
    with pytest.raises(
        ValueError, match=r"wire 1 \(tag 1\) would lie on top of wire 3"
    ):
        cls(dict(cls.default_params, dcl_ddis=-1.8228)).build_wires()


def test_the_web_error_panel_gets_the_same_sentence():
    importlib.import_module("antennaknobs.web.examples")
    from antennaknobs.web import adapter, user_designs

    ex = adapter._make_example(
        "user.yagi", builder_from_file(str(YAGI)), defer_hints=True
    )
    with pytest.raises(ValueError) as exc:
        ex.momwire_solve(
            {"geometry": "user.yagi", "measurement_freq_mhz": 14.2, "dcl_ddis": 0.0}
        )
    assert user_designs.format_solve_error(exc.value) == f"ValueError: {REFUSAL}"


NEC_SY = """CM two parallel dipoles, the second a knob's distance from the first
CE
SY len=10.4 'Dipole length
SY gap=2 'Spacing
SY half=len/2
GW 1 21 -half 0 10 half 0 10 1e-3
GW 2 11 -2 gap 10 2 gap 10 1e-3
GE 0
EX 0 1 11 0 1 0
FR 0 1 0 0 14.1 0
EN
"""


def test_a_nec_sy_knob_is_refused_the_same_way(tmp_path):
    path = tmp_path / "pair.nec"
    path.write_text(NEC_SY)
    cls = builder_from_file(str(path))
    assert len(cls().build_wires()) == 2
    with pytest.raises(ValueError) as exc:
        cls(dict(cls.default_params, sy_gap=0.0)).build_wires()
    assert str(exc.value) == (
        "pair: sy_gap = 0 (the deck has 2) is refused: wire 1 (tag 1) would lie "
        "on top of wire 2 (tag 2): the two run along the same line and share "
        "4 m of it; the deck's topology is frozen at its own values"
    )


def test_a_file_that_stacks_two_wires_itself_is_not_refused(tmp_path):
    """The freeze is against the file's own values. A deck that overlaps two
    wires as written still opens, and it is the knob that pulls them apart
    that is named."""
    path = tmp_path / "stacked.nec"
    path.write_text(NEC_SY.replace("SY gap=2", "SY gap=0"))
    cls = builder_from_file(str(path))
    assert len(cls().build_wires()) == 2
    with pytest.raises(
        ValueError,
        match=r"sy_gap = 1 .*wire 1 \(tag 1\) would no longer lie on top of "
        r"wire 2 \(tag 2\), as it does in the file",
    ):
        cls(dict(cls.default_params, sy_gap=1.0)).build_wires()


def test_what_counts_as_lying_on_top():
    a = ((0.0, 0.0, 5.0), (10.0, 0.0, 5.0))
    # One inside the other, and a partial overlap, with the length shared.
    assert _pairs(a, ((2.0, 0.0, 5.0), (6.0, 0.0, 5.0))) == {(0, 1): 4.0}
    assert _pairs(a, ((8.0, 0.0, 5.0), (15.0, 0.0, 5.0))) == {(0, 1): 2.0}
    # Drawn in the opposite direction, and listed shorter wire first.
    assert _pairs(a, ((6.0, 0.0, 5.0), (2.0, 0.0, 5.0))) == {(0, 1): 4.0}
    assert _pairs(((2.0, 0.0, 5.0), (6.0, 0.0, 5.0)), a) == {(0, 1): 4.0}
    # End to end on one line is a contact, not an overlap.
    assert _pairs(a, ((10.0, 0.0, 5.0), (15.0, 0.0, 5.0))) == {}
    # Parallel beside it, crossing it, and on the same line further along.
    assert _pairs(a, ((2.0, 0.1, 5.0), (6.0, 0.1, 5.0))) == {}
    assert _pairs(a, ((5.0, -1.0, 5.0), (5.0, 1.0, 5.0))) == {}
    assert _pairs(a, ((11.0, 0.0, 5.0), (15.0, 0.0, 5.0))) == {}
    # A zero-length wire is the zero-length refusal's, not this one's.
    assert _pairs(a, ((3.0, 0.0, 5.0), (3.0, 0.0, 5.0))) == {}
