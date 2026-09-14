"""AK#1492: a settings.toml says where the workbench starts.

AC6LA asked to start the workbench with the frequency sweep off. The Settings
menu's switches, the ground and the A/B/C solver slots all started from values
fixed in code, and the one switch the browser remembered (adaptive resolution)
forgot it at every workbench launch, because the workbench opens on a fresh
port and browser storage is per origin. The defaults now come from a file the
server reads at every page load and the Settings menu can write.
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


BUILTIN_SWITCHES = {k: d for k, _, d in ui_settings.SWITCHES}


def test_no_file_means_the_builtin_defaults(cat, local):
    payload = ui_settings.load(cat, hosted=False)
    assert payload["exists"] is False
    assert payload["problems"] == []
    assert payload["switches"] == BUILTIN_SWITCHES
    assert payload["ground"] == ui_settings.GROUND_BUILTIN
    assert payload["slots"] == {}
    assert payload["path"] == str(local)


def test_the_path_is_the_variable_else_the_home_folder(monkeypatch, tmp_path):
    monkeypatch.delenv(ui_settings.SETTINGS_ENV, raising=False)
    assert (
        ui_settings.settings_path() == Path.home() / ".antennaknobs" / "settings.toml"
    )
    monkeypatch.setenv(ui_settings.SETTINGS_ENV, str(tmp_path / "x.toml"))
    assert ui_settings.settings_path() == tmp_path / "x.toml"


def test_a_file_sets_switches_ground_and_slots(cat, local):
    soil_name = next(iter(cat.soils))
    terrain = sorted(cat.terrains)[0]
    local.write_text(
        f"""
[switches]
freq_sweep = false
live = false

[ground]
enabled = false
method = "sommerfeld"
soil = "{soil_name}"
terrain_preset = "{terrain}"

[slots.A]
backend = "razor-2p"
n_per_wire = 21

[slots.B]
model = {{ degree = 2 }}
"""
    )
    payload = ui_settings.load(cat, hosted=False)
    assert payload["problems"] == []
    assert payload["switches"] == {
        **BUILTIN_SWITCHES,
        "freq_sweep": False,
        "live": False,
    }
    assert sorted(payload["switches_set"]) == ["freq_sweep", "live"]
    eps, sig = cat.soils[soil_name]
    assert payload["ground"] == {
        "enabled": False,
        "type": "finite",
        "method": "sommerfeld",
        "soil": {"eps_r": eps, "sigma": sig},
        "terrain_preset": terrain,
    }
    seeds = {
        s["slot"]: s
        for s in ui_settings.overlay_slots(list(cat.stock_slots), payload["slots"])
    }
    # A new backend starts from its own defaults.
    assert seeds["A"] == {
        "slot": "A",
        "backend": "razor-2p",
        "n_per_wire": 21,
        "model": {},
    }
    # The same backend keeps the stock seed and takes the file's knobs on top.
    assert seeds["B"]["backend"] == "bspline"
    assert seeds["B"]["n_per_wire"] == 20
    assert seeds["B"]["model"] == {"degree": 2}
    assert seeds["C"] == {
        **cat.stock_slots[2],
        "model": dict(cat.stock_slots[2]["model"]),
    }


def test_each_problem_is_named_and_everything_else_applies(cat, local):
    local.write_text(
        """
[switches]
freq_swep = false
wire_labels = true
live = 1

[ground]
type = "concrete"
eps_r = 13

[slots.A]
model = { no_such_knob = 3 }

[slots.B]
n_per_wire = 0

[slots.C]
backend = "nec9"

[slots.D]
backend = "bspline"

