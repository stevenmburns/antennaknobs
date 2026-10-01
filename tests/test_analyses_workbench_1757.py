"""POST /analyses: the workbench lists a design's analyses and says how the
Z-vs-parameter view runs each (AK#1757, sweep-framework step 3;
``web/analyses_offer.py``).

The gates: E1 and E3 on the invvee are runnable with the ladder and range
the CLI sweeps (parity is checked against ``antennaknobs analyze`` itself,
solves stubbed); what the workbench cannot draw yet is listed with the step
it is planned for; a deck's own density knob runs as a knob sweep with the
CLI-only Z∞ note. Nothing here solves.
"""

from __future__ import annotations

import importlib
from pathlib import Path

import numpy as np
import pytest
from fastapi.testclient import TestClient

from antennaknobs.cli import cli

sw = importlib.import_module("antennaknobs.sweep")

SSN = (
    Path(__file__).parent
    / "fixtures"
    / "ssn_numericparam_1716"
    / "snDipoleVarLenSegs.ssn"
)

INVVEE = {
    "geometry": "dipoles.invvee",
    "measurement_freq_mhz": 28.47,
    "design_freq_mhz": 28.47,
    "momwire_model": "bspline",
    "n_per_wire": 9,
}


# The crosses beyond engines and grounds (AK#1757 step 5 unit 4b).
CROSSES = ("axes", "planes", "designs", "states", "cells", "step")


@pytest.fixture(scope="module")
def client() -> TestClient:
    from antennaknobs.web import server

    return TestClient(server.app)


def _offered(client, req) -> dict[str, dict]:
    r = client.post("/analyses", json=req)
    assert r.status_code == 200, r.text
    return {a["name"]: a for a in r.json()["analyses"]}


@pytest.fixture(scope="module")
def invvee(client) -> dict[str, dict]:
    return _offered(client, INVVEE)


def test_every_entry_has_the_documented_shape(invvee):
    for a in invvee.values():
        # `spec`: the analysis as data, which the chart sends back to keep
        # what it built (AK#1757 step 7, unit 4).
        assert set(a) == {
            "name",
            "summary",
            "code",
            "spec",
            "problems",
            "workbench",
            "study",
        }
        # A study (AK#1757 step 7) says so; the design's own say None.
        assert (a["study"] is not None) is (":" in a["name"]), a["name"]
        assert a["code"].startswith("an.")
        w = a["workbench"]
        if w["runs"] and w["kind"] == "frequency":
            assert set(w) == {
                "runs",
                "kind",
                "range",
                "level",
                "points",
                "freqs",
                "views",
                "swr",
                "engines",
                "grounds",
                *CROSSES,
                "note",
            }
        elif w["runs"] and w["kind"] == "pattern":
            # A pattern (AK#1757 step 7): no sweep, one solve per cell.
            assert set(w) == {
                "runs",
                "kind",
                "views",
                "freq",
                "engines",
                "grounds",
                *CROSSES,
                "note",
            }
        elif w["runs"]:
            # `metric`: its MetricPlot as the chart draws it, or None
            # (AK#1828).
            assert set(w) == {
                "runs",
                "kind",
                "param",
                "values",
                "log",
                "views",
                "metric",
                # The hold at every point (step 6), None on a plain sweep.
                "hold",
                "engines",
                "grounds",
                *CROSSES,
                "note",
            }
        else:
            assert set(w) == {"runs", "why"} and w["why"]


def test_e3_height_runs_as_a_base_sweep_2_to_20_in_37_points(invvee):
    w = invvee["height"]["workbench"]
    assert w["runs"] is True
    assert w["param"] == "base"
    assert w["values"] == [2 + 0.5 * i for i in range(37)]
    assert w["log"] is False
    # The ground cross is served for the chart to preselect its ground
    # slots from (AK#1757 step 5 unit 4), in the analysis's order; it names
    # no engine, so the chart draws the session's active slot.
    assert w["grounds"] == ["free", "finite:13,0.005", "finite:5,0.001"]
    assert w["engines"] is None
    assert w["note"] is None
    assert invvee["height"]["summary"].startswith("height (base) 2..20, 37 points")


def test_e1_convergence_runs_as_the_density_ladder(invvee):
    w = invvee["convergence"]["workbench"]
    assert w["runs"] is True
    assert w["param"] == "n_per_wire"
    assert w["values"] == list(sw.NOMINAL_NSEGS_LADDER) == [8, 12, 17, 24, 34, 48, 68]
    assert w["log"] is True
    # The engine cross, and the one ground E1 names, as the chart's
    # preselection (a listed engine no slot holds is the chart's to skip,
    # not the server's: the list is served whole).
    assert w["engines"] == ["momwire:bspline", "momwire:razor-2p", "nec5"]
    assert w["grounds"] == ["finite:13,0.005"]
    assert w["note"] is None
    # Its views, the Table among them since step 5 unit 5.
    assert w["views"] == ["Rx", "Table", "Smith"]


