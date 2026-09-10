"""antennaknobs#1382: a deck that is not legal NEC input is refused, not passed on.

The eight decks both NEC-5 binaries rejected with `DATAGN: Input data error`
on the 09-09 corpus run are not NEC-5 findings and not translator findings:
they are source decks no NEC reads, and nec2c rejects every one of them too.
Passing them through faithfully put eight decks in each binary's error column
that say nothing about the binary.

Three faults, all named in the refusal so a census can tell them apart:

1. a program-control card before `GE` — the geometry section is over at `GE`
   and NEC reads a control card found before it as geometry;
2. no `GE` anywhere — a geometry fragment, not a model;
3. a `GW` whose radius is 0, which in NEC means "a `GC` follows with the
   taper", and no `GC` follows.

Refused, never repaired: a moved `GN` would be our model rather than the
author's, and the working group is comparing binaries on published decks.

These carried the `refused` status when #1382 built them, beside "no NEC-5 card
for it". #1386 gave them their own, `invalid`, because they are a different
claim -- see `test_nec5_corpus_status_split_1386.py`.

The decks below are hand-written minimal reproductions of the eight, whose own
sources are third-party and are fetched rather than vendored.
"""

from __future__ import annotations

import importlib.util
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "nec5_corpus" / "nec5_corpus.py"

PREFIX = "not valid NEC input: "

VALID = """CM a deck that is legal NEC input
CE
GW 1 5 0 0 0 0 0 1 .001
GE 0
EX 0 1 3 0 1 0
GN -1
XQ
EN
"""

# 1. Control card before GE. sokyrad's three Moxons and arcanum/helix-axial
#    put GN on the line above GE; icecube-dbesson/BCone35 puts EX there.
CONTROL_BEFORE_GE = """CM the ground card sits above GE
CE
GW 1 5 0 0 0 0 0 1 .001
{card}
GE 0
EX 0 1 3 0 1 0
XQ
EN
"""

# 2a. No GE, and a control card to prove the deck meant to be a model:
#     g1ojs/_2m/Helix/Chimney.nec, which ends on an LD.
NO_GE_WITH_CONTROL = """CM wires and a load, and no GE
CE
GW 777 5 0 0 0 0 0 1 .0025
LD 1 777 0 0 0 0 5.3e-14
"""

# 2b. No GE, no control card, no EN either: g1ojs/Clutter file.nec, a geometry
#     fragment meant to be pasted into another deck. The issue's rule ("no GE
#     before the first control card or EN") does not reach this one, which is
#     why the test is here: the rule that does is "no GE at all".
NO_GE_AT_ALL = """CM Clutter, to paste into a model
CE
GW 1000 9 1.3 -1.67 5.1 2.7 -1.67 5.1 0.01
GM 1 2 0 0 0 0 1.67 0 1000
"""

# 3. A GW with radius 0 and no GC. rchacker's turnstil writes the radius field
#    away entirely (eight fields, not nine) and follows with GS.
GW_NO_RADIUS = """CM the last wire has no radius field, and GS follows
CE
GW 1 5 0 0 0 0 0 1 .001
GW 7 5 0 0 1 0 0 2
GS 0 0 0.001
GE 0
EX 0 1 3 0 1 0
XQ
EN
"""

GW_ZERO_RADIUS_AT_END = """CM radius written as 0, and nothing follows
CE
GW 1 5 0 0 0 0 0 1 .001
GW 7 5 0 0 1 0 0 2 0
GE 0
EX 0 1 3 0 1 0
XQ
EN
"""

# The same shape, legal: radius 0 IS how NEC-2 says "the taper is on the GC".
GW_ZERO_RADIUS_WITH_GC = """CM a tapered wire, spelled the way NEC-2 spells it
CE
GW 1 5 0 0 0 0 0 1 .001
GW 7 5 0 0 1 0 0 2 0
GC 0 0 .002 .001 .003
GE 0
EX 0 1 3 0 1 0
XQ
EN
"""


