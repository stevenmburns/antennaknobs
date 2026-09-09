"""Issue #1312: a designs refresh evicts the solve, cuts and sweep cache
entries written for USER designs — and only those.

The cache keys hash the request, and nothing in a request changes when a
`user.*` design's file (or a `.nec` beside it) changes on disk. Reloading
the Builder rebuilt the geometry preview from the new file while the solve
came back from the pre-edit entry: a 135-degree mast drawn over a
45-degree heat map. The refresh the user clicked is the invalidation signal.

Seeded directly rather than solved: what is under test is the bookkeeping
between the write sites and the refresh, not the physics, and a seeded
entry is a solve the gate can afford to run a thousand times.
"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

import antennaknobs.web.server as server


@pytest.fixture
def userdir(tmp_path, monkeypatch):
    """An empty user-design dir, so /examples refreshes nothing real."""
    monkeypatch.setenv("ANTENNAKNOBS_USER_DIR", str(tmp_path))
    yield tmp_path


@pytest.fixture
def seeded(monkeypatch):
    """One user and one catalog entry in each cache, tagged the way the
    write sites tag them."""
    monkeypatch.setattr(server, "_SOLVE_CACHE", server._SOLVE_CACHE.__class__())
    monkeypatch.setattr(server, "_CUTS_SRC_CACHE", server._CUTS_SRC_CACHE.__class__())
    monkeypatch.setattr(server, "_SWEEP_Z_CACHE", server._SWEEP_Z_CACHE.__class__())
    monkeypatch.setattr(server, "_SWEEP_Z_WRITER", {})
    monkeypatch.setattr(server, "_USER_CACHE_KEYS", {"solve": set(), "sweep": set()})
    server._SOLVE_CACHE["k_user"] = {"geometry": "user.x"}
    server._SOLVE_CACHE["k_cat"] = {"geometry": "dipoles.invvee"}
    server._CUTS_SRC_CACHE["k_user"] = {"wires": []}
    server._CUTS_SRC_CACHE["k_cat"] = {"wires": []}
    server._SWEEP_Z_CACHE[("d_user", 7)] = (1.0, 0.0, None, None)
    server._SWEEP_Z_CACHE[("d_user", 8)] = (1.0, 0.0, None, None)
    server._SWEEP_Z_CACHE[("d_cat", 7)] = (1.0, 0.0, None, None)
    server._SWEEP_Z_WRITER["d_user"] = "s1"
    server._SWEEP_Z_WRITER["d_cat"] = "s1"
    server._USER_CACHE_KEYS["solve"].add("k_user")
    server._USER_CACHE_KEYS["sweep"].add("d_user")


def _assert_only_user_entries_gone():
    assert "k_user" not in server._SOLVE_CACHE and "k_cat" in server._SOLVE_CACHE
    assert "k_user" not in server._CUTS_SRC_CACHE and "k_cat" in server._CUTS_SRC_CACHE
    assert ("d_user", 7) not in server._SWEEP_Z_CACHE
    assert ("d_user", 8) not in server._SWEEP_Z_CACHE
    assert ("d_cat", 7) in server._SWEEP_Z_CACHE
    assert "d_user" not in server._SWEEP_Z_WRITER and "d_cat" in server._SWEEP_Z_WRITER
    # The index is spent: a second refresh has nothing to evict.
    assert server._USER_CACHE_KEYS == {"solve": set(), "sweep": set()}


def test_eviction_drops_user_entries_and_keeps_the_catalog(seeded):
    counts = server._evict_user_design_caches()
    assert counts == {"solve": 1, "cuts": 1, "sweep": 2}
    _assert_only_user_entries_gone()
    assert server._evict_user_design_caches() == {"solve": 0, "cuts": 0, "sweep": 0}


def test_the_examples_refresh_is_the_invalidation_signal(seeded, userdir):
    """GET /examples is what the refresh button (and a page load) calls."""
    with TestClient(server.app) as c:
        r = c.get("/examples")
        assert r.status_code == 200
    _assert_only_user_entries_gone()


def test_the_write_sites_tag_user_geometries_only():
    assert server._is_user_geometry({"geometry": "user.plumb_vertical_slope"})
    assert not server._is_user_geometry(
        {"geometry": "verticals.buried_radial_vertical"}
    )
    assert not server._is_user_geometry({})


def test_an_evicted_entry_no_longer_answers_an_identical_request(seeded, monkeypatch):
    """The user-visible property: after the refresh, the same request MISSES
    the cache and is solved again, so the answer follows the file."""
    calls = []
    monkeypatch.setattr(
        server, "_canonical_solve_key", lambda req: "k_user", raising=True
    )
    monkeypatch.setattr(
        server,
        "_solve_uncached",
        lambda req, cancel=None: calls.append(req) or {"geometry": req["geometry"]},
    )
    monkeypatch.setattr(server, "_attach_request_cuts", lambda out, req: None)
    req = {"geometry": "user.x"}
    assert server.solve(req)["cache_hit"] is True and calls == []
    server._evict_user_design_caches()
    out = server.solve(req)
    assert out["cache_hit"] is False and len(calls) == 1
    # ...and the re-solve is tagged again, so the NEXT refresh evicts it too.
    assert "k_user" in server._USER_CACHE_KEYS["solve"]
