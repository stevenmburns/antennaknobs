"""``ak_refusals_total{reason}``: how often the hosted server turned a request
away for capacity or limits, and why (AK#405's counters; web/hosting.py).

Each reason is driven through its real refusal path and must move the counter
by exactly one, with no other reason moving. Ordinary user errors (a malformed
deck) and superseded solves are not refusals and must not count. These tests
fail with the ``_count_refusal`` / ``_refused`` calls removed.
"""

from __future__ import annotations

import json
import re
import time
from pathlib import Path
from types import SimpleNamespace

import momwire
import pytest
from fastapi.testclient import TestClient
from test_maa_import_1897 import DIPOLE as MAA_DIPOLE
from test_optimize_bands_1901 import _fan_body
from test_opened_decks import (
    DIPOLE,
    FAKE,
    _Blocker,
    _hold_slot,
    _open,
    _ws_solve,
)

from antennaknobs.web import cost, decks, hosting, server

INVVEE = {
    "geometry": "dipoles.invvee",
    "variant": "dipole",
    "measurement_freq_mhz": 28.47,
    "design_freq_mhz": 28.47,
    "momwire_model": "bspline",
    "n_per_wire": 7,
}

REASONS = {
    "busy",
    "deck_watchdog",
    "deck_cap",
    "deck_rate",
    "sweep_budget",
    "optimize_budget",
    "cost_refused",
    "cost_withheld",
}


@pytest.fixture()
def client() -> TestClient:
    return TestClient(server.app)


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
    monkeypatch.setattr(server, "_DECK_GATE", decks.DeckGate(st))
    store = decks.DeckStore(st, server._register_deck, server._unregister_deck)
    monkeypatch.setattr(server, "_DECK_STORE", store)
    yield store
    for key in list(server.EXAMPLES):
        if decks.is_deck(key):
            del server.EXAMPLES[key]


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


def _refusals(c: hosting.UsageCounters) -> dict:
    return {k[0]: n for k, n in c.series("ak_refusals_total").items()}


def _records(text: str) -> list[dict]:
    return [json.loads(line) for line in text.splitlines() if line.strip()]


def _count_solves(monkeypatch) -> list:
    calls: list = []

    def stub(req, cancel=None):
        calls.append(req["length_factor"])
        return complex(50.0 + len(calls), 0.0), None, None

    monkeypatch.setattr(server, "_solve_z_only", stub)
    return calls


# ---------------------------------------------------------------------------
# The set, and the counter's own contract
# ---------------------------------------------------------------------------


def test_the_reason_set_is_closed_and_in_one_place():
    assert hosting.REFUSAL_REASONS == REASONS


def test_every_reason_is_counted_somewhere_and_nothing_else_is():
    """The literals at the count sites are exactly the set: no dead reason,
    no reason spelled at a site that the set does not hold."""
    web = Path(server.__file__).parent
    used = set()
    for name in ("server.py", "decks.py"):
        src = (web / name).read_text()
        used |= set(re.findall(r'(?:_count_refusal|_refused)\(\s*"([a-z_]+)"', src))
    assert used == REASONS


def test_an_unknown_reason_raises_enabled_or_not():
    for enabled in (True, False):
        c = hosting.UsageCounters(enabled=enabled)
        with pytest.raises(ValueError, match="unknown refusal reason"):
            c.inc("ak_refusals_total", "because")
        with pytest.raises(ValueError):
            c.inc("ak_refusals_total")


def test_a_local_instance_is_a_no_op():
    c = hosting.UsageCounters(enabled=False)
    for r in REASONS:
        c.inc("ak_refusals_total", r)
    assert c.series("ak_refusals_total") == {}
    assert c.exposition() == ""


def test_exposition_carries_help_type_and_the_series():
    c = hosting.UsageCounters(enabled=True)
    c.inc("ak_refusals_total", "busy")
    c.inc("ak_refusals_total", "busy")
    c.inc("ak_refusals_total", "deck_cap")
    text = c.exposition()
    assert "# HELP ak_refusals_total Requests turned away" in text
    assert "# TYPE ak_refusals_total counter" in text
    assert 'ak_refusals_total{reason="busy"} 2' in text
    assert 'ak_refusals_total{reason="deck_cap"} 1' in text
    # Series appear only once counted: nothing is pre-seeded.
    assert "deck_rate" not in text


