"""antennaknobs#1423: a tag-0 range and a zero end field survive the knot remesh.

#1416 made a per-tag `LD` range cover the same wire after `translate` remeshes it.
Two spellings were left out, deliberately, until NEC's reading of them was
established. Measured 2026-09-14 on nec2c 1.3.1, two 11-segment wires, LD 5:

- `LD 5 1 2 0` and `LD 5 1 2 2` give the same impedance, so a zero END field
  means "segment M only".
- `LD 5 0 1 22` matches loading both wires whole, and `LD 5 0 5 15` matches
  `LD 5 1 5 11` + `LD 5 2 1 4`, so tag 0 addresses ABSOLUTE segment numbers
  across wires, in card order.

Both used to pass through translation untouched. On five corpus decks
(K8UY_yagi_2m_original's `LD 5 0 1 211` against 222 segments after the remesh)
a whole-structure load became a partial one: momwire refused it, and NEC-5
answered for an antenna that was not the author's.
"""

from __future__ import annotations

import importlib.util
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "nec5_corpus" / "nec5_corpus.py"


@pytest.fixture(scope="module")
def tool():
    spec = importlib.util.spec_from_file_location("nec5_corpus_ld_tag0_probe", SCRIPT)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def _translate(tool, tmp_path, ld: str) -> list[str]:
    """Two 11-segment wires. The centre source on wire 1 is what forces the
    remesh (11 → 22 under the "double" policy); wire 2 is not referenced and
    keeps its 11, so the new structure has 33 segments and the two wires moved
    by DIFFERENT factors."""
    text = (
        "CM ld tag 0\nCE\n"
        "GW 1 11 0 0 -2.5 0 0 2.5 0.0005\n"
        "GW 2 11 1 0 -2.5 1 0 2.5 0.0005\n"
        "GE 0\n"
        f"{ld}\n"
        "EX 0 1 6 0 1 0\nGN -1\nXQ\nEN\n"
    )
    p = tmp_path / "ld_tag0.nec"
    p.write_text(text, encoding="utf-8")
    rec = tool.translate_file(p, "ld_tag0.nec", "double", False)
    deck = rec["outputs"][0][1]
    return [ln for ln in deck.splitlines() if ln.split() and ln.split()[0] == "LD"]


def test_the_remesh_is_what_the_cases_below_assume(tool, tmp_path):
    """Guards the rest from passing vacuously: wire 1 doubles, wire 2 does not."""
    text = (
        "CM\nCE\nGW 1 11 0 0 -2.5 0 0 2.5 0.0005\nGW 2 11 1 0 -2.5 1 0 2.5 0.0005\n"
        "GE 0\nEX 0 1 6 0 1 0\nGN -1\nXQ\nEN\n"
    )
    p = tmp_path / "remesh.nec"
    p.write_text(text, encoding="utf-8")
    deck = tool.translate_file(p, "remesh.nec", "double", False)["outputs"][0][1]
    gw = [ln.split() for ln in deck.splitlines() if ln.startswith("GW")]
    assert [(g[1], g[2]) for g in gw] == [("1", "22"), ("2", "11")], gw


@pytest.mark.parametrize(
    ("ld", "expected"),
    [
        # the whole structure before the remesh is the whole structure after it
        ("LD 5 0 1 22 5.8001E7", "LD 5 0 1 33 5.8001E7"),
        # a range straddling both wires: each edge maps on its own wire's mesh
        ("LD 5 0 5 15 5.8001E7", "LD 5 0 9 26 5.8001E7"),
        # a range inside the unremeshed second wire only moves by wire 1's growth
        ("LD 5 0 12 22 5.8001E7", "LD 5 0 23 33 5.8001E7"),
    ],
    ids=["whole-structure", "straddles-both-wires", "inside-wire-2"],
)
def test_a_tag0_range_is_remapped_as_absolute_segments(tool, tmp_path, ld, expected):
    assert _translate(tool, tmp_path, ld) == [expected]


def test_a_zero_end_field_is_segment_m_only_and_written_explicitly(tool, tmp_path):
    """`LD 5 1 2 0` is segment 2 alone on nec2c. On the doubled wire that span is
    new segments 3..4. The end is written explicitly, since how NEC-5 reads a
    zero end field was not measured."""
    assert _translate(tool, tmp_path, "LD 5 1 2 0 5.8001E7") == ["LD 5 1 3 4 5.8001E7"]
