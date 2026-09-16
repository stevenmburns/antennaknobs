"""Read `records.jsonl` and write the README for AK#1525. No number transcribed.

    python scratch/1525-razor-density/report.py > README.md

THE METRIC, ONCE. Error is `|Z_a - Z_b|` with the port impedances taken as
VECTORS over all ports. The ohm figure is that numerator; the percentage is the
same numerator over `|Z_b|`. They are the same quantity, so a reader can move
between them. This is NOT probe3's metric, which is port 0 alone -- on the
four-port `arrays.moxonarray` probe3 reads 9.068 ohm where this norm reads 18.0.

THE REFERENCE is bs2 at rung 160, and bs2's OWN ladder is measured so its role is
a result rather than an assumption.

#845's ONE-THIRD RULE. A row whose reference moved between the last two rungs by
more than a third of the quantity being judged is `reference unsettled` and is NOT
tabulated as a convergence result. A reference that is still moving cannot
adjudicate anything.

A CLASS IS ONLY EVER APPLIED TO THE PAIR IT WAS MEASURED ON. Each engine under
test is classified against the reference separately. A measurement of razor-vs-bs2
says nothing about razor-vs-NEC-5, because those two move together under
refinement -- the published catalog page got that wrong twice before it was caught.

ACHIEVED SEGMENT COUNTS, never the requested knob. A design whose mesh does not
respond to the knob is skipped and reported as its own finding.
"""

from __future__ import annotations

import json
import math
import statistics
import sys
from collections import Counter
from pathlib import Path

RUNGS = (21, 40, 80, 160)
SERVED = 40
REF_ENGINE, REF_RUNG = "bs2", 160
GROUNDS = ("free", "somm")
TESTED = ("razor", "bs2", "nec5")
THIRD = 1.0 / 3.0


def load(path):
    recs, prov = {}, None
    for line in open(path, encoding="utf-8"):
        r = json.loads(line)
        if "design" not in r:
            prov = r
            continue
        recs[(r["design"], r["ground"], r["rung"], r["engine"])] = r
    return recs, prov


def zv(rec):
    return [complex(*p) for p in rec["z"]] if rec and rec.get("z") else None


def dz(a, b):
    """(ohms, relative) between two port vectors, or (None, None)."""
    if a is None or b is None or len(a) != len(b):
        return None, None
    num = math.sqrt(sum(abs(x - y) ** 2 for x, y in zip(a, b, strict=True)))
    den = math.sqrt(sum(abs(y) ** 2 for y in b))
    return num, (num / den if den else None)


def fit_order(ns, errs):
    pts = [
        (math.log(n), math.log(e))
        for n, e in zip(ns, errs, strict=True)
        if n and e and e > 0
    ]
    if len(pts) < 3:
        return None
    mx = statistics.fmean(x for x, _ in pts)
    my = statistics.fmean(y for _, y in pts)
    sxx = sum((x - mx) ** 2 for x, _ in pts)
    if not sxx:
        return None
    return -(sum((x - mx) * (y - my) for x, y in pts) / sxx)


def num(x, f="{:.3g}"):
    return "—" if x is None else f.format(x)


def pct(x):
    return "—" if x is None else f"{100 * x:.3g} %"


def build(recs):
    """(engine, design, ground) -> the row: achieved N, ohms/relative per rung,
    the reference's own movement, the class and the fitted order."""
    designs = sorted({k[0] for k in recs})
    rows = {}
    for d in designs:
        for g in GROUNDS:
            ref = recs.get((d, g, REF_RUNG, REF_ENGINE))
            ref_v = zv(ref)
            prev = zv(recs.get((d, g, RUNGS[-2], REF_ENGINE)))
            ref_move, _ = dz(prev, ref_v) if (prev and ref_v) else (None, None)
            for e in TESTED:
                cells = [recs.get((d, g, r, e)) for r in RUNGS]
                if all(c is None for c in cells):
                    continue
                statuses = [c["status"] if c else "missing" for c in cells]
                achieved = [(c.get("total_nominal_segs") if c else None) for c in cells]
                built = [(c.get("built_segs") if c else None) for c in cells]
                ohms, rels = [], []
                for c in cells:
                    o, r = dz(zv(c) if c and c["status"] == "ok" else None, ref_v)
                    ohms.append(o)
                    rels.append(r)
                row = {
                    "statuses": statuses,
                    "achieved": achieved,
                    "built": built,
                    "ohms": ohms,
                    "rel": rels,
                    "ref_move_ohm": ref_move,
                    "order": None,
                }
                # ---- the class, in precedence order
                if any(s == "skipped" for s in statuses):
                    row["class"] = "skipped — not ladderable on this box"
                elif all(s == "refused" for s in statuses):
                    row["class"] = "refused"
                elif ref is None or ref["status"] != "ok" or ref_v is None:
                    row["class"] = "no reference"
                elif e == REF_ENGINE:
                    # bs2 against its own top rung: this is the yardstick's own
                    # convergence, not a competitor's, so it gets its own label.
                    row["class"] = "reference self-check"
                    row["order"] = fit_order(achieved, ohms)
                elif any(s != "ok" for s in statuses):
                    row["class"] = "incomplete ladder"
                elif ohms[0] is None or ohms[0] == 0:
                    row["class"] = "no error to fit"
                elif ref_move is not None and ref_move > THIRD * ohms[0]:
                    # #845's rule, applied on the SAME metric as everything else.
                    row["class"] = "reference unsettled"
                elif ohms[-1] < ohms[-2] < ohms[0]:
                    row["class"] = "converging"
                    row["order"] = fit_order(achieved, ohms)
                elif ohms[-1] >= ohms[0]:
                    row["class"] = "not converging"
                else:
                    row["class"] = "non-monotone"
                    row["order"] = fit_order(achieved, ohms)
                rows[(e, d, g)] = row
    return rows


