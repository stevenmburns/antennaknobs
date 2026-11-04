"""Opening a design .py like a deck (AK#2149 unit 3).

A .py opens through the same store, gates and routes as a .nec, but its code
runs only in the sandbox (`design_sandbox.sandboxed_builder`); the server
holds a proxy builder that answers every hook from decoded snapshot data.
The hosted app opens one only when the sandbox's jail is active.
"""

from __future__ import annotations

import importlib
import json
import textwrap
import warnings
from pathlib import Path

import numpy as np
import pytest
from fastapi.testclient import TestClient

from antennaknobs import design_sandbox as sb
from antennaknobs import design_snapshot as ds
from antennaknobs.web import decks, server

cli = importlib.import_module("antennaknobs.cli")

# A real catalog design's own source: a folded inverted vee through a balun
# composite (network, transformer, instances).
CATALOG = "dipoles.folded_invvee_balun"


def catalog_source(name=CATALOG):
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        cls = type(cli.get_builder(name)())
    path = Path(importlib.import_module(cls.__module__).__file__)
    return cls, path.name, path.read_text()


def local_settings(**kw):
    return decks.DeckSettings(hosted=False, **kw)


def test_a_py_payload_opens_locally_under_its_own_cap():
    _, name, src = catalog_source()
    got = decks.decode_payload({"name": name, "text": src}, local_settings())
    assert got == (name, src)
    with pytest.raises(decks.DeckError) as e:
        decks.decode_payload(
            {"name": "big.py", "text": "#" * (300 * 1024)}, local_settings()
        )
    assert e.value.status == 413
    # A .nec keeps the deck cap.
    with pytest.raises(decks.DeckError):
        decks.decode_payload(
            {"name": "big.nec", "text": "CM " + "x" * (70 * 1024)}, local_settings()
        )


def test_the_hosted_app_refuses_a_py_without_the_jail(monkeypatch):
    monkeypatch.setattr(
        sb, "sandbox_status", lambda: {"layer": "baseline", "jail": None}
    )
    st = decks.DeckSettings(hosted=True)
    with pytest.raises(decks.DeckError) as e:
        decks.decode_payload({"name": "d.py", "text": "x = 1\n"}, st)
    assert e.value.status == 403 and "cannot isolate" in e.value.message
    monkeypatch.setattr(
        sb, "sandbox_status", lambda: {"layer": "jail", "jail": "bwrap"}
    )
    assert decks.decode_payload({"name": "d.py", "text": "x = 1\n"}, st)[0] == "d.py"


def test_the_policy_can_turn_py_off_everywhere():
    with pytest.raises(decks.DeckError) as e:
        decks.decode_payload(
            {"name": "d.py", "text": "x = 1\n"}, local_settings(py_policy="off")
        )
    assert "turned off" in e.value.message


def test_the_proxy_builder_answers_every_hook_as_the_design_does():
    cls, name, src = catalog_source()
    proxy = sb.sandboxed_builder(name, src)
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        here = ds.snapshot(cls())
    there = ds.snapshot(proxy())
    assert json.loads(json.dumps(there)) == json.loads(json.dumps(here))
    assert dict(proxy.default_params) == dict(cls.default_params)
    assert proxy.sandboxed_source_name == name


def test_the_proxy_builder_solves_bit_for_bit_like_the_design():
    cls, name, src = catalog_source()
    proxy = sb.sandboxed_builder(name, src)
    engine = cli.make_engine_factory("momwire:bspline", "free")
    f = float(cls.default_params["freq"])
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        z_here = np.asarray(engine(cls()).impedance_sweep([f]))
        z_there = np.asarray(engine(proxy()).impedance_sweep([f]))
    assert np.array_equal(z_here, z_there)


def test_the_proxy_follows_the_knobs_and_caches_by_params():
    src = textwrap.dedent("""
        from types import MappingProxyType
        from antennaknobs import AntennaBuilder

        class Builder(AntennaBuilder):
            default_params = MappingProxyType({"freq": 14.2, "design_freq": 14.2, "half": 5.0})

            def build_wires(self):
                return [((0.0, -self.half, 10.0), (0.0, self.half, 10.0), 21, 1 + 0j)]
    """)
    proxy = sb.sandboxed_builder("knob.py", src)
    b = proxy()
    assert b.build_wires()[0][1] == (0.0, 5.0, 10.0)
    b.half = 6.5
    assert b.build_wires()[0][1] == (0.0, 6.5, 10.0)


def test_the_store_opens_a_py_and_holds_it_to_the_deck_limits():
    _, name, src = catalog_source()
    registered = {}
    store = decks.DeckStore(local_settings(), registered.__setitem__, registered.pop)
    key, new = store.open(name, src)
    assert new and key.startswith("deck.") and key in registered
    assert getattr(registered[key], "sandboxed_source_name", None) == name

    many = textwrap.dedent("""
        from types import MappingProxyType
        from antennaknobs import AntennaBuilder

        class Builder(AntennaBuilder):
            default_params = MappingProxyType({"freq": 14.2, "design_freq": 14.2})

            def build_wires(self):
                return [((0.0, float(i), 10.0), (1.0, float(i), 10.0), 3, None) for i in range(250)]
    """)
    tight = decks.DeckStore(
        local_settings(max_wires=200), registered.__setitem__, registered.pop
    )
    with pytest.raises(decks.DeckError) as e:
        tight.open("many.py", many)
    assert "250 wires" in e.value.message


def test_a_design_that_fails_is_refused_by_name():
    store = decks.DeckStore(local_settings(), lambda *a: None, lambda *a: None)
    with pytest.raises(decks.DeckError) as e:
        store.open("broken.py", "raise ImportError('no such thing')\n")
    assert e.value.message.startswith("broken.py:") and "ImportError" in e.value.message


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


def test_the_routes_open_solve_and_show_a_py(fresh_decks):
    client = TestClient(server.app)
    _, name, src = catalog_source()
    r = client.post("/deck", json={"name": name, "text": src})
    assert r.status_code == 200, r.text
    key = r.json()["key"]
    with client.websocket_connect("/ws") as ws:
        ws.send_text(json.dumps({"geometry": key, "_session": "s1", "_seq": 1}))
        out = json.loads(ws.receive_text())
    assert "error" not in out, out
    shown = client.post("/design_source", json={"geometry": key}).json()
    assert shown["text"] == src and shown["filename"] == name
    caps = client.get("/capabilities").json()["open_design_py"]
    assert caps["accepted"] is True and caps["layer"] in ("jail", "baseline")


def test_the_hosted_route_refuses_a_py_without_the_jail(fresh_decks, monkeypatch):
    monkeypatch.setattr(server, "_DECK_SETTINGS", decks.DeckSettings(hosted=True))
    monkeypatch.setattr(
        sb, "sandbox_status", lambda: {"layer": "baseline", "jail": None}
    )
    client = TestClient(server.app)
    r = client.post("/deck", json={"name": "d.py", "text": "x = 1\n"})
    assert r.status_code == 403
    caps = client.get("/capabilities").json()["open_design_py"]
    assert caps["accepted"] is False and "cannot isolate" in caps["refusal"]
