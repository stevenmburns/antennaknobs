"""The hosted fleet (AK#405): session pinning and the usage counters.

Pinning: on Fly (``FLY_MACHINE_ID`` set) every HTTP response names its
machine, the /ws channel's first message does too, and a /ws upgrade pinned to
another machine is answered with ``fly-replay`` rather than accepted. Off Fly
all three are absent and nothing changes. The client half (lib/pin.ts) is
pinned by pin.test.tsx, including a two-machine simulation of an opened
deck's /deck, /ws and /param_sweep; the wire names both halves use are held
equal here.

Counters: per live solve, per live-solve connection, per deck open, with
labels from fixed rosters only, and nothing at all unless hosted.
"""

from __future__ import annotations

import json
import re
import urllib.error
import urllib.request
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from starlette.testclient import WebSocketDenialResponse

from antennaknobs.web import decks, hosting, server

FRONTEND = Path(server.__file__).parent / "frontend" / "src"

DIPOLE = """CM pinning test dipole
CE
GW 1 11 0 -5.1 10 0 5.1 10 0.001
GE 0
EX 0 1 6 0 1 0
FR 0 1 0 0 14.0 0
EN
"""

SOLVE = {
    "geometry": "dipoles.invvee",
    "measurement_freq_mhz": 28.47,
    "momwire_model": "bspline",
    "_session": "pin-405",
    "_seq": 1,
}


@pytest.fixture()
def client() -> TestClient:
    return TestClient(server.app)


@pytest.fixture()
def on_fly(monkeypatch):
    monkeypatch.setenv("FLY_MACHINE_ID", "e2865013be1d86")
    return "e2865013be1d86"


@pytest.fixture()
def off_fly(monkeypatch):
    monkeypatch.delenv("FLY_MACHINE_ID", raising=False)


@pytest.fixture()
def counters(monkeypatch):
    c = hosting.UsageCounters(enabled=True)
    monkeypatch.setattr(server, "_METRICS", c)
    monkeypatch.setattr(server, "_SOLVE_CACHE", server._SOLVE_CACHE.__class__())
    return c


@pytest.fixture()
def fresh_decks(monkeypatch):
    st = server._DECK_SETTINGS
    monkeypatch.setattr(server, "_DECK_OPENS", decks.RateLimiter(st.opens_per_min))
    store = decks.DeckStore(st, server._register_deck, server._unregister_deck)
    monkeypatch.setattr(server, "_DECK_STORE", store)
    yield store
    for key in list(server.EXAMPLES):
        if decks.is_deck(key):
            del server.EXAMPLES[key]


# ---------------------------------------------------------------------------
# Pinning
# ---------------------------------------------------------------------------


def test_off_fly_nothing_is_advertised(client, off_fly):
    assert hosting.machine_id() is None
    assert hosting.machine_hello() is None
    for r in (client.get("/healthz"), client.get("/capabilities")):
        assert hosting.MACHINE_HEADER not in r.headers
    # The /ws channel's first message is the solve's own answer.
    with client.websocket_connect("/ws") as ws:
        ws.send_text(json.dumps(SOLVE))
        first = json.loads(ws.receive_text())
    assert first.get("_kind") is None and first["_seq"] == 1


def test_off_fly_a_pin_in_the_ws_url_is_ignored(client, off_fly):
    # Defence in depth: a stale page that still names a machine is served.
    with client.websocket_connect("/ws?fly_instance=abc123") as ws:
        ws.send_text(json.dumps(SOLVE))
        assert json.loads(ws.receive_text())["_seq"] == 1


def test_on_fly_every_response_names_its_machine(client, on_fly):
    for r in (
        client.get("/healthz"),
        client.get("/capabilities"),
        client.post("/deck", json={"name": "x.nec", "text": "not a deck"}),
    ):
        assert r.headers[hosting.MACHINE_HEADER] == on_fly


def test_on_fly_the_channel_says_its_machine_first(client, on_fly):
    with client.websocket_connect("/ws") as ws:
        assert json.loads(ws.receive_text()) == {"_kind": "machine", "id": on_fly}
        ws.send_text(json.dumps(SOLVE))
        assert json.loads(ws.receive_text())["_seq"] == 1


def test_on_fly_a_channel_pinned_here_is_accepted(client, on_fly):
    with client.websocket_connect(f"/ws?fly_instance={on_fly}") as ws:
        assert json.loads(ws.receive_text())["id"] == on_fly


