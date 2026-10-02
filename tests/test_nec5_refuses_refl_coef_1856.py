"""AK#1856 part 2: the workbench refuses NEC-5 on a refl-coef ground.

NEC-5 has no reflection-coefficient model (its IPERF 0 is a full Sommerfeld
solution). The engine and the CLI already refused ``finite-fast``; the web
adapter used to serve the request with the Sommerfeld solve instead, an
upgrade nobody asked for and a curve on different physics beside the engines
that honour the request. Now all three front doors refuse with one sentence,
and the roster serves that refusal, derived from the SAME ground spec the
solve runs, so the page can mark the pair before anything solves.

None of this needs a NEC-5 binary: the spec refuses before an engine is built.
"""

from __future__ import annotations

import json
import re
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

# The server package first: importing adapter directly at collection time
# trips the adapter <-> examples circular import.
from antennaknobs.web import server

from antennaknobs.engines.nec5 import REFL_COEF_CLI_HINT, REFL_COEF_REFUSAL, NEC5Engine
from antennaknobs.web import adapter, nec5_backend
from antennaknobs.web.adapter import (
    DEFAULT_GROUND,
    _nec5_ground_spec,
    backend_roster,
)

DESIGN = {"geometry": "dipoles.invvee", "measurement_freq_mhz": 28.47}
SOIL = tuple(DEFAULT_GROUND[1:])
REFUSED = re.escape(REFL_COEF_REFUSAL)


@pytest.fixture
def nec5_offered(monkeypatch):
    """The server's NEC-5 lane as a machine with the binary has it. The
    refusal comes before the binary is reached, so no binary is needed."""
    monkeypatch.setitem(server._EXTERNAL_BACKENDS, "nec5", (nec5_backend, lambda: True))


# --- the spec: refused by name, everything else unchanged ----------------


@pytest.mark.parametrize(
    "req",
    [
        {"ground": True, "ground_model": "fast"},
        # The legacy boolean means "fast" when no ground_model is sent.
        {"ground": True, "ground_fast": True},
    ],
    ids=["fast", "legacy-ground_fast"],
)
def test_the_spec_refuses_refl_coef_in_the_engines_words(req):
    with pytest.raises(NotImplementedError, match=REFUSED):
        _nec5_ground_spec(req)


@pytest.mark.parametrize(
    "req,spec",
    [
        ({"ground": True, "ground_model": "sommerfeld"}, ("finite", *SOIL)),
        ({"ground": True}, ("finite", *SOIL)),
        ({"ground": True, "ground_model": "pec"}, "pec"),
        ({"ground": True, "ground_model": "mininec"}, ("mininec", *SOIL)),
        ({"ground": False, "ground_model": "fast"}, None),
        ({}, None),
    ],
    ids=["sommerfeld", "default", "pec", "mininec", "off-with-fast", "free"],
)
def test_every_other_ground_maps_as_before(req, spec):
    assert _nec5_ground_spec(req) == spec


def test_terrain_still_rides_the_crest_medium():
    spec = _nec5_ground_spec({"ground": True, "ground_model": "terrain"})
    assert spec[0] == "finite" and len(spec) == 3


def test_the_engine_refuses_with_the_same_sentence():
    """What `--engine nec5 --ground finite-fast` reaches: one sentence for
    the engine, the CLI and the workbench. The ground is checked before the
    builder or the binary is touched."""
    with pytest.raises(NotImplementedError, match=REFUSED) as e:
        NEC5Engine(object(), ground=("finite-fast", *SOIL), require_exe=False)
    # The command line's spelling of the way out, which the web leaves to its
    # button.
    assert str(e.value).endswith(REFL_COEF_CLI_HINT)


# --- the served refusal is the spec's ------------------------------------


def _nec5_entry() -> dict:
    roster = backend_roster(have_pynec=False, have_nec5=True)
    return next(e for e in roster if e["name"] == "nec5")


def test_the_roster_serves_the_refusal_and_no_applied_row_for_it():
    nec5 = _nec5_entry()
    assert nec5["ground_refusals"] == {"fast": REFL_COEF_REFUSAL}
    assert nec5["ground_applied"] == {"sommerfeld": "sommerfeld", "mininec": "mininec"}


