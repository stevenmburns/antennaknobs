"""AK#1801: the ground slots are X, Y, Z, not 1, 2, 3.

The letters make them their own family beside the A/B/C solver slots. Past Z
they run in chunks of three, each read forwards: U V W, then R S T, and so on
(Steve's ruling in the issue). The numbered spelling was on main but in no
release, so ``[grounds.1]`` and its kin are still read, as the slot at that
place in the sequence, with a note; a file spelling one slot both ways is
refused by name. The stock set and the rest of the slot rules are
``test_ground_slots_1794.py``.
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


def _note(n: int, sid: str) -> str:
    return (
        f"[grounds.{n}] is read as [grounds.{sid}]: ground slots are named "
        "X, Y, Z, ... now, and a save writes the letter"
    )


def _body_from(cat, payload) -> dict:
    """What the page posts for the slots a payload served, untouched."""
    grounds = {}
    for g in payload["grounds"]:
        soil = g["soil"] or {"eps_r": cat.soil_default[0], "sigma": cat.soil_default[1]}
        grounds[g["id"]] = {
            "enabled": g["enabled"],
            "type": g["type"],
            "method": g["method"],
            **soil,
            "terrain_preset": g["terrain_preset"] or cat.terrain_default,
        }
    return {"switches": dict(BUILTIN_SWITCHES), "grounds": grounds}


def test_the_sequence_is_chunks_of_three_read_forwards():
    ids = ui_settings.GROUND_SLOT_IDS
    assert "".join(ids[:9]) == "XYZUVWRST"
    # Down to F G H, and never into the solver slots' A-E.
    assert "".join(ids) == "XYZUVWRSTOPQLMNIJKFGH"
    assert not set(ids) & set("ABCDE")
    assert len(set(ids)) == len(ids)
    assert [sid for sid, _ in ui_settings.STOCK_GROUNDS] == ["X", "Y", "Z"]


def test_the_frontend_names_the_same_sequence():
    """lib/groundSlots.ts's GROUND_SLOT_IDS is the twin of the Python one."""
    ts = (ROOT / "src/antennaknobs/web/frontend/src/lib/groundSlots.ts").read_text()
    block = re.search(
        r'GROUND_SLOT_IDS: readonly GroundSlotId\[\] = \[\.\.\."([A-Z]+)"\];', ts
    )
    assert block, "GROUND_SLOT_IDS not found in lib/groundSlots.ts"
    assert tuple(block.group(1)) == ui_settings.GROUND_SLOT_IDS


def test_letters_round_trip(cat, local):
    payload = _load(
        cat,
        local,
        '[grounds.X]\nmethod = "mininec"\n\n[grounds.Z]\ntype = "pec"\n\n'
        '[grounds.U]\nsoil = "poor"\n',
    )
    assert payload["problems"] == []
    grounds = _by_id(payload)
    assert list(grounds) == ["X", "Y", "Z", "U"]
    body = _body_from(cat, payload)
    ui_settings.save(body, cat, path=local)
    assert tomllib.loads(local.read_text()) == {
        "grounds": {
            "X": {"method": "mininec"},
            "Z": {"type": "pec"},
            "U": {"soil": "poor"},
        }
    }
    again = ui_settings.load(cat, hosted=False, path=local)
    assert again["problems"] == []
    assert _by_id(again) == grounds


def test_numbered_tables_are_read_as_their_letters_with_a_note(cat, local):
    payload = _load(
        cat,
        local,
        '[grounds.1]\nmethod = "mininec"\n\n[grounds.2]\nenabled = true\n\n'
        '[grounds.3]\ntype = "pec"\n',
    )
    assert payload["problems"] == [_note(1, "X"), _note(2, "Y"), _note(3, "Z")]
    grounds = _by_id(payload)
    assert list(grounds) == ["X", "Y", "Z"]
    assert grounds["X"]["method"] == "mininec"
    assert payload["ground"]["method"] == "mininec"
    assert payload["ground_set"] == ["method"]
    assert grounds["Y"]["enabled"] is True
    # Over the stock: Z keeps its refl-coef (AK#1856).
    assert grounds["Z"]["type"] == "pec"
    assert grounds["Z"]["method"] == "fast"


