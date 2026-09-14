"""AK#1428 — the Files view: the deck an external engine was given, the report
it printed, and the file the design was written as.

The engines record each run's texts (``io_runs``). ``_engine_solve`` hands them
to the server under ``_engine_runs``, or on the exception when the run failed,
and ``server.solve`` parks them by solve_id before the response is cached or
sent. ``/engine_io`` answers the solve on screen from there, re-running the deck
only when its runs have aged out. ``/design_source`` reads the design's file.

Most of this is bookkeeping, so the binaries and the server's solve are stubbed.
The last test drives nec2c when this machine has one: only a real run proves
the texts shown are the ones the readout was parsed from.
"""

from __future__ import annotations

import json
import shutil
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

import antennaknobs.web.server as server
import antennaknobs.designs.dipoles.invvee as invvee_module
from antennaknobs.designs.dipoles.invvee import Builder
from antennaknobs.engines import nec2 as nec2_mod
from antennaknobs.engines.nec2 import NEC2Engine, NEC2Error
from antennaknobs.engines.nec5 import NEC5Engine
from antennaknobs.web.examples import REGISTRY

DECK = "CM stub\nCE\nGW 1 3 0 0 1 0 0 2 0.001\nGE 0\nEX 0 1 2 0 1 0\nFR 0 1 0 0 14.1 0\nXQ 0\nEN\n"
PRINTOUT = "STUB PRINTOUT\n" * 3
RUNS = [{"deck": DECK, "printout": PRINTOUT, "cached": False}]
NEC5_REQ = {"geometry": "dipoles.invvee", "solver": "nec5"}

USER_DECK = """CM 20 m dipole
CE
GW 1 21 -5.05 0 10 5.05 0 10 0.001
GE 0
EX 0 1 11 0 1 0
FR 0 1 0 0 14.1 0
EN
"""

STUB = """
from types import MappingProxyType
from antennaknobs import AntennaBuilder

class Builder(AntennaBuilder):
    label = "the stub wins"
    default_params = MappingProxyType({"freq": 14.1})
    def build_wires(self):
        return [((-5.0, 0.0, 10.0), (5.0, 0.0, 10.0))]
"""


@pytest.fixture
def client():
    return TestClient(server.app)


@pytest.fixture
def caches(monkeypatch):
    """Empty solve, cuts and engine-text caches: no earlier test's entry answers."""
    for name in ("_SOLVE_CACHE", "_CUTS_SRC_CACHE", "_ENGINE_IO_CACHE"):
        monkeypatch.setattr(server, name, getattr(server, name).__class__())
    monkeypatch.setattr(server, "_USER_CACHE_KEYS", {"solve": set(), "sweep": set()})


@pytest.fixture
def nec5_resolves(monkeypatch):
    """The NEC-5 lane as if $NEC5_EXE resolved. Which binary is irrelevant when
    the solve itself is stubbed."""
    monkeypatch.setitem(
        server._EXTERNAL_BACKENDS, "nec5", (server.nec5_backend, lambda: True)
    )


@pytest.fixture
def userdir(tmp_path, monkeypatch):
    monkeypatch.setenv("ANTENNAKNOBS_USER_DIR", str(tmp_path))
    monkeypatch.delenv("ANTENNAKNOBS_TRUST_USER_DESIGNS", raising=False)
    yield tmp_path
    for key in [k for k in REGISTRY if k.startswith("user.")]:
        del REGISTRY[key]


def _stub_solve(monkeypatch, *, calls=None, raises=None):
    def fake(req, cancel=None):
        if calls is not None:
            calls.append(req)
        if raises is not None:
            raise raises
        return {
            "geometry": req["geometry"],
            "solver": "nec5",
            "z_in_re": 50.0,
            "_engine_runs": list(RUNS),
        }

    monkeypatch.setattr(server, "_solve_uncached", fake)
    monkeypatch.setattr(server, "_attach_request_cuts", lambda out, req: None)