[display]
theme = "dark"
"""
    )
    payload = ui_settings.load(cat, hosted=False)
    problems = "\n".join(payload["problems"])
    for fragment in (
        "unknown table [display]",
        "[switches] freq_swep: not a switch",
        "[switches] live = 1: must be true or false",
        "[ground] type = 'concrete': must be one of finite, pec, terrain",
        "[ground] eps_r and sigma go together",
        "[slots.A] model.no_such_knob: not a knob the bspline solver takes",
        "[slots.B] n_per_wire = 0: must be a whole number of at least 1",
        "[slots.C] backend = 'nec9': not a solver this server offers",
        "[slots.D]: not a solver slot",
    ):
        assert fragment in problems, fragment
    assert len(payload["problems"]) == 9
    # What was valid still applies; what was not keeps its default.
    assert payload["switches"] == {**BUILTIN_SWITCHES, "wire_labels": True}
    assert payload["ground"] == ui_settings.GROUND_BUILTIN
    assert "C" not in payload["slots"] and "D" not in payload["slots"]


def test_a_file_that_is_not_toml_falls_back_by_name(cat, local):
    local.write_text("[switches]\nfreq_sweep = = false\n")
    payload = ui_settings.load(cat, hosted=False)
    assert payload["exists"] is True
    assert len(payload["problems"]) == 1
    assert "is not valid TOML" in payload["problems"][0]
    assert payload["switches"] == BUILTIN_SWITCHES


def test_capabilities_serves_the_file_and_overlays_the_slots(client, local):
    local.write_text('[switches]\nfreq_sweep = false\n\n[slots.A]\nbackend = "pulse"\n')
    caps = client.get("/capabilities").json()
    ui = caps["ui_defaults"]
    assert ui["switches"]["freq_sweep"] is False
    assert ui["writable"] is True
    assert ui["problems"] == []
    assert [s["backend"] for s in caps["default_slots"]][0] == "pulse"
    # The soil knobs' served default is untouched: the request path omits a
    # default-valued soil, so moving it would silently change what solves.
    assert caps["soil_ranges"]["eps_r"]["default"] == 13.0
    assert caps["soil_ranges"]["sigma"]["default"] == 0.005


def test_the_hosted_instance_reads_no_file(client, local, monkeypatch):
    local.write_text("[switches]\nfreq_sweep = false\n")
    monkeypatch.setattr(server, "_HOSTED", True)
    ui = client.get("/capabilities").json()["ui_defaults"]
    assert ui["path"] is None and ui["writable"] is False
    assert ui["switches"] == BUILTIN_SWITCHES


SAVE_BODY = {
    "switches": {**BUILTIN_SWITCHES, "freq_sweep": False, "wire_labels": True},
    "ground": {
        "enabled": True,
        "type": "finite",
        "method": "sommerfeld",
        "eps_r": 20.0,
        "sigma": 0.03,
        "terrain_preset": "levee",
    },
    "slots": {
        "A": {
            "backend": "bspline",
            "n_per_wire": 17,
            "model": {"degree": 2, "feed_smoothing_factor": None},
        },
        "B": {"backend": "bspline", "n_per_wire": 20, "model": {"degree": 1}},
        "C": {"backend": "sinusoidal", "n_per_wire": 15, "model": {}},
    },
}


def test_save_writes_a_file_that_reads_back_the_same(client, local, monkeypatch):
    monkeypatch.setattr(server.pynec_backend, "HAVE_PYNEC", True)
    r = client.post("/settings", json=SAVE_BODY)
    assert r.status_code == 200, r.text
    data = tomllib.loads(local.read_text())
    # Only what differs from the built-in defaults is written (#1497).
    assert data["switches"] == {"freq_sweep": False, "wire_labels": True}
    assert data["ground"] == {"method": "sommerfeld", "eps_r": 20.0, "sigma": 0.03}
    # Degree 2 is where slot A starts and a knob left at null (the solver
    # decides) is absent too; slot B is exactly its stock seed.
    assert data["slots"] == {
        "A": {"n_per_wire": 17},
        "C": {"backend": "sinusoidal", "n_per_wire": 15},
    }
    caps = client.get("/capabilities").json()
    assert caps["ui_defaults"]["switches"] == SAVE_BODY["switches"]
    assert caps["ui_defaults"]["problems"] == []
    assert caps["default_slots"][0]["n_per_wire"] == 17
    assert caps["default_slots"][2]["backend"] == "sinusoidal"

    first = local.read_text()
    assert client.post("/settings", json=SAVE_BODY).status_code == 200
    assert (local.parent / "settings.toml.bak").read_text() == first


def test_save_refuses_a_body_with_problems_and_writes_nothing(client, local):
    body = {**SAVE_BODY, "switches": {**SAVE_BODY["switches"], "freq_swep": False}}
    r = client.post("/settings", json=body)
    assert r.status_code == 422
    assert any("freq_swep" in p for p in r.json()["detail"]["problems"])
    assert not local.exists()


def test_save_is_refused_on_the_hosted_instance(client, local, monkeypatch):
    monkeypatch.setattr(server, "_HOSTED", True)
    assert client.post("/settings", json=SAVE_BODY).status_code == 403
    assert not local.exists()


def test_the_frontend_fallback_is_this_table():
    """lib/settings.ts carries a fallback for a payload without ui_defaults;
    it must be the same defaults, or the two would drift."""
    ts = (ROOT / "src/antennaknobs/web/frontend/src/lib/settings.ts").read_text()
    block = re.search(
        r"BUILTIN_SWITCHES: Record<SwitchKey, boolean> = \{(.*?)\};", ts, re.S
    )
    assert block, "BUILTIN_SWITCHES not found in lib/settings.ts"
    parsed = dict(re.findall(r"(\w+): (true|false),", block.group(1)))
    assert {k: v == "true" for k, v in parsed.items()} == BUILTIN_SWITCHES
    ground = re.search(r"BUILTIN_GROUND: GroundDefaults = \{(.*?)\};", ts, re.S)
    assert ground, "BUILTIN_GROUND not found in lib/settings.ts"
    g = ground.group(1)
    assert f"enabled: {str(ui_settings.GROUND_BUILTIN['enabled']).lower()}," in g
    assert f'type: "{ui_settings.GROUND_BUILTIN["type"]}",' in g
    assert f'method: "{ui_settings.GROUND_BUILTIN["method"]}",' in g
    # A save leaves out the terrain preset the panel starts on (#1497), so the
    # panel's fallback must be the catalog's first preset.
    hook = (
        ROOT / "src/antennaknobs/web/frontend/src/components/session/useGroundConfig.ts"
    )
    start = re.search(r'defaults\.terrain_preset \?\? "([\w-]+)"', hook.read_text())
    assert start, "the terrain preset fallback not found in useGroundConfig.ts"
    cat = ui_settings.catalog(have_pynec=False, have_nec5=False, have_nec2=False)
    assert start.group(1) == cat.terrain_default


def test_engines_and_capture_come_from_the_file_and_a_variable_wins(
    local, monkeypatch, tmp_path
):
    """The CLI and the workbench find engines and the capture folder through
    the library, so the file's [engines] and [capture] reach both."""
    from antennaknobs.engine_capture import capture_dir_from_env
    from antennaknobs.engines._external import find_exe

    exe, other = tmp_path / "nec5cl", tmp_path / "other-nec5"
    for f in (exe, other):
        f.write_text("#!/bin/sh\n")
        f.chmod(0o755)
    local.write_text(
        f'[engines]\nnec5_exe = "{exe}"\n\n[capture]\ndir = "{tmp_path / "caps"}"\n'
    )
    monkeypatch.setenv("NEC5_EXE", "")
    monkeypatch.setenv("ANTENNAKNOBS_CAPTURE_DIR", "")
    monkeypatch.delenv("ANTENNAKNOBS_HOSTED", raising=False)
    assert find_exe("NEC5_EXE") == str(exe)
    assert find_exe("NEC2_EXE") is None
    assert capture_dir_from_env("nec5") == tmp_path / "caps" / "nec5"
    monkeypatch.setenv("NEC5_EXE", str(other))
    assert find_exe("NEC5_EXE") == str(other)
    assert find_exe("NEC5_EXE", str(exe)) == str(exe)
    monkeypatch.setenv("NEC5_EXE", "")
    monkeypatch.setenv("ANTENNAKNOBS_HOSTED", "1")
    assert find_exe("NEC5_EXE") is None