@pytest.mark.parametrize(("name", "step"), [("tuning map", "step 5")])
def test_what_the_workbench_cannot_draw_is_listed_with_its_step(invvee, name, step):
    w = invvee[name]["workbench"]
    assert w["runs"] is False
    assert step in w["why"]


def test_a_hold_runs_with_its_knobs_bounds_and_spec(invvee):
    # Step 6: E8 and E9 run in the chart. The hold rides on the knob entry,
    # its knobs bounded by their ui_params, its spec the data each curve's
    # /param_sweep sends back.
    w = invvee["match vs height"]["workbench"]
    assert w["runs"] is True and w["kind"] == "knob" and w["param"] == "base"
    assert w["views"] == ["Rx", "Knobs"]
    assert w["hold"] == {
        "objective": "match_z0",
        "knobs": ["length_factor", "angle_deg"],
        "bounds": {"length_factor": [0.8, 1.25], "angle_deg": [0.0, 60.0]},
        "z0": 50,
        "warm_start": True,
        "spec": {
            "an": "Hold",
            "objective": "match_z0",
            "adjust": ["length_factor", "angle_deg"],
            "z0": 50,
            "warm_start": True,
        },
    }
    e9 = invvee["resonance vs angle"]["workbench"]
    assert e9["runs"] is True and e9["hold"]["knobs"] == ["length_factor"]
    # A plain knob analysis carries no hold.
    assert invvee["height"]["workbench"]["hold"] is None


def test_code_is_the_analysis_as_python(invvee):
    from antennaknobs import analyses as an

    a = invvee["height"]
    got = eval(a["code"], {"an": an})
    assert got.name == "height"
    assert got.sweep == an.Sweep(an.HEIGHT, 2, 20, points=37)


def test_a_design_with_no_height_role_offers_no_height(client):
    got = _offered(client, {"geometry": "beams.yagi"})
    assert "height" not in got
    assert "convergence" in got


def test_an_unknown_geometry_is_a_422(client):
    r = client.post("/analyses", json={"geometry": "nope.nope"})
    assert r.status_code == 422


# ── a deck's own density knob ─────────────────────────────────────────────


@pytest.fixture
def userdir(tmp_path, monkeypatch):
    import antennaknobs.web.examples as examples

    monkeypatch.setenv("ANTENNAKNOBS_USER_DIR", str(tmp_path))
    monkeypatch.delenv("ANTENNAKNOBS_TRUST_USER_DESIGNS", raising=False)
    yield tmp_path
    for key in [k for k in examples.REGISTRY if k.startswith("user.")]:
        del examples.REGISTRY[key]


def test_a_decks_density_knob_runs_as_a_knob_sweep_with_the_cli_only_note(
    userdir, client
):
    import antennaknobs.web.user_designs as web_user_designs

    (userdir / SSN.name).write_bytes(SSN.read_bytes())
    web_user_designs.refresh()
    got = _offered(client, {"geometry": f"user.{SSN.stem}"})
    w = got["convergence"]["workbench"]
    assert w["runs"] is True
    assert w["param"] == "tmp_segs"
    # The CLI's own ladder for a density role with no range of its own.
    assert w["values"] == list(sw.NOMINAL_NSEGS_LADDER)
    assert w["log"] is True
    assert "Z∞ for a deck's own density knob is CLI-only" in w["note"]
    assert "height" not in got


# ── parity with `antennaknobs analyze` ────────────────────────────────────


def test_e3_values_equal_what_analyze_sweeps(monkeypatch, invvee, tmp_path):
    """The picker sends ``workbench.values``; ``analyze`` solves the same
    knob at the same values, cell by cell (solves stubbed: this is about
    which values, not which numbers)."""
    calls = []

    def fake_solve_at(builder, knob, xs, factory):
        calls.append((knob, list(xs)))
        return [np.array([50 + 0j]) for _ in xs]

    monkeypatch.setattr(sw, "_solve_at", fake_solve_at)
    cli(["analyze", "--builder", "dipoles.invvee", "--analysis", "height",
         "--fn", str(tmp_path / "a.png")])  # fmt: skip
    w = invvee["height"]["workbench"]
    assert len(calls) == 3  # one per ground
    for knob, xs in calls:
        assert knob == w["param"]
        assert xs == w["values"]


def test_e1_rungs_equal_what_analyze_sweeps(monkeypatch, invvee, tmp_path):
    calls = []

    def fake_rows(builder, factory, rungs, knob="nominal_nsegs"):
        calls.append((knob, list(rungs)))
        rows = [(n, 2 * n, complex(70 + 10 / n, -10 + 5 / n)) for n in rungs]
        return rows, [None] * len(rungs), 1

    monkeypatch.setattr(sw, "_convergence_rows", fake_rows)
    cli(["analyze", "--builder", "dipoles.invvee", "--analysis", "convergence",
         "--fn", str(tmp_path / "a.png")])  # fmt: skip
    w = invvee["convergence"]["workbench"]
    assert calls  # nec5 may be refused on this machine; the others ran
    for knob, rungs in calls:
        # The CLI's nominal_nsegs IS the request's n_per_wire.
        assert knob == "nominal_nsegs"
        assert rungs == w["values"]
