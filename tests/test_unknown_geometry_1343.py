"""Issue #1343: a request naming a design the registry does not hold is
refused with the key in the sentence, never answered for a different design.
"""

from __future__ import annotations

import pytest
from starlette.testclient import TestClient

import antennaknobs.web.server as server  # noqa: I001 — the server must load before examples (adapter/examples import cycle)
from antennaknobs.web.examples import REGISTRY, UnknownGeometryError, example_for


def test_example_for_names_the_key_and_the_nearest_designs():
    with pytest.raises(UnknownGeometryError) as ei:
        example_for("invvee")
    msg = str(ei.value)
    assert "'invvee'" in msg and "dipoles.invvee" in msg
    assert example_for("dipoles.invvee") is REGISTRY["dipoles.invvee"]


def test_an_absent_key_still_defaults_but_an_unknown_one_refuses():
    default = next(iter(REGISTRY))
    assert example_for(default) is REGISTRY[default]
    with pytest.raises(UnknownGeometryError):
        server.solve({"geometry": "no.such.design", "freqs_mhz": [14.1]})


def test_http_routes_answer_400_with_the_key():
    client = TestClient(server.app)
    r = client.post("/geometry", json={"geometry": "invvee"})
    assert r.status_code == 400, r.text
    assert "invvee" in r.json()["error"] and "dipoles.invvee" in r.json()["error"]