def test_on_fly_a_channel_pinned_elsewhere_is_replayed_there(client, on_fly):
    with pytest.raises(WebSocketDenialResponse) as denied:
        with client.websocket_connect("/ws?fly_instance=148e21ea7d4e89"):
            pass
    resp = denied.value
    assert resp.headers["fly-replay"] == "instance=148e21ea7d4e89"


def test_a_malformed_pin_is_never_echoed(client, on_fly):
    # Only a Fly-shaped id reaches a header; anything else is ignored.
    with client.websocket_connect("/ws?fly_instance=x%0d%0aSet-Cookie:a") as ws:
        assert json.loads(ws.receive_text())["id"] == on_fly


def test_the_client_uses_the_same_wire_names():
    src = (FRONTEND / "lib" / "pin.ts").read_text()
    assert f'MACHINE_HEADER = "{hosting.MACHINE_HEADER}"' in src
    assert f'WS_PIN_PARAM = "{hosting.WS_PIN_PARAM}"' in src
    assert 'PIN_HEADER = "fly-force-instance-id"' in src
    assert (
        '"machine"' in (FRONTEND / "components/session/useSolveChannel.ts").read_text()
    )


def test_every_session_request_goes_through_the_pin():
    # A raw fetch of an API route would escape the pin and could land on
    # another machine than the session's lane. The crash reporter is the one
    # deliberate exception (it must work whatever state the page is in).
    raw = re.compile(r'(?<![\w.])fetch\("/')
    offenders = [
        str(p.relative_to(FRONTEND))
        for p in FRONTEND.rglob("*.ts*")
        if "__tests__" not in p.parts
        and p.name not in ("pin.ts", "clientErrors.ts")
        and raw.search(p.read_text())
    ]
    assert offenders == []


# ---------------------------------------------------------------------------
# Counters
# ---------------------------------------------------------------------------


def test_off_unless_hosted():
    c = hosting.UsageCounters(enabled=False)
    c.inc("ak_solves_total", "dipoles.invvee", "bspline", "free")
    assert c.value("ak_solves_total", "dipoles.invvee", "bspline", "free") == 0
    assert c.exposition() == ""
    # And the server's own instance is built from the hosted switch.
    assert server._METRICS.enabled is server._HOSTED


def test_a_live_solve_and_its_session_are_counted(client, counters, off_fly):
    with client.websocket_connect("/ws") as ws:
        ws.send_text(json.dumps(SOLVE))
        assert "error" not in json.loads(ws.receive_text())
        # Same request again: a cache hit is not a solve the server paid for.
        ws.send_text(json.dumps({**SOLVE, "_seq": 2}))
        assert json.loads(ws.receive_text())["cache_hit"] is True
    assert counters.series("ak_solves_total") == {
        ("dipoles.invvee", "bspline", "free"): 1
    }
    assert counters.series("ak_sessions_total") == {("catalog",): 1}
    # A second connection is a second session.
    with client.websocket_connect("/ws") as ws:
        ws.send_text(json.dumps({**SOLVE, "ground": True, "ground_model": "pec"}))
        ws.receive_text()
    assert counters.value("ak_sessions_total", "catalog") == 2
    assert counters.value("ak_solves_total", "dipoles.invvee", "bspline", "pec") == 1


def test_deck_opens_are_counted_by_dialect_and_outcome(
    client, counters, fresh_decks, monkeypatch
):
    ok = client.post("/deck", json={"name": "d.nec", "text": DIPOLE})
    assert ok.status_code == 200, ok.text
    assert counters.value("ak_deck_opens_total", "nec2", "ok") == 1
    bad = client.post("/deck", json={"name": "d.nec", "text": "GW junk\nEN\n"})
    assert bad.status_code in (400, 422)
    assert counters.value("ak_deck_opens_total", "auto", "refused") == 1
    monkeypatch.setattr(server, "_DECK_OPENS", decks.RateLimiter(1))
    client.post("/deck", json={"name": "a.nec", "text": DIPOLE.replace("14.0", "14.1")})
    busy = client.post(
        "/deck", json={"name": "b.nec", "text": DIPOLE.replace("14.0", "14.2")}
    )
    assert busy.status_code == 429
    assert counters.value("ak_deck_opens_total", "auto", "busy") == 1
    # The opened deck's live session counts as a deck session, its solves
    # under the literal "deck", never its key or file name.
    key = ok.json()["key"]
    with client.websocket_connect("/ws") as ws:
        ws.send_text(
            json.dumps({"geometry": key, "momwire_model": "bspline", "_seq": 1})
        )
        assert "error" not in json.loads(ws.receive_text())
    assert counters.value("ak_sessions_total", "deck") == 1
    text = counters.exposition()
    assert key not in text and "d.nec" not in text
    assert 'ak_solves_total{design="deck",engine="bspline",ground="free"} 1' in text


