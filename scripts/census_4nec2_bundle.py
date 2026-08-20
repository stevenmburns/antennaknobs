#!/usr/bin/env python3
"""Census of the 4nec2 bundled model corpus, in the dialect the ENGINE sees.

Backs the statement matrix in docs/status/2026-08-19-frontend-statement-matrix.md
(momwire#456 workstream 1). Every model is translated from 4nec2's source
dialect into the emitted engine dialect using the pre-engine resolutions the
2026-08-18 subengine capture established (momwire#413):

  - lines commented with a leading ' are dropped; an inline ' truncates
  - SY symbol lines never reach the engine (symbols resolve to literals)
  - LD 6 (LC trap) arrives as LD 1; LD 7's translation is unsampled
  - GN 3 (MININEC-type ground) arrives as GN 1 plus a manufactured GD
  - EX 6 (current source) arrives as EX 0 + NT + a phantom 1-segment wire

Each emitted deck is then scored against momwire's nec2 dialect refusal
tables (deck-grammar-nec2.md):

  serve   — every statement runs
  refuse  — at least one statement hits a loud, named (or unrecognised-card)
            refusal; parse() raises, so this preempts any silent risk
  silent  — the deck parses but means something the frontend didn't:
            the MININEC GD idiom (GD alongside GN 1 — manufactured from
            GN 3 or hand-written), or a missing EN/NX terminator (the
            parser discards an unterminated body; NEC synthesizes EN at EOF)

Statically undecidable refusals (LD ranges over 8 segments, doubled loads,
partial-wire LD 5) are not modelled; symbolic fields that resolve at emit
time are skipped where a value is needed (e.g. the GN 0 contact check).

Usage:
    python scripts/census_4nec2_bundle.py [--root DIR] [--json OUT]

Default root is the local mirror of the corpus the capture read statically.
"""

from __future__ import annotations

import argparse
import json
import re
from collections import Counter
from pathlib import Path

DEFAULT_ROOT = Path.home() / "antennas/nec-wild/opensource/4nec2"

REFUSE_BY_NAME = {
    "TL",
    "NT",
    "GA",
    "GH",
    "GX",
    "GR",
    "GC",
    "GF",
    "SP",
    "SM",
    "KH",
    "PQ",
    "CP",
    "PL",
    "WG",
    "ZO",
    "SY",
}
# SC is not on the by-name list; it hits "unrecognised NEC card" — still loud.
REFUSE_UNRECOGNISED = {"SC"}

GEOMETRY_CLUSTER = {"GX", "GR", "GH", "GC", "GA"}
NETWORK_CLUSTER = {"NT", "TL"}
PATCH_CLUSTER = {"SP", "SM", "SC"}
LONG_TAIL = {
    "PQ",
    "CP",
    "WG",
    "GF",
    "LD2",
    "LD7",
    "RP1",
    "EX1",
    "EX2",
    "EX3",
    "EX4",
    "EX5",
    "GN+NRADL",
}


def tokens(line: str) -> list[str]:
    return [t for t in re.split(r"[,\s]+", line.strip()) if t]


def num(tok: str):
    try:
        return float(tok.replace("D", "E").replace("d", "e"))
    except ValueError:
        return None


def field_int(fields: list[str], idx: int):
    """Integer value of a field; 0 when missing, None when symbolic."""
    if len(fields) <= idx:
        return 0
    v = num(fields[idx])
    return None if v is None else int(round(v))


def parse_source(path: Path):
    """Read a 4nec2 source model into (mnemonic, fields) cards."""
    try:
        text = path.read_text(encoding="latin-1")
    except OSError:
        return None
    cards = []
    for raw in text.splitlines():
        line = raw
        if line.lstrip().startswith("'"):
            continue
        if "'" in line:
            line = line.split("'", 1)[0]
        s = line.strip()
        if len(s) < 2:
            continue
        mn = s[:2].upper()
        if not re.fullmatch(r"[A-Z]{2}", mn):
            continue
        cards.append((mn, tokens(s[2:])))
    return cards


