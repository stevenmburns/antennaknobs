"""Opened decks: a visitor's own NEC deck on the (hosted) workbench.

AC6LA, QRZ 1005128 #40/#42: let an MMANA / 4nec2 / EZNEC user share and study
a model that is not in the catalog without installing anything. The link
carries the deck; the server parses it from text, bounded before anything is
built, and solves it under a wall-time budget and one server-wide slot.

Laid out by layer: the text route against the file route, the structure
limits (which must refuse BEFORE a card builds anything), the payload and the
rate limit, admission, the gate's busy / budget behaviour, and the routes.
"""

from __future__ import annotations

import asyncio
import base64
import json
import threading
import time
import zlib
from pathlib import Path
from types import SimpleNamespace

import momwire
import numpy as np
import pytest
from fastapi.testclient import TestClient

from antennaknobs import nec_import
from antennaknobs.engines import MomwireEngine
from antennaknobs.file_designs import builder_from_file, builder_from_text
from antennaknobs.nec_import import GeometryLimits, parse_nec
from antennaknobs.simnec_import import parse_ssn
from antennaknobs.web import cost, decks, server, user_designs

FIXTURES = Path(__file__).parent / "fixtures"

# A UR0GT-like inverted L: 306 segments over real ground, the size class of
# the decks the hosted limits are drawn around.
INVL_306 = """CM UR0GT-like inverted L, 306 segments
CE
GW 1 100 0 0 0.3 0 0 12.3 0.001
GW 2 206 0 0 12.3 25.0 0 12.3 0.001
GE 1
GN 2 0 0 0 13 0.005
EX 0 1 1 0 1 0
FR 0 1 0 0 3.6 0
EN
"""

DIPOLE = """CM opened-deck test dipole
CE
GW 1 11 0 -5.1 10 0 5.1 10 0.001
GE 0
EX 0 1 6 0 1 0
FR 0 1 0 0 14.0 0
EN
"""

LIMITS = GeometryLimits(3000, 200, note="run it locally")


def _z(cls) -> complex:
    return complex(MomwireEngine(cls(), ground=None).impedance()[0])


def _payload(text: str, name: str = "dipole.nec") -> dict:
    c = zlib.compressobj(9, zlib.DEFLATED, -15)
    packed = c.compress(text.encode()) + c.flush()
    return {"name": name, "z": base64.urlsafe_b64encode(packed).decode().rstrip("=")}


# ---------------------------------------------------------------------------
# The text route is the file route
# ---------------------------------------------------------------------------

_DECKS = [
    FIXTURES / "ac6la_1678" / "dan118-eznec-lnet.nec",
    FIXTURES / "sy_knobs_1705" / "3el-inverted-V.nec",
    FIXTURES / "ssn_dcl_knobs_1714" / "half-squares-sy.ssn",
    "invl306",
    FIXTURES / "opened_decks" / "ezLoadPositionsB.nec",
]


def _outcome(fn):
    """A solve's Z, or the error it raised (type and text): two routes agree
    when their outcomes are equal, whichever kind it is."""
    try:
        return ("z", fn())
    except Exception as exc:  # noqa: BLE001 — the outcome IS the comparison
        return ("error", type(exc).__name__, str(exc))


@pytest.mark.parametrize("deck", _DECKS, ids=lambda d: getattr(d, "name", d))
def test_text_builder_is_the_file_builder(deck, tmp_path):
    if deck == "invl306":
        path = tmp_path / "invl306.nec"
        path.write_text(INVL_306)
    else:
        path = deck
    text = path.read_text(encoding="utf-8", errors="replace")
    from_file = _outcome(lambda: builder_from_file(str(path)))
    from_text = _outcome(lambda: builder_from_text(path.name, text, limits=LIMITS))
    assert from_file[0] == from_text[0], (from_file, from_text)
    if from_file[0] == "error":
        assert from_file == from_text
        return
    file_cls, text_cls = from_file[1], from_text[1]
    assert text_cls.label == file_cls.label == path.stem
    assert dict(text_cls.default_params) == dict(file_cls.default_params)
    wf = _outcome(lambda: file_cls().build_wires())
    wt = _outcome(lambda: text_cls().build_wires())
    assert repr(wf) == repr(wt)
    zf = _outcome(lambda: _z(file_cls))
    zt = _outcome(lambda: _z(text_cls))
    assert zf[0] == zt[0], (zf, zt)
    if zf[0] == "z":
        assert zt[1] == zf[1]  # the same parse, the same solve: bit-identical
    else:
        assert zf == zt


