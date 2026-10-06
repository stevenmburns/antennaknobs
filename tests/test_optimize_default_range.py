"""The default Optimize range is one rule in both front ends (AK 0.97.2).

``optimize`` on the command line searches a knob's ``ui_params`` min/max
when the design declares both ends, else +/-20 % of its value
(``band_opt.free_for``). The workbench seeds its Optimize range from the
knob schema (frontend ``lib/params.ts`` ``defaultKnobOpt``), whose min/max
are the slider's: either the declared range, or the adapter's own +/-50 %
window. ``auto_range`` is what tells the two apart, and these gates pin that
it says "declared" exactly where the command line finds a ui_params range.
"""

from __future__ import annotations

import importlib

import pytest
from fastapi.testclient import TestClient

from antennaknobs import band_opt


DESIGNS = {
    "dipoles.invvee": "antennaknobs.designs.dipoles.invvee",
    "multiband.twoband_fan_dipole": "antennaknobs.designs.multiband.twoband_fan_dipole",
}


@pytest.fixture(scope="module")
def schemas() -> dict[str, dict[str, dict]]:
    from antennaknobs.web import server

    r = TestClient(server.app).get("/examples")
    assert r.status_code == 200
    out = {}
    for e in r.json()["examples"]:
        if e["name"] in DESIGNS:
            out[e["name"]] = {
                p["name"]: p for p in e["param_schema"] if p.get("kind") == "float"
            }
    return out


def test_declared_and_auto_knobs_are_told_apart(schemas):
    # ui_params declares min and max for these.
    for name in ("base", "length_factor", "angle_deg"):
        assert schemas["dipoles.invvee"][name]["auto_range"] is False, name
    # The fan's base has no ui_params range: its slider is the +/-50 % window.
    s = schemas["multiband.twoband_fan_dipole"]["base"]
    assert s["auto_range"] is True
    assert s["min"] == pytest.approx(0.5 * s["default"])
    assert s["max"] == pytest.approx(1.5 * s["default"])


@pytest.mark.parametrize("design", sorted(DESIGNS))
def test_the_command_line_uses_the_same_rule(schemas, design):
    """Where the schema says declared, ``free_for`` searches the slider's
    range; where it says auto, +/-20 % of the value: what the workbench's
    ``defaultKnobOpt`` seeds."""
    b = importlib.import_module(DESIGNS[design]).Builder()
    schema = schemas[design]
    seen = set()
    for f in band_opt.free_for(b, sorted(schema)):
        s = schema[f["name"]]
        v = float(getattr(b, f["name"]))
        if s["auto_range"]:
            span = band_opt.DEFAULT_SPAN
            want = sorted((v * (1 - span), v * (1 + span)))
        else:
            want = [s["min"], s["max"]]
        assert [f["min"], f["max"]] == pytest.approx(want), f["name"]
        seen.add(s["auto_range"])
    assert band_opt.DEFAULT_SPAN == 0.2
    assert seen  # the design has float knobs to check


def test_one_declared_end_is_not_a_declared_range():
    """A design declaring only one end leaves the other to the window: not a
    range it chose, as ``band_opt._ui_range`` reads it."""
    from antennaknobs.web.adapter import _auto_paramspec

    assert _auto_paramspec("x", 10.0, {"min": 1.0}).auto_range is True
    assert _auto_paramspec("x", 10.0, {"min": 1.0, "max": 20.0}).auto_range is False
    assert _auto_paramspec("x", 10.0, None).auto_range is True
