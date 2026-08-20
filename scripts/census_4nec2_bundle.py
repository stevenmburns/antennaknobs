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
  - EX 6 (current source) arrives as EX 0 + NT + a phantom 1-segment wire,
    and the three manufactured cards are emitted GROUPED, not in place:
    the phantom GW at the end of the geometry section, the EX 0 at the
    EX 6's own site, and the NT block immediately before the execute card
    (capture 0036, `out__QFH1280.inp`, whose source writes EX 6 before FR
    and whose emitted deck writes NT after it)

Each emitted deck is then scored against momwire's nec2 dialect refusal
tables (deck-grammar-nec2.md):

  serve   — every statement runs
  refuse  — at least one statement hits a loud, named (or unrecognised-card)
            refusal; parse() raises, so this preempts any silent risk
  silent  — the deck parses but means something the frontend didn't; the
            zero-tolerance column, and empty as of the re-baseline below

**"today" tracks the submodule's live dialect, re-baselined 2026-08-20**
after momwire#456 workstream 2's MININEC-ground arc (momwire#487) landed on
momwire main. Four waves have moved since the 2026-08-19 matrix was first
written, and all four are IN the "today" rung now:

  - the hygiene wave — EOF is read as EN, SC refuses by name, and PQ is a
    by-VALUE gate (PQ -1 suppresses and serves; PQ >= 0 requests a report
    and refuses)
  - GX/GR structure symmetry (momwire#415), served since then
  - TL/NT (momwire#482, phase C), served with the by-value guards this
    script models below
  - the MININEC-type ground idiom (momwire#487) — GD with GN 1 SERVES
    letter-faithfully to NEC-2 (perfect-ground physics under RP 0 or a
    request-less execute, the second medium behind RP 2/3), so the
    hygiene wave's idiom gate is gone from this script the way it is gone
    from the dialect (decision record: momwire
    docs/design/mininec-ground-idiom.md)

The by-NAME half of the scoring is therefore no longer written out here.
It is READ from the live table, `momwire.deck._nec2._REFUSED_BY_NAME`,
because a hand-embedded copy went stale twice in three weeks — it still
listed GX/GR long after #415 served them, and TL/NT after phase C did.
Importing a private name across the repo boundary is acceptable here and
only here: this is a dev-side measurement script, not shipped code, it runs
against the submodule checkout in the same working tree, and it has no
runtime contract to keep. It fails LOUDLY if momwire renames the table —
ImportError at module import, before a single number is printed — which is
the whole point: a census that cannot read the live table must not print a
stale one instead. The same argument covers the four card-set imports below.

What CANNOT come from the live table, and is modelled by hand here, is the
by-VALUE half — a card that refuses on the strength of its fields. Each gate
is audited against deck-grammar-nec2.md at re-baseline time; see `score`.

The manufactured `NT` block's placement, once this census's one modelled
prediction, is now OBSERVED (capture 0041, `out__Coax.inp`, merged in
antennaknobs#963): 4nec2 emits it immediately before the deck's first
hand-written network card — adjacent, no destroy pattern — falling back to
the execute card only when the deck has no network cards of its own
(capture 0036, `out__QFH1280.inp`).  The old at-the-execute-card model
invented destroy patterns 4nec2 never emits; `emit` now implements the
observed rule, and the former sensitivity line is retired.

Statically undecidable refusals (LD ranges over 8 segments, doubled loads,
partial-wire LD 5, and the momwire#415 out-of-cell LD drop that costs
`1MHz_tower`) are not modelled; symbolic fields that resolve at emit time
are skipped where a value is needed (e.g. the GN 0 contact check).

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

from momwire.deck._nec2 import (
    _EXECUTE_CARDS,
    _GEOMETRY_CARDS,
    _NETWORK_CARDS,
    _NETWORK_TRANSPARENT,
    _REFUSED_BY_NAME,
    _TERMINATORS,
)

DEFAULT_ROOT = Path.home() / "antennas/nec-wild/opensource/4nec2"

# The live by-name refusal table, read rather than copied (see module docstring).
REFUSE_BY_NAME = frozenset(_REFUSED_BY_NAME)

# The cards momwire's reader DISPATCHES.  Everything importable is imported;
# what remains is the list of singleton handlers in `Nec2Reader.card`, which
# has no published set to read.  Its only use is computing the generic
# "unrecognised NEC card" refusal, which the census REPORTS rather than
# asserts on: a mnemonic that lands here is either a bundle card momwire has
# never seen or a handler momwire has dropped, and both want a human.
RECOGNISED = (
    REFUSE_BY_NAME
    | frozenset(_GEOMETRY_CARDS)
    | frozenset(_EXECUTE_CARDS)
    | frozenset(_NETWORK_CARDS)
    | frozenset(_TERMINATORS)
    | frozenset(
        {"CM", "CE", "GN", "GD", "FR", "EX", "LD", "IS", "EK", "PT", "PQ", "MP"}
    )
)

# Cards a network card may be read across without NEC destroying the earlier
# network list — also read from the live table rather than copied.
NETWORK_TRANSPARENT = frozenset(_NETWORK_TRANSPARENT) | {"CM", "CE"}

# The remaining geometry work: GX/GR are served (momwire#415), these are not.
GEOMETRY_CLUSTER = {"GA", "GH", "GC"}
PATCH_CLUSTER = {"SP", "SM", "SC"}
LONG_TAIL = {
    "PQ>=0",
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
# Refused by DESIGN, and still refused at the bottom of the ladder: each is a
# place where NEC-2 itself is wrong or silent and the dialect says so out loud.
BY_DESIGN = {"GN0-contact", "net-contiguity", "no-EX"}


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
    """Apply 4nec2's pre-engine resolutions; return the emitted card list.

    The `EX 6` translation manufactures three cards, and WHERE each lands is
    load-bearing now that TL/NT serve: the network-contiguity rule reads the
    emitted card ORDER, so an inline expansion (all three at the EX 6's own
    site) would invent destroy patterns that 4nec2 never emits.  The grouping
    below is the captured one, from BOTH placements now observed.  Capture
    0036 (`out__QFH1280.inp`, no hand-written network cards): phantom `GW`
    cards at the end of the geometry section, `EX 0` where the source wrote
    `EX 6`, and the `NT` block after `FR`, immediately before the injected
    `XQ`.  Capture 0041 (`out__Coax.inp`, a hand-written `TL`): the `NT`
    block sits at the HEAD of the network section, immediately before the
    hand-written `TL`, with `EX`/`GN`/`FR` after the network block — and the
    engine's own printout solves the network, so nothing between a network
    block and the execute card destroys it.  One rule covers both: the
    manufactured `NT` block lands immediately before the deck's first
    hand-written network card, or before the execute card when there is none.
    """
    phantom_gw, phantom_nt, body = [], [], []
    for mn, f in cards:
        if mn == "SY":
            continue
        if mn == "LD":
            t = field_int(f, 0)
            if t == 6:
                body.append(("LD", ["1"] + f[1:]))
                continue
            # LD 7's translation is unsampled; assume it reaches the engine.
        if mn == "GN" and field_int(f, 0) == 3:
            body.append(("GN", ["1"]))
            body.append(("GD", ["0", "0", "0", "0"] + f[4:6]))
            continue
        if mn == "EX" and field_int(f, 0) == 6:
            # Phantom 1-segment wire parked at z = its own tag, verbatim from
            # the capture (docs/status/2026-08-18-4nec2-subengine-capture.md);
            # momwire's `dipole_ex6_gyrator` fixture pins the same bytes, so
            # this models the deck that fixture answers.
            tag = str(9901 + len(phantom_gw))
            phantom_gw.append(
                (
                    "GW",
                    [tag, "1", "-1.1945e-4", "0", tag,
                     "1.19452e-4", "0", tag, "5.97258e-6"],
                )
            )  # fmt: skip
            phantom_nt.append(("NT", [tag, "1"] + f[1:3] + ["0", "0", "0", "1"]))
            body.append(("EX", ["0", tag, "1", "0", "0", "1"]))
            continue
        body.append((mn, f))
    if not phantom_gw:
        return body
    out, placed_gw, placed_nt = [], False, False
    for mn, f in body:
        if mn == "GE" and not placed_gw:
            out.extend(phantom_gw)
            placed_gw = True
        if (mn in _NETWORK_CARDS or mn in _EXECUTE_CARDS) and not placed_nt:
            out.extend(phantom_nt)
            placed_nt = True
        out.append((mn, f))
    # A deck with no GE gets its phantom geometry first; a deck whose execute
    # cards are all injected at run time gets its NT block at the tail, which
    # is where 4nec2 puts the injected XQ.
    if not placed_gw:
        out = phantom_gw + out
    if not placed_nt:
        out = _before_terminator(out, phantom_nt)
    return out


def _before_terminator(out, extra):
    """Insert `extra` ahead of the deck's first EN/NX, or at the tail."""
    for i, (mn, _) in enumerate(out):
        if mn in _TERMINATORS:
            return out[:i] + extra + out[i:]
    return out + extra


def score(emitted):
    """Return (refusal reasons, silent reasons) for one emitted deck.

    The by-VALUE gates, each audited against deck-grammar-nec2.md at the
    2026-08-19 re-baseline:

      EX          `_ex`: every type but 0 refuses
      RP          `_RP_MODES`: modes 0, 2, 3 only
      GN type     `_gn`: -1, 0, 1, 2 only
      GN + NRADL  `_gn`: a radial screen refuses on the two reflection-
                  coefficient types (0 and 2) and NOT on PEC or free space
      GN 0 contact  solver-level, `_ground_spec`: a GN 0 deck whose geometry
                  reaches z = 0; refused by design (momwire#282)
      LD type     `_ld`: -1, 0, 1, 4, 5 only — so 2, 3, 6 and 7 all refuse,
                  and the census sees 6 only as the LD 1 4nec2 emits for it
      NE/NH       `_near_field`: spherical refuses; so does a finite ground
                  (GN 0 or GN 2), because a Sommerfeld near field is no image
      PQ          `_pq`, since the hygiene wave: PQ -1 SUPPRESSES the charge
                  report and serves; PQ >= 0 REQUESTS one and refuses.  Was a
                  by-name refusal in the pre-re-baseline census
      NT/TL seg   `_network`: an endpoint segment below 1 refuses (NEC halts)
      TL Z0       `_network`: a zero (or absent) characteristic impedance
                  refuses (NEC aborts while reading)
      contiguity  `_network`: a network card with a non-transparent card
                  between it and an earlier one refuses, because NEC silently
                  DESTROYS every network card read before it
      no EX       `parse_nec2`: a deck that drives nothing refuses

    Zero bundle decks trip the nonpositive-segment or zero-Z0 guards, which
    matches phase C's own corpus scan.  The contiguity guard is the one that
    bites, and only through the manufactured `NT` — see `emit`.
    """
    refuse, silent = set(), set()
    mns = {m for m, _ in emitted}
    has_gn0 = has_gn1 = has_gn2 = touches_z0 = False
    saw_network = False
    destroyer = None
    for mn, f in emitted:
        if mn in _TERMINATORS:
            break
        if mn in REFUSE_BY_NAME:
            refuse.add(mn)
        elif mn not in RECOGNISED:
            refuse.add(f"unrecognised-{mn}")
        if mn in _NETWORK_CARDS:
            if destroyer is not None:
                refuse.add("net-contiguity")
            saw_network = True
            for idx in (1, 3):
                seg = field_int(f, idx)
                if seg is not None and seg < 1:
                    refuse.add("net-nonpositive-segment")
            if mn == "TL" and (len(f) <= 4 or num(f[4]) == 0.0):
                refuse.add("TL-zero-Z0")
        elif saw_network and destroyer is None and mn not in NETWORK_TRANSPARENT:
            destroyer = mn
        if mn == "EX":
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
            has_gn2 |= t == 2
        elif mn == "LD":
            t = field_int(f, 0)
            if t is not None and t not in (-1, 0, 1, 4, 5):
                refuse.add(f"LD{t}")
        elif mn == "PQ":
            flag = field_int(f, 0)
            if flag is not None and flag >= 0:
                refuse.add("PQ>=0")
        elif mn in ("NE", "NH"):
            if field_int(f, 0) not in (0, None):
                refuse.add(f"{mn}-spherical")
        elif mn == "GW":
            z1 = num(f[4]) if len(f) > 4 else None
            z2 = num(f[7]) if len(f) > 7 else None
            touches_z0 |= z1 == 0.0 or z2 == 0.0
    if has_gn0 and touches_z0:
        refuse.add("GN0-contact")
    if (has_gn0 or has_gn2) and ("NE" in mns or "NH" in mns):
        refuse.add("NE/NH-finite-ground")
    if "EX" not in mns:
        refuse.add("no-EX")
    return refuse, silent


def classify(refuse, silent, waived_refuse=frozenset()):
    """Waived reasons are served — that is what a ladder rung buys."""
    if refuse - waived_refuse:
        return "refuse"
    return "silent" if silent else "serve"


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

    # Each rung waives only work NOT YET DONE.  The hygiene, GX/GR, NT/TL and
    # MININEC-ground rungs of earlier ladders are gone because they have
    # landed: they are inside "today" now.
    GEOM = frozenset(GEOMETRY_CLUSTER)
    TAIL = frozenset(LONG_TAIL)
    ladder = [
        ("today (live dialect)", frozenset()),
        ("+ remaining geometry (GA/GH/GC)", GEOM),
        ("+ long tail", GEOM | TAIL),
        (
            "(+ patches — excluded by #456)",
            GEOM | TAIL | frozenset(PATCH_CLUSTER),
        ),
    ]
    print("\n== serve ladder ==")
    for label, waived in ladder:
        c = Counter(classify(r, s, waived) for _, r, s in decks)
        assert c["serve"] + c["refuse"] + c["silent"] == n, label
        print(
            f"  {label:36s} serve {c['serve']:3d} ({100 * c['serve'] / n:5.1f}%)"
            f"  refuse {c['refuse']:3d}  silent {c['silent']:3d}"
        )
    bottom = Counter()
    for _, r, s in decks:
        rest = r - (GEOM | TAIL | frozenset(PATCH_CLUSTER))
        if rest:
            for x in rest:
                bottom[x] += 1
    print("\n== refused by design at the bottom of the ladder ==")
    for k, v in bottom.most_common():
        print(f"  {k:24s} {v}{'' if k in BY_DESIGN else '   <- NOT on a ladder rung'}")

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
