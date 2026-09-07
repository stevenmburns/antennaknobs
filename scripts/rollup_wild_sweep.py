"""Roll up a `bench_nec_corpus.py` wild-corpus sweep, in the 07-17 doc's shape.

The sweep writes one JSON row per deck; this turns a run into the tables
`docs/status/2026-07-17-wild-corpus-solve-sweep.md` carries, so two runs can be
read side by side rather than described. It also diffs two runs per deck when a
baseline is given (AK#1234 step 3).

    python scripts/rollup_wild_sweep.py bench_out/wild-solve-2026-09-07.jsonl
    python scripts/rollup_wild_sweep.py NEW.jsonl --baseline OLD.jsonl

CLEAN FLAGS are the doc's: supported ground, full network, no virtualized
anchors. They are not a quality filter -- a deck with an unsupported ground
still solves, its number just is not apples-to-apples against nec2c, and
reporting it inside the agreement median would flatter or blame the engine for
a ground neither side modelled.
"""

from __future__ import annotations

import argparse
import collections
import json
import math
from pathlib import Path

ENGINES = ("pynec", "sin", "bs1", "bs2", "nec5")
LABEL = {
    "pynec": "PyNEC",
    "sin": "Sinusoidal",
    "bs1": "BSpline d=1",
    "bs2": "BSpline d=2",
    "nec5": "NEC-5",
}


def load(path):
    meta, rows = None, []
    with open(path) as fh:
        for line in fh:
            line = line.strip()
            if not line:
                continue
            r = json.loads(line)
            if "_meta" in r:
                meta = r["_meta"]
            else:
                rows.append(r)
    return meta, rows


def gamma(z, z0=50.0):
    zc = complex(*z) if isinstance(z, (list, tuple)) else complex(z)
    return (zc - z0) / (zc + z0)


def dgamma(z_eng, z_ref):
    try:
        return abs(gamma(z_eng) - gamma(z_ref))
    except (TypeError, ZeroDivisionError):
        return None


def first_z(entry, key="z"):
    zs = (entry or {}).get(key)
    if not zs:
        return None
    return zs[0]


def is_clean(r):
    return (
        bool(r.get("ground_supported"))
        and not r.get("partial_net")
        and not r.get("virtualized_anchors")
    )


# A DECLARED refusal is a sentence saying what is out of scope and, usually,
# what to do instead. The bench's OOS bucket was written for NEC-5's dialect
# refusals, but momwire's are the same kind of thing and belong there too --
# otherwise 07-17 shows zero momwire OOS and today shows a jump in ERR that
# reads as breakage when it is a capability being declared.
#
# Keyed on the SENTENCE because the row carries only a string: the engines
# raise ValueError and NotImplementedError for both declared refusals and real
# faults, so the exception class cannot separate them. Said here rather than
# left implicit, because a marker list is a maintenance burden and the next
# refusal sentence has to be added to it.
_DECLARED = (
    "notimplementederror",
    "cannot",
    "does not serve",
    "is outside momwire",
    "outside momwire",
    "no buried fill",
    "not supported",
    "refuse",
    "out of scope",
    "has no ",
    "grazing floor",
    "below/below",
)


def is_bare_exception(err):
    """True when the message is a class name with no sentence behind it.

    #1235's rule, applied here too: a refusal that arrives as a bare class
    name tells a user nothing and is an issue to file, not a taxonomy row.
    """
    e = str(err).strip()
    if ":" not in e:
        return len(e.split()) <= 2 and e.endswith("Error")
    head, _, tail = e.partition(":")
    return head.strip().endswith("Error") and len(tail.split()) <= 2


def classify(err):
    """The doc's taxonomy, from an engine's error string."""
    if err is None:
        return "ok"
    e = str(err)
    low = e.lower()
    # Resource bounds first: they can carry any wording.
    if "memoryerror" in low or "mem-limit" in low or "memory" in low:
        return "MEM"
    if "timeout" in low or "timeoutexpired" in e:
        return "TIME"
    # Then declared refusals, BEFORE the geometry heuristic -- momwire's
    # buried refusal contains the word "geometry" and would otherwise be
    # filed as a data error.
    if any(m in low for m in _DECLARED):
        return "OOS"
    if "geometry data error" in low or "segment" in low or "geometry" in low:
        return "GEO"
    return "ERR"


