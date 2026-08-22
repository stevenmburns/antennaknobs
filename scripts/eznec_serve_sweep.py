#!/usr/bin/env python3
"""Sweep the whole EZNEC capture corpus through momwire's NEC-5 seam.

The scored matrix (``docs/status/2026-08-20-eznec-nec5-scored-matrix.md``)
weights every dialect statement by how many captured launches carry it, and
scores the seam by how many of those launches come back with an answer.  Both
numbers are properties of a corpus that keeps growing and of an engine that
keeps landing rungs, so both have to be re-measured rather than remembered.
This script is that measurement, kept rerunnable so the doc's next re-score is
a command rather than an archaeology exercise.

What it does, per capture in ``scratch/eznec-capture/index.json``: read the
deck EZNEC wrote (the index's ``deck`` field, written with Windows separators),
push it through :func:`momwire.eznec.render` IN-PROCESS — one interpreter, 122
solves, not 122 subprocesses — and classify the printout that comes back.  A
printout carrying ``ANTENNA INPUT PARAMETERS`` is SERVED; one carrying a
``NEC ERROR`` line is REFUSED, and the sentence after that prefix is the
refusal's identity.  Anything else, or an exception out of ``render``, is a
CRASH: the seam's contract is that every deck comes back one of the first two
ways at exit 0, so a third outcome is a finding and this script says so loudly
rather than folding it into a count.

It also counts the statement weights the matrix tables quote — captures
containing each mnemonic, from the index's own ``cards`` census — so the
weights and the ladder come out of one pass over one corpus.

Sanity anchors, checked on every run and fatal when they fail (``--json`` still
gets written so a failed anchor is debuggable):

* the original 49-capture corpus (``0000``-``0048``) still stands 48 of 49,
  with ``0022`` the one refusal and its sentence naming the OBSERVATION POINT
  on its monopole's ground contact (momwire#545 narrowed it from the ground);
* the 62 captures momwire's own fixture corpus pins stand 59 of 62, refusing
  exactly the three ids momwire's corpus-ladder test names.

Usage::

    .venv/bin/python scripts/eznec_serve_sweep.py            # summary to stdout
    .venv/bin/python scripts/eznec_serve_sweep.py --json out.json

Exit status is 0 when every anchor holds and nothing crashed, 1 otherwise.
"""

from __future__ import annotations

import argparse
import json
import re
import statistics
import sys
import time
import traceback
from collections import Counter
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
CAPTURE_ROOT = REPO_ROOT / "scratch" / "eznec-capture"
INDEX = CAPTURE_ROOT / "index.json"

SERVED_MARKER = "ANTENNA INPUT PARAMETERS"
ERROR_PREFIX = "NEC ERROR - "
# Where a refusal stops naming and starts explaining.
NAMING_SPLIT = " is not served at this seam"

# The two anchors.  Both are other people's numbers — the first is this doc's
# own first re-score (2026-08-20, momwire#504 U4), the second is momwire's
# ``tests/test_eznec_serve.py::test_the_corpus_ladder_stands_where_545_left_it``
# — and a sweep that cannot reproduce them is measuring something else.
ANCHOR_49 = {"served": 48, "refused": ["0022"]}
# The sentence's stable NAMING prefix, compared with startswith: momwire#545's
# contact-point refusal carries the measured ladder in its explanation, and an
# anchor that pinned the whole paragraph would break on every re-measure of the
# numbers it quotes.  What is anchored is what the refusal is ABOUT.
ANCHOR_49_SENTENCE = "NE (near electric field) asks for the field at (0, 0, 0) metres"
ANCHOR_FIXTURE_IDS = tuple(
    f"{n:04d}"
    for n in (
        *range(0, 49),
        *range(107, 118),
        120,
        121,
    )
)
# The widest |dZ| the 49-capture corpus showed, quoted in the matrix's first
# re-score.  Not an anchor — a corpus that grows is entitled to widen it — but
# every row above it is a row the doc has to name.
ENVELOPE_CEILING = 16.3

ANCHOR_FIXTURE = {
    "served": 59,
    "refused": ["0022", "0107", "0112"],
}


def capture_id(entry: dict) -> str:
    """The four-digit id a capture directory leads with."""
    return entry["capture"].split("_", 1)[0]


def deck_path(entry: dict) -> Path:
    """The captured deck, from an index field written on Windows."""
    return CAPTURE_ROOT / entry["deck"].replace("\\", "/")


