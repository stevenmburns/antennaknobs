"""AK#1737: settings.toml sets the Antenna view's orientation on a design load.

AC6LA asked for Iso as a default. Steve's scope: ``auto`` (the default) is
today's per-design guess; ``top`` / ``front`` / ``side`` / ``iso`` win over
that guess at every design load. The save is sparse (#1497): ``auto`` writes
nothing. What the frontend does with the value is pinned in
``useViewState.orientation.test.tsx``; this file pins the file's round trip.
"""

from __future__ import annotations

import re
import tomllib
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from antennaknobs.web import server
from antennaknobs.web import settings as ui_settings

ROOT = Path(__file__).resolve().parents[1]
BUILTIN_SWITCHES = {k: d for k, _, d in ui_settings.SWITCHES}


@pytest.fixture
def cat():
    return ui_settings.catalog(have_pynec=False, have_nec5=False, have_nec2=False)


@pytest.fixture
def local(monkeypatch, tmp_path):
    """The settings file this test owns, on a local (not hosted) instance."""
    path = tmp_path / "settings.toml"
    monkeypatch.setenv(ui_settings.SETTINGS_ENV, str(path))
    monkeypatch.setattr(server, "_HOSTED", False)
    return path


@pytest.fixture(scope="module")
def client():
    return TestClient(server.app)


def _body(orientation: str | None) -> dict:
    """A save body for an otherwise untouched session (built-in switches,
    ground at its built-ins, no slot overrides)."""
    body: dict = {
        "switches": dict(BUILTIN_SWITCHES),
        "ground": {
            k: ui_settings.GROUND_BUILTIN[k] for k in ("enabled", "type", "method")
        },
        "slots": {},
    }
    if orientation is not None:
        body["antenna_view"] = {"orientation": orientation}
    return body


def test_no_file_means_auto(cat, local):
    payload = ui_settings.load(cat, hosted=False)
    assert payload["antenna_view"] == {"orientation": "auto"}
    assert payload["problems"] == []


@pytest.mark.parametrize("orientation", ["auto", "top", "front", "side", "iso"])
def test_each_orientation_is_served(client, local, orientation):
    local.write_text(f'[antenna_view]\norientation = "{orientation}"\n')
    ui = client.get("/capabilities").json()["ui_defaults"]
    assert ui["antenna_view"] == {"orientation": orientation}
    assert ui["problems"] == []


def test_a_bad_value_or_key_is_named_and_auto_applies(cat, local):
    local.write_text(
        '[switches]\nwire_labels = true\n\n[antenna_view]\norientation = "Iso"\nzoom = 2\n'
    )
    payload = ui_settings.load(cat, hosted=False)
    assert payload["antenna_view"] == {"orientation": "auto"}
    assert payload["switches"]["wire_labels"] is True
    assert payload["problems"] == [
        "[antenna_view] orientation = 'Iso': must be one of auto, top, front, side, iso",
        "[antenna_view] zoom: not an antenna view setting (known: orientation)",
    ]


def test_a_table_that_is_not_a_table_is_named(cat, local):
    local.write_text('antenna_view = "iso"\n')
    payload = ui_settings.load(cat, hosted=False)
    assert payload["antenna_view"] == {"orientation": "auto"}
    assert payload["problems"] == ["[antenna_view] must be a table"]


def test_save_iso_writes_the_table_and_reads_back(client, local):
    r = client.post("/settings", json=_body("iso"))
    assert r.status_code == 200, r.text
    assert tomllib.loads(local.read_text()) == {"antenna_view": {"orientation": "iso"}}
    assert r.json()["antenna_view"] == {"orientation": "iso"}
    ui = client.get("/capabilities").json()["ui_defaults"]
    assert ui["antenna_view"] == {"orientation": "iso"}


def test_save_auto_writes_nothing_and_clears_an_earlier_choice(client, local):
    assert client.post("/settings", json=_body("side")).status_code == 200
    assert tomllib.loads(local.read_text()) == {"antenna_view": {"orientation": "side"}}
    assert client.post("/settings", json=_body("auto")).status_code == 200
    assert tomllib.loads(local.read_text()) == {}
    ui = client.get("/capabilities").json()["ui_defaults"]
    assert ui["antenna_view"] == {"orientation": "auto"}


def test_a_page_predating_the_key_saves_auto(client, local):
    """An older frontend posts no antenna_view: that is auto, and a save of
    it writes nothing, so a stale tab cannot invent a choice."""
    assert client.post("/settings", json=_body(None)).status_code == 200
    assert tomllib.loads(local.read_text()) == {}


def test_save_refuses_a_bad_orientation_and_writes_nothing(client, local):
    r = client.post("/settings", json=_body("isometric"))
    assert r.status_code == 422
    assert any("isometric" in p for p in r.json()["detail"]["problems"])
    assert not local.exists()


def test_the_frontend_list_is_this_table():
    """lib/settings.ts carries the same orientations and the same default."""
    ts = (ROOT / "src/antennaknobs/web/frontend/src/lib/settings.ts").read_text()
    listed = re.search(r"ORIENTATIONS: Orientation\[\] = \[(.*?)\];", ts, re.S)
    assert listed, "ORIENTATIONS not found in lib/settings.ts"
    assert tuple(re.findall(r'"(\w+)"', listed.group(1))) == ui_settings.ORIENTATIONS
    default = re.search(r'BUILTIN_ORIENTATION: Orientation = "(\w+)"', ts)
    assert default, "BUILTIN_ORIENTATION not found in lib/settings.ts"
    assert default.group(1) == ui_settings.ANTENNA_VIEW_BUILTIN["orientation"]