def emit(cards):
    """Apply 4nec2's pre-engine resolutions; return the emitted card list."""
    out = []
    for mn, f in cards:
        if mn == "SY":
            continue
        if mn == "LD":
            t = field_int(f, 0)
            if t == 6:
                out.append(("LD", ["1"] + f[1:]))
                continue
            # LD 7's translation is unsampled; assume it reaches the engine.
        if mn == "GN" and field_int(f, 0) == 3:
            out.append(("GN", ["1"]))
            out.append(("GD", ["0", "0", "0", "0"] + f[4:6]))
            continue
        if mn == "EX" and field_int(f, 0) == 6:
            # Phantom wire parked at z = its own tag, per the capture.
            out.append(
                (
                    "GW",
                    [
                        "9901",
                        "1",
                        "-1.2e-4",
                        "0",
                        "9901",
                        "1.2e-4",
                        "0",
                        "9901",
                        "6e-6",
                    ],
                )
            )
            out.append(("EX", ["0", "9901", "1", "0", "1", "0"]))
            out.append(("NT", ["9901", "1"] + f[1:3] + ["0", "0", "0", "1"]))
            continue
        out.append((mn, f))
    return out


def score(emitted):
    """Return (refusal reasons, silent reasons) for one emitted deck."""
    refuse, silent = set(), set()
    mns = {m for m, _ in emitted}
    has_gn0 = has_gn1 = touches_z0 = False
    for mn, f in emitted:
        if mn in REFUSE_BY_NAME or mn in REFUSE_UNRECOGNISED:
            refuse.add(mn)
        elif mn == "EX":
            t = field_int(f, 0)
            if t not in (0, None):
                refuse.add(f"EX{t}")
        elif mn == "RP":
            m = field_int(f, 0)
            if m not in (0, 2, 3, None):
                refuse.add(f"RP{m}")
        elif mn == "GN":
            t = field_int(f, 0)
            if t not in (-1, 0, 1, 2, None):
                refuse.add(f"GN{t}")
            elif t in (0, 2) and field_int(f, 1) not in (0, None):
                refuse.add("GN+NRADL")
            has_gn0 |= t == 0
            has_gn1 |= t == 1
        elif mn == "LD":
            t = field_int(f, 0)
            if t in (2, 3, 7):
                refuse.add(f"LD{t}")
        elif mn in ("NE", "NH"):
            if field_int(f, 0) not in (0, None):
                refuse.add(f"{mn}-spherical")
        elif mn == "GW":
            z1 = num(f[4]) if len(f) > 4 else None
            z2 = num(f[7]) if len(f) > 7 else None
            touches_z0 |= z1 == 0.0 or z2 == 0.0
    if has_gn0 and touches_z0:
        refuse.add("GN0-contact")
    if (
        has_gn0
        or "GN2" not in refuse
        and any(m == "GN" and field_int(f, 0) == 2 for m, f in emitted)
    ):
        if "NE" in mns or "NH" in mns:
            refuse.add("NE/NH-finite-ground")
    if "GD" in mns and has_gn1:
        silent.add("MININEC-GD")
    if "EN" not in mns and "NX" not in mns:
        silent.add("no-terminator")
    return refuse, silent


def classify(
    refuse,
    silent,
    waived_refuse=frozenset(),
    waived_silent=frozenset(),
    promoted_silent=frozenset(),
):
    """Waived reasons are served; promoted silent reasons refuse loudly."""
    r = (refuse | (silent & promoted_silent)) - waived_refuse
    s = silent - waived_silent - promoted_silent
    if r:
        return "refuse"
    return "silent" if s else "serve"