def test_text_route_reads_only_a_file_name_never_a_path(tmp_path):
    cls = builder_from_text("../../etc/some/dir/dipole.nec", DIPOLE)
    assert cls.label == "dipole"


def test_text_route_refuses_an_unknown_extension_by_name():
    with pytest.raises(ValueError, match=r"\.txt"):
        builder_from_text("dipole.txt", DIPOLE)


# ---------------------------------------------------------------------------
# Structure limits: refused BEFORE the card builds anything
# ---------------------------------------------------------------------------


def _spy(monkeypatch, *names):
    """Replace nec_import's geometry builders with spies: a refusal must come
    before the card runs, so a spy that was called is a failure."""
    called = []
    for n in names:
        real = getattr(nec_import, n)

        def spy(card, wires, _real=real, _n=n):
            called.append(_n)
            return _real(card, wires)

        monkeypatch.setattr(nec_import, n, spy)
    return called


@pytest.mark.parametrize(
    ("cards", "bomb"),
    [
        ("GW 1 5000 0 0 0 0 0 10 0.001", "_gw"),
        ("GW 1 10 0 0 0 0 0 10 0.001\nGR 1 10000", "_gr"),
        ("GW 1 10 0 0 0 0 0 10 0.001\nGM 1 1000000 0 0 0 0 0 1 0", "_gm"),
        ("GH 1 1000000000 1 10 1 1 1 1 0.001", "_gh"),
        ("GA 1 1000000 1 0 90 0.001", "_ga"),
        ("GW 1 20 1 1 1 1 1 10 0.001\nGX 10 111\nGX 100 111\nGX 1000 111", "_gx"),
        ("SY n=1e7\nGW 1 n 0 0 0 0 0 10 0.001", "_gw"),
        ("SY k=100000\nGW 1 10 0 0 0 0 0 10 0.001\nGR 1 k", "_gr"),
        ("SY k=1e400\nGW 1 10 0 0 0 0 0 10 0.001\nGR 1 k", "_gr"),
    ],
)
def test_limits_refuse_before_the_card_builds(monkeypatch, cards, bomb):
    called = _spy(monkeypatch, bomb)
    deck = f"CM bomb\nCE\n{cards}\nGE 0\nEX 0 1 1 0 1 0\nFR 0 1 0 0 14 0\nEN\n"
    t0 = time.perf_counter()
    with pytest.raises(ValueError) as err:
        parse_nec(deck, name="bomb.nec", limits=LIMITS)
    assert time.perf_counter() - t0 < 2.0
    msg = str(err.value)
    assert (
        ("the limit is 3000" in msg)
        or ("the limit is 200" in msg)
        or (
            "finite" in msg  # 1e400 is an infinity the SY evaluator refuses itself
        )
    ), msg
    if "limit" in msg:
        assert "run it locally" in msg
        # The refused card never ran; only earlier cards of its kind did.
        earlier = cards.count(bomb[1:].upper() + " ") - 1
        assert called.count(bomb) == earlier


def test_limits_count_the_wires_too():
    wires = "\n".join(f"GW {i} 1 {i} 0 0 {i} 0 1 0.001" for i in range(1, 202))
    deck = f"CE\n{wires}\nGE 0\nEX 0 1 1 0 1 0\nEN\n"
    with pytest.raises(ValueError, match=r"201 wires \(the limit is 200\)"):
        parse_nec(deck, limits=LIMITS)


def test_without_limits_the_parse_is_unchanged():
    # The bound is opt-in: the file route and the CLI parse what they did.
    deck = parse_nec(
        "CE\nGW 1 5000 0 0 0 0 0 10 0.001\nGE 0\nEX 0 1 1 0 1 0\nEN\n", name="big.nec"
    )
    assert deck.wires[0].n_seg == 5000


