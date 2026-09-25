"""AK#1727: a settled change with the compare table open fills Z once.

The live row sends /pattern_metrics right after every settled /ws solve, for
the design that solve just described. It used to build its own engine and fill
Z again. A momwire solve now files a thunk that computes the metrics off its
own state, and /pattern_metrics takes it when the SESSION, the GENERATION and
the exact REQUEST all match; anything else solves fresh.

Driven through the real routes (the /ws socket, then POST /pattern_metrics),
counting fills with a spy on `BSplineSolver._compute_Z_operator`:

- solve then metrics is one fill, and the metrics are bit-identical to the
  fresh `far_field_metrics` path, on a plain and a network design;
- the snapshot releases the network engine's held Z, and its evaluator is
  bit-identical to `gain_evaluator` on a fresh engine;
- negative controls: a knob change, a frequency change, another session,
  another generation and a gen-less (pinned-row) request all solve fresh,
  and match the fresh path;
- the knob and frequency controls FAIL against a key that ignores the
  request (the negative control of the negative controls).
"""

from __future__ import annotations

from collections import OrderedDict

import numpy as np
import pytest
from fastapi.testclient import TestClient
from momwire import BSplineSolver

# server first: adapter <-> examples resolve their import cycle examples-first.
from antennaknobs.web import server  # isort: skip
from antennaknobs.web import adapter  # isort: skip

PLAIN = {"geometry": "dipoles.invvee", "solver": "momwire", "ground": True}
# A network design (the tuner is an MNA network), which is the path whose
# engine holds a shared Z (`_share_z_fill`).
NETWORK = {"geometry": "wire.doublet_ladder_tuner", "solver": "momwire"}


@pytest.fixture
def fills(monkeypatch):
    calls: list[int] = []
    real = BSplineSolver._compute_Z_operator

    def spy(self, *a, **k):
        calls.append(1)
        return real(self, *a, **k)

    monkeypatch.setattr(BSplineSolver, "_compute_Z_operator", spy)
    return calls


@pytest.fixture
def client(monkeypatch):
    # Fresh caches: a result-cache hit would skip the solve (and file nothing),
    # and an entry left by another test must not answer this one.
    monkeypatch.setattr(server, "_SOLVE_CACHE", OrderedDict())
    monkeypatch.setattr(server, "_SOLVED_METRICS", OrderedDict())
    return TestClient(server.app)


def _live_solve(client, body, seq):
    with client.websocket_connect("/ws") as ws:
        ws.send_json({**body, "_seq": seq})
        while True:
            res = ws.receive_json()
            if res.get("_seq") == seq:
                break
    assert "error" not in res, res["error"]
    assert res["cache_hit"] is False
    return res


def _metrics(client, body, gen=None):
    payload = body if gen is None else {**body, "_gen": gen}
    resp = client.post("/pattern_metrics", json=payload).json()
    assert resp.get("available"), resp
    return resp["metrics"]


def _fresh(body):
    """What the metrics were before AK#1727: their own engine, their own fill."""
    return server.example_for(body["geometry"]).far_field_metrics(dict(body))


def _bits(metrics):
    return {
        k: (np.float64(v).tobytes() if isinstance(v, float) else v)
        for k, v in metrics.items()
    }


@pytest.mark.parametrize("design", [PLAIN, NETWORK], ids=["plain", "network"])
def test_solve_then_metrics_fills_once_and_matches_the_fresh_path(
    design, fills, client
):
    body = {**design, "_session": "tab-A"}
    _live_solve(client, body, seq=1)
    assert len(fills) == 1
    got = _metrics(client, body, gen=1)
    assert len(fills) == 1, "the live row's metrics must not fill Z again"
    assert _bits(got) == _bits(_fresh(body))


