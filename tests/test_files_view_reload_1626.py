"""A reloaded design file gets a new solve_id, so the Files view shows the deck
the engine actually ran (AK#1626).

AC6LA edited a user design on disk and clicked reload: the numbers followed the
file, and the Files view kept the pre-edit NEC-5 deck, even across a solver
switch and back, until the app restarted. The server evicted its caches on the
reload (#1312), but the solve_id is a hash of the REQUEST and a file edit
changes no request field, so the re-solve came back under the same solve_id
and the client, which fetches a solve's texts once per solve_id, kept the old
ones. The reload count now salts a user design's key.
"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

import antennaknobs.web.server as server
from antennaknobs.web import user_designs
from antennaknobs.web.examples import REGISTRY

USER = {"geometry": "user.bydipole1", "solver": "nec5", "design_freq_mhz": 14.0}
CATALOG = {"geometry": "dipoles.invvee", "solver": "nec5", "design_freq_mhz": 14.0}


@pytest.fixture
def userdir(tmp_path, monkeypatch):
    """An empty user-design dir, so a reload loads nothing real."""
    monkeypatch.setenv("ANTENNAKNOBS_USER_DIR", str(tmp_path))
    monkeypatch.delenv("ANTENNAKNOBS_TRUST_USER_DESIGNS", raising=False)
    yield tmp_path
    for key in [k for k in REGISTRY if k.startswith("user.")]:
        del REGISTRY[key]


def test_a_reload_moves_a_user_designs_solve_id_and_nothing_else(userdir):
    user, catalog = (
        server._canonical_solve_key(USER),
        server._canonical_solve_key(CATALOG),
    )
    assert server._canonical_solve_key(USER) == user  # stable between reloads
    user_designs.refresh()
    assert server._canonical_solve_key(USER) != user
    # Catalog code is fixed for the process, and its cache stays warm.
    assert server._canonical_solve_key(CATALOG) == catalog


def test_the_files_view_is_handed_the_reloaded_files_deck(userdir, monkeypatch):
    """The whole path: solve, click reload, re-solve, ask for the deck."""
    for name in ("_SOLVE_CACHE", "_CUTS_SRC_CACHE", "_ENGINE_IO_CACHE"):
        monkeypatch.setattr(server, name, getattr(server, name).__class__())
    monkeypatch.setattr(server, "_USER_CACHE_KEYS", {"solve": set(), "sweep": set()})
    # The NEC-5 lane as if $NEC5_EXE resolved; the solve itself is stubbed.
    monkeypatch.setitem(
        server._EXTERNAL_BACKENDS, "nec5", (server.nec5_backend, lambda: True)
    )
    decks = iter(["GS 0 0 0.0254 (before the edit)", "no GS (after the edit)"])

    def fake(req, cancel=None):
        return {
            "geometry": req["geometry"],
            "solver": "nec5",
            "z_in_re": 50.0,
            "_engine_runs": [{"deck": next(decks), "printout": "p", "cached": False}],
        }

    monkeypatch.setattr(server, "_solve_uncached", fake)
    monkeypatch.setattr(server, "_attach_request_cuts", lambda out, req: None)

    before = server.solve(dict(USER))
    with TestClient(server.app) as c:
        assert c.get("/examples").status_code == 200  # the reload button
        after = server.solve(dict(USER))
        r = c.post("/engine_io", json={**USER, "solve_id": after["solve_id"]})
    assert after["cache_hit"] is False
    # The client asks for a solve's texts once per solve_id: an unchanged id
    # is what kept the old deck on screen.
    assert after["solve_id"] != before["solve_id"]
    assert r.status_code == 200
    assert r.json()["runs"][0]["deck"] == "no GS (after the edit)"