# ---------------------------------------------------------------------------
# the engines record what each run was given and printed
# ---------------------------------------------------------------------------


def test_nec5_records_each_run_fresh_or_served_from_the_capture(monkeypatch, tmp_path):
    e = NEC5Engine(Builder(), require_exe=False, capture_dir=tmp_path)
    monkeypatch.setattr(e, "_run_binary", lambda deck: PRINTOUT)
    e._exe = "stub-nec5"
    e._run(DECK)
    e._run(DECK)  # the second is served from the capture folder
    assert e.io_runs == [
        {"deck": DECK, "printout": PRINTOUT, "cached": False},
        {"deck": DECK, "printout": PRINTOUT, "cached": True},
    ]


def _nec2(monkeypatch, tmp_path, printout):
    monkeypatch.setattr(nec2_mod, "find_nec2", lambda explicit=None: "stub-nec2")
    monkeypatch.setattr(
        nec2_mod, "run_deck", lambda exe, deck, *, timeout, form=None: printout
    )
    return NEC2Engine(Builder(), capture_dir=tmp_path)


def test_nec2_records_the_run_it_faulted_on(monkeypatch, tmp_path):
    """The printout of a failed run is where the reason is written, so it is
    recorded before the fault is raised."""
    fault = "  LD type 2 is not supported by this engine\n"
    e = _nec2(monkeypatch, tmp_path, fault)
    with pytest.raises(NEC2Error, match="not supported"):
        e._run(DECK)
    assert e.io_runs == [{"deck": DECK, "printout": fault, "cached": False}]


def test_nec2_names_the_rerun_it_made_for_a_missing_budget(monkeypatch, tmp_path):
    e = _nec2(monkeypatch, tmp_path, PRINTOUT)
    budgets = iter(
        [
            NEC2Error("no POWER BUDGET"),
            {
                "efficiency_pct": 100.0,
                "input_w": 1.0,
                "wire_loss_w": 0.0,
                "network_loss_w": 0.0,
                "radiated_w": 1.0,
            },
        ]
    )

    def parse_budget(text):
        b = next(budgets)
        if isinstance(b, Exception):
            raise b
        return b

    monkeypatch.setattr(e, "_parse_power_budget", parse_budget)
    monkeypatch.setattr(e, "_parse_input_parameters", lambda text: [[]])
    monkeypatch.setattr(e, "_parse_currents", lambda text: [{}])
    monkeypatch.setattr(e, "_currents_from", lambda per_tag: [])
    monkeypatch.setattr(e, "_parse_feed_voltages", lambda text: [])
    e.solve_snapshot()
    assert len(e.io_runs) == 2
    assert "note" not in e.io_runs[0]
    assert "RP 0 1 1" in e.io_runs[1]["deck"]
    assert "power budget" in e.io_runs[1]["note"]


def test_a_failed_engine_solve_carries_its_runs(monkeypatch):
    monkeypatch.setattr(nec2_mod, "find_nec2", lambda explicit=None: "stub-nec2")

    def boom(self):
        self.io_runs.append({"deck": DECK, "printout": "FAULT", "cached": False})
        raise NEC2Error("stub fault")

    monkeypatch.setattr(NEC2Engine, "solve_snapshot", boom)
    with pytest.raises(NEC2Error) as info:
        REGISTRY["dipoles.invvee"].nec2_solve(
            {"geometry": "dipoles.invvee", "solver": "nec2"}
        )
    assert info.value.engine_runs == [
        {"deck": DECK, "printout": "FAULT", "cached": False}
    ]


# ---------------------------------------------------------------------------
# the server parks them by solve_id, and /engine_io answers from there
# ---------------------------------------------------------------------------


