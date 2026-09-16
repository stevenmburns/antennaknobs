"""Re-cut the three density records on ΔΓ. Arithmetic only — nothing is re-solved.

    python scratch/1553-gamma-recut/recut_gamma.py

Writes one dated "ΔΓ re-cut" fragment per study, which each study's own
`hypotheses.md` carries and its `report.py` includes, so every README regenerates
with the new section in place and no number is transcribed.

Γ = (Z − Z0)/(Z + Z0), Z0 = 50 Ω. For a passive antenna R ≥ 0, so Z + Z0 has real
part ≥ Z0 > 0: Γ is never singular and |Γ| ≤ 1, which bounds ΔΓ on [0, 2]. That is
the property the relative-Z metric lacks, and the reason a row sitting at a
near-cancellation can read 240 % on one metric and 0.03 on the other.

MULTI-PORT ROWS REPORT BOTH the max over ports and the vector norm. The old
relative-Z column was a vector norm, so the norm is what compares with it; the max
is what a user of any single port experiences. Every table says which is which.
"""

from __future__ import annotations

import json
import math
import statistics
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
HERE = Path(__file__).resolve().parent
Z0 = 50.0


def gamma(z):
    return (z - Z0) / (z + Z0)


def load(p):
    recs, prov = {}, None
    for line in open(p, encoding="utf-8"):
        r = json.loads(line)
        if "design" not in r:
            prov = r
            continue
        recs[(r["design"], r["ground"], r["rung"], r["engine"])] = r
    return recs, prov


def zv(r):
    return (
        [complex(*p) for p in r["z"]]
        if r and r.get("z") and r["status"] == "ok"
        else None
    )


def dgam(a, b):
    """(max over ports, vector norm) of |Γ_a − Γ_b|, or (None, None)."""
    if a is None or b is None or len(a) != len(b):
        return None, None
    d = [abs(gamma(x) - gamma(y)) for x, y in zip(a, b, strict=True)]
    return max(d), math.sqrt(sum(v * v for v in d))


def dzrel(a, b):
    if a is None or b is None or len(a) != len(b):
        return None, None
    n = math.sqrt(sum(abs(x - y) ** 2 for x, y in zip(a, b, strict=True)))
    den = math.sqrt(sum(abs(y) ** 2 for y in b))
    return n, (n / den if den else None)


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
    return -(sum((x - mx) * (y - my) for x, y in pts) / sxx) if sxx else None


def q(v, p):
    s = sorted(v)
    return s[min(len(s) - 1, int(p * len(s)))] if s else None


def f(x, n=4):
    return "—" if x is None else f"{x:.{n}f}"


# ---------------------------------------------------------------- #1525
def recut_1525():
    recs, _ = load(ROOT / "scratch/1525-razor-density/records.jsonl")
    RUNGS, GR = (21, 40, 80, 160), ("free", "somm")
    designs = sorted({k[0] for k in recs})
    rows = {}
    for d in designs:
        for g in GR:
            ref = zv(recs.get((d, g, 160, "bs2")))
            prev = zv(recs.get((d, g, 80, "bs2")))
            if ref is None:
                continue
            mv_max, mv_nrm = dgam(prev, ref)
            for e in ("razor", "bs2"):
                cells = [recs.get((d, g, r, e)) for r in RUNGS]
                if any(c is None or c["status"] != "ok" for c in cells):
                    continue
                gm = [dgam(zv(c), ref)[1] for c in cells]
                ns = [c.get("total_nominal_segs") for c in cells]
                rows[(e, d, g)] = {"g": gm, "ns": ns, "mv": mv_nrm}
    out, cls = [], {}
    for e in ("razor", "bs2"):
        sel = {k: v for k, v in rows.items() if k[0] == e}
        c = {}
        for k, v in sel.items():
            gm = v["g"]
            if any(x is None for x in gm) or gm[0] == 0:
                lab = "no error to fit"
            elif e == "bs2":
                lab = "reference self-check"
            elif v["mv"] is not None and v["mv"] > gm[0] / 3:
                lab = "reference unsettled"
            elif gm[-1] < gm[-2] < gm[0]:
                lab = "converging"
            elif gm[-1] >= gm[0]:
                lab = "not converging"
            else:
                lab = "non-monotone"
            c[lab] = c.get(lab, 0) + 1
            v["class"] = lab
        cls[e] = c
    conv = [
        fit_order(v["ns"], v["g"])
        for k, v in rows.items()
        if k[0] == "razor" and v.get("class") == "converging"
    ]
    conv = [x for x in conv if x is not None]
    served = [
        v["g"][RUNGS.index(40)]
        for k, v in rows.items()
        if k[0] == "razor"
        and v.get("class") == "converging"
        and v["g"][RUNGS.index(40)]
    ]
    out.append("\n## ΔΓ re-cut, 2026-09-16\n")
    out.append(
        "Re-cut of this record on **ΔΓ = |Γ_a − Γ_b|**, `Γ = (Z − 50)/(Z + 50)`, "
        "the metric `docs/status/2026-07-16-nec2c-corpus-benchmark.md` uses. "
        "**No cell was re-solved** — every record stores Z per port. The "
        "relative-Z columns above are unchanged and stay; ΔΓ is reported as the "
        "**vector norm over ports**, which is what compares with the `|ΔZ|` norm "
        "used above.\n"
    )
    out.append("| class (razor-2p vs bs2@160) | on relative Z | on ΔΓ |")
    out.append("|---|---:|---:|")
    prior = {
        "converging": 155,
        "reference unsettled": 30,
        "non-monotone": 12,
        "not converging": 2,
    }
    for lab in ("converging", "reference unsettled", "non-monotone", "not converging"):
        out.append(f"| {lab} | {prior.get(lab, 0)} | {cls['razor'].get(lab, 0)} |")
    out.append("")
    out.append(
        f"The relative-Z column counts 5 refused and 2 skipped rows that ΔΓ's "
        f"table omits (they have no Z to transform), so the ΔΓ column totals "
        f"{sum(cls['razor'].values())} where the other totals 206.\n"
    )
    if conv:
        out.append(
            f"Fitted order on razor-2p's converging rows, **on ΔΓ**: median "
            f"**{statistics.median(conv):.2f}** over {len(conv)} rows "
            f"(relative Z gave 0.90).\n"
        )
    if served:
        out.append(
            f"razor-2p at its ×40 rung, over converging rows: median ΔΓ "
            f"**{f(statistics.median(served))}**, p90 **{f(q(served, 0.90))}**, "
            f"worst **{f(q(served, 1.0))}** — against a relative-Z median of "
            f"2.42 %.\n"
        )
    return "\n".join(out), rows, cls


