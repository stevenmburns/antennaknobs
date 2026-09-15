"""Read `records.jsonl` and write the README for #1516. No number is hand-typed.

    python scratch/1516-ladders/report.py > README.md

Same rule as the catalog study: every table and every verdict is computed from
the records, so a verdict cannot disagree with the ladder it is read off. The
per-design prose in `hypotheses.md` is INCLUDED verbatim rather than written
into the generated file, so the README still regenerates byte-for-byte.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

ENGINES = ("razor", "nec5", "bs2")
REF = "nec5"
LADDER = (21, 42, 84, 168)  # the x1/x2/x4/x8 rungs; 40 is the served rung
SERVED = 40


def load(path):
    recs = {}
    order = []
    for line in open(path, encoding="utf-8"):
        r = json.loads(line)
        key = (r["design"], r["variant"], r["ground"], r["rung"], r["engine"])
        recs[key] = r
        k3 = (r["design"], r["variant"], r["ground"])
        if k3 not in order:
            order.append(k3)
    return recs, order


def zc(rec, port=0):
    return complex(*rec["z"][port])


def rel(a, b):
    return abs(a - b) / abs(b)


def fmt(z):
    return f"{z.real:.4f}{z.imag:+.4f}j"


def pct(x):
    return "n/a" if x is None else f"{100 * x:.3g} %"


def case_recs(recs, case, rung):
    d, v, g = case
    return {e: recs.get((d, v, g, rung, e)) for e in ENGINES}


def mesh_diffs(recs, case):
    """Where the engines' built meshes differ, rung by rung.

    Returns (rows, other_than_fed) -- `rows` is one line per rung, and
    `other_than_fed` counts the rungs whose razor/NEC-5 counts disagree at all,
    or whose bs2 counts differ from NEC-5's by anything but a single fed edge.
    A mesh difference anywhere else would make the ladder a comparison of two
    structures, so it is COUNTED rather than described.
    """
    rows, other = [], 0
    for rung in (*LADDER, SERVED):
        cr = case_recs(recs, case, rung)
        if any(r is None or r["status"] != "ok" for r in cr.values()):
            continue
        # Compare BY GEOMETRY, not by position: momwire walks the fed polyline
        # first and the NEC-5 deck lists GW cards in builder-wire order, so the
        # flat lists differ in order on designs whose feed is not wire 0 even
        # when the mesh is identical.
        mn, mr5, mb = (cr[e]["mesh_by_wire"] for e in ("razor", REF, "bs2"))
        razor_extra = sorted(set(mn) ^ set(mr5))
        razor_bad = [k for k in set(mn) & set(mr5) if mn[k] != mr5[k]]
        if razor_extra or razor_bad:
            razor_vs_nec5 = (
                f"DIFFER — {len(razor_extra)} wire(s) only one side has, "
                f"{len(razor_bad)} with different counts"
            )
            other += 1
        else:
            razor_vs_nec5 = "identical"
        # bs2 may legitimately differ on the FED wires -- its odd parity leaves
        # each of them a different count from the even pair's. The allowance is
        # the number of feeds the engine reports, not 1: `verticals.four_square`
        # has four driven elements, and a hardcoded 1 called its four expected
        # parity differences a deck difference.
        nfeeds = (
            len(cr[REF]["fed_segments"])
            if isinstance(cr[REF]["fed_segments"], list)
            else 1
        )
        bs2_extra = sorted(set(mb) ^ set(mr5))
        bs2_bad = [k for k in set(mb) & set(mr5) if mb[k] != mr5[k]]
        deltas = [(k, mb[k], mr5[k]) for k in bs2_bad]
        ok = not bs2_extra and len(bs2_bad) <= nfeeds
        if not ok:
            other += 1
        rows.append(
            {
                "rung": rung,
                "razor_vs_nec5": razor_vs_nec5,
                "bs2_edges": deltas,
                "bs2_ok": ok,
                "totals": {e: cr[e]["total_segs"] for e in ENGINES},
                "fed": {e: cr[e]["fed_segments"] for e in ENGINES},
                "dora": cr["razor"]["min_delta_over_a"],
            }
        )
    return rows, other


def gap(recs, case, rung, a, b, port=0):
    cr = case_recs(recs, case, rung)
    if (
        cr[a] is None
        or cr[b] is None
        or cr[a]["status"] != "ok"
        or cr[b]["status"] != "ok"
    ):
        return None
    if port >= len(cr[a]["z"]) or port >= len(cr[b]["z"]):
        return None
    return rel(zc(cr[a], port), zc(cr[b], port))


def movement(recs, case, engine, port=0):
    """How far an engine's own answer moves from x1 to x8, relative to its x8.
    This is what separates 'bs2 was unconverged' from 'the tent pair was'."""
    lo = case_recs(recs, case, LADDER[0])[engine]
    hi = case_recs(recs, case, LADDER[-1])[engine]
    if lo is None or hi is None or lo["status"] != "ok" or hi["status"] != "ok":
        return None
    return rel(zc(lo, port), zc(hi, port))


def verdict(recs, case, other_mesh_diffs, port=0):
    g1 = gap(recs, case, LADDER[0], "bs2", REF, port)
    g8 = gap(recs, case, LADDER[-1], "bs2", REF, port)
    mv_b = movement(recs, case, "bs2", port)
    mv_r = movement(recs, case, "razor", port)
    mv_n = movement(recs, case, REF, port)
    if other_mesh_diffs:
        return "deck difference", g1, g8, mv_b, mv_r, mv_n
    if g1 is None or g8 is None:
        return "unexplained — a rung is missing", g1, g8, mv_b, mv_r, mv_n
    if g8 > 0.8 * g1:
        label = "formulation — the gap does not close"
    elif mv_r is not None and mv_b is not None and mv_r > 2.0 * mv_b:
        label = "tent pair unconverged — razor and NEC-5 move together toward bs2"
    elif mv_b is not None and mv_r is not None and mv_b > 2.0 * mv_r:
        label = "bs2 unconverged — bs2 moves toward the tent pair"
    else:
        label = "both unconverged — every engine moves"
    return label, g1, g8, mv_b, mv_r, mv_n


def main(argv=None):
    path = Path(argv[0]) if argv else Path(__file__).with_name("records.jsonl")
    recs, cases = load(path)
    out = []
    w = out.append

    w("# antennaknobs#1516 — refinement ladders\n")
    w(
        "Generated by `report.py` from `records.jsonl`; every number and every "
        "verdict below is computed, none transcribed. `PLAN.md` registers the "
        "predictions and the setup.\n"
    )
    w(
        f"**Scope.** {len(recs)} cells across {len(cases)} design/variant/ground cases.\n"
    )

    verdicts = {}
    for case in cases:
        d, v, g = case
        title = f"`{d}`" + (f" — {v} variant" if v != "stock" else "") + f", {g}"
        w(f"## {title}\n")

        rows, other = mesh_diffs(recs, case)
        lab, g1, g8, mv_b, mv_r, mv_n = verdict(recs, case, other)
        verdicts[case] = (lab, g1, g8, mv_b, mv_r, mv_n, other)

        # ---- step 1: deck equivalence
        w("### Deck equivalence\n")
        w(
            "| rung | segments razor / NEC-5 / bs2 | razor vs NEC-5 mesh | bs2 vs NEC-5 mesh | min Δ/a |"
        )
        w("|---:|---|---|---|---:|")
        for r in rows:
            t = r["totals"]
            if r["bs2_edges"] and r["bs2_ok"]:
                uniq = sorted({(x, y) for _k, x, y in r["bs2_edges"]})
                bl = f"{len(r['bs2_edges'])} fed wire(s): " + "; ".join(
                    f"{x} vs {y} segments" for x, y in uniq
                )
            elif r["bs2_ok"]:
                bl = "identical"
            else:
                bl = f"DIFFERS ON {len(r['bs2_edges'])} wire(s)"
            w(
                f"| ×{r['rung']} | {t['razor']} / {t['nec5']} / {t['bs2']} | "
                f"{r['razor_vs_nec5']} | {bl} | {r['dora']:.1f} |"
            )
        w("")
        first = case_recs(recs, case, LADDER[0])
        w("Fed segments at ×21, as each engine meshes the feed:\n")
        for e in ENGINES:
            fs = first[e]["fed_segments"]
            if isinstance(fs, list):
                desc = "; ".join(
                    f"port {f.get('port')}: {f.get('segments')} seg "
                    f"× {f.get('length_m', 0):.4g} m at the {f.get('site')}"
                    for f in fs
                )
            else:
                desc = str(fs)
            w(f"  - `{e}` (parity {first[e]['parity']}): {desc}")
        w("")
        net = first[REF].get("builder_network")
        cards = first[REF].get("deck_card_types") or []
        if net:
            w(
                "Network: `build_network()` returns one object and all three "
                "engines consume it — momwire keeps it on `_network`, "
                "`nec5.py:394` runs the same thing through "
                "`_network_as_meshed`. It is applied to the antenna Y in "
                "Python, so it CANNOT be a deck difference; the NEC-5 deck "
                f"antennaknobs wrote carries only {', '.join('`' + c + '`' for c in cards)}"
                " — no `NT`, no `LD` for it.\n"
            )
            w(f"```\n{net}\n```\n")
        else:
            w(
                "Network: none — the design drives a bare port. NEC-5 deck "
                f"cards: {', '.join('`' + c + '`' for c in cards) or 'n/a'}\n"
            )

        # ---- step 2: the ladder
        w("### Ladder (port 0)\n")
        w("| rung | segments | razor | NEC-5 | bs2 | razor−NEC-5 | bs2−NEC-5 |")
        w("|---:|---:|---|---|---|---:|---:|")
        for rung in (*LADDER, SERVED):
            cr = case_recs(recs, case, rung)
            if any(r is None or r["status"] != "ok" for r in cr.values()):
                continue
            tag = f"×{rung}" + (" (served)" if rung == SERVED else "")
            w(
                f"| {tag} | {cr['razor']['total_segs']} | {fmt(zc(cr['razor']))} | "
                f"{fmt(zc(cr[REF]))} | {fmt(zc(cr['bs2']))} | "
                f"{pct(gap(recs, case, rung, 'razor', REF))} | "
                f"{pct(gap(recs, case, rung, 'bs2', REF))} |"
            )
        w("")
        nports = len(first["razor"]["z"])
        if nports > 1:
            w(f"Gaps at all {nports} ports:\n")
            w(
                "| rung | "
                + " | ".join(f"p{i} razor−NEC-5 / bs2−NEC-5" for i in range(nports))
                + " |"
            )
            w("|---:|" + "---|" * nports)
            for rung in (*LADDER, SERVED):
                cells = [
                    f"{pct(gap(recs, case, rung, 'razor', REF, i))} / "
                    f"{pct(gap(recs, case, rung, 'bs2', REF, i))}"
                    for i in range(nports)
                ]
                w(f"| ×{rung} | " + " | ".join(cells) + " |")
            w("")

        # ---- how fast does the gap close, and where do the two sides meet?
        w("### Order in the mesh, and the extrapolated limit\n")
        w(
            "The local exponent is `ln(g_k / g_k+1) / ln(N_k+1 / N_k)` on the "
            "bs2−NEC-5 gap against the ACTUAL segment count. A tent pair that "
            "is first order in the mesh gives ≈ 1.\n"
        )
        w("| rungs | segments | bs2−NEC-5 | local exponent |")
        w("|---|---|---:|---:|")
        prev = None
        for rung in LADDER:
            cr = case_recs(recs, case, rung)
            if any(r is None or r["status"] != "ok" for r in cr.values()):
                continue
            n = cr[REF]["total_segs"]
            g = gap(recs, case, rung, "bs2", REF)
            if prev and g and prev[1] and n != prev[0]:
                import math

                p_local = math.log(prev[1] / g) / math.log(n / prev[0])
                exp_s = f"{p_local:.2f}"
            else:
                exp_s = "—"
            w(f"| ×{rung} | {n} | {pct(g)} | {exp_s} |")
            prev = (n, g)
        w("")
        # First-order Richardson from the x4 and x8 rungs: Z_inf ~ Z8 +
        # (Z8 - Z4) / (N8/N4 - 1). Both sides are extrapolated, because bs2 is
        # not stationary either -- reporting only razor's limit would credit it
        # with closing a gap that bs2 also moved.
        c4, c8 = case_recs(recs, case, LADDER[-2]), case_recs(recs, case, LADDER[-1])
        if all(
            r is not None and r["status"] == "ok" for r in (*c4.values(), *c8.values())
        ):
            n4, n8 = c4[REF]["total_segs"], c8[REF]["total_segs"]
            k = n8 / n4 - 1.0
            lim = {}
            for e in ENGINES:
                z4, z8 = zc(c4[e]), zc(c8[e])
                lim[e] = z8 + (z8 - z4) / k if k else z8
            sep = rel(lim["razor"], lim["bs2"])
            w(
                f"First-order Richardson from ×{LADDER[-2]} → ×{LADDER[-1]} "
                f"({n4} → {n8} segments): razor → **{fmt(lim['razor'])}**, "
                f"NEC-5 → **{fmt(lim[REF])}**, bs2 → **{fmt(lim['bs2'])}**; "
                f"razor and bs2 land **{pct(sep)}** apart, against "
                f"{pct(gap(recs, case, LADDER[-1], 'bs2', 'razor'))} at ×"
                f"{LADDER[-1]} itself.\n"
            )

        w("### Verdict\n")
        w(
            "| bs2−NEC-5 at ×1 | at ×8 | ratio | bs2 moves ×1→×8 | razor moves | "
            "NEC-5 moves |"
        )
        w("|---:|---:|---:|---:|---:|---:|")
        ratio = (g8 / g1) if (g1 and g8) else None
        w(
            f"| {pct(g1)} | {pct(g8)} | "
            f"{'n/a' if ratio is None else f'{ratio:.3f}×'} | {pct(mv_b)} | "
            f"{pct(mv_r)} | {pct(mv_n)} |"
        )
        w("")
        w(f"**{lab}**\n")

    # ---------------- predictions ----------------
    w("## Predictions P1–P6, scored\n")
    scored = []
    free_cases = [c for c in cases if c[2] == "free" and c[1] == "stock"]

    p1_detail = []
    p1 = True
    for c in free_cases:
        _lab, g1, g8, *_ = verdicts[c]
        r = (g8 / g1) if (g1 and g8) else None
        p1_detail.append(f"{c[0].split('.')[-1]} {r:.3f}×" if r else f"{c[0]} n/a")
        if r is None or r > 0.25:
            p1 = False
    scored.append(
        (
            "P1",
            "bs2−NEC-5 gap at ×8 ≤ 0.25× its ×1 value, all four",
            ", ".join(p1_detail),
            p1,
        )
    )

    worst_free, worst_somm = 0.0, 0.0
    for c in cases:
        if c[1] != "stock":
            continue
        for rung in (*LADDER, SERVED):
            for i in range(len(case_recs(recs, c, rung)["razor"]["z"])):
                v = gap(recs, c, rung, "razor", REF, i)
                if v is None:
                    continue
                if c[2] == "free":
                    worst_free = max(worst_free, v)
                else:
                    worst_somm = max(worst_somm, v)
    p2 = worst_free <= 0.01 and worst_somm <= 0.025
    scored.append(
        (
            "P2",
            "razor−NEC-5 ≤ 1 % at every free rung, ≤ 2.5 % at every Sommerfeld rung",
            f"worst free {pct(worst_free)}, worst somm {pct(worst_somm)}",
            p2,
        )
    )

    total_other = sum(verdicts[c][6] for c in cases)
    scored.append(
        (
            "P3",
            "razor/NEC-5 meshes identical; bs2 differs only on the fed edge",
            f"{total_other} rung(s) with any other difference",
            total_other == 0,
        )
    )

    sky = ("loops.skyloop_lmatch", "stock", "free")
    bare = ("loops.skyloop_lmatch", "bare", "free")
    ratios, p4 = [], True
    for rung in (*LADDER, SERVED):
        a = gap(recs, sky, rung, "bs2", REF)
        b = gap(recs, bare, rung, "bs2", REF)
        if a is None or b is None or b == 0:
            continue
        ratios.append(f"×{rung}: {a / b:.2f}")
        if a / b <= 1.2:
            p4 = False
    scored.append(
        (
            "P4",
            "L-match amplifies the bs2 gap by > 1.2× at every rung",
            ", ".join(ratios),
            p4,
        )
    )

    p5_detail, p5 = [], True
    for c in free_cases:
        cr1 = case_recs(recs, c, LADDER[0])["razor"]
        cr8 = case_recs(recs, c, LADDER[-1])["razor"]
        cr40 = case_recs(recs, c, SERVED)["razor"]
        base = abs(zc(cr1) - zc(cr8))
        served = abs(zc(cr40) - zc(cr8))
        r = served / base if base else None
        p5_detail.append(f"{c[0].split('.')[-1]} {r:.3f}×" if r else f"{c[0]} n/a")
        if r is None or r > 0.25:
            p5 = False
    scored.append(
        (
            "P5",
            "razor at the served mesh (×40) keeps ≤ 0.25 of its ×1 residual to ×8",
            ", ".join(p5_detail),
            p5,
        )
    )

    dora = [
        r["min_delta_over_a"]
        for r in recs.values()
        if r["status"] == "ok" and r.get("min_delta_over_a") is not None
    ]
    scored.append(
        (
            "P6",
            "min Δ/a stays above 30 at every rung of every design",
            f"minimum over all cells {min(dora):.1f}",
            min(dora) > 30.0,
        )
    )

    w("| prediction | bar | measured | verdict |")
    w("|---|---|---|---|")
    for tag, bar, got, ok in scored:
        w(f"| **{tag}** | {bar} | {got} | {'**HIT**' if ok else '**MISS**'} |")
    w("")
    w(f"Hit {sum(1 for *_x, ok in scored if ok)} of {len(scored)}.\n")

    notes = Path(__file__).with_name("hypotheses.md")
    if notes.is_file():
        w(notes.read_text(encoding="utf-8").rstrip())
        w("")

    sys.stdout.write("\n".join(out) + "\n")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
