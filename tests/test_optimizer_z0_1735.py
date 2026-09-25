"""AK#1735: the reference impedance (Zo) is a request field, and a file's.

AC6LA: "Suppose I want Zo to be something other than 50 for a built-in model
where I have enabled two knobs for optimizing. Where do I set a desired Zo
value?" What is pinned here:

- a ``.ssn`` Generator's Zo seeds the design's ``target_z0``; AC6LA's own
  files (Zo 50) are unchanged, and a missing / zero / unreadable Zo seeds
  nothing;
- a request's ``z0_ohms`` is the reference every response echoes, with the
  design's own beside it as ``design_z0_ohms``: the live /ws solve, the
  /geometry preview, and a solve-cache HIT (the field is out of the cache key,
  so the hit is re-stamped from the request);
- /optimize measures against it: a ``match_z0`` run lands on 75 + j0 and an
  ``swr`` run reports SWR against 75, both through the server route;
- a bad Zo is refused by name, never silently replaced by 50;
- the tracker's staleness signature includes it (a new Zo is a new root).
"""

from __future__ import annotations

import json
import math
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from test_simnec_import import _SCRIPT_M, _ssn

from antennaknobs.file_designs import builder_from_file
from antennaknobs.web import server
from antennaknobs.web.adapter import request_z0
from antennaknobs.web.optimize import _swr
from antennaknobs.web.server import _track_signature

FIXTURES = Path(__file__).parent / "fixtures"
# AC6LA's circuits, every one saved with a 50 ohm Generator.
DANS_FILES = sorted(FIXTURES.rglob("*.ssn"))

INVVEE = {
    "geometry": "dipoles.invvee",
    "measurement_freq_mhz": 14.2,
    "design_freq_mhz": 14.2,
    "momwire_model": "bspline",
    "ground": True,
    "ground_model": "fast",
}
TWO_KNOBS = [
    {"name": "length_factor", "min": 0.8, "max": 1.25},
    {"name": "angle_deg", "min": 0.0, "max": 60.0},
]


def _with_zo(zo: str) -> str:
    text = _ssn(_SCRIPT_M)
    assert text.count("<n>Zo</n><v>50</v>") == 1
    return text.replace("<n>Zo</n><v>50</v>", f"<n>Zo</n><v>{zo}</v>")


def _ui(path: Path) -> dict:
    return dict(builder_from_file(str(path)).default_params.get("ui_params") or {})


@pytest.fixture(scope="module")
def client() -> TestClient:
    return TestClient(server.app)


# --- the .ssn seed -------------------------------------------------------------


def test_a_75_ohm_generator_seeds_target_z0(tmp_path):
    path = tmp_path / "zo75.ssn"
    path.write_text(_with_zo("75"), encoding="utf-8")
    assert _ui(path)["target_z0"] == 75.0


@pytest.mark.parametrize("zo", ["0", "-50", "abc", "nan", "inf"])
def test_a_generator_zo_that_is_no_reference_seeds_nothing(tmp_path, zo):
    path = tmp_path / "zo.ssn"
    path.write_text(_with_zo(zo), encoding="utf-8")
    assert "target_z0" not in _ui(path)


def test_a_file_with_no_generator_seeds_nothing(tmp_path):
    path = tmp_path / "nogen.ssn"
    path.write_text(_ssn(_SCRIPT_M, generator=False), encoding="utf-8")
    assert "target_z0" not in _ui(path)


def test_a_nec_deck_names_no_zo_so_the_default_applies(tmp_path):
    path = tmp_path / "d.nec"
    path.write_text(
        "GW 1 21 0 -5 10 0 5 10 .001\nGE 0\nEX 0 1 11 0 1 0\nFR 0 1 0 0 14.2 0\nEN\n",
        encoding="utf-8",
    )
    assert "target_z0" not in _ui(path)


def test_dans_files_are_unchanged_at_50_ohms():
    """Every AC6LA fixture names Zo 50, which is the default anyway: the seed
    moves no number the app showed before."""
    assert len(DANS_FILES) >= 5
    for path in DANS_FILES:
        assert _ui(path).get("target_z0") == 50.0, path.name


def test_a_75_ohm_file_is_served_at_75(tmp_path, monkeypatch):
    """Through the server: the file design's preview and solve both measure
    against the Generator's Zo, with no request override."""
    (tmp_path / "zo75.ssn").write_text(_with_zo("75"), encoding="utf-8")
    monkeypatch.setenv("ANTENNAKNOBS_USER_DIR", str(tmp_path))
    with TestClient(server.app) as c:
        # The catalog load is what (re)scans the user folder, as in the app.
        assert "user.zo75" in {e["name"] for e in c.get("/examples").json()["examples"]}
        geo = c.post("/geometry", json={"geometry": "user.zo75"}).json()
        with c.websocket_connect("/ws") as ws:
            ws.send_text(json.dumps({"geometry": "user.zo75"}))
            live = json.loads(ws.receive_text())
    assert geo["z0_ohms"] == geo["design_z0_ohms"] == 75.0
    assert live.get("error") is None, live.get("error")
    assert live["z0_ohms"] == live["design_z0_ohms"] == 75.0


# --- the request override ------------------------------------------------------


