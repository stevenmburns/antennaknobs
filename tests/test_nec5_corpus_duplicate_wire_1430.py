"""antennaknobs#1430: a deck listing the same wire twice is invalid, not hard.

Two `GW` cards with coincident endpoints are two basis functions with identical
kernels of opposite sign, so the moment matrix is EXACTLY singular. Comparing
engines on such a deck measures floating point: `qantenna/airplane.nec` (cards
GW 116 and GW 117, one wire with reversed endpoints) returned three different
impedances across three NEC-5 builds — 80.9−83.1j, 92.2−61.5j, 74.2+105.4j —
because each build's fill order left a different ~1e-13 residue for the LU to
pivot on. It was the public corpus's widest engine-vs-engine mover, and the
disagreement was entirely about rounding. So the tool refuses the deck before
either engine runs.

The half of this that measurement forced, and which the reported cases do not
show: **a `GM` can separate an authored coincident pair.** Both `dscn2.nec`
copies write `GW 1` and `GW 2` with identical coordinates and then carry
`GM ... 2.0`, a tag range naming tag 2 alone, which moves the second away from
the first. Refusing those would be the tool telling a user their working model
is broken. Without the guard, three valid corpus decks are lost.
"""

from __future__ import annotations

import importlib.util
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "nec5_corpus" / "nec5_corpus.py"


@pytest.fixture(scope="module")
def tool():
    spec = importlib.util.spec_from_file_location("nec5_corpus_dup_probe", SCRIPT)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def _deck(*geometry: str) -> str:
    body = "\n".join(geometry)
    return f"CM dup probe\nCE\n{body}\nGE 0\nEX 0 1 1 0 1 0\nGN -1\nXQ\nEN\n"


def _translate(tool, tmp_path, text, name="dup.nec"):
    p = tmp_path / name
    p.write_text(text, encoding="utf-8")
    return tool.translate_file(p, name, "double", False)


# --- the shapes that MUST be refused ---------------------------------------

A = "GW 1 1 6.32782 -3.08619 2.80627 5.41486 -3.08670 2.80627 0.01"
REVERSED = "GW 2 1 5.41486 -3.08670 2.80627 6.32782 -3.08619 2.80627 0.01"
IDENTICAL = "GW 2 1 6.32782 -3.08619 2.80627 5.41486 -3.08670 2.80627 0.01"
# qantenna/adrian.nec's shape: same tag, same endpoints, DIFFERENT radius
SAME_TAG_OTHER_RADIUS = "GW 1 1 6.32782 -3.08619 2.80627 5.41486 -3.08670 2.80627 0.02"

REFUSE = [
    ("reversed endpoints — airplane.nec / plane.nec", REVERSED),
    ("identical endpoints — 21-2-1 / RICE-dipole", IDENTICAL),
    ("same tag, other radius — adrian.nec", SAME_TAG_OTHER_RADIUS),
]


@pytest.mark.parametrize(
    "why,second", [(w, s) for w, s in REFUSE], ids=[w for w, _ in REFUSE]
)
def test_a_duplicated_wire_is_invalid(tool, tmp_path, why, second):
    rec = _translate(tool, tmp_path, _deck(A, second))
    assert rec["status"] == "invalid", (why, rec)
    assert "listed twice" in rec["reason"], rec["reason"]
    # the pair is NAMED: a bare "invalid" leaves the user hunting 256 cards
    assert "GW tag" in rec["reason"] and rec["reason"].count("GW tag") == 2, rec[
        "reason"
    ]


# --- the shapes that MUST NOT be refused -----------------------------------


def test_a_GM_that_moves_one_of_the_pair_is_not_a_duplicate(tool, tmp_path):
    """`dscn2.nec`'s shape. Three valid corpus decks depend on this."""
    rec = _translate(
        tool,
        tmp_path,
        _deck(A, IDENTICAL, "GM 0 0 0 0 0 1.0 0 0 2.0"),
    )
    assert rec["status"] == "translated", rec.get("reason")


def test_a_GM_covering_BOTH_still_refuses(tool, tmp_path):
    """A rigid move of everything — airplane.nec's own `GM 0 0 ...` — moves the
    pair together and does not un-duplicate it. Without this the guard above
    would be a blanket exemption for any deck carrying a GM, which is 15 % of
    the corpus."""
    rec = _translate(
        tool,
        tmp_path,
        _deck(A, IDENTICAL, "GM 0 0 0 0 0 -13.5 0 -2.0 0"),
    )
    assert rec["status"] == "invalid", rec.get("reason")


def test_two_distinct_wires_translate(tool, tmp_path):
    rec = _translate(
        tool,
        tmp_path,
        _deck(A, "GW 2 1 0 0 0 0 0 1 0.01"),
    )
    assert rec["status"] == "translated", rec.get("reason")


def test_a_pair_outside_the_tolerance_translates(tool, tmp_path):
    """The tolerance is a millionth of the wire's length, deliberately tight:
    the defect is a deck listing one wire twice, not wires that are merely
    close. Two wires a millimetre apart on a metre scale are a modelling
    choice and none of the tool's business."""
    near = "GW 2 1 6.32782 -3.08619 2.80727 5.41486 -3.08670 2.80727 0.01"
    rec = _translate(tool, tmp_path, _deck(A, near))
    assert rec["status"] == "translated", rec.get("reason")


def test_a_shared_endpoint_is_not_a_duplicate(tool, tmp_path):
    """Wires meeting at a junction share ONE endpoint. Refusing those would
    refuse most of the corpus."""
    rec = _translate(
        tool,
        tmp_path,
        _deck(A, "GW 2 1 5.41486 -3.08670 2.80627 5.41486 -3.08670 3.80627 0.01"),
    )
    assert rec["status"] == "translated", rec.get("reason")
