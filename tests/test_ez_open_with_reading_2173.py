"""Open… an .ez whose format leaves a reading undefined: the refusal names
the reading and the page offers it as a button, "Open with this reading"
(AK#2173). The environment variable stays the command line's switch; on the
web app nobody can set it, which is what Dan (AC6LA) ran into.

The request flag (`accept_guesses`) is part of the deck's key, as a chosen
dialect is: the same file opened with the reading is another design from the
file refused, and a link carries it.
"""

from __future__ import annotations

import base64
import zlib

import pytest
from fastapi.testclient import TestClient

from antennaknobs.web import decks, server
from test_ez_import_1958 import DIPOLE, LAPLACE, engine_block, ez_file

RAW = ez_file(DIPOLE, loads=(LAPLACE,), load_type="L")


def _payload(raw=RAW, name="laplace.ez", **kw) -> dict:
    c = zlib.compressobj(9, zlib.DEFLATED, -15)
    packed = c.compress(raw) + c.flush()
    return {
        "name": name,
        "z": base64.urlsafe_b64encode(packed).decode().rstrip("="),
        **kw,
    }


@pytest.fixture()
def client(monkeypatch):
    monkeypatch.delenv("ANTENNAKNOBS_EZ_ACCEPT_GUESSES", raising=False)
    st = server._DECK_SETTINGS
    monkeypatch.setattr(server, "_DECK_OPENS", decks.RateLimiter(0))
    monkeypatch.setattr(server, "_DECK_GATE", decks.DeckGate(st))
    store = decks.DeckStore(st, server._register_deck, server._unregister_deck)
    monkeypatch.setattr(server, "_DECK_STORE", store)
    yield TestClient(server.app)
    for key in list(server.EXAMPLES):
        if decks.is_deck(key):
            del server.EXAMPLES[key]


def test_the_refusal_names_the_reading_and_no_environment_variable(client):
    r = client.post("/deck", json=_payload())
    assert r.status_code == 422
    body = r.json()
    assert body["deck_status"] == "undefined"
    assert body["reading"]
    assert "Laplace" in body["detail"] and "Open with this reading" in body["detail"]
    assert "ANTENNAKNOBS_" not in body["detail"]


def test_opening_with_the_reading_opens_it_and_lists_the_reading(client):
    r = client.post("/deck", json=_payload(accept_guesses=True))
    assert r.status_code == 200, r.text
    assert "Readings taken on request" in r.json()["example"]["notes"]


def test_the_reading_is_part_of_the_key_and_false_keeps_the_old_one():
    text = RAW.decode("latin-1")
    old = decks.deck_key("laplace.ez", text)
    assert decks.deck_key("laplace.ez", text, accept_guesses=False) == old
    assert decks.deck_key("laplace.ez", text, accept_guesses=True) != old


def test_the_flag_means_nothing_for_a_file_that_is_not_an_ez():
    assert decks.payload_accept_guesses({"name": "a.ez", "accept_guesses": True})
    assert not decks.payload_accept_guesses({"name": "a.nec", "accept_guesses": True})
    assert not decks.payload_accept_guesses({"name": "a.ez", "accept_guesses": "yes"})
    assert not decks.payload_accept_guesses({"name": "a.ez"})


def test_a_request_carrying_the_flag_rebuilds_that_design(client):
    key = client.post("/deck", json=_payload(accept_guesses=True)).json()["key"]
    server._DECK_STORE._decks.clear()
    server.EXAMPLES.pop(key)
    r = client.post(
        "/geometry", json={"geometry": key, "_deck": _payload(accept_guesses=True)}
    )
    assert r.status_code == 200, r.text


def test_a_refusal_with_no_reading_offers_none(client):
    """An undefined value the import has no reading for stays a plain
    refusal: no button."""
    # A parallel load on a free wire end under NEC-5 (AK#2061): no reading.
    raw = ez_file(
        DIPOLE,
        loads=({"wire": 1, "pct": 0.0, "z": (5.0, 0.0), "conn": "P"},),
        blocks=[engine_block(8, "Ext NEC-5")],
    )
    r = client.post("/deck", json=_payload(raw, name="none.ez", accept_guesses=True))
    assert r.status_code == 422
    assert "reading" not in r.json()