def main():
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--root", type=Path, default=DEFAULT_ROOT)
    ap.add_argument("--json", type=Path, help="write full census as JSON")
    args = ap.parse_args()

    paths = sorted({*args.root.rglob("*.nec"), *args.root.rglob("*.NEC")})
    decks = []
    src_cards, emit_cards = Counter(), Counter()
    src_variants, emit_variants = Counter(), Counter()
    for p in paths:
        cards = parse_source(p)
        if not cards:
            continue
        emitted = emit(cards)
        refuse, silent = score(emitted)
        decks.append((str(p.relative_to(args.root)), refuse, silent))
        for counter, deck in ((src_cards, cards), (emit_cards, emitted)):
            for mn in {m for m, _ in deck}:
                counter[mn] += 1
        for counter, deck in ((src_variants, cards), (emit_variants, emitted)):
            seen = set()
            for mn, f in deck:
                if mn in ("EX", "GN", "LD", "RP"):
                    t = field_int(f, 0)
                    seen.add(f"{mn} {'sym' if t is None else t}")
                elif mn == "FR":
                    nfrq = field_int(f, 1) or 1
                    seen.add("FR multi" if nfrq > 1 else "FR single")
            for k in seen:
                counter[k] += 1

    n = len(decks)
    print(f"models: {n}  (root: {args.root})")

    GATE = frozenset({"MININEC-GD"})
    EOFEN = frozenset({"no-terminator"})
    ladder = [
        ("today", frozenset(), frozenset(), frozenset()),
        ("hygiene (EOF-as-EN, GD/GN1 gate)", frozenset(), EOFEN, GATE),
        ("+ NT/TL", NETWORK_CLUSTER, EOFEN, GATE),
        ("+ geometry transforms", NETWORK_CLUSTER | GEOMETRY_CLUSTER, EOFEN, GATE),
        (
            "+ MININEC-type ground",
            NETWORK_CLUSTER | GEOMETRY_CLUSTER,
            EOFEN | GATE,
            frozenset(),
        ),
        (
            "+ long tail",
            NETWORK_CLUSTER | GEOMETRY_CLUSTER | LONG_TAIL,
            EOFEN | GATE,
            frozenset(),
        ),
        (
            "(+ patches — excluded by #456)",
            NETWORK_CLUSTER | GEOMETRY_CLUSTER | LONG_TAIL | PATCH_CLUSTER,
            EOFEN | GATE,
            frozenset(),
        ),
    ]
    print("\n== serve ladder ==")
    for label, wr, ws, ps in ladder:
        c = Counter(classify(r, s, frozenset(wr), ws, ps) for _, r, s in decks)
        print(
            f"  {label:36s} serve {c['serve']:3d} ({100 * c['serve'] / n:5.1f}%)"
            f"  refuse {c['refuse']:3d}  silent {c['silent']:3d}"
        )

    print("\n== refusal reasons today (models, non-exclusive) ==")
    reasons = Counter()
    for _, r, s in decks:
        for x in r if r else set():
            reasons[x] += 1
    for k, v in reasons.most_common():
        print(f"  {k:20s} {v}")

    print("\n== silent reasons today (otherwise-clean decks) ==")
    sil = Counter()
    for _, r, s in decks:
        if not r:
            for x in s:
                sil[x] += 1
    for k, v in sil.most_common():
        print(f"  {k:20s} {v}")

    for title, counter in (
        ("emitted-dialect cards", emit_cards),
        ("emitted variants", emit_variants),
        ("source-dialect cards", src_cards),
        ("source variants", src_variants),
    ):
        print(f"\n== {title} (models) ==")
        for k, v in sorted(counter.items(), key=lambda kv: (-kv[1], kv[0])):
            print(f"  {k:12s} {v}")

    if args.json:
        args.json.write_text(
            json.dumps(
                {
                    "models": n,
                    "src_cards": dict(src_cards),
                    "emit_cards": dict(emit_cards),
                    "src_variants": dict(src_variants),
                    "emit_variants": dict(emit_variants),
                    "decks": [
                        {"path": p, "refuse": sorted(r), "silent": sorted(s)}
                        for p, r, s in decks
                    ],
                },
                indent=1,
            )
        )
        print(f"\nwrote {args.json}")


if __name__ == "__main__":
    main()