# ---------------------------------------------------------------- #1543
def recut_1543():
    recs, _ = load(ROOT / "scratch/1543-bspline-served-density/records.jsonl")
    lad, _ = load(ROOT / "scratch/1525-razor-density/records.jsonl")
    SERVED = {"bs1": 20, "bs2": 15, "bs3": 12}
    GR = ("free", "somm")
    designs = sorted({k[0] for k in recs})
    res = {}
    for e, rung in SERVED.items():
        adm, unres = [], []
        for d in designs:
            for g in GR:
                ref = zv(lad.get((d, g, 160, "bs2")))
                prev = zv(lad.get((d, g, 80, "bs2")))
                c = zv(recs.get((d, g, rung, e)))
                if ref is None or prev is None or c is None:
                    continue
                _mx, gm = dgam(c, ref)
                _mvx, mv = dgam(prev, ref)
                if gm is None:
                    continue
                if gm > 0 and mv is not None and mv > gm / 3:
                    unres.append((d, g, gm))
                else:
                    adm.append((d, g, gm))
        res[e] = (adm, unres)
    # razor@40 on the same rule
    radm = []
    for d in designs:
        for g in GR:
            ref = zv(lad.get((d, g, 160, "bs2")))
            prev = zv(lad.get((d, g, 80, "bs2")))
            c = zv(lad.get((d, g, 40, "razor")))
            if ref is None or prev is None or c is None:
                continue
            _mx, gm = dgam(c, ref)
            _mvx, mv = dgam(prev, ref)
            if gm is None or (gm > 0 and mv is not None and mv > gm / 3):
                continue
            radm.append(gm)
    o = ["\n## ΔΓ re-cut, 2026-09-16\n"]
    o.append(
        "Same rows, same reference, **no cell re-solved** — re-scored on "
        "**ΔΓ**, with the admissibility rule itself re-stated on ΔΓ (bs2's own "
        "×80→×160 move in Γ under a third of the ΔΓ being judged). Relative-Z "
        "columns above are unchanged. ΔΓ is the **vector norm over ports**.\n"
    )
    o.append(
        "| basis | served N | admissible | median ΔΓ | p90 | worst | median rel-Z (above) |"
    )
    o.append("|---|---:|---:|---:|---:|---:|---:|")
    prior_med = {"bs1": "1.53 %", "bs2": "0.964 %", "bs3": "1.11 %"}
    for e in ("bs1", "bs2", "bs3"):
        adm, _u = res[e]
        v = [x[2] for x in adm]
        o.append(
            f"| d={e[-1]} | {SERVED[e]} | {len(v)} | {f(statistics.median(v))} | "
            f"{f(q(v, 0.90))} | {f(q(v, 1.0))} | {prior_med[e]} |"
        )
    o.append("")
    if radm:
        o.append(
            f"**razor-2p at 40 on the same rule**: median ΔΓ "
            f"**{f(statistics.median(radm))}** over {len(radm)} admissible rows. "
            f"On ΔΓ there is no 2.42-versus-2.72 population question — that split "
            f"was an artefact of two relative-Z cuts, and it retires here.\n"
        )
    o.append("| basis | admissible on rel-Z | admissible on ΔΓ | unresolved on ΔΓ |")
    o.append("|---|---:|---:|---:|")
    prior_adm = {"bs1": 149, "bs2": 147, "bs3": 158}
    for e in ("bs1", "bs2", "bs3"):
        adm, unres = res[e]
        o.append(f"| d={e[-1]} | {prior_adm[e]} | {len(adm)} | {len(unres)} |")
    o.append("")
    return "\n".join(o), res