def test_request_z0_prefers_the_request_and_refuses_junk():
    assert request_z0({}, 50.0) == 50.0
    assert request_z0({"z0_ohms": 75}, 50.0) == 75.0
    assert request_z0({"z0_ohms": None}, 200.0) == 200.0
    for bad in (0, -1, float("nan"), float("inf"), "x", True):
        with pytest.raises(ValueError, match="z0_ohms"):
            request_z0({"z0_ohms": bad}, 50.0)


def _ws(client: TestClient, req: dict) -> dict:
    with client.websocket_connect("/ws") as ws:
        ws.send_text(json.dumps(req))
        return json.loads(ws.receive_text())


def test_the_live_solve_echoes_the_requested_z0_and_a_cache_hit_is_restamped(
    client,
):
    server._SOLVE_CACHE.clear()
    first = _ws(client, {**INVVEE, "z0_ohms": 75.0})
    assert first["cache_hit"] is False
    assert first["z0_ohms"] == 75.0
    assert first["design_z0_ohms"] == 50.0
    # Same physics, another reference: the same cache entry (Zo is not in the
    # key), speaking for THIS request's reference.
    second = _ws(client, {**INVVEE, "z0_ohms": 200.0})
    assert second["cache_hit"] is True
    assert second["solve_id"] == first["solve_id"]
    assert second["z0_ohms"] == 200.0
    assert (second["z_in_re"], second["z_in_im"]) == (
        first["z_in_re"],
        first["z_in_im"],
    )
    # And no override is the design's own again, not the cached 75.
    third = _ws(client, dict(INVVEE))
    assert third["cache_hit"] is True
    assert third["z0_ohms"] == 50.0


def test_the_preview_echoes_the_requested_z0(client):
    out = client.post("/geometry", json={**INVVEE, "z0_ohms": 75}).json()
    assert out["z0_ohms"] == 75.0
    assert out["design_z0_ohms"] == 50.0


def test_a_bad_z0_is_refused_on_the_live_solve(client):
    out = _ws(client, {**INVVEE, "z0_ohms": -5})
    assert "z0_ohms" in str(out.get("error")), out


# --- /optimize -----------------------------------------------------------------


def _optimize(client, objective: str, **extra) -> dict:
    body = {**INVVEE, **extra}
    body["optimize"] = {"free": TWO_KNOBS, "objective": objective}
    return client.post("/optimize", json=body).json()


def test_a_match_run_at_75_ohms_lands_on_75_plus_j0(client):
    out = _optimize(client, "match_z0", z0_ohms=75)
    assert out.get("error") is None, out.get("error")
    after = out["metrics_after"]
    assert after["z0_ohms"] == 75.0
    assert after["z_in_re"] == pytest.approx(75.0, abs=0.5)
    assert after["z_in_im"] == pytest.approx(0.0, abs=0.5)
    assert after["swr"] < 1.02
    # The before point is measured against the same reference.
    before = out["metrics_before"]
    assert before["swr"] == pytest.approx(
        _swr(before["z_in_re"], before["z_in_im"], 75.0)
    )


def test_without_an_override_the_same_run_matches_the_designs_50(client):
    out = _optimize(client, "match_z0")
    after = out["metrics_after"]
    assert after["z0_ohms"] == 50.0
    assert after["z_in_re"] == pytest.approx(50.0, abs=0.5)


def test_an_swr_run_reports_swr_against_the_requested_z0(client):
    out = _optimize(client, "swr", z0_ohms=75)
    assert out.get("error") is None, out.get("error")
    after = out["metrics_after"]
    assert after["z0_ohms"] == 75.0
    assert after["swr"] == pytest.approx(_swr(after["z_in_re"], after["z_in_im"], 75.0))
    # Minimising SWR against 75 lands nearer 75 than 50.
    assert abs(after["z_in_re"] - 75.0) < abs(after["z_in_re"] - 50.0)


@pytest.mark.parametrize("bad", [0, -75, "abc"])
def test_optimize_refuses_a_bad_z0_by_name_before_any_eval(client, bad):
    out = _optimize(client, "match_z0", z0_ohms=bad)
    assert "z0_ohms" in out["error"]
    assert "params" not in out


def test_optimize_refuses_a_non_finite_z0(client):
    # json.dumps writes NaN as a bare literal, which the server's json.loads
    # accepts -- the physics boundary is where it has to be caught.
    body = {**INVVEE, "z0_ohms": math.nan}
    body["optimize"] = {"free": TWO_KNOBS, "objective": "match_z0"}
    out = client.post(
        "/optimize",
        content=json.dumps(body),
        headers={"Content-Type": "application/json"},
    ).json()
    assert "z0_ohms" in out["error"]


# --- the tracker ---------------------------------------------------------------


def test_a_new_z0_is_a_new_tracker_root():
    t = {"objective": "match_z0", "free": TWO_KNOBS, "drag": {"name": "base"}}
    a = _track_signature({**INVVEE, "_track": t})
    b = _track_signature({**INVVEE, "z0_ohms": 75.0, "_track": t})
    c = _track_signature({**INVVEE, "z0_ohms": 75.0, "_track": t})
    assert a != b
    assert b == c