def pct(n, d):
    return f"{100.0 * n / d:.0f}%" if d else "—"


def quantile(xs, q):
    # Non-finite values must never reach sorted(): NaN compares False against
    # everything, which leaves the list in an arbitrary order and makes every
    # quantile meaningless rather than merely noisy. Measured on the 09-07
    # sweep, five NaNs among 2765 scores moved BSpline d=1's reported median
    # from 0.0324 to 0.6248 and printed a p90 BELOW the median -- the only
    # reason the corruption was visible at all. Callers report the dropped
    # count separately; see the open-port section.
    s = sorted(x for x in xs if math.isfinite(x))
    if not s:
        return float("nan")
    i = min(len(s) - 1, max(0, int(math.ceil(q * len(s))) - 1))
    return s[i]


def deck_scores(rows):
    """{deck: {engine: dGamma}} over rows that have a nec2c reference."""
    out = {}
    for r in rows:
        ref = first_z(r.get("nec2c"))
        if ref is None or (r.get("nec2c") or {}).get("error"):
            continue
        per = {}
        for e in ENGINES:
            ent = (r.get("engines") or {}).get(e)
            if not ent or ent.get("error"):
                continue
            z = first_z(ent) or first_z(ent, "nec5_z_doubled")
            if z is None:
                continue
            d = dgamma(z, ref)
            if d is not None:
                per[e] = d
        if per:
            out[r["deck"]] = per
    return out


def open_ports(rows):
    """{deck: ([engine], ref_z)} where an engine returned a non-finite Z.

    A non-finite impedance means the port saw no current -- an open circuit.
    The engine raised nothing, so the deck lands in the scored population and
    its NaN score silently poisons any sort it reaches.
    """
    out = {}
    for r in rows:
        ref = first_z(r.get("nec2c"))
        if ref is None or (r.get("nec2c") or {}).get("error"):
            continue
        hit = []
        for e in ENGINES:
            ent = (r.get("engines") or {}).get(e)
            if not ent or ent.get("error"):
                continue
            z = first_z(ent) or first_z(ent, "nec5_z_doubled")
            if z is None:
                continue
            d = dgamma(z, ref)
            if d is not None and not math.isfinite(d):
                hit.append(e)
        if hit:
            out[r["deck"]] = (hit, ref)
    return out


def deck_z(rows):
    """{deck: {engine: complex Z}} -- the engine's own answer, no reference.

    The ΔΓ-vs-nec2c movers cannot separate "the engine changed" from "the
    reference or the import changed", because the reference is on both sides
    of that subtraction. Comparing an engine against ITSELF between runs can:
    if every engine on a deck moves together the cause is upstream of all of
    them, and if one moves alone it is that engine.
    """
    out = {}
    for r in rows:
        per = {}
        for e in ENGINES:
            ent = (r.get("engines") or {}).get(e)
            if not ent or ent.get("error"):
                continue
            z = first_z(ent) or first_z(ent, "nec5_z_doubled")
            if z is not None:
                per[e] = complex(*z)
        if per:
            out[r["deck"]] = per
    return out


def self_movers(old_rows, new_rows, move):
    """Per-deck ΔΓ(engine now, engine then), grouped so the cause is readable."""
    o, n = deck_z(old_rows), deck_z(new_rows)
    rows = []
    for deck, per in n.items():
        if deck not in o:
            continue
        moved = {}
        for e, z in per.items():
            if e not in o[deck]:
                continue
            try:
                d = abs(
                    gamma([z.real, z.imag]) - gamma([o[deck][e].real, o[deck][e].imag])
                )
            except ZeroDivisionError:
                continue
            if d > move:
                moved[e] = d
        if moved:
            shared = [e for e in ENGINES if e in per and e in o[deck]]
            rows.append((max(moved.values()), deck, moved, len(shared)))
    rows.sort(reverse=True)
    return rows