def test_a_knob_that_grows_the_deck_past_the_limit_is_refused(monkeypatch):
    text = (
        "CM knob-driven count\nCE\nSY n=11, len=10\n"
        "GW 1 n 0 0 10 0 len 10 0.001\nGE 0\nEX 0 1 6 0 1 0\nFR 0 1 0 0 14 0\nEN\n"
    )
    assert parse_nec(text, limits=LIMITS).wires[0].n_seg == 11
    with pytest.raises(ValueError, match="the limit is 3000"):
        parse_nec(text, sy_overrides={"n": 4001}, limits=LIMITS)
    # Through the builder: the knob re-parse carries the import's limits.
    cls = builder_from_text("knobbed.nec", text, limits=LIMITS)
    knobs = [k for k in dict(cls.default_params) if k.startswith("sy_n")]
    if knobs:  # offered as a knob: a value past the limit is refused by name
        params = dict(cls.default_params)
        params[knobs[0]] = 4001
        with pytest.raises(ValueError, match="the limit is 3000"):
            cls(params).build_wires()


def test_ssn_is_bounded_too():
    text = (FIXTURES / "ssn_dcl_knobs_1714" / "half-squares-sy.ssn").read_text()
    parse_ssn(text, name="half-squares-sy.ssn", limits=LIMITS)  # within
    with pytest.raises(ValueError, match="the limit is 5"):
        parse_ssn(text, name="half-squares-sy.ssn", limits=GeometryLimits(5, 200))


# ---------------------------------------------------------------------------
# Payload, key, rate limit, client address
# ---------------------------------------------------------------------------


def _settings(**kw) -> decks.DeckSettings:
    return decks.DeckSettings(hosted=kw.pop("hosted", True), **kw)


def test_payload_round_trips_and_keys_by_name_and_text():
    name, text = decks.decode_payload(_payload(DIPOLE, "my dipole.nec"), _settings())
    assert (name, text) == ("my dipole.nec", DIPOLE)
    k = decks.deck_key(name, text)
    assert k.startswith("deck.") and len(k) == len("deck.") + 12
    assert decks.deck_key("other.nec", text) != k


def test_oversize_text_is_refused_before_it_parses(monkeypatch):
    def boom(*a, **k):
        raise AssertionError("parsed an over-size deck")

    monkeypatch.setattr("antennaknobs.file_designs.builder_from_text", boom)
    big = DIPOLE + "CM " + "x" * (64 * 1024) + "\n"
    for payload in (_payload(big), {"name": "big.nec", "text": big}):
        with pytest.raises(decks.DeckError) as err:
            decks.decode_payload(payload, _settings())
        assert err.value.status == 413 and "64 KB" in err.value.message


def test_a_compression_bomb_stops_at_the_limit():
    c = zlib.compressobj(9, zlib.DEFLATED, -15)
    packed = c.compress(b"CM " + b"x" * 50_000_000) + c.flush()
    z = base64.urlsafe_b64encode(packed).decode()
    assert len(z) < 128 * 1024  # small on the wire...
    with pytest.raises(decks.DeckError) as err:  # ...refused, never expanded
        decks.decode_payload({"name": "bomb.nec", "z": z}, _settings())
    assert err.value.status == 413


@pytest.mark.parametrize("name", ["model.ez", "model.mmana", "model"])
def test_unsupported_files_are_refused_by_name(name):
    with pytest.raises(decks.DeckError, match=r"\.nec .*\.ssn"):
        decks.decode_payload({"name": name, "text": DIPOLE}, _settings())


def test_rate_limiter_counts_per_key_per_minute():
    now = [0.0]
    rl = decks.RateLimiter(2, clock=lambda: now[0])
    assert rl.allow("a") and rl.allow("a") and not rl.allow("a")
    assert rl.allow("b")
    now[0] = 61.0
    assert rl.allow("a")
    assert decks.RateLimiter(0).allow("x")  # 0 = off (a local install)


