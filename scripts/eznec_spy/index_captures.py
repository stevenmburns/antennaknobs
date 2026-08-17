"""Index the EZNEC -> NEC-5 capture corpus (momwire#390 step 3).

Walks the capture directories the spy shim wrote, pairs each run's input deck with
its printout, and tabulates the card vocabulary. The headline question the issue
asks -- does EZNEC emit TL/NT into the deck, or keep lines/networks in its own code
-- is answered by the TL/NT columns of the emitted table.

Usage:
    python scripts/eznec_spy/index_captures.py [--root scratch/eznec-capture]
                                               [--json out.json] [--markdown out.md]
"""

from __future__ import annotations

import argparse
import json
import re
from collections import Counter
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_ROOT = REPO_ROOT / "scratch" / "eznec-capture"

# A NEC data/geometry card is a 2-letter mnemonic at the start of a line. Comment
# cards (CM/CE) carry EZNEC's model title, so they are parsed but not counted as
# dialect surface.
CARD_RE = re.compile(r"^\s*([A-Z]{2})\b")
COMMENT_CARDS = {"CM", "CE"}

# Cards that decide the headline question, and the ones whose presence tells us how
# much of NEC-5's surface a momwire front-end would have to speak.
HEADLINE_CARDS = ("TL", "NT")


def read_meta(capture: Path) -> dict:
    meta = {}
    path = capture / "meta.tsv"
    if path.exists():
        for line in path.read_text(encoding="utf-8", errors="replace").splitlines():
            if "\t" in line:
                key, value = line.split("\t", 1)
                meta[key] = value
    return meta


def find_deck(capture: Path) -> Path | None:
    """The deck EZNEC wrote before launching the engine.

    It exists in the pre-snapshot (the parent writes it, then starts us), so prefer
    pre/ over post/. `.NEC` wins over any other extension; `.OUT` is the printout
    and is never a deck.
    """
    for phase in ("pre", "post"):
        directory = capture / phase
        if not directory.is_dir():
            continue
        candidates = [
            p
            for p in sorted(directory.iterdir())
            if p.is_file() and p.suffix.upper() == ".NEC"
        ]
        if candidates:
            return candidates[0]
    return None


def find_printout(capture: Path) -> Path | None:
    directory = capture / "post"
    if not directory.is_dir():
        return None
    candidates = [
        p
        for p in sorted(directory.iterdir())
        if p.is_file() and p.suffix.upper() in (".OUT", ".PRT")
    ]
    return candidates[0] if candidates else None


def parse_deck(text: str) -> tuple[str, Counter, str]:
    """Return (model title, card counts, frequency). Title is EZNEC's first CM
    line; frequency is the FR card's FMHZ field, which is the only thing that
    varies across the launches of a sweep."""
    title = ""
    freq = ""
    counts: Counter = Counter()
    for line in text.splitlines():
        match = CARD_RE.match(line)
        if not match:
            continue
        card = match.group(1)
        if card in COMMENT_CARDS:
            if card == "CM" and not title:
                rest = line.strip()[2:].strip()
                # EZNEC pads the deck with bare `CM` separators and `CM !` notes.
                if rest and not rest.startswith("!"):
                    title = rest
            continue
        if card == "FR" and not freq:
            fields = line.strip()[2:].strip().split(",")
            if len(fields) >= 5:
                freq = fields[4].strip()
        counts[card] += 1
    return title, counts, freq


def index(root: Path) -> list[dict]:
    rows = []
    for capture in sorted(p for p in root.iterdir() if p.is_dir()):
        meta = read_meta(capture)
        deck_path = find_deck(capture)
        printout = find_printout(capture)

        title, counts, freq = ("", Counter(), "")
        deck_text = ""
        if deck_path is not None:
            deck_text = deck_path.read_text(encoding="utf-8", errors="replace")
            title, counts, freq = parse_deck(deck_text)

        rows.append(
            {
                "capture": capture.name,
                "title": title,
                "freq_mhz": freq,
                "cards": dict(sorted(counts.items())),
                "has_tl": counts.get("TL", 0) > 0,
                "has_nt": counts.get("NT", 0) > 0,
                "deck": str(deck_path.relative_to(root)) if deck_path else None,
                "deck_lines": len(deck_text.splitlines()) if deck_text else 0,
                "printout": str(printout.relative_to(root)) if printout else None,
                "command_line": meta.get("command_line", ""),
                "argument_tail": meta.get("argument_tail", ""),
                "cwd": meta.get("cwd", ""),
                "stdin_redirected": meta.get("stdin_redirected", ""),
                "exit_code": meta.get("exit_code", ""),
                "elapsed_ms": meta.get("elapsed_ms", ""),
            }
        )
    return rows