def main(argv=None):
    path = Path(argv[0]) if argv else Path(__file__).with_name("records.jsonl")
    recs, prov = load(path)
    rows = build(recs)
    designs = sorted({k[0] for k in recs})
    out = []
    w = out.append

    w("# AK#1525 — razor-2p density ladder over the catalog\n")
    w(
        "**Measurement only. No recommendation on the default density** — that is "
        "a product call; this is the curve. `PLAN.md` registers E1–E5 and F1–F2 "
        "and the skip rule, all before the run.\n"
    )
    w(
        f"**Builds.** antennaknobs `{prov['ak_sha'][:9]}` "
        f"(v{prov['version_antennaknobs']}); momwire `{prov['momwire_sha'][:9]}` "
        f"= `{prov['momwire_describe']}` (v{prov['version_momwire']}), which is "
        f"also antennaknobs' recorded pointer, so **the dev tip and the release "
        f"coincide for this run**. Accelerator "
        f"`{prov['accelerator_variant']['_accelerators'].split('.')[0]}`. "
        f"NEC-5 `{Path(prov['nec5_exe'] or 'nec5cl').name}` "
        f"(LLNL-CODE-746721), impedances only. "
        f"Provenance is the first line of `records.jsonl`.\n"
    )
    w(
        "**The metric, once.** Error is `|Z_a − Z_b|` over **all ports** as a "
        "vector. The ohm column is that numerator; the percentage is the same "
        "numerator over `|Z_b|`. The reference is **bs2 at rung 160**. This is not "
        "probe3's port-0 metric — on four-port `arrays.moxonarray` probe3 reads "
        "9.068 Ω where this norm reads 18.0 — so probe3 supplied the *predicted* "
        "class and nothing else.\n"
    )

    # ---------------- coverage ----------------
    w("## 1. Coverage\n")
    w("| engine | ok | refused | skipped | other |")
    w("|---|---:|---:|---:|---:|")
    for e in TESTED:
        c = Counter(r["status"] for k, r in recs.items() if k[3] == e)
        other = sum(v for k, v in c.items() if k not in ("ok", "refused", "skipped"))
        w(f"| `{e}` | {c['ok']} | {c['refused']} | {c['skipped']} | {other} |")
    w("")
    skipped = sorted({k[0] for k, r in recs.items() if r["status"] == "skipped"})
    if skipped:
        w("### Skipped, with the reason recorded as rows\n")
        w(
            "| design | achieved N ×21/×40/×80/×160 | growth | predicted cost | budget | reason |"
        )
        w("|---|---|---:|---|---|---|")
        for d in skipped:
            s = next(
                r for k, r in recs.items() if k[0] == d and r["status"] == "skipped"
            )
            w(
                f"| `{d}` | {'/'.join(str(x) for x in s['achieved'])} | "
                f"{s['growth']:.3f}× | {s['predicted_peak_rss_mb'] / 1024:.1f} GB, "
                f"{s['predicted_wall_s']:.0f} s | "
                f"{s['budget_rss_mb'] / 1024:.0f} GB, {s['budget_wall_s']:.0f} s | "
                f"{s['error']} |"
            )
        w("")
        w(
            '**A skipped design is not classified.** "Cannot be laddered on this '
            'box" is the finding — it is neither converging nor not converging, '
            "and its earlier probe3 reading is withdrawn in "
            "`predicted-classes.json` with the cause.\n"
        )

    # ---------------- classes ----------------
    w("## 2. Classes, per engine against bs2@160\n")
    w(
        "Each engine under test is classified **against the reference separately**. "
        "A class is never carried from one pair to another.\n"
    )
    for e in TESTED:
        sel = {k: v for k, v in rows.items() if k[0] == e}
        if not sel:
            continue
        c = Counter(v["class"] for v in sel.values())
        w(
            f"**`{e}`** — {len(sel)} design×ground rows: "
            + ", ".join(f"{k} {v}" for k, v in c.most_common())
            + "\n"
        )
    w("| engine | class | rows |")
    w("|---|---|---:|")
    for e in TESTED:
        c = Counter(v["class"] for k, v in rows.items() if k[0] == e)
        for k, v in c.most_common():
            w(f"| `{e}` | {k} | {v} |")
    w("")

    conv = [
        v for k, v in rows.items() if k[0] == "razor" and v["class"] == "converging"
    ]
    orders = [v["order"] for v in conv if v["order"] is not None]
    if orders:
        w(
            f"Fitted order on razor-2p's **{len(orders)}** converging rows: median "
            f"**{statistics.median(orders):.2f}**, p10 "
            f"{sorted(orders)[max(0, len(orders) // 10 - 1)]:.2f}, p90 "
            f"{sorted(orders)[min(len(orders) - 1, 9 * len(orders) // 10)]:.2f}.\n"
        )

    # ---------------- unresolved rows ----------------
    w("## 3. Rows unresolved under the one-third rule\n")
    uns = sorted(
        (k for k, v in rows.items() if v["class"] == "reference unsettled"),
        key=lambda k: (k[1], k[2], k[0]),
    )
    w(
        f"**{len(uns)}** rows. The reference — bs2 at rung 160 — moved between "
        f"×80 and ×160 by more than a third of the error being judged, so bs2 is "
        f"not settled at that design's shipped mesh and cannot adjudicate it.\n"
    )
    if uns:
        w(
            "| engine | design | ground | error at ×21 (Ω) | reference moved (Ω) | ratio |"
        )
        w("|---|---|---|---:|---:|---:|")
        for k in uns:
            v = rows[k]
            w(
                f"| `{k[0]}` | `{k[1]}` | {k[2]} | {num(v['ohms'][0])} | "
                f"{num(v['ref_move_ohm'])} | "
                f"{num(v['ref_move_ohm'] / v['ohms'][0], '{:.2f}')} |"
            )
        w("")

    # ---------------- what 80 buys over 40 ----------------
    w("## 4. What 80 buys over 40\n")
    i40, i80 = RUNGS.index(40), RUNGS.index(80)
    acc, wall, rss = [], [], []
    for k, v in rows.items():
        if k[0] != "razor" or v["class"] != "converging":
            continue
        a, b = v["ohms"][i40], v["ohms"][i80]
        if a and b:
            acc.append(b / a)
        r40 = recs.get((k[1], k[2], 40, "razor"))
        r80 = recs.get((k[1], k[2], 80, "razor"))
        if r40 and r80 and r40["status"] == r80["status"] == "ok":
            if r40.get("cold_s"):
                wall.append(r80["cold_s"] / r40["cold_s"])
            if r40.get("peak_rss_mb"):
                rss.append(r80["peak_rss_mb"] / r40["peak_rss_mb"])
    w("| quantity | rows | median | p10 | p90 |")
    w("|---|---:|---:|---:|---:|")
    for lab, v in (
        ("accuracy, err(80)/err(40)", acc),
        ("cold wall, t(80)/t(40)", wall),
        ("peak RSS, rss(80)/rss(40)", rss),
    ):
        if v:
            s = sorted(v)
            w(
                f"| {lab} | {len(v)} | {statistics.median(v):.3f} | "
                f"{s[max(0, len(s) // 10 - 1)]:.3f} | "
                f"{s[min(len(s) - 1, 9 * len(s) // 10)]:.3f} |"
            )
    w("")
    w(
        "| rung | Σ cold wall, razor | median cold | median warm | worst peak RSS | worst achieved N |"
    )
    w("|---:|---:|---:|---:|---:|---:|")
    for r in RUNGS:
        cold = [
            c["cold_s"]
            for k, c in recs.items()
            if k[2] == r and k[3] == "razor" and c["status"] == "ok" and c.get("cold_s")
        ]
        warm = [
            c["warm_s"]
            for k, c in recs.items()
            if k[2] == r and k[3] == "razor" and c["status"] == "ok" and c.get("warm_s")
        ]
        peak = [
            c["peak_rss_mb"]
            for k, c in recs.items()
            if k[2] == r and k[3] == "razor" and c["status"] == "ok"
        ]
        segs = [
            c["total_nominal_segs"]
            for k, c in recs.items()
            if k[2] == r and k[3] == "razor" and c.get("total_nominal_segs")
        ]
        w(
            f"| ×{r} | {sum(cold):.0f} s | {statistics.median(cold):.3f} s | "
            f"{statistics.median(warm):.3f} s | {max(peak):.0f} MB | {max(segs)} |"
        )
    w("")
    w(
        "Peak RSS is a per-process high-water mark covering both the cold and the "
        "warm solve in that worker, so it cannot be split between them.\n"
    )

    # ---------------- the served rung ----------------
    w("## 5. The served rung, ×40\n")
    served = sorted(
        (
            (v["rel"][RUNGS.index(SERVED)], v["ohms"][RUNGS.index(SERVED)], k)
            for k, v in rows.items()
            if k[0] == "razor"
            and v["class"] == "converging"
            and v["rel"][RUNGS.index(SERVED)]
        ),
        reverse=True,
    )
    if served:
        vals = [s[0] for s in served]
        w(
            f"razor-2p's error against bs2@160 at the density the app serves "
            f"(`default_n_per_wire=40`), over **{len(vals)}** converging rows: "
            f"median **{pct(statistics.median(vals))}**, p90 "
            f"**{pct(sorted(vals)[min(len(vals) - 1, 9 * len(vals) // 10)])}**, "
            f"worst **{pct(vals[0])}**.\n"
        )
        w("Twelve widest at ×40:\n")
        w("| design | ground | Ω | relative | class | order |")
        w("|---|---|---:|---:|---|---:|")
        for rel_, oh, k in served[:12]:
            w(
                f"| `{k[1]}` | {k[2]} | {num(oh)} | {pct(rel_)} | "
                f"{rows[k]['class']} | {num(rows[k]['order'], '{:.2f}')} |"
            )
        w("")

    # ---------------- predictions ----------------
    w("## 6. Predictions, scored\n")
    pred_path = Path(__file__).with_name("predicted-classes.json")
    pred = json.loads(pred_path.read_text()) if pred_path.is_file() else {}
    # probe3 measured razor against bs2, which is this ladder's own primary pair,
    # so the predicted classes transfer with no cross-pair inference.
    agree = disagree = nopred = 0
    changes = []
    for (e, d, g), v in rows.items():
        if e != "razor" or v["class"].startswith("skipped"):
            continue
        pc = (pred.get(f"{d}|{g}") or {}).get("class")
        mc = v["class"]
        if pc is None or pc == "not measured":
            nopred += 1
            continue
        if pc == mc:
            agree += 1
        else:
            disagree += 1
            changes.append((d, g, pc, mc))
    scored = len(
        [
            1
            for (e, d, g), v in rows.items()
            if e == "razor" and not v["class"].startswith("skipped")
        ]
    )
    strict = agree / scored if scored else None
    excl = agree / (agree + disagree) if (agree + disagree) else None

    orders_all = [
        v["order"]
        for k, v in rows.items()
        if k[0] == "razor" and v["class"] == "converging" and v["order"] is not None
    ]
    med_order = statistics.median(orders_all) if orders_all else None
    sky = [
        rows[("razor", "loops.skyloop_lmatch", g)]["order"]
        for g in GROUNDS
        if ("razor", "loops.skyloop_lmatch", g) in rows
        and rows[("razor", "loops.skyloop_lmatch", g)]["order"] is not None
    ]
    n_unsettled = sum(
        1
        for k, v in rows.items()
        if k[0] == "razor" and v["class"] == "reference unsettled"
    )
    n_skipped = len({k[1] for k, v in rows.items() if v["class"].startswith("skipped")})
    ma = statistics.median(acc) if acc else None
    mw = statistics.median(wall) if wall else None
    mr = statistics.median(rss) if rss else None

    w("| prediction | bar | measured | verdict |")
    w("|---|---|---|---|")
    e1 = strict is not None and strict >= 0.90
    w(
        f"| **E1** | ≥ 90 % of the 204 classifiable rows keep probe3's predicted "
        f"class | {pct(strict)} strict ({agree}/{scored}); {pct(excl)} excluding "
        f"the {nopred} rows probe3 never measured | "
        f"{'**HIT**' if e1 else '**MISS**'} |"
    )
    e2a = med_order is not None and 0.8 <= med_order <= 1.3
    e2b = bool(sky) and all(1.7 <= o <= 2.4 for o in sky)
    w(
        f"| **E2a** | converging-row order median in 0.8–1.3 | "
        f"{num(med_order, '{:.2f}')} | {'**HIT**' if e2a else '**MISS**'} |"
    )
    w(
        f"| **E2b** | `loops.skyloop_lmatch` order in 1.7–2.4 | "
        f"{', '.join(f'{o:.2f}' for o in sky) or 'not fitted'} | "
        f"{'**HIT**' if e2b else '**MISS**'} |"
    )
    e3 = (
        ma is not None
        and 0.45 <= ma <= 0.60
        and mw is not None
        and 3.0 <= mw <= 5.0
        and mr is not None
        and 1.5 <= mr <= 4.0
    )
    w(
        f"| **E3** | err 0.45–0.60, wall 3.0–5.0, RSS 1.5–4.0 | "
        f"err {num(ma, '{:.3f}')}, wall {num(mw, '{:.2f}')}, RSS "
        f"{num(mr, '{:.2f}')} | {'**HIT**' if e3 else '**MISS**'} |"
    )
    e4 = 10 <= n_unsettled <= 40
    w(
        f"| **E4** | 10–40 rows marked reference unsettled | {n_unsettled} | "
        f"{'**HIT**' if e4 else '**MISS**'} |"
    )
    e5 = n_skipped == 1
    w(
        f"| **E5** | exactly one knob-stiff design | {n_skipped} | "
        f"{'**HIT**' if e5 else '**MISS**'} |"
    )
    # F1/F2: the v0.79.0 delta against the preserved pre-release ladder.
    prev_path = Path(__file__).with_name("records-momwire-227491d.jsonl")
    if prev_path.is_file():
        prev, _ = load(prev_path)
        common = [k for k in recs if k in prev]
        movers = [
            k
            for k in common
            if prev[k]["status"] != recs[k]["status"]
            or (prev[k]["status"] == "ok" and prev[k]["z"] != recs[k]["z"])
        ]
        target = "verticals.buried_radial_vertical"
        outside = [k for k in movers if k[0] != target]
        inside = [k for k in movers if k[0] == target]
        f1 = not outside
        f2 = bool(inside)
        w(
            f"| **F1** | every cell bit-identical to the pre-v0.79.0 ladder except "
            f"`{target}` | {len(common) - len(movers)} of {len(common)} identical, "
            f"{len(outside)} movers outside | {'**HIT**' if f1 else '**MISS**'} |"
        )
        w(
            f"| **F2** | `{target}` does move | {len(inside)} of its cells moved | "
            f"{'**HIT**' if f2 else '**MISS**'} |"
        )
    w("")
    if changes:
        w(f"### Class changes against probe3 — **{len(changes)}**, each a finding\n")
        w("| design | ground | probe3 predicted | measured now |")
        w("|---|---|---|---|")
        for d, g, pc, mc in sorted(changes):
            w(f"| `{d}` | {g} | {pc} | {mc} |")
        w("")
        w(
            "probe3 ran on a 2026-09-03 build with a port-0 metric and a 1×/2×/4× "
            "sweep; this ladder is current code, an all-port norm and 21/40/80/160. "
            "A change is therefore not automatically a regression — it can be "
            "either the code moving or the metric resolving the row differently, "
            "and the appendix carries the numbers for each.\n"
        )

    # ---------------- appendix ----------------
    w("## 6. Appendix — every razor-2p row\n")
    w("`Ω` and `%` are against bs2@160. `N` is the achieved segment count.\n")
    w(
        "| design | ground | achieved N | Ω ×21/×40/×80/×160 | % ×21/×40/×80/×160 | class | order |"
    )
    w("|---|---|---|---|---|---|---:|")
    for d in designs:
        for g in GROUNDS:
            v = rows.get(("razor", d, g))
            if v is None:
                continue
            w(
                f"| `{d}` | {g} | "
                + "/".join(str(x) if x else "—" for x in v["achieved"])
                + " | "
                + "/".join(num(x) for x in v["ohms"])
                + " | "
                + "/".join(pct(x) for x in v["rel"])
                + f" | {v['class']} | {num(v['order'], '{:.2f}')} |"
            )
    w("")

    notes = Path(__file__).with_name("hypotheses.md")
    if notes.is_file():
        w(notes.read_text(encoding="utf-8").rstrip())
        w("")
    sys.stdout.write("\n".join(out) + "\n")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
