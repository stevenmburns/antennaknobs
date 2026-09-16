"""Read `records.jsonl` and write README.md and COMMENT.md. No number transcribed.

    python scratch/1543-bspline-served-density/report.py

ONE RUNG PER DEGREE, SO THERE IS NO CLASS COLUMN. The #1525 ladder could classify
a row converging or not because it had four rungs; this has one. The only
classification available is ADMISSIBILITY -- whether the reference is settled
enough under #845's one-third rule for the row to count -- and the layout below
deliberately does not put admissibility where a reader expects a class, because a
column headed like a class would be read as one.

The metric is the ladder's, unchanged: `|dZ|` over all ports as a vector, relative
to `|Z_ref|`, reference bs2@160 from `scratch/1525-razor-density/records.jsonl`.
"""

from __future__ import annotations

import json
import math
import statistics
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
LADDER = HERE.parent / "1525-razor-density" / "records.jsonl"
SERVED = {"bs2": 15, "bs1": 20, "bs3": 12}
DEGREE_LABEL = {"bs1": "B-spline d=1", "bs2": "B-spline d=2", "bs3": "B-spline d=3"}
GROUNDS = ("free", "somm")
GROUND_LABEL = {"free": "free space", "somm": "Sommerfeld"}
REF_RUNG, PREV_RUNG = 160, 80
RAZOR40_MEDIAN = None  # computed from the ladder, never typed


def load(path):
    recs, prov = {}, None
    for line in open(path, encoding="utf-8"):
        r = json.loads(line)
        if "design" not in r:
            prov = r
            continue
        recs[(r["design"], r["ground"], r["rung"], r["engine"])] = r
    return recs, prov


def zv(r):
    return [complex(*p) for p in r["z"]] if r and r.get("z") else None


def dz(a, b):
    if a is None or b is None or len(a) != len(b):
        return None, None
    n = math.sqrt(sum(abs(x - y) ** 2 for x, y in zip(a, b, strict=True)))
    d = math.sqrt(sum(abs(y) ** 2 for y in b))
    return n, (n / d if d else None)


def pct(x):
    return "—" if x is None else f"{100 * x:.3g} %"


def q(v, p):
    s = sorted(v)
    return s[min(len(s) - 1, int(p * len(s)))] if s else None


