"""The web app's OpenNEC lane (web/opennec_backend.py).

The roster is served, so a new backend is data: these pin that the entry is
served exactly where pyopennec imports and the instance is not hosted, that a
``solver: "opennec"`` request really solves on OpenNEC (and says so), and that
its shape matches the PyNEC lane it is a twin of.
"""

from __future__ import annotations

import numpy as np
import pytest
from fastapi.testclient import TestClient

from antennaknobs.web import server  # first: resolves the adapter import cycle
from antennaknobs.web import adapter, opennec_backend, pynec_backend
from antennaknobs.web import settings as ui_settings

needs_opennec = pytest.mark.skipif(
    not opennec_backend.HAVE_OPENNEC, reason="pyopennec not installed"
)

REQ = {"geometry": "dipoles.invvee", "measurement_freq_mhz": 28.47}


@pytest.fixture
def client() -> TestClient:
    return TestClient(server.app)


def _names(roster):
    return [e["name"] for e in roster]


def test_the_roster_entry_follows_have_opennec():
    on = adapter.backend_roster(have_pynec=True, have_opennec=True)
    off = adapter.backend_roster(have_pynec=True, have_opennec=False)
    assert "opennec" not in _names(off)
    names = _names(on)
    # Beside PyNEC, its twin.
    assert names.index("opennec") == names.index("pynec") + 1
    entry = next(e for e in on if e["name"] == "opennec")
    pynec = next(e for e in on if e["name"] == "pynec")
    assert entry["label"] == "OpenNEC"
    assert entry["kind"] == "opennec"
    # PyNEC's panel, grounds, density and exact pattern: the same NEC-2.
    for key in ("panel", "ground_applied", "ground_refusals", "default_n_per_wire"):
        assert entry[key] == pynec[key], key
    assert entry["exact_pattern"]["label"] == "OpenNEC"
    assert entry["buried"] is False
    assert entry["buried_refusal"].startswith("OpenNEC cannot model")
    # porty has no fill choice, so the knob is not offered.
    assert "fill_reuse" not in entry["model_kwargs"]


def test_the_served_roster_follows_the_import_at_request_time(client, monkeypatch):
    monkeypatch.setattr(server, "_HOSTED", False)
    monkeypatch.setattr(opennec_backend, "HAVE_OPENNEC", False)
    assert "opennec" not in _names(client.get("/capabilities").json()["backends"])
    monkeypatch.setattr(opennec_backend, "HAVE_OPENNEC", True)
    assert "opennec" in _names(client.get("/capabilities").json()["backends"])


def test_hosted_mode_does_not_offer_it(client, monkeypatch):
    monkeypatch.setattr(opennec_backend, "HAVE_OPENNEC", True)
    monkeypatch.setattr(server, "_HOSTED", True)
    assert "opennec" not in _names(client.get("/capabilities").json()["backends"])
    # A request naming it anyway falls back, the pynec contract (#429).
    assert server._external_backend({"solver": "opennec"}) is None
    monkeypatch.setattr(server, "_HOSTED", False)
    assert server._external_backend({"solver": "opennec"}) is opennec_backend


def test_the_settings_catalog_names_it_where_served():
    cat = ui_settings.catalog(
        have_pynec=False, have_nec5=False, have_nec2=False, have_opennec=True
    )
    assert "opennec" in cat.backends
    cat = ui_settings.catalog(have_pynec=False, have_nec5=False, have_nec2=False)
    assert "opennec" not in cat.backends


@needs_opennec
def test_the_served_roster_lists_opennec_with_pyopennec_installed(client, monkeypatch):
    monkeypatch.setattr(server, "_HOSTED", False)
    served = client.get("/capabilities").json()["backends"]
    assert "opennec" in _names(served)


@needs_opennec
def test_a_solve_request_returns_z_from_opennec(monkeypatch):
    monkeypatch.setattr(server, "_HOSTED", False)
    made = []
    from antennaknobs.engines import opennec as opennec_mod

    real = opennec_mod.porty.Structure.solve

    def spy(self, freqs, *args, **kwargs):
        made.append(tuple(freqs))
        return real(self, freqs, *args, **kwargs)

    monkeypatch.setattr(opennec_mod.porty.Structure, "solve", spy)
    out = server.solve({**REQ, "solver": "opennec"})
    assert out["solver"] == "opennec"
    # One porty solve for the impedance and the currents together.
    assert made == [(REQ["measurement_freq_mhz"],)], made
    z = complex(out["z_in_re"], out["z_in_im"])
    assert 10 < z.real < 500, z
    assert out["k_meas_m_inv"] > 0 and out["directivity_norm"] > 0
    assert out["ground_model_applied"] == "free"
    if pynec_backend.HAVE_PYNEC:
        ref = server.solve({**REQ, "solver": "pynec"})
        zp = complex(ref["z_in_re"], ref["z_in_im"])
        assert z != zp  # two bindings, not one twice
        assert abs(z - zp) / abs(zp) < 2e-3, (z, zp)


@needs_opennec
def test_a_grounded_solve_carries_the_ground_it_used(monkeypatch):
    monkeypatch.setattr(server, "_HOSTED", False)
    out = server.solve(
        {**REQ, "solver": "opennec", "ground": True, "ground_model": "sommerfeld"}
    )
    assert out["ground_model_applied"] == "sommerfeld"
    assert out["ground_eps_r"] == 13.0


@needs_opennec
def test_the_exact_pattern_and_a_sweep_point():
    pat = opennec_backend.pattern(REQ)
    g = np.asarray(pat["gain_dbi"])
    assert g.shape == (46, 73)
    assert 0.0 < g.max() < 10.0
    z = opennec_backend._sweep_at(REQ, 28.0)
    assert isinstance(z, complex) and z.real > 0
    primary, feeds = opennec_backend._sweep_at_multifeed(REQ, 28.0)
    assert primary == z


def test_the_solve_seams_are_pynecs_with_the_engine_swapped():
    assert (
        adapter._SEAMS_BY_SOLVER["opennec"].make_engine is adapter._make_opennec_engine
    )
    assert adapter._OPENNEC_SEAMS.run is adapter._PYNEC_SEAMS.run