def test_client_ip_trusts_fly_then_the_last_forwarded_hop():
    assert decks.client_ip({"fly-client-ip": "1.2.3.4"}, "10.0.0.1") == "1.2.3.4"
    assert (
        decks.client_ip({"x-forwarded-for": "6.6.6.6, 5.6.7.8"}, "10.0.0.1")
        == "5.6.7.8"
    )
    assert decks.client_ip({}, "10.0.0.1") == "10.0.0.1"


# ---------------------------------------------------------------------------
# Admission: fails closed for an opened deck, and PyNEC is refused hosted
# ---------------------------------------------------------------------------


def _ex(est):
    return SimpleNamespace(count_basis=lambda req: est)


def test_admission_fails_closed_for_an_opened_deck_hosted():
    req = {"geometry": "deck.0123456789ab"}
    adm = cost.admit(
        req,
        kind="live",
        use_pynec=False,
        hosted=True,
        example=_ex(None),
        why_unsized=lambda: "wire 3 would have zero length",
    )
    assert adm.verdict == "refuse"
    assert "could not be judged (wire 3 would have zero length)" in adm.reason
    # A catalog design still fails open (the real error surfaces at solve).
    catalog = cost.admit(
        {"geometry": "dipoles.invvee"},
        kind="live",
        use_pynec=False,
        hosted=True,
        example=_ex(None),
    )
    assert catalog.verdict == "run"


def test_pynec_is_refused_for_an_opened_deck_hosted_only():
    req = {"geometry": "deck.0123456789ab", "solver": "pynec"}
    hosted = cost.admit(req, kind="live", use_pynec=True, hosted=True, example=_ex(50))
    assert hosted.verdict == "refuse" and "PyNEC" in hosted.reason
    local = cost.admit(req, kind="live", use_pynec=True, hosted=False, example=_ex(50))
    assert local.verdict == "run"


# ---------------------------------------------------------------------------
# The gate: busy at once, a short wait waited out, the budget
# ---------------------------------------------------------------------------


class _Token:
    def __init__(self) -> None:
        self.cancelled = False

    def cancel(self) -> None:
        self.cancelled = True


def test_busy_answers_at_once_when_the_wait_would_be_long():
    now = [100.0]
    gate = decks.DeckGate(_settings(budget_s=60.0), clock=lambda: now[0])
    assert gate._try_acquire("tab-A")[0]
    now[0] = 105.0  # A has run 5 s of its 60: up to 55 s more

    async def other():
        async with gate.hold(_Token(), "tab-B"):
            raise AssertionError("granted while busy")

    t0 = time.perf_counter()
    with pytest.raises(
        decks.DeckBusy, match=r"busy with another opened deck \(for up to 55 s"
    ):
        asyncio.run(other())
    assert time.perf_counter() - t0 < 2.0
    assert gate.would_refuse("tab-B") is not None
    # The holder's own session is never "another deck".
    assert gate.would_refuse("tab-A") is None


def test_a_short_wait_is_waited_out():
    now = [0.0]
    gate = decks.DeckGate(_settings(budget_s=60.0), clock=lambda: now[0])
    assert gate._try_acquire("tab-A")[0]
    now[0] = 55.0  # A may run 5 s more: under the 10 s threshold
    assert gate.would_refuse("tab-B") is None

    async def scenario():
        async def a_finishes():
            await asyncio.sleep(0.3)
            gate._release()

        async def b_waits():
            async with gate.hold(_Token(), "tab-B"):
                return "granted"

        _, got = await asyncio.gather(a_finishes(), b_waits())
        return got

    assert asyncio.run(scenario()) == "granted"


def test_the_slot_is_off_on_a_local_install():
    gate = decks.DeckGate(_settings(hosted=False, budget_s=0.0))
    assert gate._try_acquire("a")[0] is True or gate.would_refuse("b") is None

    async def two_at_once():
        async with gate.hold(_Token(), "a"), gate.hold(_Token(), "b"):
            return True

    assert asyncio.run(two_at_once())