def test_a_solve_parks_its_runs_by_solve_id_and_never_sends_them(
    monkeypatch, caches, nec5_resolves
):
    _stub_solve(monkeypatch)
    out = server.solve(dict(NEC5_REQ))
    assert "_engine_runs" not in out
    sid = out["solve_id"]
    assert server._ENGINE_IO_CACHE[sid] == {
        "solver": "nec5",
        "label": "NEC-5",
        "runs": RUNS,
    }
    assert "_engine_runs" not in server._SOLVE_CACHE[sid]
    # The response says only that texts exist, and names their engine.
    assert out["engine_io_label"] == "NEC-5"
    hit = server.solve(dict(NEC5_REQ))
    assert hit["cache_hit"] is True and "_engine_runs" not in hit
    assert hit["engine_io_label"] == "NEC-5"


def test_a_solve_that_ran_no_binary_carries_no_label(monkeypatch, caches):
    monkeypatch.setattr(
        server,
        "_solve_uncached",
        lambda req, cancel=None: {"geometry": req["geometry"], "solver": "momwire"},
    )
    monkeypatch.setattr(server, "_attach_request_cuts", lambda out, req: None)
    out = server.solve({"geometry": "dipoles.invvee", "solver": "momwire"})
    assert "engine_io_label" not in out and not server._ENGINE_IO_CACHE


def test_engine_io_answers_the_solve_on_screen_without_running(
    client, monkeypatch, caches, nec5_resolves
):
    server._ENGINE_IO_CACHE["sid-1"] = {
        "solver": "nec5",
        "label": "NEC-5",
        "runs": RUNS,
    }
    calls = []
    _stub_solve(monkeypatch, calls=calls)
    r = client.post("/engine_io", json={**NEC5_REQ, "solve_id": "sid-1"})
    assert r.status_code == 200
    assert r.json() == {
        "available": True,
        "solve_id": "sid-1",
        "rerun": False,
        "solver": "nec5",
        "label": "NEC-5",
        "runs": RUNS,
    }
    assert calls == []


def test_engine_io_reruns_a_solve_whose_runs_aged_out(
    client, monkeypatch, caches, nec5_resolves
):
    calls = []
    _stub_solve(monkeypatch, calls=calls)
    r = client.post("/engine_io", json={**NEC5_REQ, "solve_id": "aged-out"}).json()
    assert r["available"] is True and r["rerun"] is True and r["runs"] == RUNS
    assert r["label"] == "NEC-5"
    assert len(calls) == 1 and "solve_id" not in calls[0]
    assert r["solve_id"] == server._canonical_solve_key(NEC5_REQ)
    # Remembered under the request's own key: asking again runs nothing.
    again = client.post("/engine_io", json={**NEC5_REQ, "solve_id": r["solve_id"]})
    assert again.json()["rerun"] is False and len(calls) == 1


def test_a_failed_rerun_answers_with_what_the_binary_printed(
    client, monkeypatch, caches, nec5_resolves
):
    exc = RuntimeError("NEC-5 refused the deck")
    exc.engine_runs = RUNS
    _stub_solve(monkeypatch, raises=exc)
    r = client.post("/engine_io", json=NEC5_REQ).json()
    assert r["available"] is True and r["runs"] == RUNS and r["label"] == "NEC-5"
    assert "refused the deck" in r["error"]
    assert not server._ENGINE_IO_CACHE, "a failure is not remembered"


@pytest.mark.parametrize("solver", ["momwire", "pynec", "nec5-unavailable"])
def test_engine_io_has_nothing_for_a_solver_that_runs_no_binary(
    client, monkeypatch, caches, solver
):
    calls = []
    _stub_solve(monkeypatch, calls=calls)
    req = {"geometry": "dipoles.invvee", "solver": solver}
    if solver == "pynec":
        monkeypatch.setitem(
            server._EXTERNAL_BACKENDS, "pynec", (server.pynec_backend, lambda: True)
        )
    if solver == "nec5-unavailable":
        # A NEC-5 slot on a machine without the binary is served by momwire,
        # and momwire ran no deck.
        monkeypatch.setitem(
            server._EXTERNAL_BACKENDS, "nec5", (server.nec5_backend, lambda: False)
        )
        req["solver"] = "nec5"
    expected = "pynec" if solver == "pynec" else "momwire"
    assert client.post("/engine_io", json=req).json() == {
        "available": False,
        "solver": expected,
    }
    assert calls == []