def test_no_other_backend_refuses_a_finite_method():
    roster = backend_roster(
        have_pynec=True, have_nec5=True, have_nec2=True, have_nec42=True
    )
    assert {e["name"]: e["ground_refusals"] for e in roster if e["name"] != "nec5"} == {
        e["name"]: {} for e in roster if e["name"] != "nec5"
    }


def test_each_method_is_served_or_refused_never_both():
    roster = backend_roster(
        have_pynec=True, have_nec5=True, have_nec2=True, have_nec42=True
    )
    for e in roster:
        served, refused = set(e["ground_applied"]), set(e["ground_refusals"])
        assert not served & refused, e["name"]
        assert served | refused == {"fast", "sommerfeld", "mininec"}, e["name"]


def test_the_served_refusal_follows_the_spec(monkeypatch):
    """Would fail if the roster kept a table of its own: a spec that also
    refused MININEC is served as refusing it, and one that refused nothing
    is served as refusing nothing."""
    real = adapter._nec5_ground_spec

    def also_refuses_mininec(req):
        if adapter._requested_ground_model(req) == "mininec":
            raise NotImplementedError("no MININEC here")
        return real(req)

    monkeypatch.setattr(adapter, "_nec5_ground_spec", also_refuses_mininec)
    assert _nec5_entry()["ground_refusals"] == {
        "fast": REFL_COEF_REFUSAL,
        "mininec": "no MININEC here",
    }

    def refuses_nothing(req):
        if adapter._requested_ground_model(req) == "fast":
            return ("finite",) + SOIL
        return real(req)

    monkeypatch.setattr(adapter, "_nec5_ground_spec", refuses_nothing)
    nec5 = _nec5_entry()
    assert nec5["ground_refusals"] == {}
    assert nec5["ground_applied"]["fast"] == "sommerfeld"


# --- the web solve path ----------------------------------------------------


@pytest.mark.parametrize(
    "ground",
    [{"ground_model": "fast"}, {"ground_fast": True}],
    ids=["fast", "legacy-ground_fast"],
)
def test_the_web_solve_refuses(nec5_offered, ground):
    req = {**DESIGN, "solver": "nec5", "ground": True, **ground}
    with pytest.raises(NotImplementedError, match=REFUSED):
        server.solve(req)


def test_the_live_socket_answers_with_the_sentence(nec5_offered):
    with TestClient(server.app).websocket_connect("/ws") as ws:
        ws.send_text(
            json.dumps(
                {**DESIGN, "solver": "nec5", "ground": True, "ground_model": "fast"}
            )
        )
        res = json.loads(ws.receive_text())
    assert res["error"] == f"NotImplementedError: {REFL_COEF_REFUSAL}"


def test_the_nec5_deck_download_refuses_as_the_solve_does():
    """The deck is written with no binary; on a refl-coef slot it used to
    carry the Sommerfeld ground the solve upgraded to."""
    r = TestClient(server.app).post(
        "/export_nec",
        json={**DESIGN, "dialect": "nec5", "ground": True, "ground_model": "fast"},
    )
    assert r.status_code == 422
    assert r.json()["detail"] == REFL_COEF_REFUSAL


def test_the_nec5_deck_on_sommerfeld_is_unchanged():
    r = TestClient(server.app).post(
        "/export_nec",
        json={
            **DESIGN,
            "dialect": "nec5",
            "ground": True,
            "ground_model": "sommerfeld",
        },
    )
    assert r.status_code == 200, r.text


def test_the_frontend_fixture_carries_the_sentence_verbatim():
    """backendFixtures.ts is hand-maintained; the session tests assert the
    page shows the served sentence, so the fixture's copy must be it."""
    fixture = (
        Path(__file__).resolve().parents[1]
        / "src/antennaknobs/web/frontend/src/__tests__/backendFixtures.ts"
    ).read_text(encoding="utf-8")
    assert f"NEC5_REFL_COEF_REFUSAL =\n  {json.dumps(REFL_COEF_REFUSAL)};" in fixture