def test_a_refusal_on_a_local_instance_counts_nothing(client, fake_deck, monkeypatch):
    """The real busy path, with the server's own switch off."""
    monkeypatch.setattr(server, "_METRICS", hosting.UsageCounters(enabled=False))
    monkeypatch.setattr(server._DECK_SETTINGS, "hosted", True)
    monkeypatch.setattr(server._DECK_SETTINGS, "budget_s", 60.0)
    _hold_slot()
    r = client.post(
        "/sweep", json={"geometry": FAKE, "_session": "s1", "freqs_mhz": [14.0]}
    )
    assert r.status_code == 503
    assert server._METRICS.series("ak_refusals_total") == {}


# ---------------------------------------------------------------------------
# busy
# ---------------------------------------------------------------------------


def test_busy_on_rest_counts_once(client, counters, fake_deck, monkeypatch):
    monkeypatch.setattr(server._DECK_SETTINGS, "hosted", True)
    monkeypatch.setattr(server._DECK_SETTINGS, "budget_s", 60.0)
    _hold_slot()
    r = client.post(
        "/sweep", json={"geometry": FAKE, "_session": "s1", "freqs_mhz": [14.0]}
    )
    assert r.status_code == 503 and r.json()["deck_status"] == "busy"
    assert _refusals(counters) == {"busy": 1}
    assert counters.series("ak_solves_total") == {}


def test_busy_on_the_socket_counts_once(client, counters, fake_deck, monkeypatch):
    monkeypatch.setattr(server._DECK_SETTINGS, "hosted", True)
    monkeypatch.setattr(server._DECK_SETTINGS, "budget_s", 60.0)
    _hold_slot()
    out = _ws_solve(client, {"geometry": FAKE, "_session": "s1", "_seq": 1})
    assert out["deck_status"] == "busy"
    assert _refusals(counters) == {"busy": 1}
    assert counters.series("ak_solves_total") == {}


def test_a_session_waiting_on_its_own_turn_is_not_busy(
    client, counters, fake_deck, monkeypatch
):
    """The holder's own session never reads as another deck: no refusal."""
    monkeypatch.setattr(server._DECK_SETTINGS, "hosted", True)
    monkeypatch.setattr(server._DECK_SETTINGS, "budget_s", 60.0)
    assert server._DECK_GATE.would_refuse("s1") is None
    _hold_slot(owner="s1")
    assert server._DECK_GATE.would_refuse("s1") is None
    assert _refusals(counters) == {}


# ---------------------------------------------------------------------------
# deck_watchdog
# ---------------------------------------------------------------------------


def test_the_watchdog_on_a_live_solve_counts_once(
    client, counters, fake_deck, monkeypatch
):
    monkeypatch.setattr(server._DECK_SETTINGS, "budget_s", 0.3)
    out = _ws_solve(client, {"geometry": FAKE, "_session": "s1", "_seq": 1})
    assert out["deck_status"] == "budget"
    assert _refusals(counters) == {"deck_watchdog": 1}


def test_the_watchdog_on_a_sweep_counts_once(client, counters, fake_deck, monkeypatch):
    monkeypatch.setattr(server._DECK_SETTINGS, "budget_s", 0.3)
    r = client.post(
        "/sweep", json={"geometry": FAKE, "_session": "s1", "freqs_mhz": [14.0, 14.1]}
    )
    assert _records(r.text)[-1]["deck_status"] == "budget"
    # Not also a sweep_budget: that is the hosted 120 s clock, a different stop.
    assert _refusals(counters) == {"deck_watchdog": 1}


def test_the_watchdog_on_an_optimize_eval_counts_once(
    client, counters, fake_deck, monkeypatch
):
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
    assert "solve budget" in r.json()["error"]
    assert _refusals(counters) == {"deck_watchdog": 1}


def test_a_superseded_solve_is_not_a_refusal(counters):
    gate = decks.DeckGate(decks.DeckSettings(hosted=True, budget_s=30.0))
    tok = momwire.CancelToken()

    import asyncio

    async def solve():
        async with gate.hold(tok, "tab-A"):
            tok.cancel()  # a newer knob drag, not the watchdog
            tok.raise_if_cancelled()

    with pytest.raises(momwire.SolveAborted):
        asyncio.run(solve())
    assert _refusals(counters) == {}