def refusal_key(sentence: str) -> str:
    """The naming clause of a refusal — what the matrix rosters it under.

    A refusal here is a paragraph: it names the thing it will not do, then
    explains why and says what the operator can get instead.  The matrix
    rosters refusals by what the seam REFUSES, not by which deck asked, so the
    key is the clause before the explanation — the same string momwire's own
    ``REFUSALS`` table keys on.  A refusal that has no such clause keys on its
    whole text, which is exactly what a new refusal shape should look like.
    """
    head, _, _ = sentence.partition(NAMING_SPLIT)
    return head.strip()


def classify(printout: str) -> tuple[bool, str | None]:
    """``(served, refusal sentence)`` for one rendered printout."""
    if SERVED_MARKER in printout:
        return True, None
    for line in printout.splitlines():
        if ERROR_PREFIX in line:
            return False, line.split(ERROR_PREFIX, 1)[1].strip()
    return False, None


def sweep(entries: list[dict]) -> list[dict]:
    """Render every capture, serially, recording what came back."""
    from momwire.eznec import render

    results = []
    for entry in entries:
        cid = capture_id(entry)
        text = deck_path(entry).read_bytes().decode("latin-1")
        started = time.perf_counter()
        crash = None
        printout = ""
        try:
            printout = render(text)
        except Exception:  # noqa: BLE001 — a crash is the headline, not a skip
            crash = traceback.format_exc()
        elapsed_ms = round((time.perf_counter() - started) * 1000, 1)
        served, reason = classify(printout) if crash is None else (False, None)
        results.append(
            {
                "id": cid,
                "capture": entry["capture"],
                "title": entry["title"],
                "cards": sorted(entry.get("cards", {})),
                "served": served,
                "reason": refusal_key(reason) if reason else None,
                "reason_full": reason,
                "crash": crash,
                "elapsed_ms": elapsed_ms,
            }
        )
    return results


def card_weights(entries: list[dict]) -> list[tuple[str, int]]:
    """Captures containing each mnemonic — the weight tables' denominators."""
    counts: Counter[str] = Counter()
    for entry in entries:
        counts.update(entry.get("cards", {}).keys())
    return sorted(counts.items(), key=lambda item: (-item[1], item[0]))


def cards_of(text: str) -> list[tuple[str, list[str]]]:
    """One deck's cards as ``(mnemonic, fields)``, comments and blanks dropped."""
    cards = []
    for raw in text.splitlines():
        line = raw.strip()
        if not line or line[:2].upper() in {"CM", "CE"}:
            continue
        mnemonic, _, tail = line.partition(" ")
        cards.append(
            (mnemonic.upper(), [f.strip() for f in tail.split(",")] if tail else [])
        )
    return cards


def _field(fields: list[str], index: int) -> str:
    return fields[index] if index < len(fields) else ""


def variant_weights(entries: list[dict]) -> dict[str, int]:
    """The FINER weights the matrix's tables quote, read off the decks.

    The index's ``cards`` census counts mnemonics, and half the matrix's rows
    are narrower than a mnemonic: ``GN`` is four different grounds, an ``EX``
    is a voltage or a current and one card or four, an ``RP`` is a 2-D or a 3-D
    printout.  Those splits are in the deck text and nowhere else, so they get
    read there — one pass, same corpus, same denominators.
    """
    counts: Counter[str] = Counter()
    for entry in entries:
        text = deck_path(entry).read_bytes().decode("latin-1")
        cards = cards_of(text)
        wavelength = 300.0 / float(entry["freq_mhz"])
        seen: set[str] = set()
        ground = None
        excitations = []
        for mnemonic, fields in cards:
            if mnemonic == "GN":
                ground = f"GN {_field(fields, 0)}"
            elif mnemonic == "GD":
                ground = "GD (bare, MININEC-type)"
            elif mnemonic == "GE":
                seen.add(f"GE {_field(fields, 0)},{_field(fields, 1)}")
            elif mnemonic == "EX":
                excitations.append(_field(fields, 0))
            elif mnemonic == "LD":
                seen.add(f"LD {_field(fields, 0)}")
            elif mnemonic == "RP":
                seen.add(f"RP {_field(fields, 0)} XNDA {_field(fields, 3)}")
            elif mnemonic == "GW":
                span = max((abs(float(f)) for f in fields[2:8] if f), default=0.0)
                if span > 10.0 * wavelength:
                    seen.add("remote anchor wire (> 10 lambda out)")
            if mnemonic in {"EX", "LD", "TL", "NT"} and "-1" in fields:
                seen.add("signed node addressing (-1 tag)")
            if mnemonic in {"EX", "LD", "TL", "NT"}:
                for f in fields:
                    if f.startswith("-") and f not in {"-1", "-1."} and _is_int(f):
                        seen.add(f"negative node field other than -1 ({f})")
        if ground:
            seen.add(ground)
        if excitations:
            shape = "single" if len(excitations) == 1 else "phased multi-source"
            seen.add(f"EX {excitations[0]} {shape}")
        counts.update(seen)
    return dict(sorted(counts.items(), key=lambda item: (-item[1], item[0])))