def test_bad_engine_and_capture_entries_are_named(cat, local):
    local.write_text(
        '[engines]\nnec5_exe = 5\nnec9_exe = "x"\n\n[capture]\ndir = ""\nlevel = "DEBUG"\n'
    )
    problems = "\n".join(ui_settings.load(cat, hosted=False)["problems"])
    for fragment in (
        "[engines] nec5_exe = 5: must be a path",
        "[engines] nec9_exe: not an engine setting",
        "[capture] dir = '': must be a path",
        "[capture] level: not a capture setting",
    ):
        assert fragment in problems, fragment


def test_the_page_can_never_set_engines_or_capture(client, local):
    body = {**SAVE_BODY, "engines": {"nec5_exe": "/bin/sh"}}
    r = client.post("/settings", json=body)
    assert r.status_code == 422
    assert any(
        "[engines]" in p and "by hand" in p for p in r.json()["detail"]["problems"]
    )
    assert not local.exists()


def test_save_keeps_the_hand_edited_engines_and_capture(client, local):
    local.write_text(
        '[engines]\nnec5_exe = "/opt/nec5/nec5cl"\n\n[capture]\ndir = "/tmp/caps"\n'
    )
    assert client.post("/settings", json=SAVE_BODY).status_code == 200
    data = tomllib.loads(local.read_text())
    assert data["engines"] == {"nec5_exe": "/opt/nec5/nec5cl"}
    assert data["capture"] == {"dir": "/tmp/caps"}
    assert data["switches"]["freq_sweep"] is False