# ---------------------------------------------------------------- #1552
def recut_1552():
    recs, _ = load(ROOT / "scratch/1552-bspline-tail/records.jsonl")
    D = ("dipoles.short_dipole_loaded", "specialty.continuous_helix", "wire.zepp")
    LAD = {"bs3": (12, 15, 20, 30), "bs2": (15, 20, 30)}
    o = ["\n## ΔΓ re-cut, 2026-09-16\n"]
    o.append(
        "The same three ladders on **ΔΓ**, no cell re-solved. The verdicts are "
        "about *why* a row is far, so they are unchanged by the metric; what "
        "changes is how far it looks.\n"
    )
    o.append("| design | ground | basis | N | rel-Z | ΔΓ (norm) | ΔΓ (max port) |")
    o.append("|---|---|---|---:|---:|---:|---:|")
    summary = {}
    for d in D:
        for g in ("free", "somm"):
            ref = zv(recs.get((d, g, 160, "bs2")))
            if ref is None:
                continue
            for e, rungs in LAD.items():
                for n in rungs:
                    c = zv(recs.get((d, g, n, e)))
                    if c is None:
                        continue
                    _o, rel = dzrel(c, ref)
                    mx, nrm = dgam(c, ref)
                    o.append(
                        f"| `{d}` | {g} | {e} | {n} | {100 * rel:.0f} % | "
                        f"{f(nrm)} | {f(mx)} |"
                    )
                    if (e, n) in (("bs3", 12), ("bs2", 15)) and g == "free":
                        summary.setdefault(d, {})[e] = (rel, nrm)
    o.append("")
    o.append("At each design's **served** rung, free space:\n")
    o.append("| design | basis | relative Z | ΔΓ |")
    o.append("|---|---|---:|---:|")
    for d, v in summary.items():
        for e, (rel, nrm) in sorted(v.items()):
            o.append(f"| `{d}` | {e} | {100 * rel:.0f} % | **{f(nrm)}** |")
    o.append("")
    # ---- the verdicts, recomputed on the bounded metric
    o.append("### The verdicts on ΔΓ — one of the three changes\n")
    o.append(
        "| design | verdict on relative Z | verdict on ΔΓ | ΔΓ fall 12→30 | reference's own ΔΓ at 320 | reference / row |"
    )
    o.append("|---|---|---|---:|---:|---:|")
    prior = {
        "dipoles.short_dipole_loaded": "reference",
        "specialty.continuous_helix": "density",
        "wire.zepp": "placement",
    }
    verd = {}
    for d in D:
        ref = zv(recs.get((d, "free", 160, "bs2")))
        lad = (12, 15, 20, 30)
        lo = dgam(zv(recs.get((d, "free", lad[0], "bs3"))), ref)[1]
        hi = dgam(zv(recs.get((d, "free", lad[-1], "bs3"))), ref)[1]
        mv = dgam(zv(recs.get((d, "free", 320, "bs2"))), ref)[1]
        fl = (recs.get((d, "free", lad[0], "bs3")) or {}).get("fed_segments")
        fh = (recs.get((d, "free", lad[-1], "bs3")) or {}).get("fed_segments")
        fl = fl[0]["length_m"] if isinstance(fl, list) and fl else None
        fh = fh[0]["length_m"] if isinstance(fh, list) and fh else None
        fell = (1 - hi / lo) if (lo and hi) else None
        refines = bool(fl and fh and fh < 0.9 * fl)
        ratio = (mv / lo) if (mv and lo) else None
        if fell is not None and fell >= 0.40 and ratio is not None and ratio < 1 / 3:
            v = "density"
        elif fell is not None and fell < 0.20 and not refines:
            v = "placement"
        elif ratio is not None and ratio >= 1 / 3:
            v = "reference"
        else:
            v = "unexplained"
        verd[d] = v
        mark = " **(changed)**" if v != prior[d] else ""
        o.append(
            f"| `{d}` | {prior[d]} | **{v}**{mark} | {100 * fell:.0f} % | "
            f"{f(mv)} | {ratio:.3f} |"
        )
    o.append("")
    return "\n".join(o), verd


def main():
    a, _rows, _cls = recut_1525()
    b, _res = recut_1543()
    c, _sm = recut_1552()
    (HERE / "recut-1525.md").write_text(a, encoding="utf-8")
    (HERE / "recut-1543.md").write_text(b, encoding="utf-8")
    (HERE / "recut-1552.md").write_text(c, encoding="utf-8")
    print(a)
    print(b)
    print(c)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