def _is_int(field: str) -> bool:
    try:
        int(field)
    except ValueError:
        return False
    return True


_CELL = re.compile(r"[-+]?\d\.\d{4}E[-+]\d{2}")


def input_impedances(text: str) -> list[complex]:
    """Every source impedance an ``ANTENNA INPUT PARAMETERS`` table prints.

    Cells 5 and 6 of the twelve-column row (three integers, nine E12.4 cells)
    are the resistance and the reactance.  Read positionally rather than by
    column offset so the same reader works on the captured Windows file and on
    this seam's rendering of it.
    """
    out: list[complex] = []
    lines = text.split("\n")
    for index, line in enumerate(lines):
        if "ANTENNA INPUT PARAMETERS" not in line:
            continue
        for row in lines[index + 1 :]:
            cells = _CELL.findall(row)
            if len(cells) >= 9:
                out.append(complex(float(cells[4]), float(cells[5])))
            elif out:
                break
    return out


def envelope(entries: list[dict], results: list[dict]) -> dict:
    """|ΔZ| against the captured printout, for every served capture with one.

    Serving a deck and answering it right are two questions, and a sweep that
    only counts printouts answers the first one.  The matrix quotes a family
    envelope (measured + 25 % per capture, in momwire's own gates) and an
    envelope is only honest while something keeps re-measuring it against the
    whole corpus rather than against the subset that has fixtures.

    A capture whose printout is unusable (the frequency-stepping session's
    withheld files) shows up as a row-count mismatch and is reported as
    uncomparable rather than silently dropped.
    """
    by_id = {row["id"]: row for row in results}
    deltas: list[dict] = []
    uncomparable: list[str] = []
    for entry in entries:
        cid = capture_id(entry)
        row = by_id[cid]
        printout = entry.get("printout")
        if not row["served"] or not printout:
            continue
        path = CAPTURE_ROOT / printout.replace("\\", "/")
        if not path.exists():
            uncomparable.append(cid)
            continue
        captured = input_impedances(
            path.read_bytes().decode("latin-1").replace("\r\n", "\n")
        )
        from momwire.eznec import render

        served = input_impedances(
            render(deck_path(entry).read_bytes().decode("latin-1"))
        )
        if not captured or len(captured) != len(served):
            uncomparable.append(cid)
            continue
        for source, (want, got) in enumerate(zip(captured, served)):
            deltas.append(
                {
                    "id": cid,
                    "title": entry["title"],
                    "source": source,
                    "captured": [want.real, want.imag],
                    "served": [got.real, got.imag],
                    "abs_delta": abs(want - got),
                }
            )
    deltas.sort(key=lambda row: -row["abs_delta"])
    magnitudes = [row["abs_delta"] for row in deltas]
    return {
        "rows": len(deltas),
        "uncomparable": sorted(set(uncomparable)),
        "min": min(magnitudes, default=None),
        "median": statistics.median(magnitudes) if magnitudes else None,
        "max": max(magnitudes, default=None),
        "deltas": deltas,
    }


def subset_check(results: list[dict], ids, expected: dict, label: str) -> list[str]:
    """One anchor: served count and refused-id set over a subset of the sweep."""
    wanted = set(ids)
    rows = [row for row in results if row["id"] in wanted]
    problems = []
    if len(rows) != len(wanted):
        problems.append(
            f"{label}: swept {len(rows)} of {len(wanted)} expected captures"
        )
    served = sum(1 for row in rows if row["served"])
    if served != expected["served"]:
        problems.append(f"{label}: {served} served, anchor says {expected['served']}")
    refused = sorted(row["id"] for row in rows if not row["served"])
    if refused != expected["refused"]:
        problems.append(
            f"{label}: refused {refused}, anchor says {expected['refused']}"
        )
    return problems