def census(rows):
    parse_rejected = sum(1 for r in rows if r.get("error"))
    no_ref = sum(
        1
        for r in rows
        if not r.get("error")
        and (first_z(r.get("nec2c")) is None or (r.get("nec2c") or {}).get("error"))
    )
    scored = len(rows) - parse_rejected - no_ref
    return parse_rejected, no_ref, scored


def report(meta, rows, baseline=None, move=0.02):
    print("## Meta\n")
    for k in ("corpus", "engines", "timeout_s", "mem_limit_gb", "started"):
        if meta and k in meta:
            print(f"- {k}: `{meta[k]}`")
    if meta and "nec2c" in meta:
        n = meta["nec2c"]
        print(f"- nec2c: `{n.get('version')}` md5 `{n.get('md5')}`")
    print(f"- rows: **{len(rows)}**\n")

    pr, nr, sc = census(rows)
    print("## Headline census\n")
    print("| outcome | decks |")
    print("|---|--:|")
    print(f"| scored vs nec2c | **{sc}** |")
    print(f"| parse-rejected | {pr} |")
    print(f"| parsed, no nec2c reference | {nr} |\n")

    print("## Per-engine outcome taxonomy\n")
    print("| engine | ok | OOS | MEM | TIME | GEO | ERR |")
    print("|---|--:|--:|--:|--:|--:|--:|")
    for e in ENGINES:
        c = collections.Counter(
            classify(((r.get("engines") or {}).get(e) or {}).get("error"))
            for r in rows
            if (r.get("engines") or {}).get(e) is not None
        )
        print(
            f"| {LABEL[e]} | {c['ok']} | {c['OOS']} | {c['MEM']} | "
            f"{c['TIME']} | {c['GEO']} | {c['ERR']} |"
        )
    print()

    # Every distinct refusal sentence, so the taxonomy can be audited rather
    # than trusted, and so a BARE exception gets named for an issue.
    bare = []
    print("### Distinct refusal sentences\n")
    for e in ENGINES:
        seen = collections.Counter()
        for r in rows:
            err = ((r.get("engines") or {}).get(e) or {}).get("error")
            if err:
                seen[str(err)[:150]] += 1
                if is_bare_exception(err):
                    bare.append((e, str(err)[:80]))
        if not seen:
            continue
        print(f"**{LABEL[e]}**\n")
        for msg, n in seen.most_common(6):
            print(f"- `{classify(msg)}` ×{n} — {msg}")
        print()
    if bare:
        print("### BARE exceptions (file an issue for each)\n")
        for e, msg in collections.Counter(bare).most_common(10):
            print(f"- {LABEL[e[0]]}: `{e[1]}`")
        print()
    else:
        print("No bare exceptions: every refusal carried a sentence.\n")

    openp = open_ports(rows)
    if openp:
        print("### Open-circuit ports (reported as success, not refused)\n")
        print("An engine returned a non-finite impedance with no error raised,")
        print("so the deck counts as solved while carrying no usable number.\n")
        print("| deck | engines | reference Z |")
        print("|---|---|---|")
        for deck, (engs, ref) in sorted(openp.items()):
            names = ", ".join(LABEL[e] for e in engs)
            print(f"| `{deck}` | {names} | {ref[0]:g}{ref[1]:+g}j |")
        print()

    for name, keep in (("all scored", lambda r: True), ("clean", is_clean)):
        sel = [r for r in rows if keep(r)]
        sco = deck_scores(sel)
        print(f"## Agreement rollup ({name})\n")
        print("| engine | n | median | p90 | ≤0.01 | ≤0.05 | ≤0.2 | open |")
        print("|---|--:|--:|--:|--:|--:|--:|--:|")
        for e in ENGINES:
            raw = [v[e] for v in sco.values() if e in v]
            xs = [x for x in raw if math.isfinite(x)]
            n_open = len(raw) - len(xs)
            if not xs:
                print(f"| {LABEL[e]} | 0 | — | — | — | — | — | {n_open} |")
                continue
            med, p90 = quantile(xs, 0.5), quantile(xs, 0.9)
            # A p90 below the median is arithmetically impossible from a sorted
            # list, so it is a live check that nothing non-finite reached the
            # sort. This is how the 09-07 NaN corruption was caught; keep it.
            assert p90 >= med, f"{e}: p90 {p90} < median {med} -- unsorted input"
            print(
                f"| {LABEL[e]} | {len(xs)} | **{med:.4f}** | "
                f"{p90:.4f} | "
                f"{pct(sum(x <= 0.01 for x in xs), len(xs))} | "
                f"{pct(sum(x <= 0.05 for x in xs), len(xs))} | "
                f"{pct(sum(x <= 0.2 for x in xs), len(xs))} | {n_open} |"
            )
        print()

    print("## Cost\n")
    print("| engine | solves | total solve s | median s | p90 s | max peak RSS MB |")
    print("|---|--:|--:|--:|--:|--:|")
    for e in ENGINES:
        ts, rss = [], []
        for r in rows:
            ent = (r.get("engines") or {}).get(e) or {}
            if ent.get("solve_s") is not None:
                ts.append(float(ent["solve_s"]))
            if ent.get("peak_rss_mb") is not None:
                rss.append(float(ent["peak_rss_mb"]))
        if not ts:
            print(f"| {LABEL[e]} | 0 | — | — | — | — |")
            continue
        print(
            f"| {LABEL[e]} | {len(ts)} | {sum(ts):.1f} | {quantile(ts, 0.5):.4f} | "
            f"{quantile(ts, 0.9):.3f} | {max(rss) if rss else float('nan'):.0f} |"
        )
    print()

    if baseline is None:
        return
    _bm, brows = load(baseline)
    old, new = deck_scores(brows), deck_scores(rows)
    movers = []
    for deck, per in new.items():
        if deck not in old:
            continue
        for e, d in per.items():
            if e in old[deck] and abs(d - old[deck][e]) > move:
                movers.append((abs(d - old[deck][e]), e, deck, old[deck][e], d))
    movers.sort(reverse=True)
    print(f"## Movers (|ΔΓ| moved by more than {move}) — {len(movers)}\n")
    by_eng = collections.Counter(m[1] for m in movers)
    print("| engine | movers |")
    print("|---|--:|")
    for e in ENGINES:
        print(f"| {LABEL[e]} | {by_eng[e]} |")
    print("\n### The largest\n")
    print("| move | engine | deck | was | now |")
    print("|--:|---|---|--:|--:|")
    for mv, e, deck, was, now in movers[:20]:
        print(f"| {mv:.3f} | {LABEL[e]} | `{deck}` | {was:.4f} | {now:.4f} |")
    print()

    # The engine-against-itself view: which movers are the ENGINE, and which
    # are the reference or the import moving underneath all of them.
    sm = self_movers(brows, rows, move)
    together = [r for r in sm if len(r[2]) == r[3] and r[3] > 1]
    alone = [r for r in sm if len(r[2]) == 1]
    print(f"## Engine-vs-itself movers (ΔΓ between runs > {move}) — {len(sm)}\n")
    print(
        f"- **all engines on the deck moved together: {len(together)}** — the "
        "reference, the import or the deck's own translation changed; not an "
        "engine change"
    )
    print(f"- **exactly one engine moved: {len(alone)}** — that engine\n")
    if alone:
        print("### One engine alone, largest first\n")
        print("| move | engine | deck |")
        print("|--:|---|---|")
        for mv, deck, moved, _n in alone[:20]:
            e = next(iter(moved))
            print(f"| {mv:.3f} | {LABEL[e]} | `{deck}` |")
        print()


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("jsonl", type=Path)
    ap.add_argument("--baseline", type=Path, default=None)
    ap.add_argument("--move", type=float, default=0.02)
    a = ap.parse_args()
    meta, rows = load(a.jsonl)
    report(meta, rows, a.baseline, a.move)


if __name__ == "__main__":
    main()