def test_numbers_past_three_map_onto_the_sequence(cat, local):
    payload = _load(
        cat,
        local,
        '[grounds.4]\ntype = "pec"\n\n[grounds.5]\n\n[grounds.6]\n\n'
        '[grounds.7]\nmethod = "sommerfeld"\n',
    )
    assert payload["problems"] == [
        _note(4, "U"),
        _note(5, "V"),
        _note(6, "W"),
        _note(7, "R"),
    ]
    grounds = _by_id(payload)
    assert list(grounds) == ["X", "Y", "Z", "U", "V", "W", "R"]
    assert grounds["U"] == {**ui_settings.GROUND_BUILTIN, "type": "pec"}
    assert grounds["R"]["method"] == "sommerfeld"
    # Past the last letter there is no slot to map onto.
    payload = _load(cat, local, "[grounds.22]\n")
    assert payload["problems"][0].startswith("[grounds.22]: not a ground slot")
    assert list(_by_id(payload)) == ["X", "Y", "Z"]


def test_one_slot_spelled_both_ways_is_refused_by_name(cat, local):
    payload = _load(
        cat,
        local,
        '[ground]\nmethod = "mininec"\n\n'
        '[grounds.1]\nmethod = "sommerfeld"\n\n[grounds.X]\ntype = "pec"\n\n'
        "[grounds.Y]\nenabled = true\n\n[grounds.2]\nenabled = false\n",
    )
    assert payload["problems"] == [
        "[grounds.1] and [grounds.X] both given: they name the same ground "
        "slot X, so neither is used",
        "[grounds.Y] and [grounds.2] both given: they name the same ground "
        "slot Y, so neither is used",
    ]
    grounds = _by_id(payload)
    # Neither table applies: X falls back to [ground], Y to its stock.
    assert grounds["X"]["method"] == "mininec"
    assert grounds["X"]["type"] == "finite"
    assert grounds["Y"]["enabled"] is False


def test_a_posted_body_spelling_one_slot_both_ways_is_refused(client, local):
    entry = {"enabled": True, "type": "finite", "method": "fast"}
    body = {"switches": BUILTIN_SWITCHES, "grounds": {"1": entry, "X": entry}}
    r = client.post("/settings", json=body)
    assert r.status_code == 422
    assert any(
        "[grounds.1] and [grounds.X] both given" in p
        for p in r.json()["detail"]["problems"]
    )
    assert not local.exists()


def test_a_save_after_a_numbered_file_writes_letters(cat, local):
    payload = _load(
        cat, local, '[grounds.1]\nmethod = "mininec"\n\n[grounds.4]\ntype = "pec"\n'
    )
    assert [p.split(":")[0] for p in payload["problems"]] == [
        "[grounds.1] is read as [grounds.X]",
        "[grounds.4] is read as [grounds.U]",
    ]
    # The page posts the slots by the ids it was served: letters.
    body = _body_from(cat, payload)
    assert list(body["grounds"]) == ["X", "Y", "Z", "U"]
    saved = ui_settings.save(body, cat, path=local)
    text = local.read_text()
    assert "[grounds.X]" in text and "[grounds.U]" in text
    assert not re.search(r"\[grounds\.\d", text), text
    assert tomllib.loads(text) == {
        "grounds": {"X": {"method": "mininec"}, "U": {"type": "pec"}}
    }
    # Read back, the note is gone.
    assert saved["problems"] == []


def test_a_posted_body_with_numbered_ids_is_saved_as_letters(cat, local, client):
    """A page loaded before AK#1801 posts numbered ids; the save takes them as
    their letters, with no refusal, and writes the letters."""
    payload = ui_settings.load(cat, hosted=False)
    body = _body_from(cat, payload)
    body["grounds"] = {
        str(n): entry for n, entry in enumerate(body["grounds"].values(), start=1)
    }
    body["grounds"]["2"]["type"] = "pec"
    r = client.post("/settings", json=body)
    assert r.status_code == 200, r.text
    assert tomllib.loads(local.read_text()) == {"grounds": {"Y": {"type": "pec"}}}
