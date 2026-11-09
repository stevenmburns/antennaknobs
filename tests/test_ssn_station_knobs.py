"""A full ``.ssn`` opened as a design offers its station chain as knobs.

A line's length, an L, a C and a transformer's ratio in the chain between
the antenna block and the GENERATOR become design knobs (``stn_<label>_
<param>``) beside the file's dcl knobs. The oracle for every knob value is
the same ``.ssn`` saved with that value: turning the knob must build exactly
the design that file builds. Every fixture is synthetic.
"""

from __future__ import annotations

import pytest
from test_simnec_import import _SCRIPT_M, _el, _ssn

from antennaknobs.cli import make_engine_factory
from antennaknobs.file_designs import builder_from_text

_ENGINE = make_engine_factory("momwire:razor-2p", None)


def _line(ft="100", label="T1"):
    return _el(
        "SERIES_TLINE",
        {"Zo": 450, "VFnom": 0.91, "ft": ft, "k0": 0, "k1": 0.02, "k2": 0.0001},
        label=label,
    )


def _text(ft="100", c="500p", h="1.2u", c_label="C1", unlabelled=False):
    # Antenna side first, as SimNEC saves a station.
    chain = (
        _line(ft)
        + _el("SHUNT_CAP", {"F": c, "Q": 0}, label=c_label)
        + _el("SERIES_IND", {"H": h, "Q": 200, "@MHz": 7.1}, label="L1")
    )
    if unlabelled:
        chain += _el("SERIES_CAP", {"F": "1n", "Q": 0})
    return _ssn(_SCRIPT_M, extra_elements=chain)


def _design(**kw):
    return builder_from_text("station.ssn", _text(**kw))


def _z(cls, **params):
    return complex(_ENGINE(cls({**cls.default_params, **params})).impedance()[0])


def test_the_chain_values_are_knobs_in_units_a_knob_reads_well_in():
    B = _design()
    p, ui = B.default_params, B.default_params["ui_params"]
    assert (p["stn_T1_ft"], p["stn_C1_F"], p["stn_L1_H"]) == (100.0, 500.0, 1.2)
    assert ui["stn_T1_ft"]["unit"] == "ft" and ui["stn_T1_ft"]["label"] == "T1 length"
    assert ui["stn_C1_F"]["unit"] == "pF" and ui["stn_L1_H"]["unit"] == "µH"
    # A cable's model and a component's Q are not knobs.
    assert not any(k.startswith("stn_T1_") and k != "stn_T1_ft" for k in p)
    assert "stn_C1_Q" not in p and "stn_L1_Q" not in p
    assert "L1, C1, T1 length are knobs" in ui["notes"]


def test_at_its_defaults_the_design_is_the_file():
    with_knobs = _z(_design())
    assert with_knobs == _z(_design(), stn_T1_ft=100.0, stn_C1_F=500.0)


@pytest.mark.parametrize(
    ("knob", "saved"),
    [
        ({"stn_T1_ft": 60.0}, {"ft": "60"}),
        ({"stn_C1_F": 250.0}, {"c": "250p"}),
        ({"stn_L1_H": 2.5}, {"h": "2.5u"}),
        ({"stn_T1_ft": 33.0, "stn_C1_F": 120.0}, {"ft": "33", "c": "120p"}),
    ],
)
def test_a_knob_value_is_the_file_saved_with_it(knob, saved):
    got = _z(_design(), **knob)
    want = _z(_design(**saved))
    assert got == pytest.approx(want, rel=1e-12)
    assert abs(got - _z(_design())) > 1e-3 * abs(want)


def test_an_element_without_its_own_label_has_no_knob():
    p = _design(unlabelled=True).default_params
    assert [k for k in p if k.startswith("stn_")] == [
        "stn_L1_H",
        "stn_C1_F",
        "stn_T1_ft",
    ]
    shared = _design(c_label="T1").default_params  # the cap shares T1's label
    assert [k for k in shared if k.startswith("stn_")] == ["stn_L1_H"]
