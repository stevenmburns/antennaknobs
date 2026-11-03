"""settings.toml picks the polar pattern charts' scale (AC6LA, 2026-11-03).

Dan compared the rings EZNEC, AutoEZ, 4nec2 and the ARRL Antenna Book draw,
and asked for a Scale choice of ARRL (the Antenna Book's rings, a -3 dB
half-power ring among them), EZNEC (5/10/15/20/30) and linear dB, with the
default settable in settings.toml. ``arrl`` is the built-in, so a save of it
writes nothing (sparse, #1497). A choice made in the page is remembered per
browser over this default; that half is pinned in patternScale.test.ts.
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
def local(monkeypatch, tmp_path):
    """The settings file this test owns, on a local (not hosted) instance."""
    path = tmp_path / "settings.toml"
    monkeypatch.setenv(ui_settings.SETTINGS_ENV, str(path))
    monkeypatch.setattr(server, "_HOSTED", False)
    return path


@pytest.fixture(scope="module")
def client():
    return TestClient(server.app)


def _body(scale: str | None) -> dict:
    body: dict = {
        "switches": dict(BUILTIN_SWITCHES),
        "ground": {
            k: ui_settings.GROUND_BUILTIN[k] for k in ("enabled", "type", "method")
        },
        "slots": {},
    }
    if scale is not None:
        body["pattern_chart"] = {"scale": scale}
    return body


def _ui(client):
    return client.get("/capabilities").json()["ui_defaults"]


def test_no_file_means_arrl(client, local):
    assert _ui(client)["pattern_chart"] == {"scale": "arrl"}


@pytest.mark.parametrize("scale", ["arrl", "eznec", "linear"])
def test_the_file_sets_the_scale(client, local, scale):
    local.write_text(f'[pattern_chart]\nscale = "{scale}"\n')
    ui = _ui(client)
    assert ui["pattern_chart"] == {"scale": scale}
    assert ui["problems"] == []


def test_a_bad_value_or_key_is_named_and_the_builtin_applies(client, local):
    local.write_text('[pattern_chart]\nscale = "polar"\nrings = 7\n')
    ui = _ui(client)
    assert ui["pattern_chart"] == {"scale": "arrl"}
    assert ui["problems"] == [
        "[pattern_chart] scale = 'polar': must be one of arrl, eznec, linear",
        "[pattern_chart] rings: not a pattern chart setting (known: scale)",
    ]


def test_save_eznec_writes_the_table_and_reads_back(client, local):
    r = client.post("/settings", json=_body("eznec"))
    assert r.status_code == 200, r.text
    assert tomllib.loads(local.read_text()) == {"pattern_chart": {"scale": "eznec"}}
    assert _ui(client)["pattern_chart"] == {"scale": "eznec"}


def test_save_arrl_writes_nothing_and_clears_an_earlier_choice(client, local):
    assert client.post("/settings", json=_body("linear")).status_code == 200
    assert tomllib.loads(local.read_text()) == {"pattern_chart": {"scale": "linear"}}
    assert client.post("/settings", json=_body("arrl")).status_code == 200
    assert tomllib.loads(local.read_text()) == {}


def test_a_page_predating_the_key_saves_nothing(client, local):
    assert client.post("/settings", json=_body(None)).status_code == 200
    assert tomllib.loads(local.read_text()) == {}


def test_save_refuses_a_bad_scale_and_writes_nothing(client, local):
    r = client.post("/settings", json=_body("polar"))
    assert r.status_code == 422
    assert any("polar" in p for p in r.json()["detail"]["problems"])
    assert not local.exists()


def test_the_frontend_list_is_this_table():
    ts = (ROOT / "src/antennaknobs/web/frontend/src/lib/patternScale.ts").read_text()
    listed = re.search(
        r"PATTERN_SCALES: readonly PatternScale\[\] = \[(.*?)\];", ts, re.S
    )
    assert listed, "patternScale.ts no longer lists PATTERN_SCALES"
    names = tuple(re.findall(r'"([a-z]+)"', listed.group(1)))
    assert names == ui_settings.PATTERN_SCALES
    default = re.search(r'DEFAULT_PATTERN_SCALE: PatternScale = "([a-z]+)"', ts)
    assert default and default.group(1) == ui_settings.PATTERN_CHART_BUILTIN["scale"]
