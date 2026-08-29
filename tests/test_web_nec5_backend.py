"""Unit + live tests for web/nec5_backend.py (issue #825 follow-up).

The delegation layer and availability probe are covered everywhere; the
end-to-end web solves run only where $NEC5_EXE resolves a licensed binary
(the same skip contract as the engine tests)."""

from __future__ import annotations

import sys
from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient

from antennaknobs.web import server as _server

from antennaknobs.web import nec5_backend
from antennaknobs.web.examples._base import AntennaExample

from conftest import needs_nec5


@pytest.fixture(scope="module")
def client() -> TestClient:
    return TestClient(_server.app)


def test_have_nec5_is_a_runtime_probe(monkeypatch):
    monkeypatch.delenv("NEC5_EXE", raising=False)
    assert nec5_backend.have_nec5() is False
    monkeypatch.setenv("NEC5_EXE", sys.executable)
    assert nec5_backend.have_nec5() is True


def test_solve_raises_when_example_has_no_nec5_solve():
    stub = AntennaExample(
        name="stub_no_nec5",
        label="stub",
        momwire_solve=lambda req: {},
        momwire_sweep=lambda req, freqs: ([], []),
        nec5_solve=None,
    )
    with patch.dict(nec5_backend.EXAMPLES, {"stub_no_nec5": stub}, clear=False):
        with pytest.raises(ValueError, match="NEC-5 solve not implemented"):
            nec5_backend.solve({"geometry": "stub_no_nec5"})


def _ws_solve(client, req: dict) -> dict:
    import json

    with client.websocket_connect("/ws") as ws:
        ws.send_text(json.dumps(req))
        return json.loads(ws.receive_text())


def test_unavailable_nec5_falls_back_to_momwire(client, monkeypatch):
    """A solver:'nec5' request on a machine without the binary takes the
    momwire path — the existing unavailable-pynec contract."""
    monkeypatch.delenv("NEC5_EXE", raising=False)
    res = _ws_solve(client, {"geometry": "dipoles.invvee", "solver": "nec5"})
    assert res["solver"] == "momwire"


@needs_nec5
def test_live_web_solve_via_nec5(client):
    res = _ws_solve(client, {"geometry": "dipoles.invvee", "solver": "nec5"})
    assert res["solver"] == "nec5"
    assert res["z_in_re"] > 0
    assert res["wires"] and res["power_budget"] is not None
    assert 0.0 < res["radiation_efficiency"] <= 1.0


@needs_nec5
def test_live_web_solve_fast_ground_served_as_sommerfeld(client):
    # NEC-5 has no reflection-coefficient model: the UI's "fast" request is
    # served by the full Sommerfeld solve and the applied label says so.
    res = _ws_solve(
        client,
        {
            "geometry": "dipoles.invvee",
            "solver": "nec5",
            "ground": True,
            "ground_model": "fast",
        },
    )
    assert res["solver"] == "nec5"
    assert res["ground_model_applied"] == "sommerfeld"


@needs_nec5
def test_live_web_pattern_via_nec5(client):
    res = client.post(
        "/pattern", json={"geometry": "dipoles.invvee", "solver": "nec5"}
    ).json()
    assert res["available"] is True
    assert len(res["theta_deg"]) == 46 and len(res["phi_deg"]) == 73
    assert len(res["gain_dbi"]) == 46 and len(res["gain_dbi"][0]) == 73