def test_the_snapshot_releases_the_held_z_and_matches_gain_evaluator():
    ex = server.example_for(NETWORK["geometry"])

    def engine():
        builder = adapter._build_builder(ex.builder_cls, NETWORK)
        return adapter._make_momwire_engine(dict(NETWORK), builder)

    eng = engine()
    eng.impedance()
    eng.current_distribution()
    eng.input_power()
    assert eng._z_fill_held[0] is not None, "the network path holds a Z"
    build = eng.solved_gain_evaluator()
    assert eng._z_fill_held[0] is None, "the snapshot must not keep Z alive"

    theta = np.linspace(-10.0, 100.0, 23)
    phi = np.linspace(0.0, 360.0, 37)
    kept = build()
    fresh = engine().gain_evaluator()
    assert kept(theta, phi).tobytes() == fresh(theta, phi).tobytes()
    assert kept.moment_below == fresh.moment_below
    assert kept.has_ground == fresh.has_ground


def test_an_engine_that_never_solved_has_no_snapshot():
    ex = server.example_for(PLAIN["geometry"])
    builder = adapter._build_builder(ex.builder_cls, PLAIN)
    assert (
        adapter._make_momwire_engine(dict(PLAIN), builder).solved_gain_evaluator()
        is None
    )


# --- negative controls -------------------------------------------------------


# The knob and the frequency the controls move, stated explicitly in the solved
# request, so a moved request differs from it in a VALUE, not in which keys it
# carries.
EXPLICIT = {**PLAIN, "angle_deg": 31.6846, "measurement_freq_mhz": 28.47}


def _assert_moved_request_solves_fresh(client, fills, moved):
    solved = {**EXPLICIT, "_session": "tab-A"}
    _live_solve(client, solved, seq=1)
    stale = _metrics(client, solved, gen=1)
    asked = {**solved, **moved}
    n0 = len(fills)
    got = _metrics(client, asked, gen=1)
    assert len(fills) == n0 + 1, "a different request must solve fresh"
    want = _fresh(asked)
    # Not vacuous: the moved design's metrics differ from the solved one's.
    assert _bits(want) != _bits(stale)
    assert _bits(got) == _bits(want)


def _knob_change(client, fills):
    _assert_moved_request_solves_fresh(client, fills, {"angle_deg": 20.0})


def _frequency_change(client, fills):
    _assert_moved_request_solves_fresh(client, fills, {"measurement_freq_mhz": 28.9})


def test_a_knob_change_is_not_served_the_old_state(fills, client):
    _knob_change(client, fills)


def test_a_frequency_change_is_not_served_the_old_state(fills, client):
    _frequency_change(client, fills)


def test_a_knob_move_below_the_result_cache_grid_is_a_different_request(fills, client):
    """The result cache quantises floats to 1e-6; this key must not."""
    solved = {**EXPLICIT, "_session": "tab-A"}
    _live_solve(client, solved, seq=1)
    nudged = {**solved, "angle_deg": solved["angle_deg"] + 1e-8}
    n0 = len(fills)
    _metrics(client, nudged, gen=1)
    assert len(fills) == n0 + 1


def test_another_session_does_not_share_the_state(fills, client):
    _live_solve(client, {**PLAIN, "_session": "tab-A"}, seq=1)
    other = {**PLAIN, "_session": "tab-B"}
    n0 = len(fills)
    got = _metrics(client, other, gen=1)
    assert len(fills) == n0 + 1, "a second session must solve its own"
    assert _bits(got) == _bits(_fresh(other))


@pytest.mark.parametrize("gen", [2, None], ids=["newer-gen", "gen-less"])
def test_another_generation_does_not_take_the_state(gen, fills, client):
    body = {**PLAIN, "_session": "tab-A"}
    _live_solve(client, body, seq=1)
    n0 = len(fills)
    _metrics(client, body, gen=gen)
    assert len(fills) == n0 + 1


def test_the_sessions_kept_are_bounded(fills, client, monkeypatch):
    monkeypatch.setattr(server, "_SOLVED_METRICS_MAX", 2)
    for i, s in enumerate(("a", "b", "c"), start=1):
        _live_solve(client, {**PLAIN, "_session": s, "angle_deg": 30.0 + i}, seq=1)
    assert list(server._SOLVED_METRICS) == ["b", "c"]


@pytest.mark.parametrize("check", [_knob_change, _frequency_change])
def test_the_controls_fail_against_a_key_that_ignores_the_request(
    check, fills, client, monkeypatch
):
    monkeypatch.setattr(server, "_solved_metrics_key", lambda _req: "stale")
    with pytest.raises(AssertionError):
        check(client, fills)
