"""The hosted wall-time budget for every sweep (``ANTENNAKNOBS_MAX_SWEEP_SECONDS``).

Hosted, a frequency sweep, a knob or density sweep and a held sweep each stop
at their next point once the budget is spent, keep what they streamed, and
close with ``{done, stopped: "time", time_budget_s}``. A catalog design is
bounded exactly as an opened deck is. Local runs are unbounded. The precedent
is the band optimizer's ``time_budget_s`` (AK#1909).

A budget of 0 s makes the stop deterministic: the first fresh point (or
chunk) always runs, and nothing after it does.
"""

from __future__ import annotations

import importlib
import json
import time

import pytest
from fastapi.testclient import TestClient

from antennaknobs.web import cost, server

INVVEE = {
    "geometry": "dipoles.invvee",
    "variant": "dipole",
    "measurement_freq_mhz": 28.47,
    "design_freq_mhz": 28.47,
    "momwire_model": "bspline",
    "n_per_wire": 7,
}


@pytest.fixture(scope="module")
def client() -> TestClient:
    return TestClient(server.app)


@pytest.fixture
def hosted_zero(monkeypatch):
    monkeypatch.setattr(server, "_HOSTED", True)
    monkeypatch.setattr(server, "_MAX_SWEEP_SECONDS", 0)


def _records(text: str) -> list[dict]:
    return [json.loads(line) for line in text.splitlines() if line.strip()]


def test_the_default_budget_is_120_s_and_env_overridable(monkeypatch):
    monkeypatch.delenv("ANTENNAKNOBS_MAX_SWEEP_SECONDS", raising=False)
    assert importlib.reload(cost).MAX_SWEEP_SECONDS == 120
    monkeypatch.setenv("ANTENNAKNOBS_MAX_SWEEP_SECONDS", "7")
    assert importlib.reload(cost).MAX_SWEEP_SECONDS == 7
    monkeypatch.delenv("ANTENNAKNOBS_MAX_SWEEP_SECONDS")
    importlib.reload(cost)


def _count_solves(monkeypatch) -> list:
    calls: list = []

    def stub(req, cancel=None):
        calls.append(req["length_factor"])
        return complex(50.0 + len(calls), 0.0), None, None

    monkeypatch.setattr(server, "_solve_z_only", stub)
    return calls


def test_a_knob_sweep_stops_at_the_next_point_and_says_so(
    client, hosted_zero, monkeypatch
):
    calls = _count_solves(monkeypatch)
    recs = _records(
        client.post(
            "/param_sweep",
            json={**INVVEE, "param": "length_factor", "values": [0.9, 0.95, 1.0, 1.05]},
        ).text
    )
    *points, done = recs
    assert calls == [0.9]
    assert [p["value"] for p in points] == [0.9]
    assert done["done"] is True
    assert done["stopped"] == "time"
    assert done["time_budget_s"] == 0


def test_the_budget_counts_wall_time_not_points(client, monkeypatch):
    """A real clock: 0.15 s points under a 0.4 s budget stop well short of
    twenty, and well past one."""
    monkeypatch.setattr(server, "_HOSTED", True)
    monkeypatch.setattr(server, "_MAX_SWEEP_SECONDS", 0.4)
    calls: list = []

    def slow(req, cancel=None):
        calls.append(req["length_factor"])
        time.sleep(0.15)
        return complex(50.0, 0.0), None, None

    monkeypatch.setattr(server, "_solve_z_only", slow)
    values = [0.9 + 0.005 * i for i in range(20)]
    recs = _records(
        client.post(
            "/param_sweep", json={**INVVEE, "param": "length_factor", "values": values}
        ).text
    )
    *points, done = recs
    assert 2 <= len(points) <= 5, len(points)
    assert len(points) == len(calls)
    assert done["stopped"] == "time" and done["time_budget_s"] == 0.4


def test_a_local_sweep_is_unbounded(client, monkeypatch):
    monkeypatch.setattr(server, "_HOSTED", False)
    monkeypatch.setattr(server, "_MAX_SWEEP_SECONDS", 0)
    calls = _count_solves(monkeypatch)
    values = [0.9, 0.95, 1.0, 1.05]
    *points, done = _records(
        client.post(
            "/param_sweep", json={**INVVEE, "param": "length_factor", "values": values}
        ).text
    )
    assert calls == values and len(points) == 4
    assert "stopped" not in done and "time_budget_s" not in done


def test_a_sweep_inside_the_budget_is_not_labelled(client, monkeypatch):
    monkeypatch.setattr(server, "_HOSTED", True)
    calls = _count_solves(monkeypatch)
    *points, done = _records(
        client.post(
            "/param_sweep",
            json={**INVVEE, "param": "length_factor", "values": [0.9, 1.0]},
        ).text
    )
    assert len(calls) == 2 and len(points) == 2
    assert "stopped" not in done


def test_the_density_alias_is_bounded_too(client, hosted_zero, monkeypatch):
    calls: list = []

    def stub(req, cancel=None):
        calls.append(req["n_per_wire"])
        return complex(50.0, 0.0), None, None

    monkeypatch.setattr(server, "_solve_z_only", stub)
    *points, done = _records(
        client.post("/converge", json={**INVVEE, "n_values": [5, 7, 9]}).text
    )
    assert calls == [5] and [p["n_per_wire"] for p in points] == [5]
    assert done["stopped"] == "time"


def test_a_frequency_sweep_of_a_catalog_design_stops_and_says_so(client, hosted_zero):
    # momwire's chunked path: the first chunk (an eighth of 16 = 2 points)
    # runs, the next does not.
    freqs = [28.0 + 0.01 * i for i in range(16)]
    *points, done = _records(
        client.post("/sweep", json={**INVVEE, "freqs_mhz": freqs}).text
    )
    assert [p["freq_mhz"] for p in points] == freqs[:2]
    assert all(isinstance(p["z_re"], float) for p in points)
    assert done["done"] is True
    assert done["stopped"] == "time" and done["time_budget_s"] == 0


def test_a_whole_frequency_sweep_inside_the_budget_is_not_labelled(client, monkeypatch):
    monkeypatch.setattr(server, "_HOSTED", True)
    freqs = [28.0 + 0.01 * i for i in range(16)]
    *points, done = _records(
        client.post("/sweep", json={**INVVEE, "freqs_mhz": freqs}).text
    )
    assert len(points) == 16 and "stopped" not in done


def test_a_held_sweep_stops_between_points(client, hosted_zero):
    r = client.post("/analyses", json={"geometry": "dipoles.invvee"})
    (e,) = [e for e in r.json()["analyses"] if e["name"] == "resonance vs angle"]
    w = e["workbench"]
    req = {**INVVEE, "variant": "default", "ground": True, "ground_model": "fast"}
    r = client.post(
        "/param_sweep",
        json={
            **req,
            "param": w["param"],
            "values": w["values"][:4],
            "hold": w["hold"]["spec"],
        },
    )
    assert r.status_code == 200, r.text
    *points, done = _records(r.text)
    assert len(points) == 1 and points[0]["value"] == w["values"][0]
    assert done["stopped"] == "time" and done["time_budget_s"] == 0
    assert done["held_points"] + done["gaps"] == 1
