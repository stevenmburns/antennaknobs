"""The tracker's wire path: `_track_step` and the /ws route (#1220).

The tracker itself is gated in `test_tracker_1220.py`. This covers the parts
that only exist once it is wired to a socket:

- **staleness** — what makes a tracker rebuild rather than continue. A tracker
  is a linearisation about one point on one design, so anything that changes
  the surface has to force a fresh root find.
- **the display solve is reused** — the tracker's own solve at the committed
  point IS the tick's render, so routing it back costs nothing. Re-solving it
  would double the cost of every tick and destroy the whole cost model.
- **refusals reach the client** as a status, not as a solve-error banner: the
  mode simply cannot be entered.
- **per-connection isolation** — a tracker must never be shared between
  sockets, or one user's drag is answered with another user's tangent.
"""

from __future__ import annotations

import json
import pytest
from starlette.testclient import TestClient

from antennaknobs.web import server
from antennaknobs.web.server import _track_signature, _track_step


def _stub(calls):
    """X = 40·(hold − 0.5) − 8·(drag − 0.2): the root walks with the drag.

    Patched in as `server.solve` rather than as a registry example, so the
    whole response pipeline (derived EM fields, gain norm, wires) is out of the
    picture. What is under test here is the tracker WIRING -- staleness, solve
    reuse, refusal routing, per-connection isolation -- not the solve stack.
    """

    def fake_solve(req, cancel=None):
        calls.append(dict(req))
        h = float(req.get("hold", 0.5))
        d = float(req.get("drag", 0.2))
        return {
            "z_in_re": 50.0,
            "z_in_im": 40.0 * (h - 0.5) - 8.0 * (d - 0.2),
            "z0_ohms": 50.0,
            "geometry": req.get("geometry"),
        }

    return fake_solve


def _req(value, **over):
    t = {
        "objective": "resonance",
        "free": [{"name": "hold", "min": 0.0, "max": 1.0}],
        "drag": {"name": "drag", "value": value, "span": 1.0},
    }
    t.update(over)
    return {
        "geometry": "fake.trk",
        "measurement_freq_mhz": 28.47,
        "momwire_model": "bspline",
        "hold": 0.5,
        "drag": value,
        "_track": t,
    }


@pytest.fixture(scope="module")
def client() -> TestClient:
    return TestClient(server.app)


@pytest.fixture
def stubbed(monkeypatch):
    calls: list[dict] = []
    monkeypatch.setattr(server, "solve", _stub(calls))
    server._SOLVE_CACHE.clear()
    return calls


# ---------------------------------------------------------------------------
# staleness
# ---------------------------------------------------------------------------


def test_the_signature_covers_everything_that_moves_the_surface():
    base = _req(0.2)
    sig = _track_signature(base)
    for mutate in (
        lambda r: r.update(geometry="other"),
        lambda r: r["_track"].update(objective="match_z0"),
        lambda r: r["_track"].update(free=[{"name": "hold", "min": 0.1, "max": 1.0}]),
        lambda r: r["_track"]["drag"].update(name="elsewhere"),
        lambda r: r.update(freq=14.1),
    ):
        r = json.loads(json.dumps(base))
        mutate(r)
        assert _track_signature(r) != sig, mutate


def test_an_ordinary_solve_invalidates_the_tracker(stubbed):
    """Moving something the tracker was NOT holding means the tangent was taken
    about a point that has since moved, so the next tick must re-find the root
    rather than extrapolate from it."""
    box = {"t": None, "sig": None}
    _track_step(_req(0.20), box)
    assert box["sig"] is not None
    box["sig"] = None  # what the ws loop does on a plain solve
    out = _track_step(_req(0.21), box)
    assert out["_track"]["status"] == "tracking"


# ---------------------------------------------------------------------------
# the cost model
# ---------------------------------------------------------------------------


def test_the_tick_reuses_the_trackers_own_solve(stubbed):
    """A tick costs ONE solve. If the route re-solved the committed point for
    the render, every tick would cost two and the whole design would be moot."""
    box = {"t": None, "sig": None}
    _track_step(_req(0.20), box)
    stubbed.clear()
    out = _track_step(_req(0.21), box)
    assert out["_track"]["status"] == "tracking"
    assert len(stubbed) == 1, stubbed
    # ...and the response really is the solve at the committed knob value.
    assert out["z_in_im"] == pytest.approx(
        40.0 * (out["_track"]["params"]["hold"] - 0.5) - 8.0 * (0.21 - 0.2)
    )


def test_a_run_of_ticks_costs_one_solve_each(stubbed):
    box = {"t": None, "sig": None}
    _track_step(_req(0.20), box)
    stubbed.clear()
    n = 12
    for i in range(1, n + 1):
        out = _track_step(_req(0.20 + 0.01 * i), box)
    assert out["_track"]["status"] == "tracking"
    assert len(stubbed) == n, (len(stubbed), n)


# ---------------------------------------------------------------------------
# refusals
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "over,needle",
    [
        ({"objective": "swr"}, "minimisation"),
        (
            {
                "objective": "match_z0",
                "free": [{"name": "hold", "min": 0.0, "max": 1.0}],
            },
            "exactly 2",
        ),
    ],
)
def test_a_refusal_comes_back_as_a_status_not_an_error(stubbed, over, needle):
    box = {"t": None, "sig": None}
    out = _track_step(_req(0.20, **over), box)
    assert out["_track"]["status"] == "refused"
    assert needle in out["_track"]["message"]
    assert "error" not in out  # not a solve-error banner
    assert out["z_in_re"] == pytest.approx(50.0)  # the design still rendered
    assert box["t"] is None


# ---------------------------------------------------------------------------
# the socket
# ---------------------------------------------------------------------------


def test_the_ws_route_tracks_across_ticks(client: TestClient, stubbed):
    with client.websocket_connect("/ws") as ws:
        ws.send_text(json.dumps({**_req(0.20), "_seq": 1}))
        first = json.loads(ws.receive_text())
        # Far enough that the residual exceeds tolerance: a smaller step is
        # legitimately answered by NOT moving the knob, which is the point of
        # the tolerance and not something to assert against.
        ws.send_text(json.dumps({**_req(0.55), "_seq": 2}))
        second = json.loads(ws.receive_text())
    assert first["_track"]["status"] == "tracking"
    assert second["_track"]["status"] == "tracking"
    # The root is hold = 0.5 + (drag − 0.2)/5, so it moved with the drag.
    assert second["_track"]["params"]["hold"] > first["_track"]["params"]["hold"]
    assert second["_seq"] == 2


def test_each_socket_gets_its_own_tracker(client: TestClient, stubbed):
    """Two connections, two trackers. Sharing one would answer a drag with a
    tangent taken on someone else's design."""
    with client.websocket_connect("/ws") as a:
        a.send_text(json.dumps({**_req(0.20), "_seq": 1}))
        json.loads(a.receive_text())
        with client.websocket_connect("/ws") as b:
            b.send_text(json.dumps({**_req(0.20), "_seq": 1}))
            rb = json.loads(b.receive_text())
    # B's first message is a START (a fresh root find), not a continuation of
    # A's drag — it lands on the root for its own drag value.
    assert rb["_track"]["status"] == "tracking"
    assert rb["_track"]["params"]["hold"] == pytest.approx(0.5, abs=1e-3)
