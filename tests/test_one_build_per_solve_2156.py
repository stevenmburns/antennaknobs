"""One build per solve (AK#2156).

The size probe (count_basis) used to build the design at its defaults while
the solve built it at the request's measurement and design frequencies. For a
sandboxed .py design every build is a sandbox run, so a solve whose dial was
off the default paid two. Every solve-forming closure now builds through one
helper, `_solve_builder`.
"""

from __future__ import annotations

import importlib
import json
import warnings
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from antennaknobs import design_sandbox as sb
from antennaknobs.web import decks, server

cli = importlib.import_module("antennaknobs.cli")


@pytest.fixture()
def fresh_decks(monkeypatch):
    st = decks.DeckSettings(hosted=False)
    monkeypatch.setattr(server, "_DECK_SETTINGS", st)
    monkeypatch.setattr(server, "_DECK_OPENS", decks.RateLimiter(st.opens_per_min))
    monkeypatch.setattr(server, "_DECK_GATE", decks.DeckGate(st))
    store = decks.DeckStore(st, server._register_deck, server._unregister_deck)
    monkeypatch.setattr(server, "_DECK_STORE", store)
    yield store
    for key in list(server.EXAMPLES):
        if decks.is_deck(key):
            del server.EXAMPLES[key]


def test_a_knob_turn_off_the_default_dial_is_one_sandbox_run(fresh_decks, monkeypatch):
    # skyloop_lmatch is cut for 80 m (design_freq 3.8) and operated on 17 m
    # (freq 18.1): the case where a defaults-built probe and the solve differ.
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        cls = type(cli.get_builder("loops.skyloop_lmatch")())
    src = Path(importlib.import_module(cls.__module__).__file__)
    payload = {"name": src.name, "text": src.read_text()}
    calls = []
    real, real_warm = sb.run_design, sb.warm_snapshot

    def spy(*a, **k):
        calls.append(k.get("want", "snapshot"))
        return real(*a, **k)

    def spy_warm(*a, **k):
        # A snapshot from the design's warm worker (AK#2157) is still one
        # sandbox run: counted here, not again inside run_design.
        calls.append("snapshot")
        with monkeypatch.context() as m:
            m.setattr(sb, "run_design", real)
            return real_warm(*a, **k)

    monkeypatch.setattr(sb, "run_design", spy)
    monkeypatch.setattr(sb, "warm_snapshot", spy_warm)
    client = TestClient(server.app)
    key = client.post("/deck", json=payload).json()["key"]
    v0 = float(cls.default_params["series_L_uH"])
    with client.websocket_connect("/ws") as ws:
        for i in range(3):
            before = len(calls)
            # What the page sends: the dial and the design-freq slider moved
            # off their defaults, and a knob turned.
            ws.send_text(json.dumps({
                "geometry": key, "_session": "s", "_seq": i + 1, "_deck": payload,
                "measurement_freq_mhz": 18.12 + 0.01 * i, "design_freq_mhz": 3.75,
                "series_L_uH": v0 * (1.01 + 0.01 * i),
            }))  # fmt: skip
            out = json.loads(ws.receive_text())
            assert "error" not in out, out
            assert calls[before:] == ["snapshot"], calls[before:]