def test_the_watchdog_trips_the_token_and_names_the_budget():
    gate = decks.DeckGate(_settings(budget_s=0.2))
    tok = momwire.CancelToken()

    async def solve():
        async with gate.hold(tok, "tab-A"):
            deadline = time.monotonic() + 5
            while time.monotonic() < deadline:
                tok.raise_if_cancelled()
                await asyncio.sleep(0.01)
            raise AssertionError("the budget never tripped")

    t0 = time.perf_counter()
    with pytest.raises(decks.DeckBudgetExceeded, match=r"0\.2 s solve budget"):
        asyncio.run(solve())
    assert time.perf_counter() - t0 < 2.0
    # ...and the slot is free again.
    assert gate.would_refuse("tab-B") is None


def test_a_superseded_solve_is_not_reported_as_over_budget():
    gate = decks.DeckGate(_settings(budget_s=30.0))
    tok = momwire.CancelToken()

    async def solve():
        async with gate.hold(tok, "tab-A"):
            tok.cancel()  # a newer knob drag, not the watchdog
            tok.raise_if_cancelled()

    with pytest.raises(momwire.SolveAborted):
        asyncio.run(solve())


# ---------------------------------------------------------------------------
# The routes
# ---------------------------------------------------------------------------


@pytest.fixture()
def client() -> TestClient:
    return TestClient(server.app)


@pytest.fixture()
def fresh_decks(monkeypatch):
    """A clean deck store and limiter, restored afterwards."""
    st = server._DECK_SETTINGS
    monkeypatch.setattr(server, "_DECK_OPENS", decks.RateLimiter(st.opens_per_min))
    monkeypatch.setattr(server, "_DECK_GATE", decks.DeckGate(st))
    store = decks.DeckStore(st, server._register_deck, server._unregister_deck)
    monkeypatch.setattr(server, "_DECK_STORE", store)
    yield store
    for key in list(server.EXAMPLES):
        if decks.is_deck(key):
            del server.EXAMPLES[key]


def _open(client, text=DIPOLE, name="dipole.nec", headers=None):
    return client.post("/deck", json=_payload(text, name), headers=headers or {})


def _ws_solve(client, req):
    with client.websocket_connect("/ws") as ws:
        ws.send_text(json.dumps(req))
        return json.loads(ws.receive_text())


def test_open_registers_an_ephemeral_design(client, fresh_decks):
    r = _open(client)
    assert r.status_code == 200, r.text
    body = r.json()
    key = body["key"]
    assert key.startswith("deck.")
    assert body["example"]["name"] == key and body["example"]["label"] == "dipole"
    assert body["limits"]["max_segments"] == 3000
    # Not in the catalog listing, and a user-design refresh leaves it be.
    assert all(e["name"] != key for e in client.get("/examples").json()["examples"])
    user_designs.refresh()
    assert key in server.EXAMPLES
    # It solves, and its source is the deck's text.
    out = _ws_solve(client, {"geometry": key, "_session": "s1", "_seq": 1})
    assert "error" not in out, out
    src = client.post("/design_source", json={"geometry": key}).json()
    assert src["text"] == DIPOLE and src["filename"] == "dipole.nec"


def test_a_shared_link_reproduces_the_design_on_a_fresh_server(client, fresh_decks):
    key = _open(client).json()["key"]
    first = _ws_solve(client, {"geometry": key, "_session": "s1", "_seq": 1})
    # Another machine (or a restart): nothing held.
    fresh_decks._decks.clear()
    server.EXAMPLES.pop(key)
    # Without the text, the server says so by name...
    missing = client.post("/geometry", json={"geometry": key})
    assert missing.status_code == 409 and missing.json()["deck_status"] == "missing"
    # ...and with it (what every request from the page carries), it rebuilds.
    again = _ws_solve(
        client,
        {"geometry": key, "_session": "s2", "_seq": 1, "_deck": _payload(DIPOLE)},
    )
    assert "error" not in again, again
    assert (again["z_in_re"], again["z_in_im"]) == (first["z_in_re"], first["z_in_im"])
    geo = client.post("/geometry", json={"geometry": key, "_deck": _payload(DIPOLE)})
    assert geo.status_code == 200


