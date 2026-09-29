"""AK#1794: ground slots, the A/B/C solver slots' twin.

Three stock ground slots (the design's own ground or the session default, free
space, Sommerfeld over average soil), read from ``[grounds.N]`` tables by
whatever keys exist, with the older ``[ground]`` table still
meaning slot 1. What the frontend does with them is pinned in
``groundSlots.session.test.tsx``; this file pins the file's side.
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
    path = tmp_path / "settings.toml"
    monkeypatch.setenv(ui_settings.SETTINGS_ENV, str(path))
    monkeypatch.setattr(server, "_HOSTED", False)
    return path


@pytest.fixture(scope="module")
def client():
    return TestClient(server.app)


def _load(cat, local, text: str) -> dict:
    local.write_text(text)
    return ui_settings.load(cat, hosted=False)


def _by_id(payload) -> dict:
    return {
        g["id"]: {k: v for k, v in g.items() if k != "id"} for g in payload["grounds"]
    }


def test_the_stock_set(cat, local):
    payload = ui_settings.load(cat, hosted=False)
    assert payload["problems"] == []
    grounds = _by_id(payload)
    assert list(grounds) == ["1", "2", "3"]
    # 1: the session default, which is today's single ground.
    assert grounds["1"] == ui_settings.GROUND_BUILTIN == payload["ground"]
    # 2: free space.
    assert grounds["2"] == {**ui_settings.GROUND_BUILTIN, "enabled": False}
    # 3: Sommerfeld over average soil, the preset's own numbers.
    eps, sig = cat.soils["average"]
    assert grounds["3"] == {
        **ui_settings.GROUND_BUILTIN,
        "method": "sommerfeld",
        "soil": {"eps_r": eps, "sigma": sig},
    }


def test_the_stock_table_resolves_cleanly(cat):
    problems: list[str] = []
    for sid, table in ui_settings.STOCK_GROUNDS:
        ui_settings._resolve_ground(
            table, ui_settings.GROUND_BUILTIN, f"[grounds.{sid}]", cat, problems
        )
    assert problems == []


def test_the_older_ground_table_is_slot_1(cat, local):
    payload = _load(cat, local, '[ground]\nmethod = "mininec"\nenabled = false\n')
    assert payload["problems"] == []
    grounds = _by_id(payload)
    assert grounds["1"]["method"] == "mininec"
    assert grounds["1"]["enabled"] is False
    assert payload["ground"] == grounds["1"]
    assert sorted(payload["ground_set"]) == ["enabled", "method"]
    # The other slots keep their stock.
    assert grounds["2"]["enabled"] is False
    assert grounds["3"]["method"] == "sommerfeld"


def test_grounds_tables_set_each_slot(cat, local):
    payload = _load(
        cat,
        local,
        '[grounds.1]\ntype = "pec"\n\n[grounds.2]\nenabled = true\nsoil = "poor"\n\n'
        '[grounds.3]\ntype = "terrain"\nterrain_preset = "cliff"\n',
    )
    assert payload["problems"] == []
    grounds = _by_id(payload)
    assert grounds["1"]["type"] == "pec"
    assert payload["ground"]["type"] == "pec"
    assert payload["ground_set"] == ["type"]
    eps, sig = cat.soils["poor"]
    assert grounds["2"]["enabled"] is True
    assert grounds["2"]["soil"] == {"eps_r": eps, "sigma": sig}
    # A table applies over its slot's stock: slot 3 keeps its Sommerfeld.
    assert grounds["3"]["type"] == "terrain"
    assert grounds["3"]["method"] == "sommerfeld"
    assert grounds["3"]["terrain_preset"] == "cliff"


def test_both_spellings_of_slot_1_use_grounds_1_and_say_so(cat, local):
    payload = _load(
        cat,
        local,
        '[ground]\nmethod = "mininec"\n\n[grounds.1]\nmethod = "sommerfeld"\n',
    )
    assert payload["problems"] == [
        "[ground] and [grounds.1] both given: [grounds.1] is used "
        "([ground] is the older spelling of ground slot 1)"
    ]
    assert _by_id(payload)["1"]["method"] == "sommerfeld"
    assert payload["ground"]["method"] == "sommerfeld"


def test_slots_are_read_by_whatever_keys_exist(cat, local):
    payload = _load(cat, local, '[grounds.4]\ntype = "pec"\n\n[grounds.5]\n')
    assert payload["problems"] == []
    grounds = _by_id(payload)
    assert list(grounds) == ["1", "2", "3", "4", "5"]
    # A slot past the stock set starts at the built-in ground.
    assert grounds["4"] == {**ui_settings.GROUND_BUILTIN, "type": "pec"}
    assert grounds["5"] == ui_settings.GROUND_BUILTIN


def test_bad_ground_slot_tables_are_named(cat, local):
    payload = _load(
        cat,
        local,
        "[grounds.x]\n\n[grounds.0]\n\n[grounds.01]\n\n[grounds.6]\n\n"
        '[grounds.2]\ntype = "concrete"\ncolour = "brown"\neps_r = 13\n',
    )
    problems = "\n".join(payload["problems"])
    for fragment in (
        "[grounds.x]: not a ground slot",
        "[grounds.0]: not a ground slot",
        "[grounds.01]: not a ground slot",
        "[grounds.6]: ground slots are numbered without gaps, and there is no slot 4",
        "[grounds.2] type = 'concrete': must be one of finite, pec, terrain",
        "[grounds.2] colour: not a ground setting",
        "[grounds.2] eps_r and sigma go together",
    ):
        assert fragment in problems, fragment
    assert len(payload["problems"]) == 7
    grounds = _by_id(payload)
    assert list(grounds) == ["1", "2", "3"]
    # What was invalid keeps its stock.
    assert grounds["2"] == {**ui_settings.GROUND_BUILTIN, "enabled": False}


def test_capabilities_serves_the_ground_slots(client, local):
    local.write_text("[grounds.2]\nenabled = true\n")
    ui = client.get("/capabilities").json()["ui_defaults"]
    assert [g["id"] for g in ui["grounds"]] == ["1", "2", "3"]
    assert ui["grounds"][1]["enabled"] is True
    assert "_ground_spelling" not in ui


def _body(cat) -> dict:
    """The body the page posts for an untouched session (AK#1794 shape): every
    ground slot as the page seeds it, soil numbers and terrain preset filled."""
    grounds = {}
    for g in cat.stock_grounds:
        soil = g["soil"] or {"eps_r": cat.soil_default[0], "sigma": cat.soil_default[1]}
        grounds[g["id"]] = {
            "enabled": g["enabled"],
            "type": g["type"],
            "method": g["method"],
            **soil,
            "terrain_preset": g["terrain_preset"] or cat.terrain_default,
        }
    return {"switches": dict(BUILTIN_SWITCHES), "grounds": grounds}


def test_an_untouched_set_of_ground_slots_writes_nothing(cat, local):
    ui_settings.save(_body(cat), cat, path=local)
    text = local.read_text()
    assert tomllib.loads(text) == {}, text
    loaded = ui_settings.load(cat, hosted=False, path=local)
    assert loaded["grounds"] == [dict(g) for g in cat.stock_grounds]


def test_a_save_writes_only_the_slots_that_differ_and_reads_back(cat, local):
    body = _body(cat)
    body["grounds"]["1"]["method"] = "sommerfeld"
    body["grounds"]["2"]["type"] = "pec"
    eps, sig = cat.soils["good"]
    body["grounds"]["3"].update(eps_r=eps, sigma=sig)
    # A fourth slot, as a later "+" would add it, left at the built-in ground.
    body["grounds"]["4"] = {**body["grounds"]["1"], "method": "fast"}
    ui_settings.save(body, cat, path=local)
    assert tomllib.loads(local.read_text()) == {
        "grounds": {
            "1": {"method": "sommerfeld"},
            "2": {"type": "pec"},
            "3": {"soil": "good"},
            # Present though empty: the table is what makes slot 4 exist.
            "4": {},
        }
    }
    loaded = _by_id(ui_settings.load(cat, hosted=False, path=local))
    assert list(loaded) == ["1", "2", "3", "4"]
    assert loaded["1"]["method"] == "sommerfeld"
    assert loaded["2"]["type"] == "pec"
    assert loaded["3"]["soil"] == {"eps_r": eps, "sigma": sig}
    assert loaded["4"] == ui_settings.GROUND_BUILTIN
    # And a second save of what was read is the same file, less its stamp.
    first = local.read_text().splitlines()[5:]
    ui_settings.save(body, cat, path=local)
    assert local.read_text().splitlines()[5:] == first


def test_a_body_with_both_spellings_of_slot_1_is_refused(client, local):
    body = {
        "switches": BUILTIN_SWITCHES,
        "ground": {"enabled": True, "type": "finite", "method": "fast"},
        "grounds": {"1": {"enabled": True, "type": "finite", "method": "fast"}},
    }
    r = client.post("/settings", json=body)
    assert r.status_code == 422
    assert any("[grounds.1] is used" in p for p in r.json()["detail"]["problems"])
    assert not local.exists()


def test_the_frontend_fallback_is_the_stock_set(cat):
    """lib/settings.ts's BUILTIN_GROUND_SLOTS covers a payload without
    `grounds`. Its slot 3 leaves the soil at null, the served default, which
    is only the stock's "average" while the two are the same soil."""
    ts = (ROOT / "src/antennaknobs/web/frontend/src/lib/settings.ts").read_text()
    block = re.search(
        r"BUILTIN_GROUND_SLOTS: GroundSlotDefaults\[\] = \[(.*?)\n\];", ts, re.S
    )
    assert block, "BUILTIN_GROUND_SLOTS not found in lib/settings.ts"
    rows = re.findall(r'\{ id: "(\d+)",(.*?)\}', block.group(1), re.S)
    assert [sid for sid, _ in rows] == [g["id"] for g in cat.stock_grounds]
    for (_, text), stock in zip(rows, cat.stock_grounds, strict=True):
        expect = {**ui_settings.GROUND_BUILTIN, **stock}
        for key in ("enabled", "type", "method"):
            value = expect[key]
            lit = str(value).lower() if isinstance(value, bool) else f'"{value}"'
            if f"{key}:" in text:
                assert f"{key}: {lit}" in text, (key, text)
            else:
                assert value == ui_settings.GROUND_BUILTIN[key], (key, text)
    assert cat.soils["average"] == cat.soil_default