def check_anchors(results: list[dict]) -> list[str]:
    """Every anchor, all of them, so one run reports all the drift at once."""
    problems = subset_check(
        results,
        (f"{n:04d}" for n in range(49)),
        ANCHOR_49,
        "49-capture corpus",
    )
    sentence = next(
        (row["reason"] for row in results if row["id"] == "0022"),
        None,
    )
    if sentence is None or not sentence.startswith(ANCHOR_49_SENTENCE):
        problems.append(
            f"0022 refuses with {sentence!r}, anchor says it starts with "
            f"{ANCHOR_49_SENTENCE!r}"
        )
    problems += subset_check(
        results,
        ANCHOR_FIXTURE_IDS,
        ANCHOR_FIXTURE,
        "momwire fixture corpus",
    )
    crashed = [row["id"] for row in results if row["crash"]]
    if crashed:
        problems.append(f"render raised on {crashed} — see the crash field")
    return problems


def summarize(results: list[dict], entries: list[dict], wall_s: float) -> dict:
    """The JSON the doc's numbers are read off."""
    reasons: dict[str, list[str]] = {}
    for row in results:
        if row["served"]:
            continue
        reasons.setdefault(row["reason"] or "(no NEC ERROR line)", []).append(row["id"])
    return {
        "captures": len(results),
        "served": sum(1 for row in results if row["served"]),
        "refused": sum(1 for row in results if not row["served"]),
        "refusals_by_sentence": {k: sorted(v) for k, v in sorted(reasons.items())},
        "crashes": [row["id"] for row in results if row["crash"]],
        "card_weights": card_weights(entries),
        "variant_weights": variant_weights(entries),
        "envelope": envelope(entries, results),
        "wall_seconds": round(wall_s, 1),
        "results": results,
    }


def report(summary: dict, problems: list[str]) -> None:
    """Human-readable, because the doc is written from what this prints."""
    total = summary["captures"]
    print(f"swept {total} captures in {summary['wall_seconds']} s")
    print(f"  served  {summary['served']}/{total}")
    print(f"  refused {summary['refused']}/{total}")
    print()
    print("refusals, by the sentence the seam says:")
    for sentence, ids in summary["refusals_by_sentence"].items():
        print(f"  [{len(ids)}] {sentence}")
        print(f"        {', '.join(ids)}")
    print()
    print(f"statement weights (captures carrying the card, of {total}):")
    for card, count in summary["card_weights"]:
        print(f"  {card:<3} {count:>4}/{total}")
    print()
    print(f"finer weights, read off the decks (of {total}):")
    for variant, count in summary["variant_weights"].items():
        print(f"  {count:>4}/{total}  {variant}")
    env = summary["envelope"]
    print(
        f"|dZ| vs the captured printout, {env['rows']} source rows "
        f"({len(env['uncomparable'])} captures uncomparable):"
    )
    print(
        f"  min {env['min']:.3f}  median {env['median']:.3f}  max {env['max']:.1f} ohm"
    )
    print(f"  above the 49-corpus ceiling of {ENVELOPE_CEILING} ohm:")
    for row in env["deltas"]:
        if row["abs_delta"] <= ENVELOPE_CEILING:
            break
        want = complex(*row["captured"])
        got = complex(*row["served"])
        print(
            f"    {row['abs_delta']:>9.1f}  {row['id']} src{row['source']}  "
            f"capture {want:.4f}  seam {got:.4f}  {row['title']}"
        )
    print()
    if problems:
        print("ANCHORS FAILED:")
        for problem in problems:
            print(f"  ! {problem}")
        for row in summary["results"]:
            if row["crash"]:
                print(f"\n--- {row['id']} {row['title']} crashed ---")
                print(row["crash"])
    else:
        print(
            "anchors: 48/49 on the original corpus, "
            f"{ANCHOR_FIXTURE['served']}/{len(ANCHOR_FIXTURE_IDS)} on momwire's "
            "— both hold"
        )


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--json", type=Path, help="write the full summary here")
    parser.add_argument(
        "--index",
        type=Path,
        default=INDEX,
        help="capture index to sweep (default: scratch/eznec-capture/index.json)",
    )
    args = parser.parse_args(argv)

    entries = json.loads(args.index.read_text())
    started = time.perf_counter()
    results = sweep(entries)
    wall_s = time.perf_counter() - started

    summary = summarize(results, entries, wall_s)
    problems = check_anchors(results)
    summary["anchor_problems"] = problems

    if args.json:
        args.json.write_text(json.dumps(summary, indent=2) + "\n")
    report(summary, problems)
    return 1 if problems else 0


if __name__ == "__main__":
    sys.exit(main())
