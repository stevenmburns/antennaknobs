"""Opt-in base-sweep read-through of the per-freq Z cache (issue #763).

The cache's two documented properties survive: two sessions issuing the
same sweep still both compute (a session only reads back its OWN writes),
and user designs never read through (the edited-on-disk exposure)."""

from __future__ import annotations

import json

import pytest
from fastapi.testclient import TestClient

from antennaknobs.web import server as _server


@pytest.fixture()
def client() -> TestClient:
    return TestClient(_server.app)


FREQS = [28.0, 28.25, 28.5]


def _sweep(client, session: str, *, reuse: bool = True) -> int:
    """Run one streamed sweep; returns how many points came from the cache
    (a get is only attempted when read-through is active, so hits are the
    honest zero-engine-solves count)."""
    before = dict(_server._SWEEP_Z_STATS)
    body = {
        "geometry": "dipoles.invvee",
        "momwire_model": "bspline",
        "freqs_mhz": FREQS,
        "_session": session,
        "reuse_cached_z": reuse,
    }
    with client.stream("POST", "/sweep", json=body) as resp:
        assert resp.status_code == 200
        points = [
            json.loads(line)
            for line in resp.iter_lines()
            if line.strip() and not json.loads(line).get("done")
        ]
    assert len(points) == len(FREQS)
    return _server._SWEEP_Z_STATS["hits"] - before["hits"]


def test_same_session_scrub_reads_its_own_writes(client):
    assert _sweep(client, "s763-a") == 0  # first pass computes everything
    assert _sweep(client, "s763-a") == len(FREQS)  # scrub back: all cached


def test_two_sessions_both_compute(client):
    """The #382 lane contract: a second session issuing the same sweep must
    compute — it only starts hitting once its OWN sweep has written."""
    assert _sweep(client, "s763-b1") == 0
    assert _sweep(client, "s763-b2") == 0  # other session: computes
    assert _sweep(client, "s763-b2") == len(FREQS)  # its own write serves it


def test_without_the_flag_every_sweep_computes(client):
    assert _sweep(client, "s763-c", reuse=False) == 0
    assert _sweep(client, "s763-c", reuse=False) == 0  # still no read path


def test_gate_refuses_user_designs_and_anonymous_sessions():
    key = "any-design-key"
    _server._SWEEP_Z_WRITER[key] = "s763-d"
    base = {"reuse_cached_z": True, "_session": "s763-d"}
    assert _server._base_sweep_may_read_cache(
        dict(base, geometry="dipoles.invvee"), key
    )
    # User designs: the file can change on disk under an unchanged key.
    assert not _server._base_sweep_may_read_cache(
        dict(base, geometry="user.mydesign"), key
    )
    assert not _server._base_sweep_may_read_cache(dict(base, geometry="@deck.nec"), key)
    # No session identity -> no "own writes" to speak of.
    assert not _server._base_sweep_may_read_cache(
        {"reuse_cached_z": True, "geometry": "dipoles.invvee"}, key
    )
    # Another session's writes are invisible.
    assert not _server._base_sweep_may_read_cache(
        dict(base, _session="s763-other", geometry="dipoles.invvee"), key
    )
