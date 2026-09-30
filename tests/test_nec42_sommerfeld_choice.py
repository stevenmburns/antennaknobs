"""The NEC-4.2 slot's Sommerfeld choice: GN 2 (the default) or GN 3.

`NEC42Engine(sommerfeld=)` already wrote either card, but only Python reached
GN 3. The choice now rides the slot's `model_options` (the option the roster
serves for that one backend), is seeded by `[engines] nec42_sommerfeld`, and is
a CLI flag. None of this needs the licensed binary: the deck a request would
run is the deck the download writes, and a recording engine class shows what
the factory hands the constructor. The binary's own smoke is
`test_nec42_sommerfeld_binary.py`.
"""

from __future__ import annotations

import importlib

import pytest
from fastapi.testclient import TestClient

import antennaknobs
import antennaknobs.web.server as server
from antennaknobs import settings_file
from antennaknobs.engines.nec42 import NEC42Engine
from antennaknobs.web import adapter
from antennaknobs.web import settings as ui_settings

# `antennaknobs.cli` is the entry function on the package, so the module is
# imported by its dotted name.
cli_module = importlib.import_module("antennaknobs.cli")

BURIED = "verticals.buried_radial_vertical"


@pytest.fixture
def settings_toml(monkeypatch, tmp_path):
    """The settings file this test owns; the hosted flag off."""
    path = tmp_path / "settings.toml"
    monkeypatch.setenv(settings_file.SETTINGS_ENV, str(path))
    monkeypatch.delenv(settings_file.HOSTED_ENV, raising=False)
    return path


@pytest.fixture(scope="module")
def client() -> TestClient:
    return TestClient(server.app)


# --- the served option -------------------------------------------------------


def test_only_the_nec42_row_offers_the_choice():
    rows = adapter.backend_roster(
        have_pynec=True, have_nec5=True, have_nec2=True, have_nec42=True
    )
    offering = [r["name"] for r in rows if "sommerfeld" in r["model_kwargs"]]
    assert offering == ["nec42"]
    assert len(rows) > 3, "the roster must have other rows for this to say anything"


def test_the_spec_words_the_choice_and_carries_the_hint(settings_toml):
    spec = adapter.model_option_specs()["sommerfeld"]
    assert spec["kind"] == "enum"
    assert spec["values"] == ["GN 2", "GN 3"]
    assert spec["default"] == "GN 2"
    assert spec["description"] == (
        "GN 3 is NEC-4.2's newer Sommerfeld evaluation; it can differ from "
        "GN 2 by around an ohm on buried designs."
    )


@pytest.mark.parametrize(
    ("value", "ok"),
    [("GN 2", True), ("GN 3", True), (3, False), ("GN 4", False), (None, False)],
)
def test_the_sanitiser_takes_the_two_words_only(value, ok):
    check = adapter._HOSTED_MODEL_OPTIONS["sommerfeld"]
    if ok:
        assert check(value) == value
    else:
        with pytest.raises(ValueError, match="must be one of"):
            check(value)


# --- settings.toml -----------------------------------------------------------


def test_the_file_seeds_the_served_default(settings_toml):
    settings_toml.write_text("[engines]\nnec42_sommerfeld = 3\n")
    assert adapter.model_option_specs()["sommerfeld"]["default"] == "GN 3"


def test_no_file_and_an_unset_key_leave_gn2(settings_toml):
    assert settings_file.nec42_sommerfeld() is None
    settings_toml.write_text("[engines]\n")
    assert settings_file.nec42_sommerfeld() is None
    assert adapter.model_option_specs()["sommerfeld"]["default"] == "GN 2"


@pytest.mark.parametrize("bad", ['"3"', "2.5", "4", "true", "[3]"])
def test_a_bad_value_is_refused_by_name(settings_toml, bad):
    settings_toml.write_text(f"[engines]\nnec42_sommerfeld = {bad}\n")
    with pytest.raises(ValueError, match=r"nec42_sommerfeld.*must be 2 or 3"):
        settings_file.nec42_sommerfeld()
    with pytest.raises(ValueError, match="nec42_sommerfeld"):
        adapter._nec42_sommerfeld({})
    # ...and the menu stays up rather than break /capabilities.
    assert adapter.model_option_specs()["sommerfeld"]["default"] == "GN 2"


def test_the_workbench_loader_accepts_the_key_and_names_a_bad_one(settings_toml):
    cat = ui_settings.catalog(have_pynec=False, have_nec5=False, have_nec2=False)
    settings_toml.write_text("[engines]\nnec42_sommerfeld = 3\n")
    payload = ui_settings.load(cat, hosted=False)
    assert payload["problems"] == []

    settings_toml.write_text("[engines]\nnec42_sommerfeld = 5\n")
    payload = ui_settings.load(cat, hosted=False)
    assert any("nec42_sommerfeld = 5" in p for p in payload["problems"])


def test_a_saved_nec42_slot_may_carry_the_choice(settings_toml):
    """ "Save as my defaults" writes the slot's model, so a NEC-4.2 slot on GN 3
    round-trips through the loader instead of being reported as a bad knob."""
    cat = ui_settings.catalog(
        have_pynec=False, have_nec5=False, have_nec2=False, have_nec42=True
    )
    settings_toml.write_text(
        '[slots.A]\nbackend = "nec42"\nmodel = { sommerfeld = "GN 3" }\n'
    )
    payload = ui_settings.load(cat, hosted=False)
    assert payload["problems"] == []
    assert payload["slots"]["A"]["model"] == {"sommerfeld": "GN 3"}