@pytest.mark.parametrize(
    "key, design, kind",
    [
        ("dipoles.invvee", "dipoles.invvee", "catalog"),
        ("deck.0123456789ab", "deck", "deck"),
        ("user.my_secret_design", "user", "user"),
        ("not.in.catalog", "other", "other"),
        (None, "other", "other"),
    ],
)
def test_design_labels_are_bounded(key, design, kind):
    assert hosting.design_label(key, server.EXAMPLES) == design
    assert hosting.session_kind(key, server.EXAMPLES) == kind


def test_engine_and_ground_labels_come_from_fixed_rosters():
    from antennaknobs.web import adapter

    models = adapter._BACKENDS_BY_NAME
    assert hosting.engine_label({"solver": "nec5"}, models) == "nec5"
    assert hosting.engine_label({"momwire_model": "bspline"}, models) == "bspline"
    assert hosting.engine_label({}, models) == "momwire"
    assert hosting.engine_label({"momwire_model": "x" * 99}, models) == "other"
    assert hosting.engine_label({"solver": "../etc"}, models) == "other"
    assert hosting.ground_label({"ground": False}, "sommerfeld") == "free"
    assert hosting.ground_label({"ground": True}, "sommerfeld") == "sommerfeld"
    assert hosting.ground_label({"ground": True}, "lava") == "other"
    assert hosting.dialect_label("nec5") == "nec5"
    assert hosting.dialect_label(None) == "auto"
    assert hosting.dialect_label("<script>") == "other"


def test_exposition_is_prometheus_text():
    c = hosting.UsageCounters(enabled=True)
    c.inc("ak_solves_total", "dipoles.invvee", "bspline", "free")
    c.inc("ak_solves_total", "dipoles.invvee", "bspline", "free")
    c.inc("ak_deck_opens_total", "nec2", "ok")
    text = c.exposition()
    assert "# TYPE ak_solves_total counter" in text
    assert (
        'ak_solves_total{design="dipoles.invvee",engine="bspline",ground="free"} 2'
        in text
    )
    assert 'ak_deck_opens_total{dialect="nec2",outcome="ok"} 1' in text
    assert "# TYPE ak_sessions_total counter" in text
    with pytest.raises(ValueError):
        c.inc("ak_solves_total", "only-one-label")


def test_metrics_endpoint_serves_the_counters_on_its_own_port():
    c = hosting.UsageCounters(enabled=True)
    c.inc("ak_sessions_total", "catalog")
    srv = hosting.serve_metrics(c, host="127.0.0.1", port=0)
    try:
        port = srv.server_address[1]
        with urllib.request.urlopen(f"http://127.0.0.1:{port}/metrics", timeout=5) as r:
            body = r.read().decode()
            assert r.headers["Content-Type"].startswith("text/plain; version=0.0.4")
        assert 'ak_sessions_total{kind="catalog"} 1' in body
        with pytest.raises(urllib.error.HTTPError) as e:
            urllib.request.urlopen(f"http://127.0.0.1:{port}/", timeout=5)
        assert e.value.code == 404
    finally:
        srv.shutdown()
        srv.server_close()


def test_the_metrics_endpoint_starts_with_the_server_only_when_hosted(monkeypatch):
    monkeypatch.setenv("ANTENNAKNOBS_METRICS_PORT", "0")
    started: list = []
    monkeypatch.setattr(server, "_METRICS_SERVER", started)
    monkeypatch.setattr(server, "_METRICS", hosting.UsageCounters(enabled=False))
    with TestClient(server.app):
        pass
    assert started == []
    monkeypatch.setattr(server, "_METRICS", hosting.UsageCounters(enabled=True))
    try:
        with TestClient(server.app):
            pass
        assert len(started) == 1
    finally:
        for srv in started:
            srv.shutdown()
            srv.server_close()


def test_fly_toml_points_the_scraper_at_the_endpoint():
    import tomllib

    root = Path(server.__file__).parents[3]
    cfg = tomllib.loads((root / "fly.toml").read_text())
    assert cfg["metrics"]["port"] == hosting.METRICS_PORT_DEFAULT
    assert cfg["metrics"]["path"] == hosting.METRICS_PATH
    # Not behind the public service: the edge never serves the counters.
    assert cfg["http_service"]["internal_port"] != hosting.METRICS_PORT_DEFAULT