def test_a_payload_that_is_not_its_key_is_refused(client, fresh_decks):
    key = _open(client).json()["key"]
    fresh_decks._decks.clear()
    server.EXAMPLES.pop(key)
    other = _payload(DIPOLE.replace("10 0.001", "11 0.001"))
    r = client.post("/geometry", json={"geometry": key, "_deck": other})
    assert r.status_code == 400


def test_open_refuses_oversize_and_bombs_by_name(client, fresh_decks):
    big = client.post(
        "/deck", json={"name": "big.nec", "text": DIPOLE + "CM " + "x" * 70_000}
    )
    assert big.status_code == 413
    bomb = _open(client, DIPOLE.replace("GE 0", "GR 1 10000\nGE 0"), "bomb.nec")
    assert bomb.status_code == 422 and "the limit is 3000" in bomb.json()["detail"]


def test_open_rate_limit_per_client_address(client, fresh_decks, monkeypatch):
    monkeypatch.setattr(server, "_DECK_OPENS", decks.RateLimiter(3))
    me = {"Fly-Client-IP": "203.0.113.7"}
    codes = [
        _open(
            client, DIPOLE.replace("CM opened", f"CM {i} opened"), headers=me
        ).status_code
        for i in range(4)
    ]
    assert codes == [200, 200, 200, 429]
    # Re-opening a deck already open is free; another address is not limited.
    assert (
        _open(
            client, DIPOLE.replace("CM opened", "CM 0 opened"), headers=me
        ).status_code
        == 200
    )
    assert (
        _open(client, DIPOLE, headers={"Fly-Client-IP": "198.51.100.9"}).status_code
        == 200
    )


def test_open_marks_pynec_refused_when_hosted(client, fresh_decks, monkeypatch):
    monkeypatch.setattr(server, "_HOSTED", True)
    rec = _open(client).json()["example"]
    assert "PyNEC" in rec["backend_coverage"]["refusals"]["pynec"]["reason"]


# The busy slot and the budget on the routes, against an instant fake
# deck so nothing real solves.

FAKE = "deck.0123456789ab"


class _Blocker:
    """A solve that runs until its token trips (then aborts, as a momwire
    checkpoint does)."""

    def __init__(self) -> None:
        self.started = threading.Event()

    def run(self, cancel):
        self.started.set()
        deadline = time.monotonic() + 8.0
        while time.monotonic() < deadline:
            if cancel is not None and cancel.cancelled:
                raise momwire.SolveAborted()
            time.sleep(0.005)
        raise AssertionError("the token never tripped")


@pytest.fixture()
def fake_deck(monkeypatch, fresh_decks):
    blocker = _Blocker()

    def momwire_solve(req, cancel=None):
        blocker.run(cancel)
        return {"z_in_re": 50.0, "z_in_im": 0.0}

    def momwire_sweep(req, freqs, cancel=None):
        blocker.run(cancel)
        return [50.0] * len(freqs), [0.0] * len(freqs)

    ex = SimpleNamespace(
        multi_feed=False,
        count_basis=lambda req: 100,
        momwire_solve=momwire_solve,
        momwire_sweep=momwire_sweep,
        builder_cls=None,
    )
    monkeypatch.setitem(server.EXAMPLES, FAKE, ex)
    fresh_decks._decks[FAKE] = ("fake.nec", "")
    return blocker


def _sweep_records(resp):
    return [json.loads(line) for line in resp.text.splitlines() if line.strip()]


def test_a_sweep_over_budget_ends_with_the_budget_message(
    client, fake_deck, monkeypatch
):
    monkeypatch.setattr(server._DECK_SETTINGS, "budget_s", 0.3)
    t0 = time.perf_counter()
    r = client.post(
        "/sweep", json={"geometry": FAKE, "_session": "s1", "freqs_mhz": [14.0, 14.1]}
    )
    assert time.perf_counter() - t0 < 4.0
    recs = _sweep_records(r)
    assert recs[-1]["deck_status"] == "budget", recs
    assert "0.3 s solve budget" in recs[-1]["error"]
    assert "pip install antennaknobs" in recs[-1]["error"]


