"""settings.toml's ``[workbench.run_on_pick]``: does picking an analysis start it?

AC6LA (QRZ 1003328 #179): switching a chart's picker to the convergence
analysis, or a height sweep, started a sweep at once, and he had to press Stop
to change its settings first. Steve's shape: one boolean per KIND of analysis
(a study is the kind of analysis it is), frequency sweeps and patterns on,
the minutes-long kinds off. What the frontend does with the table is pinned in
``runOnPick.test.ts`` and ``runOnPick.session.test.tsx``; this file pins the
file's reading, its validation, ``/capabilities`` and the sparse save.
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
DEFAULTS = {
    "frequency": True,
    "pattern": True,
    "knob": False,
    "held": False,
    "convergence": False,
    "map": False,
}


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


def _body(run_on_pick: dict | None) -> dict:
    """A save body for an otherwise untouched session."""
    body: dict = {
        "switches": dict(BUILTIN_SWITCHES),
        "ground": {
            k: ui_settings.GROUND_BUILTIN[k] for k in ("enabled", "type", "method")
        },
        "slots": {},
    }
    if run_on_pick is not None:
        body["workbench"] = {"run_on_pick": run_on_pick}
    return body


def test_the_defaults_are_steves_table():
    assert dict(ui_settings.RUN_ON_PICK) == DEFAULTS


def test_no_file_serves_the_defaults(cat, local):
    payload = ui_settings.load(cat, hosted=False)
    assert payload["workbench"] == {"run_on_pick": DEFAULTS}
    assert payload["problems"] == []


def test_a_partial_table_is_merged_over_the_defaults(cat, local):
    local.write_text("[workbench.run_on_pick]\nknob = true\nfrequency = false\n")
    payload = ui_settings.load(cat, hosted=False)
    assert payload["workbench"]["run_on_pick"] == {
        **DEFAULTS,
        "knob": True,
        "frequency": False,
    }
    assert payload["problems"] == []


def test_an_unknown_kind_is_refused_by_name_with_the_file(cat, local):
    # `study` is not a kind: a study counts as the kind of analysis it is.
    local.write_text("[workbench.run_on_pick]\nknob = true\nstudy = true\n")
    payload = ui_settings.load(cat, hosted=False)
    assert payload["workbench"]["run_on_pick"] == {**DEFAULTS, "knob": True}
    assert payload["problems"] == [
        f"[workbench.run_on_pick] study in {local}: not a kind of analysis "
        "(known: frequency, pattern, knob, held, convergence, map)"
    ]


@pytest.mark.parametrize("value", ['"yes"', "1", "0"])
def test_a_value_that_is_not_a_boolean_is_refused_by_name_with_the_file(
    cat, local, value
):
    local.write_text(f"[workbench.run_on_pick]\nconvergence = {value}\n")
    payload = ui_settings.load(cat, hosted=False)
    # The default stands: a typo never starts (or stops starting) a sweep.
    assert payload["workbench"]["run_on_pick"] == DEFAULTS
    (problem,) = payload["problems"]
    assert problem.startswith("[workbench.run_on_pick] convergence = ")
    assert f" in {local}: must be true or false" in problem


def test_a_table_that_is_not_a_table_and_an_unknown_key_are_named(cat, local):
    local.write_text('[workbench]\nrun_on_pick = "all"\nzoom = 2\n')
    payload = ui_settings.load(cat, hosted=False)
    assert payload["workbench"]["run_on_pick"] == DEFAULTS
    assert payload["problems"] == [
        f"[workbench] zoom in {local}: not a workbench setting (known: run_on_pick)",
        f"[workbench] run_on_pick in {local} must be a table, "
        "e.g. [workbench.run_on_pick] with knob = true",
    ]


def test_capabilities_serves_the_resolved_table(client, local):
    local.write_text("[workbench.run_on_pick]\nheld = true\n")
    ui = client.get("/capabilities").json()["ui_defaults"]
    assert ui["workbench"] == {"run_on_pick": {**DEFAULTS, "held": True}}
    assert ui["problems"] == []


def test_capabilities_serves_the_defaults_on_the_hosted_instance(
    client, local, monkeypatch
):
    local.write_text("[workbench.run_on_pick]\nheld = true\n")
    monkeypatch.setattr(server, "_HOSTED", True)
    ui = client.get("/capabilities").json()["ui_defaults"]
    assert ui["workbench"] == {"run_on_pick": DEFAULTS}


def test_save_writes_only_the_changed_kind(client, local):
    r = client.post("/settings", json=_body({**DEFAULTS, "knob": True}))
    assert r.status_code == 200, r.text
    assert tomllib.loads(local.read_text()) == {
        "workbench": {"run_on_pick": {"knob": True}}
    }
    assert "[workbench.run_on_pick]\nknob = true\n" in local.read_text()
    ui = client.get("/capabilities").json()["ui_defaults"]
    assert ui["workbench"]["run_on_pick"] == {**DEFAULTS, "knob": True}


def test_save_at_the_defaults_writes_nothing_and_clears_an_earlier_choice(
    client, local
):
    assert client.post("/settings", json=_body({**DEFAULTS, "held": True})).is_success
    assert tomllib.loads(local.read_text()) == {
        "workbench": {"run_on_pick": {"held": True}}
    }
    assert client.post("/settings", json=_body(DEFAULTS)).is_success
    assert tomllib.loads(local.read_text()) == {}


def test_a_page_predating_the_table_saves_the_defaults(client, local):
    assert client.post("/settings", json=_body(None)).is_success
    assert tomllib.loads(local.read_text()) == {}


def test_save_refuses_a_bad_kind_and_writes_nothing(client, local):
    r = client.post("/settings", json=_body({**DEFAULTS, "study": True}))
    assert r.status_code == 422
    assert any("study" in p for p in r.json()["detail"]["problems"])
    assert not local.exists()


def test_the_frontend_reads_these_kinds():
    """lib/settings.ts names the kinds it reads, and refuses a payload
    missing any of them (AK#1858), so its list must be this table's keys, in
    its order. Which of them run is served, never restated there."""
    ts = (ROOT / "src/antennaknobs/web/frontend/src/lib/settings.ts").read_text()
    block = re.search(r"RUN_ON_PICK_KINDS = \[(.*?)\] as const;", ts, re.S)
    assert block, "RUN_ON_PICK_KINDS not found in lib/settings.ts"
    assert re.findall(r'"(\w+)"', block.group(1)) == [
        k for k, _ in ui_settings.RUN_ON_PICK
    ]
