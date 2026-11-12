"""AK#2290: a ``.ssn`` script that clamps a slider in place,
``P = Max(Min(P, 90), 10);``, reads the slider as the knob's input.

SimNEC runs the clamp on the slider's value before the statements after it
read ``P``, so the slider stays an input and what the cards see is the
clamped value. What is pinned here:

- the clamp opens, ``P`` is a ``par_`` knob, and a value past either bound
  builds as that bound;
- the clamp bounds the knob's default optimize window, as a declared range
  does (AK#2283);
- negative controls: an assignment of ``P`` that reads another name as well
  as itself is refused as an output, by the message it had; ``P = Q + 1``
  stays a derived parameter, as AK#1734 made it; and a constant that reads
  ``P`` above its clamp is refused.

Every name and value is invented.
"""

from __future__ import annotations

import re

import pytest
from test_ssn_numericparam_knobs_1716 import _one_wire

from antennaknobs.band_opt import free_for
from antennaknobs.file_designs import builder_from_text
from antennaknobs.simnec_import import classify_dcl, parse_ssn

OUTPUT = (
    r"reads 'P', a parameter of the element that the script assigns "
    r"\('{stmt}'\), so an output SimNEC computes, not an input"
)
# The wire's top end is a derived constant of the slider.
TOP = "dcl Top = 10 - (10 * P / 100);"


def _clamped(clamp: str = "P = Max(Min(P, 90), 10);", saved: str = "50", pre=""):
    return _one_wire(f"{pre}{clamp}\n{TOP}", "Top", {"P": saved})


def _top(cls, p: float) -> float:
    return cls(dict(cls.default_params, par_P=p)).build_wires()[0].p1[2]


@pytest.mark.parametrize(
    "clamp",
    [
        "P = Max(Min(P, 90), 10);",
        "P = Min(Max(P, 10), 90);",
        "prm P = Max(Min(P, 90), 10);",
        "P = Max(10, Min(90, P));",
    ],
)
def test_a_clamp_in_place_is_a_knob_on_its_input(clamp):
    text = _clamped(clamp)
    syms = {s.name: s for s in classify_dcl(text)}
    assert (syms["P"].kind, syms["P"].param, syms["P"].default) == (
        "knob",
        "par_P",
        50.0,
    )
    cls = builder_from_text("clamp.ssn", text)
    assert cls.default_params["par_P"] == 50.0
    assert _top(cls, 50.0) == 5.0
    # Past either bound, the build is the bound's.
    assert _top(cls, 95.0) == _top(cls, 90.0) == 1.0
    assert _top(cls, 5.0) == _top(cls, 10.0) == 9.0


def test_a_bare_declaration_above_the_clamp_changes_nothing():
    plain = builder_from_text("a.ssn", _clamped())
    bare = builder_from_text("b.ssn", _clamped(pre="P;  // Tap point\n"))
    for p in (5.0, 50.0, 95.0):
        assert _top(bare, p) == _top(plain, p)
    assert bare.default_params["ui_params"]["par_P"]["description"] == "Tap point"


def test_the_saved_value_is_clamped_on_import():
    # SimNEC's slider can sit past the clamp; the file as imported is the
    # clamped one.
    deck = parse_ssn(_clamped(saved="97")).deck
    assert deck.wires[0].p2[2] == 1.0


def test_the_clamp_bounds_the_default_optimize_window():
    # Saved near the top, the +/-20 % window would reach past 90.
    cls = builder_from_text("clamp.ssn", _clamped(saved="85"))
    meta = cls.default_params["ui_params"]["par_P"]
    assert (meta["min"], meta["max"]) == (68.0, 90.0)
    ((win,),) = [free_for(cls(), ["par_P"])]
    assert 10.0 <= win["min"] < win["max"] <= 90.0


def test_a_one_sided_clamp_bounds_one_side():
    cls = builder_from_text("clamp.ssn", _clamped("P = Max(P, 10);", saved="11"))
    meta = cls.default_params["ui_params"]["par_P"]
    assert meta["min"] == 10.0 and meta["max"] == pytest.approx(13.2)
    assert _top(cls, 2.0) == 9.0


@pytest.mark.parametrize(
    "clamp",
    ["P = Max(Min(P, Q), 10);", "P = P + Q;"],
)
def test_a_self_assignment_reading_another_name_is_still_an_output(clamp):
    text = _one_wire(f"{clamp}\n{TOP}", "Top", {"P": "50", "Q": "80"})
    with pytest.raises(
        ValueError, match=OUTPUT.format(stmt=re.escape(clamp.rstrip(";")))
    ):
        parse_ssn(text)


def test_an_assignment_from_another_parameter_stays_derived():
    # AK#1734: `P = Q + 1` is the script computing P, a derived parameter;
    # it is not a clamp, and the knob is Q.
    text = _one_wire(f"P = Q + 1;\n{TOP}", "Top", {"P": "50", "Q": "3"})
    syms = {s.name: s for s in classify_dcl(text)}
    assert (syms["P"].kind, syms["Q"].kind) == ("derived", "knob")


def test_a_constant_reading_the_slider_above_its_clamp_is_refused():
    text = _one_wire(f"{TOP}\nP = Max(Min(P, 90), 10);", "Top", {"P": "50"})
    with pytest.raises(ValueError, match=r"reads 'P' before the script clamps it"):
        parse_ssn(text)


def test_max_and_min_take_two_arguments():
    text = _one_wire("dcl Top = Max(3);", "Top", {})
    with pytest.raises(ValueError, match=r"Max\(\.\.\.\) takes two arguments"):
        parse_ssn(text)