def main():
    recs, prov = load(HERE / "records.jsonl")
    lad, _ = load(LADDER)
    designs = sorted({k[0] for k in recs})

    # razor-2p at 40 from the ladder, for the one comparison the brief asks for.
    # razor-2p at 40 under the SAME admissibility rule as the bspline rows.
    # AK#1525 quotes 2.42 %, which is a median over its CONVERGING rows -- a
    # different population from "admissible under the one-third rule". Comparing
    # the two directly would mix populations, so both are computed here and the
    # page says which is which.
    rz, rz_all = [], []
    for d in designs:
        for g in GROUNDS:
            ref = lad.get((d, g, REF_RUNG, "bs2"))
            prev = lad.get((d, g, PREV_RUNG, "bs2"))
            c = lad.get((d, g, 40, "razor"))
            if not ref or not c or ref["status"] != "ok" or c["status"] != "ok":
                continue
            ohm, r = dz(zv(c), zv(ref))
            if r is None:
                continue
            rz_all.append(r)
            move, _ = (
                dz(zv(prev), zv(ref))
                if prev and prev["status"] == "ok"
                else (None, None)
            )
            if ohm > 0 and move is not None and move > ohm / 3.0:
                continue
            rz.append(r)
    razor40 = statistics.median(rz) if rz else None
    razor40_all = statistics.median(rz_all) if rz_all else None

    per = {}
    for e, rung in SERVED.items():
        adm, unres, other = [], [], []
        for d in designs:
            for g in GROUNDS:
                ref = lad.get((d, g, REF_RUNG, "bs2"))
                prev = lad.get((d, g, PREV_RUNG, "bs2"))
                c = recs.get((d, g, rung, e))
                if c is None or c["status"] != "ok":
                    other.append((d, g, c["status"] if c else "missing"))
                    continue
                if (
                    not ref
                    or not prev
                    or ref["status"] != "ok"
                    or prev["status"] != "ok"
                ):
                    other.append((d, g, "no reference"))
                    continue
                ohm, rel = dz(zv(c), zv(ref))
                move, _ = dz(zv(prev), zv(ref))
                if rel is None or ohm is None:
                    other.append((d, g, "not comparable"))
                elif ohm > 0 and move is not None and move > ohm / 3.0:
                    unres.append((d, g, ohm, move))
                else:
                    adm.append((d, g, ohm, rel))
        per[e] = {"adm": adm, "unres": unres, "other": other}

    out = []
    w = out.append
    w("# AK#1543 — the bspline family at the densities #1547 serves\n")
    w(
        f"**Builds.** antennaknobs main `{prov['ak_sha'][:9]}` "
        f"(v{prov['version_antennaknobs']}); momwire `{prov['momwire_sha'][:9]}` "
        f"(`{prov['momwire_describe']}`, v{prov['version_momwire']}), detached at "
        f"the briefed commit and rebuilt; accelerator "
        f"`{prov['accelerator_variant']['_accelerators'].split('.')[0]}`. "
        f"**Reference: bs2@160 from the AK#1525 ladder**, re-validated on this "
        f"build before use — 32 cells across 7 designs × 2 grounds spanning "
        f"buried, Sommerfeld, multi-port, network and the largest catalog design "
        f"are bit-identical to the stored records. Provenance is the first line "
        f"of `records.jsonl`.\n"
    )
    w(
        "**Metric.** `|ΔZ|` over all ports as a vector; the percentage is that "
        "over `|Z_ref|`. Identical to the AK#1525 ladder's, so these rows and "
        "razor-2p's sit on one footing.\n"
    )
    w(
        "> **One rung per degree, so there is no convergence class and no fitted "
        "order here.** The AK#1525 ladder classified rows because it had four "
        "rungs; this has one. The only classification available is "
        "**admissibility** — whether bs2's own ×80→×160 move stayed under a third "
        "of the error being judged, so the reference can arbitrate the row at all. "
        "A row that is not admissible is *unresolved*, not *failing*.\n"
    )

    w("## Error at the served density\n")
    w("| basis | served N | admissible rows | median | p90 | worst |")
    w("|---|---:|---:|---:|---:|---:|")
    for e in ("bs1", "bs2", "bs3"):
        rels = [a[3] for a in per[e]["adm"]]
        w(
            f"| {DEGREE_LABEL[e]} | {SERVED[e]} | {len(rels)} | "
            f"{pct(statistics.median(rels) if rels else None)} | "
            f"{pct(q(rels, 0.90))} | {pct(q(rels, 1.0))} |"
        )
    w("")
    w(
        f"For comparison, on the same metric, the same reference **and the same "
        f"admissibility rule**, **razor-2p at its served 40** measures a median "
        f"**{pct(razor40)}** over {len(rz)} admissible rows. AK#1525 quotes "
        f"**2.42 %** for razor-2p at 40; that is a median over its *converging* "
        f"rows, a different population, and over all {len(rz_all)} comparable "
        f"rows it is {pct(razor40_all)}. The {pct(razor40)} above is the only one "
        f"of the three that is like-for-like with this table.\n"
    )

    w("## Rows the reference cannot arbitrate\n")
    w("| basis | admissible | unresolved (one-third rule) | not solved |")
    w("|---|---:|---:|---:|")
    for e in ("bs1", "bs2", "bs3"):
        p = per[e]
        w(
            f"| {DEGREE_LABEL[e]} | {len(p['adm'])} | {len(p['unres'])} | "
            f"{len(p['other'])} |"
        )
    w("")
    w(
        "Unresolved means bs2 itself had not settled between ×80 and ×160 on that "
        "design by more than a third of the error being judged. It is a statement "
        "about the reference, not about the basis under test.\n"
    )

    w("## Cost at the served density\n")
    w(
        "| basis | served N | catalog cold total | median cold | worst single | worst peak RSS |"
    )
    w("|---|---:|---:|---:|---:|---:|")
    for e in ("bs1", "bs2", "bs3"):
        cold = [
            c["cold_s"]
            for k, c in recs.items()
            if k[3] == e and c["status"] == "ok" and c.get("cold_s")
        ]
        rssv = [
            c["peak_rss_mb"]
            for k, c in recs.items()
            if k[3] == e and c["status"] == "ok"
        ]
        w(
            f"| {DEGREE_LABEL[e]} | {SERVED[e]} | {sum(cold):.1f} s | "
            f"{statistics.median(cold):.3f} s | {max(cold):.2f} s | "
            f"{max(rssv):.0f} MB |"
        )
    w("")

    # ---------------- predictions ----------------
    w("## Predictions G1–G4, scored\n")
    med = {
        e: (statistics.median([a[3] for a in per[e]["adm"]]) if per[e]["adm"] else None)
        for e in SERVED
    }
    rows = []
    g1 = med["bs2"] is not None and 0.006 <= med["bs2"] <= 0.015
    rows.append(("G1", "bs2@15 median in 0.6–1.5 %", pct(med["bs2"]), g1))
    g2 = razor40 is not None and all(
        m is not None and m < razor40 for m in med.values()
    )
    rows.append(
        (
            "G2",
            f"all three medians below razor-2p@40's {pct(razor40)}",
            ", ".join(
                f"{DEGREE_LABEL[e]} {pct(med[e])}" for e in ("bs1", "bs2", "bs3")
            ),
            g2,
        )
    )
    vals = [m for m in med.values() if m]
    ratio = (max(vals) / min(vals)) if len(vals) == 3 and min(vals) else None
    g3 = ratio is not None and ratio <= 3.0
    rows.append(
        (
            "G3",
            "the three medians within a factor of 3",
            f"{ratio:.2f}×" if ratio else "—",
            g3,
        )
    )
    counts = {e: len(per[e]["adm"]) for e in SERVED}
    g4 = all(120 <= c <= 175 for c in counts.values())
    rows.append(
        (
            "G4",
            "120–175 admissible rows per degree",
            ", ".join(f"{DEGREE_LABEL[e]} {counts[e]}" for e in ("bs1", "bs2", "bs3")),
            g4,
        )
    )
    w("| prediction | bar | measured | verdict |")
    w("|---|---|---|---|")
    for tag, bar, got, ok in rows:
        w(f"| **{tag}** | {bar} | {got} | {'**HIT**' if ok else '**MISS**'} |")
    w("")
    w(f"Hit {sum(1 for *_x, ok in rows if ok)} of {len(rows)}.\n")

    notes = HERE / "hypotheses.md"
    if notes.is_file():
        w(notes.read_text(encoding="utf-8").rstrip())
        w("")

    text = "\n".join(out) + "\n"
    (HERE / "README.md").write_text(text, encoding="utf-8")

    # COMMENT.md: the same tables, as the text to paste on AK#1525 verbatim.
    c = [
        "<!-- Comment text for AK#1525. NOT posted by this session: the standing",
        "     rule is that Steve decides what is quoted and where. Paste verbatim. -->",
        "",
        "## The bspline family at the densities #1547 serves",
        "",
    ]
    start = text.index("**Builds.**")
    end = text.index("## Predictions G1–G4")
    c.append(text[start:end].rstrip())
    c.append("")
    sys.stdout.write("\n".join(c) + "\n")
    (HERE / "COMMENT.md").write_text("\n".join(c) + "\n", encoding="utf-8")
    return 0


if __name__ == "__main__":
    sys.exit(main())