def test_the_engine_text_cache_is_bounded(caches):
    for i in range(server._ENGINE_IO_CACHE_MAX + 3):
        server._remember_engine_io(f"s{i}", "nec5", RUNS)
    assert len(server._ENGINE_IO_CACHE) == server._ENGINE_IO_CACHE_MAX
    assert "s0" not in server._ENGINE_IO_CACHE and "s18" in server._ENGINE_IO_CACHE


# ---------------------------------------------------------------------------
# /design_source
# ---------------------------------------------------------------------------


def test_design_source_serves_a_catalog_designs_module(client):
    r = client.post("/design_source", json={"geometry": "dipoles.invvee"}).json()
    assert r["available"] is True
    assert (r["filename"], r["language"]) == ("invvee.py", "python")
    assert r["text"] == Path(invvee_module.__file__).read_text(encoding="utf-8")


def test_design_source_serves_a_bare_deck_as_written(client, userdir):
    (userdir / "my_dipole.nec").write_text(USER_DECK)
    assert client.get("/examples").status_code == 200  # registers user designs
    r = client.post("/design_source", json={"geometry": "user.my_dipole"}).json()
    assert r == {
        "available": True,
        "geometry": "user.my_dipole",
        "filename": "my_dipole.nec",
        "language": "nec",
        "text": USER_DECK,
    }


def test_a_stub_beside_its_deck_is_the_source(client, userdir, monkeypatch):
    """The stub is the design (#1419), so it is what the Source tab shows."""
    monkeypatch.setenv("ANTENNAKNOBS_TRUST_USER_DESIGNS", "1")
    (userdir / "my_dipole.nec").write_text(USER_DECK)
    (userdir / "my_dipole.py").write_text(STUB)
    assert client.get("/examples").status_code == 200
    r = client.post("/design_source", json={"geometry": "user.my_dipole"}).json()
    assert (r["filename"], r["language"], r["text"]) == ("my_dipole.py", "python", STUB)


def test_design_source_refuses_a_design_the_registry_does_not_hold(client):
    r = client.post("/design_source", json={"geometry": "no.such_design"})
    assert r.status_code == 400 and "no.such_design" in r.json()["error"]


# ---------------------------------------------------------------------------
# end to end, with a real NEC-2
# ---------------------------------------------------------------------------


@pytest.mark.skipif(shutil.which("nec2c") is None, reason="no nec2c on PATH")
def test_the_texts_are_the_ones_the_readout_was_parsed_from(
    client, caches, monkeypatch
):
    monkeypatch.setenv("NEC2_EXE", shutil.which("nec2c"))
    req = {"geometry": "dipoles.invvee", "solver": "nec2"}
    with client.websocket_connect("/ws") as ws:
        ws.send_text(json.dumps(req))
        out = json.loads(ws.receive_text())
    assert out["solver"] == "nec2" and "_engine_runs" not in out
    assert out["engine_io_label"] == "NEC-2"

    io = client.post("/engine_io", json={**req, "solve_id": out["solve_id"]}).json()
    assert io["available"] is True and io["rerun"] is False and io["solver"] == "nec2"
    (run,) = io["runs"]
    assert run["deck"].rstrip().endswith("EN")
    z = NEC2Engine._parse_input_parameters(run["printout"])[0][0][2]
    assert z.real == pytest.approx(out["z_in_re"], rel=1e-12)
    assert z.imag == pytest.approx(out["z_in_im"], rel=1e-12)
