"""``POST /design_ssn`` — the .ssn export with no terminal in it (AK#1539).

The documented way to hand a design to SimNEC was ``python -m
antennaknobs.simnec_export``. The workbench is the whole interface a packaged
Windows user has, so for them the round trip did not exist. This is the same
writer behind a route, built from the request the way a solve is — so the
circuit is the antenna on screen at its frequency and ground, not the design's
defaults — and the Files view puts a tab on it.

What is pinned here: the text comes back importable (the round trip is the
point, so parse_ssn reading it is the assertion, not a substring), the request
is honoured, and a design SimNEC cannot represent gets a stated reason instead
of an error.
"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

import antennaknobs.web.server as server
from antennaknobs.simnec_import import parse_ssn

# A plain antenna, and a station whose ladder SimNEC's cascade can carry.
CATALOG = "dipoles.invvee"
STATION = "wire.doublet_ladder_tuner"
# A distributed (finite-gap) feed port: no SimNEC spelling, and no NEC-2 one.
REFUSES = "wire.zepp"


@pytest.fixture
def client():
    return TestClient(server.app)


def _req(geometry: str, **over) -> dict:
    return {
        "geometry": geometry,
        "solver": "momwire",
        "n_per_wire": 11,
        "design_freq_mhz": 14.1,
        "measurement_freq_mhz": 14.1,
        "wire_radius": 0.001,
        "ground": False,
        "ground_fast": False,
        **over,
    }


def _ssn(client, geometry: str, **over) -> dict:
    r = client.post("/design_ssn", json=_req(geometry, **over))
    assert r.status_code == 200
    return r.json()


def test_a_catalog_design_comes_back_as_an_importable_circuit(client):
    got = _ssn(client, CATALOG)
    assert got["available"] is True
    assert got["filename"] == "dipoles_invvee.ssn"
    assert got["language"] == "ssn"
    circuit = parse_ssn(got["text"], name=got["filename"])
    assert circuit.deck.wires


def test_a_station_design_carries_its_chain_back(client):
    got = _ssn(client, STATION)
    assert got["available"] is True
    circuit = parse_ssn(got["text"], name=got["filename"], network=True)
    assert circuit.chain  # the tuner ladder, element for element
    assert circuit.network() is not None


def test_the_circuit_is_the_antenna_on_screen_not_the_defaults(client):
    """The trap this route sits next to: a builder built without the request's
    frequency exports a different antenna from the one being looked at."""
    got = _ssn(client, CATALOG, design_freq_mhz=21.2, measurement_freq_mhz=21.2)
    circuit = parse_ssn(got["text"], name="f.ssn")
    assert circuit.freq_mhz == pytest.approx(21.2)


def test_the_ground_on_screen_is_the_ground_in_the_circuit(client):
    free = _ssn(client, CATALOG)["text"]
    finite = _ssn(client, CATALOG, ground=True, ground_fast=False)["text"]
    assert "Ground" not in free
    assert "SommerfeldGround" in finite


def test_a_design_simnec_cannot_represent_says_why(client):
    got = _ssn(client, REFUSES)
    assert got["available"] is False
    assert "distributed" in got["reason"]


def test_the_export_needs_no_pynec(client, monkeypatch):
    """The packaged workbench ships no PyNEC (the #1354 licence argument), and
    the writer builds a PyNECEngine for its geometry without ever running it.
    With the library absent, the route still answers."""
    import antennaknobs.engines.pynec as pynec_mod

    monkeypatch.setattr(pynec_mod, "nec", None)
    assert _ssn(client, CATALOG)["available"] is True
