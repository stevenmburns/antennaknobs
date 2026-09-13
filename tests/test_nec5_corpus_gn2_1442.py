"""antennaknobs#1442: `translate` must pass GN 2 through as GN 2.

The tool's contract always said so ("GN -1 / GN 1 / GN 2 pass"), but the
Sommerfeld branch wrote `GN 0` for both NEC-2 ground types, so 1,104 of the
corpus's 1,105 GN 2 decks came out as GN 0. NEC-5 cannot tell the difference.
It has no reflection-coefficient ground, and a GN 2 corpus deck spelled either
way prints identically apart from the echoed card (checked against the x13
build on 4nec2-models/zz_MiniNec/HFshort/VDP40C.nec).

A NEC-2 reader of the translated tree can tell. momwire's portal takes GN 0 as
reflection coefficients, so 930 rows of the #896 census compared two ground
models instead of two engines, and every buried corpus deck was refused for
ground contact under refl-coef before any other scope limit was reached.
"""

from __future__ import annotations

import importlib.util
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "nec5_corpus" / "nec5_corpus.py"


@pytest.fixture(scope="module")
def tool():
    spec = importlib.util.spec_from_file_location("nec5_corpus_gn2_probe", SCRIPT)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def _deck(gn: str) -> str:
    return (
        "CM gn\nCE\nGW 1 11 0 0 1 0 0 11 0.001\nGE 1\n"
        f"{gn}\nEX 0 1 6 0 1 0\nFR 0 1 0 0 7.1 0\nXQ\nEN\n"
    )


def _translate(tool, tmp_path, gn: str, nofile: bool = False) -> dict:
    p = tmp_path / "gn.nec"
    p.write_text(_deck(gn), encoding="utf-8")
    rec = tool.translate_file(p, "gn.nec", "double", nofile)
    assert rec["status"] == "translated", rec.get("reason")
    return rec


def _gn_lines(rec) -> list[str]:
    deck = rec["outputs"][0][1]
    return [ln for ln in deck.splitlines() if ln.split()[:1] == ["GN"]]


def test_gn2_passes_as_gn2(tool, tmp_path):
    rec = _translate(tool, tmp_path, "GN 2 0 0 0 13 0.005")
    assert _gn_lines(rec) == ["GN 2 0 0 0 13 0.005"]
    assert not any("reflection-coefficient" in n for n in rec["notes"]), rec["notes"]


def test_gn2_keeps_the_nofile_sentinel(tool, tmp_path):
    rec = _translate(tool, tmp_path, "GN 2 0 0 0 13 0.005", nofile=True)
    assert _gn_lines(rec) == ["GN 2 0 0 0 13 0.005 1 0 NOFILE"]


def test_gn0_stays_gn0_and_the_deck_says_what_it_means(tool, tmp_path):
    rec = _translate(tool, tmp_path, "GN 0 0 0 0 13 0.005")
    assert _gn_lines(rec) == ["GN 0 0 0 0 13 0.005"]
    assert any(
        n.startswith(
            "GN 0: NEC-2's reflection-coefficient ground is NEC-5's Sommerfeld"
        )
        for n in rec["notes"]
    ), rec["notes"]


def test_a_gn2_radial_screen_is_dropped_under_its_own_name(tool, tmp_path):
    rec = _translate(tool, tmp_path, "GN 2 4 0 0 13 0.005 1.5 0.001")
    assert _gn_lines(rec) == ["GN 2 0 0 0 13 0.005"]
    assert any(n.startswith("GN 2: radial screen (4 radials)") for n in rec["notes"])


@pytest.mark.parametrize(
    "gn",
    [
        "GN 2 0 0 0 13 0.005",
        "GN 2 0 0 0 5 0.001",
        "GN 2 32 0 0 13 0.005 12 0.001",
    ],
)
def test_no_gn2_in_ever_comes_out_as_gn0(tool, tmp_path, gn):
    """The invariant the issue names, over the shapes the corpus carries."""
    assert not any(
        ln.startswith("GN 0") for ln in _gn_lines(_translate(tool, tmp_path, gn))
    )


@pytest.mark.parametrize("gn, want", [("GN 1", "GN 1"), ("GN -1", "GN -1")])
def test_the_other_ground_types_are_untouched(tool, tmp_path, gn, want):
    assert _gn_lines(_translate(tool, tmp_path, gn)) == [want]
