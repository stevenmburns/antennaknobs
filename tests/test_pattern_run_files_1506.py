"""AK#1506 — the Files view shows the pattern run's deck and printout too.

The NEC overlay's pattern runs its own RP deck through the external engine, and
its printout carries the engine's gain tables: what a user compares our cuts
against. `/pattern` parks those texts under the SOLVE they belong to (the
pattern dispatch asks one fixed 46 x 73 grid of every design, so a solve has
one pattern deck), and `/engine_io` lists them after the solve's own runs.

The bookkeeping is checked with the engine stubbed; the last test drives nec2c
when this machine has one, because only a real run proves the gain table shown
is the one the overlay was drawn from.
"""

from __future__ import annotations

import json
import shutil

import pytest
from fastapi.testclient import TestClient

import antennaknobs.web.server as server
from antennaknobs.engines.nec2 import NEC2Engine

RUN = {
    "deck": "CM pattern\nRP 0 46 72 1000 0 0 2 5\nEN\n",
    "printout": "GAINS\n",
    "cached": False,
}
SOLVE_RUNS = [{"deck": "CM solve\nEN\n", "printout": "Z\n", "cached": False}]
REQ = {"geometry": "dipoles.invvee", "solver": "nec5"}


@pytest.fixture
def client():
    return TestClient(server.app)


@pytest.fixture
def caches(monkeypatch):
    for name in (
        "_SOLVE_CACHE",
        "_CUTS_SRC_CACHE",
        "_ENGINE_IO_CACHE",
        "_PATTERN_IO_CACHE",
    ):
        monkeypatch.setattr(server, name, getattr(server, name).__class__())
    monkeypatch.setattr(server, "_USER_CACHE_KEYS", {"solve": set(), "sweep": set()})


@pytest.fixture
def nec5_pattern(monkeypatch):
    """The NEC-5 lane as if $NEC5_EXE resolved, its pattern run stubbed."""
    monkeypatch.setitem(
        server._EXTERNAL_BACKENDS, "nec5", (server.nec5_backend, lambda: True)
    )
    monkeypatch.setattr(
        server.nec5_backend,
        "pattern",
        lambda req: {
            "available": True,
            "gain_dbi": [[0.0]],
            "_engine_runs": [dict(RUN)],
        },
    )


def test_a_pattern_parks_its_run_under_the_solve_and_never_sends_it(
    client, caches, nec5_pattern
):
    out = client.post("/pattern", json={**REQ, "_gen": 7}).json()
    assert "_engine_runs" not in out
    # The solve's own key: _gen is lane metadata, not physics.
    sid = server._canonical_solve_key(REQ)
    assert out["solve_id"] == sid
    (run,) = server._PATTERN_IO_CACHE[sid]
    assert run["kind"] == "pattern" and run["deck"] == RUN["deck"]
    assert "RP card" in run["note"]


def test_engine_io_lists_the_pattern_run_after_the_solves_own(
    client, caches, nec5_pattern
):
    sid = server._canonical_solve_key(REQ)
    server._ENGINE_IO_CACHE[sid] = {
        "solver": "nec5",
        "label": "NEC-5",
        "runs": SOLVE_RUNS,
    }
    before = client.post("/engine_io", json={**REQ, "solve_id": sid}).json()
    assert before["runs"] == SOLVE_RUNS
    client.post("/pattern", json=REQ)
    after = client.post("/engine_io", json={**REQ, "solve_id": sid}).json()
    assert after["runs"][:1] == SOLVE_RUNS
    assert [r.get("kind") for r in after["runs"]] == [None, "pattern"]
    # The solve's cached entry is not mutated by the listing.
    assert server._ENGINE_IO_CACHE[sid]["runs"] == SOLVE_RUNS


def test_a_designs_refresh_evicts_a_user_designs_pattern_run(caches):
    server._PATTERN_IO_CACHE["k"] = [dict(RUN, kind="pattern")]
    server._USER_CACHE_KEYS["solve"].add("k")
    assert server._evict_user_design_caches()["engine_io"] == 1
    assert "k" not in server._PATTERN_IO_CACHE


@pytest.mark.skipif(shutil.which("nec2c") is None, reason="no nec2c on PATH")
def test_the_pattern_printout_is_the_one_the_overlay_was_drawn_from(
    client, caches, monkeypatch
):
    monkeypatch.setenv("NEC2_EXE", shutil.which("nec2c"))
    req = {"geometry": "dipoles.invvee", "solver": "nec2"}
    with client.websocket_connect("/ws") as ws:
        ws.send_text(json.dumps(req))
        out = json.loads(ws.receive_text())
    pat = client.post("/pattern", json=req).json()
    assert pat["available"] is True and pat["solve_id"] == out["solve_id"]

    io = client.post("/engine_io", json={**req, "solve_id": out["solve_id"]}).json()
    *solve_runs, run = io["runs"]
    assert solve_runs and all("kind" not in r for r in solve_runs)
    assert run["kind"] == "pattern"
    assert any(line.startswith("RP") for line in run["deck"].splitlines())
    gains = NEC2Engine._parse_radiation_patterns(run["printout"])
    th, ph = pat["theta_deg"][10], pat["phi_deg"][20]
    assert pat["gain_dbi"][10][20] == pytest.approx(gains[(round(th, 2), round(ph, 2))])
