"""AK#1803: the gear menu's Download offers a NEC-4 deck beside NEC-2 and NEC-5.

EZNEC Pro/4 and 4nec2 users take NEC-4 decks. The file is `export_nec`'s NEC-4.2
dialect, so it carries what the NEC-2 deck refuses (buried wires under GE -1,
graded meshes as chained GW cards, EX 6 current sources) and its Sommerfeld
cards end NOFILE. Writing one runs no NEC-4.2: it is served with no binary on
the machine, and on the hosted app, exactly as the other two are (#1389).
"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

import antennaknobs.web.server as _server

BURIED = "verticals.buried_radial_vertical"


@pytest.fixture(scope="module")
def client() -> TestClient:
    return TestClient(_server.app)


@pytest.fixture(autouse=True)
def _no_nec42(monkeypatch):
    """No NEC-4.2 anywhere: the download must not need one."""
    monkeypatch.delenv("NEC42_EXE", raising=False)


def _post(client, geometry, **extra):
    return client.post(
        "/export_nec", json={"geometry": geometry, "dialect": "nec4", **extra}
    )


def test_a_graded_buried_design_downloads_as_nec4(client):
    """The design the NEC-2 download refuses."""
    r = _post(client, BURIED, ground=True, ground_model="sommerfeld")
    assert r.status_code == 200, r.text
    disposition = r.headers["Content-Disposition"]
    assert 'filename="verticals_buried_radial_vertical.nec4.nec"' in disposition
    lines = r.text.splitlines()
    assert "GE -1" in lines
    assert [ln for ln in lines if ln.startswith("GN ")] == [
        "GN 2 0 0 0 13 0.005 NOFILE"
    ]
    assert lines[-1] == "EN"
    assert all(len(ln) <= 80 for ln in lines if not ln.startswith("CM"))


def test_the_three_downloads_have_three_filenames(client):
    names = {
        d: client.post(
            "/export_nec", json={"geometry": "dipoles.invvee", "dialect": d}
        ).headers["Content-Disposition"]
        for d in ("nec2", "nec4", "nec5")
    }
    assert len(set(names.values())) == 3, names
    assert 'filename="dipoles_invvee.nec4.nec"' in names["nec4"]


def test_a_free_space_nec4_deck_is_the_nec2_deck_with_no_dialect_cards(client):
    """Nothing NEC-4 needs differs on an ordinary free-space dipole."""
    body = {"geometry": "dipoles.invvee"}
    n2 = client.post("/export_nec", json={**body, "dialect": "nec2"}).text
    n4 = client.post("/export_nec", json={**body, "dialect": "nec4"}).text
    assert n2 == n4


def test_a_buried_design_over_the_fast_ground_refuses_by_name(client):
    """The UI's default ground model is the reflection-coefficient one, which
    has no medium below the plane: the sentence says to choose Sommerfeld."""
    r = _post(client, BURIED, ground=True)
    assert r.status_code == 422
    assert "only over its Sommerfeld ground" in r.json()["detail"]


def test_a_tl_network_refuses_naming_the_nec4_deck(client):
    r = _post(client, "broadband.lpda")
    assert r.status_code == 422
    detail = r.json()["detail"]
    assert detail.startswith("a single NEC-4 deck cannot express"), detail
    assert "PyNEC" not in detail, detail


def test_the_download_is_served_on_the_hosted_app(client, monkeypatch):
    """Writing a deck is not running NEC-4.2, so no hosted limit applies."""
    monkeypatch.setattr(_server, "_HOSTED", True)
    r = _post(client, "dipoles.invvee")
    assert r.status_code == 200, r.text