# ---------------------------------------------------------------------------
# deck_cap and deck_rate
# ---------------------------------------------------------------------------


def test_a_deck_over_the_text_limit_counts_once(client, counters, fresh_decks):
    big = client.post(
        "/deck", json={"name": "big.nec", "text": DIPOLE + "CM " + "x" * 70_000}
    )
    assert big.status_code == 413
    assert _refusals(counters) == {"deck_cap": 1}


def test_a_compressed_deck_over_the_limit_counts_once(
    client, counters, fresh_decks, monkeypatch
):
    monkeypatch.setattr(server._DECK_SETTINGS, "max_bytes", 200)
    r = _open(client, DIPOLE + "CM " + "x" * 400, "big.nec")
    assert r.status_code == 413
    assert _refusals(counters) == {"deck_cap": 1}


def test_a_deck_over_the_segment_limit_counts_once(client, counters, fresh_decks):
    bomb = _open(client, DIPOLE.replace("GE 0", "GR 1 10000\nGE 0"), "bomb.nec")
    assert bomb.status_code == 422 and "the limit is 3000" in bomb.json()["detail"]
    assert _refusals(counters) == {"deck_cap": 1}


def test_a_deck_over_the_wire_limit_counts_once(
    client, counters, fresh_decks, monkeypatch
):
    monkeypatch.setattr(server._DECK_SETTINGS, "max_wires", 1)
    two = DIPOLE.replace("GE 0", "GW 2 11 0 -5.1 11 0 5.1 11 0.001\nGE 0")
    r = _open(client, two, "two.nec")
    assert r.status_code == 422 and "wires (the limit is 1)" in r.json()["detail"]
    assert _refusals(counters) == {"deck_cap": 1}


def test_an_mmana_deck_over_its_limits_counts_once_each(counters):
    settings = decks.DeckSettings(hosted=True, max_segments=20)
    store = decks.DeckStore(settings, lambda k, c: None, lambda k: None)
    with pytest.raises(decks.DeckError, match="segments"):
        store.open("d.maa", MAA_DIPOLE)
    assert _refusals(counters) == {"deck_cap": 1}
    settings.max_segments, settings.max_wires = 3000, 0
    with pytest.raises(decks.DeckError, match="wires"):
        store.open("e.maa", MAA_DIPOLE + " ")
    assert _refusals(counters) == {"deck_cap": 2}


def test_a_malformed_deck_is_not_a_refusal(client, counters, fresh_decks):
    bad = client.post("/deck", json={"name": "d.nec", "text": "GW junk\nEN\n"})
    assert bad.status_code in (400, 422)
    assert _refusals(counters) == {}
    # Its outcome is still the opens counter's business.
    assert counters.value("ak_deck_opens_total", "auto", "refused") == 1
    # A deck within every cap opens and counts no refusal either.
    assert _open(client).status_code == 200
    assert _refusals(counters) == {}


def test_the_opens_per_minute_limit_counts_once(
    client, counters, fresh_decks, monkeypatch
):
    monkeypatch.setattr(server, "_DECK_OPENS", decks.RateLimiter(1))
    assert _open(client, DIPOLE.replace("14.0", "14.1"), "a.nec").status_code == 200
    r = _open(client, DIPOLE.replace("14.0", "14.2"), "b.nec")
    assert r.status_code == 429
    assert _refusals(counters) == {"deck_rate": 1}
    # ak_deck_opens_total files the same 429 under its own outcome "busy":
    # a different question (opens by outcome), and the two are never summed.
    assert counters.value("ak_deck_opens_total", "auto", "busy") == 1


def test_a_missing_deck_is_not_a_refusal(client, counters, fresh_decks):
    out = _ws_solve(
        client, {"geometry": "deck.0123456789ab", "_session": "s", "_seq": 1}
    )
    assert out["deck_status"] == "missing"
    assert _refusals(counters) == {}


# ---------------------------------------------------------------------------
# sweep_budget, optimize_budget
# ---------------------------------------------------------------------------