# --- the engine the slot builds ---------------------------------------------


class _Recorder:
    def __init__(self, builder, **kw):
        self.kw = kw


@pytest.fixture
def recorded(monkeypatch):
    monkeypatch.setattr(adapter, "NEC42Engine", _Recorder)
    return lambda req: adapter._make_nec42_engine(req, object()).kw["sommerfeld"]


def test_the_slot_option_reaches_the_engine(recorded, settings_toml):
    assert recorded({}) == 2
    assert recorded({"model_options": {"sommerfeld": "GN 2"}}) == 2
    assert recorded({"model_options": {"sommerfeld": "GN 3"}}) == 3


def test_the_request_wins_over_the_file_and_the_file_over_the_stock(
    recorded, settings_toml
):
    settings_toml.write_text("[engines]\nnec42_sommerfeld = 3\n")
    assert recorded({}) == 3
    assert recorded({"model_options": {"sommerfeld": "GN 2"}}) == 2


def test_a_word_that_is_not_a_menu_word_refuses(recorded):
    with pytest.raises(ValueError, match="sommerfeld"):
        recorded({"model_options": {"sommerfeld": "GN 4"}})


# --- the Download NEC-4 deck -------------------------------------------------


def _gn_line(text):
    (line,) = [ln for ln in text.splitlines() if ln.startswith("GN ")]
    return line


def _download(client, **extra):
    r = client.post(
        "/export_nec",
        json={
            "geometry": BURIED,
            "dialect": "nec4",
            "ground": True,
            "ground_model": "sommerfeld",
            **extra,
        },
    )
    assert r.status_code == 200, r.text
    return r.text


def test_the_deck_says_gn3_when_the_request_carries_it(client, settings_toml):
    assert _gn_line(_download(client)).startswith("GN 2 ")
    deck = _download(client, model_options={"sommerfeld": "GN 3"})
    assert _gn_line(deck) == "GN 3 0 0 0 13 0.005 NOFILE"


def test_the_deck_follows_the_file_when_the_request_is_silent(client, settings_toml):
    settings_toml.write_text("[engines]\nnec42_sommerfeld = 3\n")
    assert _gn_line(_download(client)).startswith("GN 3 ")


def test_a_momwire_slots_options_do_not_confuse_the_deck(client, settings_toml):
    """The active slot may be momwire: its own kwargs ride the same field."""
    deck = _download(client, model_options={"degree": 2, "sommerfeld": "GN 3"})
    assert _gn_line(deck).startswith("GN 3 ")


# --- the command line --------------------------------------------------------


def test_the_flag_binds_the_nec42_engine(monkeypatch, settings_toml):
    monkeypatch.setitem(cli_module.ENGINE_CLASSES, "nec42", NEC42Engine)
    f = cli_module.make_engine_factory("nec42", "free", nec42_sommerfeld=3)
    assert f.func is NEC42Engine and f.keywords["sommerfeld"] == 3
    # The file seeds it, the flag wins.
    settings_toml.write_text("[engines]\nnec42_sommerfeld = 3\n")
    f = cli_module.make_engine_factory("nec42", "free")
    assert f.keywords["sommerfeld"] == 3
    f = cli_module.make_engine_factory("nec42", "free", nec42_sommerfeld=2)
    assert f.keywords["sommerfeld"] == 2


def test_the_flag_rides_along_other_engines_untouched(monkeypatch):
    f = cli_module.make_engine_factory("momwire", "free", nec42_sommerfeld=3)
    kw = getattr(f, "keywords", {})
    assert "sommerfeld" not in kw


def test_a_bad_file_value_refuses_the_engine_by_name(monkeypatch, settings_toml):
    import argparse

    monkeypatch.setitem(cli_module.ENGINE_CLASSES, "nec42", NEC42Engine)
    settings_toml.write_text("[engines]\nnec42_sommerfeld = 9\n")
    with pytest.raises(argparse.ArgumentTypeError, match="nec42_sommerfeld"):
        cli_module.make_engine_factory("nec42", "free")


def test_the_flag_is_a_choice_of_2_or_3_on_every_engine_command(capsys):
    for cmd in ("sweep", "analyze", "pattern", "compare_patterns"):
        with pytest.raises(SystemExit):
            antennaknobs.cli([cmd, "--nec42-sommerfeld", "4"])
        assert "invalid choice: 4" in capsys.readouterr().err


def test_export_writes_gn3_from_the_flag(tmp_path, settings_toml):
    out = tmp_path / "d.nec"
    antennaknobs.cli(
        [
            "export",
            "--builder",
            BURIED,
            "--dialect",
            "nec4",
            "--ground",
            "finite",
            "--nec42-sommerfeld",
            "3",
            "--out",
            str(out),
        ]
    )
    assert _gn_line(out.read_text(encoding="utf-8")).startswith("GN 3 ")


def test_export_refuses_gn3_for_a_nec2_deck(tmp_path):
    with pytest.raises(SystemExit) as exc:
        antennaknobs.cli(["export", "--nec42-sommerfeld", "3"])
    assert "--dialect nec4" in str(exc.value)