def group_runs(rows: list[dict]) -> list[list[dict]]:
    """Collapse consecutive captures that are one sweep.

    EZNEC launches the engine once per frequency point and regenerates the whole
    deck each time, so a sweep's captures share a model and a card signature and
    differ only in the `FR` frequency (and in any length that scales with
    wavelength). Grouping on (title, card signature) keeps the table one row per
    user action instead of one per frequency point.
    """
    groups: list[list[dict]] = []
    for row in rows:
        signature = (row["title"], tuple(sorted(row["cards"].items())))
        if groups and groups[-1][0]["_signature"] == signature:
            groups[-1].append(row)
        else:
            row = dict(row, _signature=signature)
            groups.append([row])
    return groups


def render_markdown(rows: list[dict]) -> str:
    vocabulary: Counter = Counter()
    for row in rows:
        vocabulary.update(row["cards"])

    tl = [r for r in rows if r["has_tl"]]
    nt = [r for r in rows if r["has_nt"]]

    out = ["# EZNEC -> NEC-5 capture corpus", ""]
    out.append(f"- captures: **{len(rows)}**")
    out.append(f"- decks emitting `TL`: **{len(tl)}** / {len(rows)}")
    out.append(f"- decks emitting `NT`: **{len(nt)}** / {len(rows)}")
    out.append("")

    out.append("## Headline verdict (momwire#390)")
    out.append("")
    if tl or nt:
        out.append(
            "**TL/NT ride the deck.** EZNEC hands NEC-5 the transmission lines and "
            "networks as cards rather than solving them itself, so a momwire drop-in "
            "would have to solve networks -- against the antenna-only stance (#388)."
        )
    else:
        out.append(
            "**Bare wires.** No captured deck carries `TL` or `NT`; EZNEC keeps the "
            "line/network arithmetic in its own code. momwire's antenna-only stance "
            "survives and a drop-in needs only the NEC-5 dialect front-end."
        )
    out.append("")

    out.append("## Card vocabulary")
    out.append("")
    out.append("| card | occurrences | decks |")
    out.append("| --- | --- | --- |")
    for card, total in sorted(vocabulary.items(), key=lambda kv: (-kv[1], kv[0])):
        decks = sum(1 for r in rows if card in r["cards"])
        out.append(f"| `{card}` | {total} | {decks} |")
    out.append("")

    out.append("## Per-run")
    out.append("")
    out.append(
        "A frequency sweep is one engine launch per point, so consecutive captures "
        "that differ only in the `FR` frequency are collapsed into a single row."
    )
    out.append("")
    out.append("| captures | model | freq (MHz) | TL | NT | cards | exit |")
    out.append("| --- | --- | --- | --- | --- | --- | --- |")
    for group in group_runs(rows):
        head = group[0]
        cards = " ".join(f"{c}x{n}" if n > 1 else c for c, n in head["cards"].items())
        span = head["capture"][:4]
        if len(group) > 1:
            span = f"{span}–{group[-1]['capture'][:4]} ({len(group)}×)"
        freqs = [r["freq_mhz"] for r in group if r["freq_mhz"]]
        freq = freqs[0] if len(set(freqs)) <= 1 else f"{freqs[0]}–{freqs[-1]}"
        exits = sorted({r["exit_code"] for r in group})
        out.append(
            f"| {span} | {head['title'] or '-'} | {freq or '-'} "
            f"| {'YES' if head['has_tl'] else ''} | {'YES' if head['has_nt'] else ''} "
            f"| {cards} | {','.join(exits)} |"
        )
    out.append("")

    if rows:
        out.append("## Invocation")
        out.append("")
        out.append("Observed command lines (the protocol a drop-in must accept):")
        out.append("")
        for line in sorted({r["command_line"] for r in rows if r["command_line"]}):
            out.append(f"- `{line}`")
        out.append("")
        for line in sorted({r["cwd"] for r in rows if r["cwd"]}):
            out.append(f"- cwd: `{line}`")
        out.append("")

    return "\n".join(out)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--root",
        type=Path,
        default=DEFAULT_ROOT,
        help=f"capture root (default: {DEFAULT_ROOT})",
    )
    parser.add_argument("--json", type=Path, help="write the raw index here")
    parser.add_argument("--markdown", type=Path, help="write the report here")
    args = parser.parse_args()

    if not args.root.is_dir():
        parser.error(f"no capture root at {args.root} -- run the shim first")

    rows = index(args.root)
    report = render_markdown(rows)

    if args.json:
        args.json.write_text(json.dumps(rows, indent=2), encoding="utf-8")
    if args.markdown:
        args.markdown.write_text(report, encoding="utf-8")
    print(report)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