def test_a_live_solve_over_budget_says_so(client, fake_deck, monkeypatch):
    monkeypatch.setattr(server._DECK_SETTINGS, "budget_s", 0.3)
    out = _ws_solve(client, {"geometry": FAKE, "_session": "s1", "_seq": 1})
    assert out["deck_status"] == "budget" and "solve budget" in out["error"]


def test_an_optimize_eval_over_budget_says_so(client, fake_deck, monkeypatch):
    monkeypatch.setattr(server._DECK_SETTINGS, "budget_s", 0.3)
    r = client.post(
        "/optimize",
        json={
            "geometry": FAKE,
            "_session": "s1",
            "length_factor": 1.0,
            "optimize": {
                "free": [{"name": "length_factor", "min": 0.9, "max": 1.1}],
                "objective": "swr",
            },
        },
    )
    assert "solve budget" in r.json()["error"], r.json()


def _hold_slot(owner="someone-else", age_s=1.0):
    gate = server._DECK_GATE
    assert gate._try_acquire(owner)[0]
    gate._since -= age_s


def test_busy_is_answered_at_once_on_rest(client, fake_deck, monkeypatch):
    monkeypatch.setattr(server._DECK_SETTINGS, "hosted", True)
    monkeypatch.setattr(server._DECK_SETTINGS, "budget_s", 60.0)
    _hold_slot()
    t0 = time.perf_counter()
    r = client.post(
        "/sweep", json={"geometry": FAKE, "_session": "s1", "freqs_mhz": [14.0]}
    )
    assert time.perf_counter() - t0 < 2.0  # at once: the 10 s wait is not taken
    assert r.status_code == 503
    assert r.json()["deck_status"] == "busy"
    assert "busy with another opened deck" in r.json()["detail"]
    assert not fake_deck.started.is_set()


def test_busy_is_a_status_message_on_the_socket(client, fake_deck, monkeypatch):
    monkeypatch.setattr(server._DECK_SETTINGS, "hosted", True)
    monkeypatch.setattr(server._DECK_SETTINGS, "budget_s", 60.0)
    _hold_slot()
    t0 = time.perf_counter()
    out = _ws_solve(client, {"geometry": FAKE, "_session": "s1", "_seq": 1})
    assert time.perf_counter() - t0 < 2.0
    assert out["deck_status"] == "busy" and out["_seq"] == 1
    assert not fake_deck.started.is_set()


def test_catalog_designs_never_wait_on_the_deck_slot(client, fresh_decks, monkeypatch):
    monkeypatch.setattr(server._DECK_SETTINGS, "hosted", True)
    monkeypatch.setattr(server._DECK_SETTINGS, "budget_s", 60.0)
    _hold_slot()
    meter = SimpleNamespace(n=0)

    def momwire_sweep(req, freqs, cancel=None):
        meter.n += 1
        return [50.0] * len(freqs), [0.0] * len(freqs)

    monkeypatch.setitem(
        server.EXAMPLES,
        "fake.catalog",
        SimpleNamespace(
            multi_feed=False,
            count_basis=lambda req: 100,
            momwire_sweep=momwire_sweep,
            builder_cls=None,
        ),
    )
    r = client.post(
        "/sweep",
        json={"geometry": "fake.catalog", "_session": "s1", "freqs_mhz": [14.0]},
    )
    assert r.status_code == 200 and meter.n == 1


def test_the_deck_text_never_reaches_the_cache_key():
    a = server._canonical_solve_key({"geometry": FAKE})
    b = server._canonical_solve_key({"geometry": FAKE, "_deck": _payload(DIPOLE)})
    assert a == b


def test_a_real_deck_solves_through_the_routes(client, fresh_decks):
    # End to end on a real (tiny) deck: open, sweep, a parameter-free solve.
    key = _open(client).json()["key"]
    r = client.post(
        "/sweep",
        json={"geometry": key, "_session": "s1", "freqs_mhz": [13.9, 14.0, 14.1]},
    )
    recs = _sweep_records(r)
    assert recs[-1].get("done") is True, recs
    z = [complex(x["z_re"], x["z_im"]) for x in recs[:-1]]
    assert len(z) == 3 and all(np.isfinite(abs(v)) for v in z)