def test_the_page_is_not_served_the_engine_paths(client, local, tmp_path):
    exe = tmp_path / "nec5cl"
    exe.write_text("#!/bin/sh\n")
    exe.chmod(0o755)
    local.write_text(f'[engines]\nnec5_exe = "{exe}"\n')
    ui = client.get("/capabilities").json()["ui_defaults"]
    assert "engines" not in ui and "capture" not in ui
    assert ui["problems"] == []


# #1497: a save writes only what differs from the built-in defaults, so a
# default that a later release moves reaches a file saved today.


@pytest.fixture
def cat_pynec():
    return ui_settings.catalog(have_pynec=True, have_nec5=False, have_nec2=False)


def _untouched(cat):
    """The body the page posts for a session nobody changed, built the way the
    frontend builds it (defaultOptsFor, slotFromSeed): every switch, the served
    soil and first terrain preset, and each stock slot with every knob its
    solver takes at the served default."""
    ground = {
        **{k: ui_settings.GROUND_BUILTIN[k] for k in ("enabled", "type", "method")},
        "eps_r": cat.soil_default[0],
        "sigma": cat.soil_default[1],
        "terrain_preset": cat.terrain_default,
    }
    slots = {}
    for seed in cat.stock_slots:
        backend = seed["backend"]
        model = {k: cat.knob_defaults[k] for k in cat.backends[backend]}
        model.update(seed["model"])
        n = seed["n_per_wire"] or cat.n_per_wire_defaults[backend]
        slots[seed["slot"]] = {"backend": backend, "n_per_wire": n, "model": model}
    return {"switches": dict(BUILTIN_SWITCHES), "ground": ground, "slots": slots}


def test_a_save_of_an_untouched_session_writes_no_settings(cat_pynec, local):
    ui_settings.save(_untouched(cat_pynec), cat_pynec, path=local)
    text = local.read_text()
    assert tomllib.loads(text) == {}, text
    loaded = ui_settings.load(cat_pynec, hosted=False, path=local)
    assert loaded["problems"] == []
    assert loaded["switches"] == BUILTIN_SWITCHES
    assert loaded["ground"] == ui_settings.GROUND_BUILTIN
    assert loaded["slots"] == {}


def test_a_save_writes_only_what_differs(cat_pynec, local):
    body = _untouched(cat_pynec)
    body["switches"]["freq_sweep"] = False
    eps_r, sigma = cat_pynec.soils["poor"]
    body["ground"].update(eps_r=eps_r, sigma=sigma, terrain_preset="cliff")
    body["slots"]["A"]["n_per_wire"] = 17
    body["slots"]["A"]["model"]["tikhonov_lambda"] = 0.2
    body["slots"]["C"] = {
        "backend": "sinusoidal",
        "n_per_wire": cat_pynec.n_per_wire_defaults["sinusoidal"],
        "model": {"n_qp_const": cat_pynec.knob_defaults["n_qp_const"]},
    }
    ui_settings.save(body, cat_pynec, path=local)
    assert tomllib.loads(local.read_text()) == {
        "switches": {"freq_sweep": False},
        # A soil that matches a preset is written by its name.
        "ground": {"soil": "poor", "terrain_preset": "cliff"},
        "slots": {
            "A": {"n_per_wire": 17, "model": {"tikhonov_lambda": 0.2}},
            # A new solver at its own defaults is just the solver.
            "C": {"backend": "sinusoidal"},
        },
    }


def test_a_default_a_later_release_moves_reaches_a_saved_file(
    cat_pynec, local, monkeypatch
):
    body = _untouched(cat_pynec)
    body["switches"]["freq_sweep"] = False
    ui_settings.save(body, cat_pynec, path=local)
    moved = tuple(
        (key, label, (not default) if key == "refine" else default)
        for key, label, default in ui_settings.SWITCHES
    )
    monkeypatch.setattr(ui_settings, "SWITCHES", moved)
    switches = ui_settings.load(cat_pynec, hosted=False, path=local)["switches"]
    assert switches["freq_sweep"] is False
    assert switches["refine"] is (not BUILTIN_SWITCHES["refine"])


def test_an_engine_path_with_no_program_is_named_and_kept(client, local, tmp_path):
    missing = tmp_path / "NEC5CL_x13.exe"
    local.write_text(f"[engines]\nnec5_exe = '{missing}'\n")
    problems = client.get("/capabilities").json()["ui_defaults"]["problems"]
    assert problems == [
        f"[engines] nec5_exe = '{missing}': no program at that path, so this "
        "entry finds no engine"
    ]
    assert client.post("/settings", json=SAVE_BODY).status_code == 200
    assert tomllib.loads(local.read_text())["engines"] == {"nec5_exe": str(missing)}
