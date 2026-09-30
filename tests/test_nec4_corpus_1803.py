"""AK#1803: `scripts/nec4_corpus/export_catalog_nec4.py`, the NEC-4 twin of the
NEC-5 catalog export. Run on a few designs that exercise each branch: a graded
buried vertical (chained GW cards under GE -1), a TL network (per-port
structure decks) and a design NEC-4 cannot carry (recorded, not fatal). The
full catalog is the same loop; it writes 532 decks for 102 designs and records
2 designs skipped (measured 2026-09-29)."""

from __future__ import annotations

import importlib.util
import json
from pathlib import Path

import pytest

SCRIPT = (
    Path(__file__).resolve().parents[1]
    / "scripts"
    / "nec4_corpus"
    / "export_catalog_nec4.py"
)


@pytest.fixture(scope="module")
def corpus(tmp_path_factory):
    spec = importlib.util.spec_from_file_location("export_catalog_nec4", SCRIPT)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    out = tmp_path_factory.mktemp("catalog-nec4")
    for only in ("buried_radial_vertical", "sterba_tl", "invvee_apex"):
        sub = out / only
        assert mod.main(["--out", str(sub), "--only", only]) == 0
    return out


def _manifest(corpus, only):
    return json.loads((corpus / only / "manifest.json").read_text())


def test_the_graded_buried_vertical_is_written_on_every_rung_and_ground(corpus):
    m = _manifest(corpus, "buried_radial_vertical")
    assert m["skipped"] == []
    assert {(w["rung"], w["ground"]) for w in m["written"]} == {
        (r, g) for r in ("default", "refined") for g in ("free", "somm13")
    }
    deck = (corpus / "buried_radial_vertical" / m["written"][0]["file"]).read_text()
    assert deck.startswith(
        "CM antennaknobs catalog design verticals.buried_radial_vertical "
    )
    assert "CM NEC-4 (NEC-4.2) syntax" in deck
    somm = [w for w in m["written"] if w["ground"] == "somm13"][0]["file"]
    lines = (corpus / "buried_radial_vertical" / somm).read_text().splitlines()
    assert "GE -1" in lines and "GN 2 0 0 0 13 0.005 NOFILE" in lines
    assert all(len(ln) <= 80 for ln in lines if not ln.startswith("CM"))


def test_a_tl_network_is_written_as_per_port_structure_decks(corpus):
    m = _manifest(corpus, "sterba_tl")
    files = [w["file"] for w in m["written"]]
    assert files and all(".port" in f for f in files)
    deck = (corpus / "sterba_tl" / files[0]).read_text()
    assert "the network is solved outside NEC-4.2" in deck
    assert not any(ln.startswith(("NT ", "TL ")) for ln in deck.splitlines())


def test_a_design_nec4_cannot_carry_is_recorded_not_fatal(corpus):
    m = _manifest(corpus, "invvee_apex")
    assert m["written"] == []
    assert len(m["skipped"]) == 4
    assert all("PortAtVertex" in s["why"] for s in m["skipped"])
