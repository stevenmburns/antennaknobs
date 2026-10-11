"""A design says how its knob sweeps (AK#1975).

Steve, tuning `wire.doublet_remote_tuner` by hand on the Smith chart: the
knob sweep's 11 linear points over the MFJ-926B capacitor's 0-3961 pF step
396 pF, and the 20 m answer (39 pF) falls between the first two. A knob's
`ui_params` may now carry a `sweep` hint (lo / hi / points / log), which the
workbench's knob sweep and `antennaknobs sweep --param` both start from.
"""

from __future__ import annotations

import argparse
import importlib

import pytest
from fastapi.testclient import TestClient

from antennaknobs.cli import _apply_knob_sweep_hint
from antennaknobs.knob_sweep import (
    TUNER_PART_SWEEP,
    knob_sweep_hint,
    sanitize_sweep_hint,
)

TUNERS = {
    "wire.doublet_remote_tuner": ("tuner_l_uH", "tuner_c_pF"),
    "wire.doublet_balanced_tuner": ("tuner_l_uH", "tuner_c_pF"),
    "wire.doublet_ladder_tuner": ("series_c1_pF", "shunt_l_uH", "series_c2_pF"),
    "verticals.inverted_l_tmatch": ("series_c1_pF", "shunt_l_uH", "series_c2_pF"),
}


@pytest.fixture(scope="module")
def schemas():
    from antennaknobs.web import server

    r = TestClient(server.app).get("/examples")
    assert r.status_code == 200
    return {e["name"]: e["param_schema"] for e in r.json()["examples"]}


def _knob(schema, name):
    return next(p for p in schema if isinstance(p, dict) and p.get("name") == name)


def test_every_tuner_part_is_served_with_its_hint(schemas):
    for design, parts in TUNERS.items():
        for part in parts:
            hint = _knob(schemas[design], part)["sweep"]
            assert hint["log"] is True and hint["points"] == 81, (design, part, hint)


def test_the_remote_tuners_parts_start_above_zero(schemas):
    # Their sliders start at 0, which has no log: the hint names where.
    s = schemas["wire.doublet_remote_tuner"]
    assert _knob(s, "tuner_c_pF")["sweep"]["lo"] == 1.0
    assert _knob(s, "tuner_l_uH")["sweep"]["lo"] == 0.05


def test_a_knob_without_a_hint_serves_none(schemas):
    s = schemas["wire.doublet_remote_tuner"]
    assert _knob(s, "line_ft")["sweep"] is None


@pytest.mark.parametrize(
    "raw",
    [
        "fine",  # not a mapping
        {"points": 1},  # below MIN_POINTS
        {"points": 500},  # above MAX_POINTS
        {"points": 40.5},  # not a whole count
        {"log": "yes"},  # not a bool
        {"lo": 5.0, "hi": 2.0},  # lo not below hi
        {"log": True},  # a log range from the knob's min of 0
    ],
)
def test_an_unsweepable_hint_is_dropped_whole(raw):
    assert sanitize_sweep_hint(raw, 0.0, 100.0) is None


def test_a_hint_keeps_only_what_the_design_said():
    assert sanitize_sweep_hint({"points": 81}, 0.0, 100.0) == {"points": 81}
    assert sanitize_sweep_hint(TUNER_PART_SWEEP, 10.0, 500.0) == {
        "log": True,
        "points": 81,
    }


def _args(**over):
    base = dict(
        param="tuner_c_pF",
        range=None,
        center=None,
        fraction=None,
        npoints=None,
        log=False,
        swr=False,
        gain=False,
        patterns=False,
    )
    base.update(over)
    return argparse.Namespace(**base)


def _make():
    return importlib.import_module(
        "antennaknobs.designs.wire.doublet_remote_tuner"
    ).Builder()


def test_the_command_line_starts_from_the_hint():
    args = _args()
    _apply_knob_sweep_hint(args, _make, density=False)
    assert args.range == [1.0, pytest.approx(3961.0, rel=1e-3)]
    assert args.npoints == 81
    assert args.log is True


def test_explicit_flags_win_on_the_command_line():
    args = _args(range=[10.0, 100.0], npoints=50)
    _apply_knob_sweep_hint(args, _make, density=False)
    assert (args.range, args.npoints, args.log) == ([10.0, 100.0], 50, False)
    args = _args(npoints=31)
    _apply_knob_sweep_hint(args, _make, density=False)
    assert args.npoints == 31 and args.log is True


def test_log_spacing_stays_with_the_impedance_chart():
    # --log serves the impedance chart only (`_check_chart_flags`); an SWR
    # sweep takes the hint's range and points, linearly.
    args = _args(swr=True)
    _apply_knob_sweep_hint(args, _make, density=False)
    assert args.npoints == 81 and args.log is False


def test_frequency_and_hintless_knobs_are_untouched():
    for over in ({"param": "freq"}, {"param": "line_ft"}):
        args = _args(**over)
        _apply_knob_sweep_hint(args, _make, density=False)
        assert (args.range, args.npoints, args.log) == (None, None, False), over


def test_the_builder_read_matches_the_served_hint(schemas):
    b = _make()
    assert (
        knob_sweep_hint(b, "tuner_c_pF")
        == _knob(schemas["wire.doublet_remote_tuner"], "tuner_c_pF")["sweep"]
    )
