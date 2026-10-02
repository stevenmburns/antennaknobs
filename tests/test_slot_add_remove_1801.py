"""AK#1801: both slot families take a + and a remove in the workbench.

Ground slots past Z (U, V, W, ...) were already read from the file and
written by a save (``test_ground_slots_1794.py``). The solver slots were a
fixed A/B/C. They now run A, B, C, D, E: a ``[slots.D]`` table makes slot D
exist, empty or not, and a save writes an added slot even when it changes
nothing. Slots run without gaps in both families, which is why the workbench
removes only the last added slot.
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


def _first(cat) -> str:
    return next(iter(cat.backends))


def test_solver_slot_ids_match_the_frontend():
    text = (ROOT / "src/antennaknobs/web/frontend/src/lib/backends.ts").read_text()
    m = re.search(
        r"SOLVER_SLOTS: SlotFamily = \{\s*ids: \[([^\]]*)\],\s*stock: (\d+)", text
    )
    assert m, "SOLVER_SLOTS not found in lib/backends.ts"
    assert tuple(re.findall(r'"([A-Z])"', m.group(1))) == ui_settings.SOLVER_SLOT_IDS
    from antennaknobs.web.adapter import default_slots

    stock = [s["slot"] for s in default_slots()]
    assert int(m.group(2)) == len(stock)
    assert tuple(stock) == ui_settings.SOLVER_SLOT_IDS[: len(stock)]


def test_the_ground_family_stock_count_matches_the_frontend():
    text = (ROOT / "src/antennaknobs/web/frontend/src/lib/groundSlots.ts").read_text()
    m = re.search(
        r"GROUND_SLOTS: SlotFamily = \{ ids: GROUND_SLOT_IDS, stock: (\d+)", text
    )
    assert m, "GROUND_SLOTS not found in lib/groundSlots.ts"
    assert int(m.group(1)) == len(ui_settings.STOCK_GROUNDS)


def test_the_two_families_never_share_a_letter():
    assert not set(ui_settings.SOLVER_SLOT_IDS) & set(ui_settings.GROUND_SLOT_IDS)


def test_an_empty_slot_d_table_makes_slot_d_on_the_first_solver(cat, local):
    payload = _load(cat, local, "[slots.D]\n")
    assert payload["problems"] == []
    assert payload["slots"] == {"D": {}}
    seeds = ui_settings.overlay_slots(
        list(cat.stock_slots), payload["slots"], _first(cat)
    )
    assert [s["slot"] for s in seeds] == ["A", "B", "C", "D"]
    assert seeds[3] == {
        "slot": "D",
        "backend": _first(cat),
        "n_per_wire": None,
        "model": {},
    }
    # The stock seeds are untouched.
    assert seeds[:3] == [{**s, "model": dict(s["model"])} for s in cat.stock_slots]


def test_slot_d_takes_its_own_settings(cat, local):
    payload = _load(cat, local, '[slots.D]\nbackend = "bspline"\nn_per_wire = 31\n')
    assert payload["problems"] == []
    seeds = ui_settings.overlay_slots(
        list(cat.stock_slots), payload["slots"], _first(cat)
    )
    assert seeds[3]["backend"] == "bspline"
    assert seeds[3]["n_per_wire"] == 31


def test_slot_e_without_slot_d_is_named_and_not_used(cat, local):
    payload = _load(cat, local, "[slots.E]\nn_per_wire = 9\n")
    assert payload["slots"] == {}
    assert payload["problems"] == [
        "[slots.E]: solver slots run A, B, C, D, E without gaps, and there is "
        "no slot D; this table is not used"
    ]


def test_a_slot_past_e_is_not_a_solver_slot(cat, local):
    payload = _load(cat, local, "[slots.F]\n")
    assert payload["slots"] == {}
    assert payload["problems"] == [
        "[slots.F]: not a solver slot (known: A, B, C, D, E)"
    ]


def test_a_stock_slot_table_that_changes_nothing_stays_out(cat, local):
    payload = _load(cat, local, "[slots.B]\n")
    assert payload["problems"] == []
    assert payload["slots"] == {}


def _body(cat, slots: list[str]) -> dict:
    stock = {s["slot"]: s for s in cat.stock_slots}
    first = _first(cat)

    def entry(sid):
        seed = stock.get(sid)
        backend = seed["backend"] if seed and seed["backend"] in cat.backends else first
        model = (seed or {}).get("model") or {}
        return {"backend": backend, "n_per_wire": 0, "model": dict(model)}

    out = {"switches": dict(BUILTIN_SWITCHES), "slots": {}}
    for sid in slots:
        e = entry(sid)
        seed = stock.get(sid)
        e["n_per_wire"] = (seed or {}).get("n_per_wire") or cat.n_per_wire_defaults[
            e["backend"]
        ]
        out["slots"][sid] = e
    return out


def test_a_save_writes_an_added_slot_even_when_it_changes_nothing(cat, local):
    ui_settings.save(_body(cat, ["A", "B", "C", "D"]), cat, path=local)
    assert tomllib.loads(local.read_text()) == {"slots": {"D": {}}}
    loaded = ui_settings.load(cat, hosted=False, path=local)
    assert loaded["slots"] == {"D": {}}
    seeds = ui_settings.overlay_slots(
        list(cat.stock_slots), loaded["slots"], _first(cat)
    )
    assert [s["slot"] for s in seeds] == ["A", "B", "C", "D"]


def test_a_save_without_the_added_slot_drops_it(cat, local):
    local.write_text("[slots.D]\nn_per_wire = 31\n\n[slots.E]\n")
    ui_settings.save(_body(cat, ["A", "B", "C", "D"]), cat, path=local)
    assert tomllib.loads(local.read_text()) == {"slots": {"D": {}}}
    ui_settings.save(_body(cat, ["A", "B", "C"]), cat, path=local)
    assert tomllib.loads(local.read_text()) == {}


def test_a_save_writes_an_added_slots_changes(cat, local):
    body = _body(cat, ["A", "B", "C", "D", "E"])
    body["slots"]["E"]["n_per_wire"] = 41
    ui_settings.save(body, cat, path=local)
    text = local.read_text()
    assert tomllib.loads(text) == {"slots": {"D": {}, "E": {"n_per_wire": 41}}}
    assert text.index("[slots.D]") < text.index("[slots.E]")


def test_capabilities_serves_the_added_slot_as_a_seed(client, local):
    local.write_text("[slots.D]\nn_per_wire = 31\n")
    r = client.get("/capabilities")
    assert r.status_code == 200
    seeds = r.json()["default_slots"]
    assert [s["slot"] for s in seeds] == ["A", "B", "C", "D"]
    assert seeds[3]["n_per_wire"] == 31
    assert seeds[3]["backend"] == r.json()["backends"][0]["name"]


def test_a_posted_body_with_slot_d_saves_and_reads_back(client, local):
    caps = client.get("/capabilities").json()
    first = caps["backends"][0]["name"]
    served = {b["name"] for b in caps["backends"]}
    body = {
        "switches": BUILTIN_SWITCHES,
        "slots": {
            s["slot"]: {
                # A seed this server does not offer falls back, as the page does.
                "backend": s["backend"] if s["backend"] in served else first,
                "n_per_wire": s["n_per_wire"] or 15,
                "model": s["model"],
            }
            for s in caps["default_slots"]
        },
    }
    body["slots"]["D"] = {"backend": first, "n_per_wire": 27, "model": {}}
    r = client.post("/settings", json=body)
    assert r.status_code == 200, r.text
    assert "D" in tomllib.loads(local.read_text())["slots"]
    seeds = client.get("/capabilities").json()["default_slots"]
    assert [s["slot"] for s in seeds][-1] == "D"
    assert seeds[-1]["n_per_wire"] == 27
