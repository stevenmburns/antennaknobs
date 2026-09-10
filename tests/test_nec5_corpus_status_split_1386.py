"""antennaknobs#1386: "unreadable" was a mixed bucket; the report now splits it.

Before this, a translate report had three outcomes — `translated`, `refused`
(no NEC-5 card for it) and `unreadable` — and `unreadable` held two unlike
things at once:

- decks NO NEC reads, whose own cards contradict each other (a wire with zero
  segments, an `EX` addressing a segment that does not exist);
- decks THIS TOOL could not read, which is a statement about the tool: a 4nec2
  dialect construct its `SY` evaluator does not resolve, a field it cannot turn
  into a number.

A census cannot tell those apart, and they belong on different ledgers: the
first is the deck's fault and no engine's, the second is ours. So the first kind
now reports its own status, `invalid`, alongside the `not valid NEC input:`
reason #1382 introduced, and `unreadable` means only the second.

**Where the line is drawn**, and why it is drawn conservatively: a deck is
`invalid` when a COUNT or an ADDRESS in it contradicts the deck itself — which
is checkable from the file alone, with no assumption about any dialect. A
non-numeric field or an unparsable card stays `unreadable` even though NEC would
also reject it, because our own symbol evaluator is a likelier explanation, and
calling it the deck's fault would be a claim about 4nec2 that this tool cannot
make.
"""

from __future__ import annotations

import importlib.util
import json
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "nec5_corpus" / "nec5_corpus.py"

INVALID = "not valid NEC input: "

HEAD = "CM probe\nCE\n"
TAIL = "GE 0\nEX 0 1 3 0 1 0\nXQ\nEN\n"
WIRE = "GW 1 5 0 0 0 0 0 1 .001\n"

# --- no NEC reads these: a count or an address the deck contradicts ----------
ZERO_SEGMENTS = HEAD + "GW 1 0 0 0 0 0 0 1 .001\n" + TAIL
EX_OFF_THE_END = HEAD + WIRE + "GE 0\nEX 0 1 9 0 1 0\nXQ\nEN\n"
EX_ABSOLUTE_OFF_THE_END = HEAD + WIRE + "GE 0\nEX 0 0 99 0 1 0\nXQ\nEN\n"
LD_UNDEFINED_TAG = (
    HEAD + WIRE + "GE 0\nLD 1 851 0 0 0 0 1e-9\n" + "EX 0 1 3 0 1 0\nXQ\nEN\n"
)

# --- this tool could not read these -----------------------------------------
SY_NO_ASSIGNMENT = "CM probe\nSY\nCE\n" + WIRE + TAIL
SY_BAD_NAME = "CM probe\nSY R-2=3\nCE\n" + WIRE + TAIL
EX_NON_NUMERIC = HEAD + WIRE + "GE 0\nEX 0 1 zz 0 1 0\nXQ\nEN\n"
NOT_A_CARD = HEAD + WIRE + "hello there\n" + TAIL

# --- and the two neighbours the split must not disturb -----------------------
GOOD = HEAD + WIRE + TAIL
NO_NEC5_CARD = HEAD + WIRE + "SC 0 0 1 1 1 1\n" + TAIL


@pytest.fixture(scope="module")
def tool():
    spec = importlib.util.spec_from_file_location("nec5_corpus_status_probe", SCRIPT)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def _translate(tool, tmp_path, text: str) -> dict:
    p = tmp_path / "deck.nec"
    p.write_text(text, encoding="utf-8")
    return tool.translate_file(p, "deck.nec", "exact", False)


def test_the_good_deck_still_translates(tool, tmp_path):
    assert _translate(tool, tmp_path, GOOD)["status"] == "translated"


@pytest.mark.parametrize(
    ("text", "what"),
    [
        (ZERO_SEGMENTS, "a wire with zero segments"),
        (EX_OFF_THE_END, "EX past the end of its tag"),
        (EX_ABSOLUTE_OFF_THE_END, "EX past the end of the structure"),
        (LD_UNDEFINED_TAG, "LD on a tag no geometry defines"),
    ],
)
def test_a_deck_no_nec_reads_is_invalid(tool, tmp_path, text, what):
    rec = _translate(tool, tmp_path, text)
    assert rec["status"] == "invalid", (what, rec)
    assert rec["reason"].startswith(INVALID), rec["reason"]


@pytest.mark.parametrize(
    ("text", "what"),
    [
        (SY_NO_ASSIGNMENT, "a SY card with no assignment"),
        (SY_BAD_NAME, "a SY name this evaluator rejects"),
        (EX_NON_NUMERIC, "a field this tool could not turn into a number"),
        (NOT_A_CARD, "a line this tool did not recognise as a card"),
    ],
)
def test_a_deck_only_this_tool_cannot_read_stays_unreadable(tool, tmp_path, text, what):
    """Not `invalid`: that would be a claim about 4nec2 this tool cannot make."""
    rec = _translate(tool, tmp_path, text)
    assert rec["status"] == "unreadable", (what, rec)
    assert not rec["reason"].startswith(INVALID), rec["reason"]


def test_the_1382_faults_report_invalid_not_refused(tool, tmp_path):
    """#1382 put them under `refused`, beside "no NEC-5 card for it". They are
    a different claim, and now they carry the status that says so."""
    gn_above_ge = HEAD + WIRE + "GN 2 0 0 0 13 .005\n" + TAIL
    rec = _translate(tool, tmp_path, gn_above_ge)
    assert rec["status"] == "invalid", rec
    assert rec["reason"].startswith(INVALID), rec["reason"]


def test_no_nec5_card_is_still_refused(tool, tmp_path):
    """The two statuses are distinct claims and must not collapse together."""
    rec = _translate(tool, tmp_path, NO_NEC5_CARD)
    assert rec["status"] == "refused", rec
    assert not rec["reason"].startswith(INVALID), rec["reason"]


def test_the_report_and_the_summary_carry_the_new_status(tmp_path):
    """End to end: a census reads the JSONL, a person reads the summary."""
    src, out = tmp_path / "src", tmp_path / "out"
    src.mkdir()
    for name, text in [
        ("good.nec", GOOD),
        ("zero.nec", ZERO_SEGMENTS),
        ("nocard.nec", NO_NEC5_CARD),
        ("sy.nec", SY_NO_ASSIGNMENT),
    ]:
        (src / name).write_text(text, encoding="utf-8")
    proc = subprocess.run(
        [
            sys.executable,
            "-S",
            str(SCRIPT),
            "translate",
            "--src",
            str(src),
            "--out",
            str(out),
        ],
        capture_output=True,
        text=True,
        check=True,
    )
    rows = {
        r["file"]: r["status"]
        for r in (
            json.loads(ln)
            for ln in (out / "translate-report.jsonl").read_text().splitlines()
        )
        if "_meta" not in r
    }
    assert rows == {
        "good.nec": "translated",
        "zero.nec": "invalid",
        "nocard.nec": "refused",
        "sy.nec": "unreadable",
    }, rows
    assert "invalid: 1" in proc.stdout, proc.stdout
    # The legend is what makes the four words mean something to a reader.
    assert "no NEC-5 card" in proc.stdout and "could not read" in proc.stdout, (
        proc.stdout
    )
