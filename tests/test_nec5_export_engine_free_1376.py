"""The catalog export writes NEC-5 decks with no engine on the box (#1376).

The corpus tool's release zip carries the 476 catalog decks, generated in a
CI lane that has no NEC-5. `NEC5Engine(require_exe=False)` is the deck-writer
mode that allows it: `deck()` works, a solve still raises NEC5Error.
"""

from __future__ import annotations

import importlib
import importlib.util
import json
import pathlib

import pytest

ROOT = pathlib.Path(__file__).resolve().parents[1]
EXPORT = ROOT / "scripts" / "nec5_corpus" / "export_catalog_nec5.py"


@pytest.fixture
def no_engine(monkeypatch):
    monkeypatch.delenv("NEC5_EXE", raising=False)


def _dipole():
    return importlib.import_module("antennaknobs.designs.dipoles.invvee").Builder()


def test_require_exe_false_writes_a_deck_and_refuses_to_solve(no_engine):
    from antennaknobs.engines.nec5 import NEC5Engine, NEC5Error

    with pytest.raises(NEC5Error):
        NEC5Engine(_dipole())
    eng = NEC5Engine(_dipole(), require_exe=False)
    deck = eng.deck([float(_dipole().freq)])
    assert "GW" in deck and "EX" in deck and deck.rstrip().endswith("EN")
    with pytest.raises(NEC5Error, match="require_exe=False"):
        eng._run_binary(deck)


def test_export_runs_without_an_engine_and_is_deterministic(no_engine, tmp_path):
    spec = importlib.util.spec_from_file_location("export_catalog_probe", EXPORT)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    for out in ("a", "b"):
        assert mod.main(["--out", str(tmp_path / out), "--only", "dipoles.invvee"]) == 0
    manifest = json.loads((tmp_path / "a" / "manifest.json").read_text())
    assert manifest["written"], manifest["skipped"]
    assert not [s for s in manifest["skipped"] if "executable not found" in s["why"]]
    names_a = sorted(p.name for p in (tmp_path / "a").iterdir())
    assert names_a == sorted(p.name for p in (tmp_path / "b").iterdir())
    for name in names_a:
        assert (tmp_path / "a" / name).read_bytes() == (
            tmp_path / "b" / name
        ).read_bytes()