def test_a_sweep_stopped_at_the_hosted_budget_counts_once(
    client, counters, monkeypatch
):
    monkeypatch.setattr(server, "_HOSTED", True)
    monkeypatch.setattr(server, "_MAX_SWEEP_SECONDS", 0)
    calls = _count_solves(monkeypatch)
    *points, done = _records(
        client.post(
            "/param_sweep",
            json={**INVVEE, "param": "length_factor", "values": [0.9, 0.95, 1.0, 1.05]},
        ).text
    )
    assert calls == [0.9] and done["stopped"] == "time"
    # Once per stopped sweep, not once per skipped point.
    assert _refusals(counters) == {"sweep_budget": 1}


def test_a_sweep_inside_its_budget_counts_nothing(client, counters, monkeypatch):
    monkeypatch.setattr(server, "_HOSTED", True)
    monkeypatch.setattr(server, "_MAX_SWEEP_SECONDS", 120)
    calls = _count_solves(monkeypatch)
    *points, done = _records(
        client.post(
            "/param_sweep",
            json={**INVVEE, "param": "length_factor", "values": [0.9, 0.95, 1.0]},
        ).text
    )
    assert len(calls) == 3 and "stopped" not in done
    assert _refusals(counters) == {}


def test_a_run_over_the_clock_counts_one_per_clock(monkeypatch, counters):
    monkeypatch.setattr(server, "_HOSTED", True)
    monkeypatch.setattr(server, "_MAX_SWEEP_SECONDS", 0.05)
    clock = server._SweepClock()
    assert clock.spent() is False  # the first fresh point always runs
    time.sleep(0.1)
    assert clock.spent() and clock.spent() and clock.spent()
    assert _refusals(counters) == {"sweep_budget": 1}


def test_an_optimize_run_stopped_at_its_budget_counts_once(
    client, counters, monkeypatch
):
    monkeypatch.setattr(server, "_HOSTED", True)
    monkeypatch.setattr(server, "_MAX_OPT_SECONDS", 0)
    body = _fan_body(
        free=[
            {"name": "bands.0.length", "min": 3.0, "max": 7.0},
            {"name": "bands.1.length", "min": 3.0, "max": 7.0},
        ],
        bands=[
            {"freq": 26.6, "objective": "resonance"},
            {"freq": 29.3, "objective": "resonance"},
        ],
        mode="root",
    )
    out = client.post("/optimize", json=body).json()
    assert out.get("stopped") == "time", out
    assert _refusals(counters) == {"optimize_budget": 1}


# ---------------------------------------------------------------------------
# cost_refused, cost_withheld
# ---------------------------------------------------------------------------


def test_a_batch_over_the_point_cap_counts_once(client, counters, monkeypatch):
    monkeypatch.setattr(server, "_HOSTED", True)
    values = [1.0] * (server._MAX_SWEEP_POINTS + 1)
    r = client.post(
        "/param_sweep", json={**INVVEE, "param": "length_factor", "values": values}
    )
    assert r.status_code == 413
    assert _refusals(counters) == {"cost_refused": 1}


def test_a_live_solve_over_the_size_cap_counts_once(client, counters, monkeypatch):
    monkeypatch.setattr(server, "_HOSTED", True)
    monkeypatch.setattr(cost, "MAX_BASIS", 5)
    out = _ws_solve(
        client, {**INVVEE, "_session": "s", "_seq": 1, "measurement_freq_mhz": 28.47}
    )
    assert "error" in out
    assert _refusals(counters) == {"cost_refused": 1}
    assert counters.series("ak_solves_total") == {}


def test_a_poor_match_batch_withheld_counts_once_and_approved_not_at_all(
    client, counters, monkeypatch
):
    calls = _count_solves(monkeypatch)
    real = server._admit

    def warn(req, **kw):
        return cost.Admission("warn", "a poor match", 5000)

    monkeypatch.setattr(server, "_admit", warn)
    body = {**INVVEE, "param": "length_factor", "values": [0.9, 1.0]}
    r = client.post("/param_sweep", json=body)
    assert r.status_code == 403
    assert _refusals(counters) == {"cost_withheld": 1}
    assert calls == []
    ok = client.post("/param_sweep", json={**body, "_approved": True})
    assert ok.status_code == 200
    assert _refusals(counters) == {"cost_withheld": 1}
    monkeypatch.setattr(server, "_admit", real)


def test_an_ordinary_solve_counts_no_refusal(client, counters):
    out = _ws_solve(client, {**INVVEE, "_session": "s", "_seq": 1})
    assert "error" not in out
    assert _refusals(counters) == {}
    assert counters.series("ak_solves_total") != {}
