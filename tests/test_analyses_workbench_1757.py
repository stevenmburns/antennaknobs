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
        assert set(a) == {"name", "summary", "code", "problems", "workbench"}
        assert a["code"].startswith("an.")
        w = a["workbench"]
        if w["runs"]:
            assert set(w) == {"runs", "param", "values", "log", "note"}
        else:
            assert set(w) == {"runs", "why"} and w["why"]


def test_e3_height_runs_as_a_base_sweep_2_to_20_in_37_points(invvee):
    w = invvee["height"]["workbench"]
    assert w["runs"] is True
    assert w["param"] == "base"
    assert w["values"] == [2 + 0.5 * i for i in range(37)]
    assert w["log"] is False
    # One cell of three: the session's ground, and the CLI draws all three.
    assert "crossed over grounds" in w["note"]
    assert "this session's ground" in w["note"]
    assert "`antennaknobs analyze` draws all 3" in w["note"]
    assert invvee["height"]["summary"].startswith("height (base) 2..20, 37 points")


def test_e1_convergence_runs_as_the_density_ladder(invvee):
    w = invvee["convergence"]["workbench"]
    assert w["runs"] is True
    assert w["param"] == "n_per_wire"
    assert w["values"] == list(sw.NOMINAL_NSEGS_LADDER) == [8, 12, 17, 24, 34, 48, 68]
    assert w["log"] is True
    assert "crossed over engines" in w["note"]
    assert "this session's engine" in w["note"]
    # E1 names its ground; the workbench says it uses the session's.
    assert "finite:13,0.005" in w["note"]


@pytest.mark.parametrize(
    ("name", "step"),
    [
        ("match vs height", "step 6"),
        ("resonance vs angle", "step 6"),
        ("tuning map", "step 5"),
        ("tuning family", "step 5"),
        ("feed spellings", "step 5"),
        ("band SWR", "step 4"),
    ],
)
def test_what_the_workbench_cannot_draw_is_listed_with_its_step(invvee, name, step):
    w = invvee[name]["workbench"]
    assert w["runs"] is False
    assert step in w["why"]


def test_a_hold_says_hold(invvee):
    assert "hold" in invvee["match vs height"]["workbench"]["why"]


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