@pytest.fixture(scope="module")
def tool():
    spec = importlib.util.spec_from_file_location("nec5_corpus_invalid_probe", SCRIPT)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def _translate(tool, tmp_path, text: str) -> dict:
    p = tmp_path / "deck.nec"
    p.write_text(text, encoding="utf-8")
    return tool.translate_file(p, "deck.nec", "exact", False)


def test_the_control_deck_translates(tool, tmp_path):
    """Guards every assertion below: the shape is fine but for the fault."""
    assert _translate(tool, tmp_path, VALID)["status"] == "translated"


@pytest.mark.parametrize(
    "card",
    ["GN 2 0 0 0 13 0.005", "EX 0 1 1 0 1 0", "FR 0 1 0 0 14.2", "LD 1 1 0 0 0 0 1e-9"],
)
def test_a_control_card_before_ge_is_refused_by_name(tool, tmp_path, card):
    rec = _translate(tool, tmp_path, CONTROL_BEFORE_GE.format(card=card))
    assert rec["status"] == "invalid"
    assert rec["reason"].startswith(PREFIX), rec["reason"]
    assert card.split()[0] in rec["reason"] and "GE" in rec["reason"], rec["reason"]


@pytest.mark.parametrize(
    ("text", "what"),
    [(NO_GE_WITH_CONTROL, "with a control card"), (NO_GE_AT_ALL, "geometry only")],
)
def test_a_deck_with_no_ge_is_refused(tool, tmp_path, text, what):
    rec = _translate(tool, tmp_path, text)
    assert rec["status"] == "invalid", what
    assert rec["reason"].startswith(PREFIX), rec["reason"]
    assert "GE" in rec["reason"], rec["reason"]


@pytest.mark.parametrize(
    ("text", "what"),
    [(GW_NO_RADIUS, "no radius field at all"), (GW_ZERO_RADIUS_AT_END, "radius 0")],
)
def test_a_gw_with_radius_zero_and_no_gc_is_refused(tool, tmp_path, text, what):
    rec = _translate(tool, tmp_path, text)
    assert rec["status"] == "invalid", what
    assert rec["reason"].startswith(PREFIX), rec["reason"]
    assert "GW" in rec["reason"] and "GC" in rec["reason"], rec["reason"]


def test_a_gw_with_radius_zero_followed_by_gc_still_translates(tool, tmp_path):
    """Radius 0 is not the fault; radius 0 with no GC is."""
    rec = _translate(tool, tmp_path, GW_ZERO_RADIUS_WITH_GC)
    assert rec["status"] == "translated", rec.get("reason")


def test_the_reason_is_one_family_so_a_census_can_count_it(tool, tmp_path):
    """Every fault shares the prefix, which is what the report groups on."""
    faults = [
        CONTROL_BEFORE_GE.format(card="GN 2 0 0 0 13 0.005"),
        NO_GE_WITH_CONTROL,
        NO_GE_AT_ALL,
        GW_NO_RADIUS,
    ]
    reasons = {_translate(tool, tmp_path, t)["reason"] for t in faults}
    assert len(reasons) == 3, reasons  # the two no-GE decks share one reason
    assert all(r.startswith(PREFIX) for r in reasons), reasons


def test_the_validity_check_runs_before_the_nec5_vocabulary_check(tool, tmp_path):
    """A deck that is BOTH invalid NEC and untranslatable reads as invalid.

    "no NEC-5 card for it" is a statement about NEC-5; "not valid NEC input" is
    a statement about the deck, and the second is the one a census wants when
    both are true — the deck was never going to run anywhere.
    """
    text = CONTROL_BEFORE_GE.format(card="GN 2 0 0 0 13 0.005").replace(
        "GW 1 5 0 0 0 0 0 1 .001\n", "GW 1 5 0 0 0 0 0 1 .001\nSC 0 0 1 1 1 1\n"
    )
    rec = _translate(tool, tmp_path, text)
    assert rec["status"] == "invalid"
    assert rec["reason"].startswith(PREFIX), rec["reason"]
