"""AK#1523 surface option: the checks, predictions, answer rule and tables
PLAN.md registers.

  python scratch/1523-surface-option/analyze_surface.py scratch/1523-surface-option

Reads rows_main.jsonl and rows_pre.jsonl (study_surface.py) from that directory.
Written, and committed with the registration, before either exists. A missing,
refused or incomplete input is reported as missing, never passed. Writes
README.md and analysis.json beside the records.

A value printed in a deck is compared with its expected value to the deck's
printed resolution (half a unit in its last digit), widened by 1e-8 relative
for the mu0 spelling.
"""

from __future__ import annotations

import json
import math
import sys
from pathlib import Path

MOMWIRE_DOC_PAIR = 49.38 + 14.93j
SEVERNS_MEASURED = 56.1 + 6.2j
MAST_RADIUS = {"surface": 0.0005, "severns": 0.51e-3}
WIRE_TYPES = ("18-awg-pvc", "22-awg-pvc", "28-awg-pvc")
Q2 = (("b", "q1-18-awg-pvc"), ("2b", "q2-2b"), ("5b", "q2-5b"), ("20a", "q2-20a"))
MESH = (("m0-18", "q1-18-awg-pvc"), ("m1-28", "q1-28-awg-pvc"), ("m2-20a", "q2-20a"))
ALL_ARMS = (
    "nec5",
    "nec5_lonly",
    "nec5_pre",
    "razor",
    "bs2",
    "razor_lonly",
    "bs2_lonly",
)
PAIR_ARMS = ("nec5", "razor", "bs2")


def a_eq(a, b, eps):
    return a * (b / a) ** ((eps - 1.0) / eps)


def l_ins(a, b, eps):
    return 2e-7 * (1.0 - 1.0 / eps) * math.log(b / a)


def resolution(s):
    mant, _, exp = s.lower().partition("e")
    dec = len(mant.split(".")[1]) if "." in mant else 0
    return 0.5 * 10.0 ** ((int(exp) if exp else 0) - dec)


def printed_equal(s, expected):
    return abs(float(s) - expected) <= resolution(s) * (1 + 1e-9) + 1e-8 * abs(expected)


def verdict(cs, miss="MISS"):
    fails = [lab for lab, v in cs if v is False]
    gaps = [lab for lab, v in cs if v is None]
    word = miss if fails else ("incomplete (inputs missing)" if gaps else "hit")
    return {"verdict": word, "fails": fails, "missing": gaps, "instances": len(cs)}


def main():
    here = Path(sys.argv[1])
    rows, metas = {}, {}
    for name in ("rows_main.jsonl", "rows_pre.jsonl"):
        path = here / name
        if not path.exists():
            continue
        for line in path.read_text().splitlines():
            rec = json.loads(line)
            if rec.get("_meta"):
                metas[rec["tree"]] = rec
            else:
                rows[rec["cell"], rec["arm"]] = rec

    def ok(cell, arm):
        rec = rows.get((cell, arm))
        return (
            rec
            if rec is not None and rec.get("status") == "ok" and "z" in rec
            else None
        )

    def z(cell, arm):
        rec = ok(cell, arm)
        return complex(*rec["z"]) if rec else None

    def rel(u, v):
        return None if u is None or v is None else abs(u - v) / abs(v)

    def gap(cell, arm):
        return rel(z(cell, arm), z(cell, "razor"))

    def shift(cell, engine):
        return rel(z(cell, engine), z(cell, f"{engine}_lonly"))

    def cmp(v, fn):
        return None if v is None else bool(fn(v))

    checks, preds, extra = {}, {}, {}

    # ------------------------------------------------------------ K0
    k0 = []
    for (cell, arm), rec in sorted(rows.items()):
        label = f"{cell} {arm}"
        if rec.get("status") != "ok":
            k0.append((label, None))
            continue
        a, b, eps, sig = rec["a"], rec["b"], rec["eps_r"], rec["sigma"]
        pair = arm in PAIR_ARMS
        kern = a_eq(a, b, eps) if pair else a
        if arm.startswith("nec5"):
            dc = rec.get("deck_cards") or {}
            if "gw" not in dc:
                k0.append((label, False))
                continue
            radial = {g["tag"] for g in dc["gw"] if g["p0"][2] == g["p1"][2]}
            other = {g["tag"] for g in dc["gw"]} - radial
            ld5 = {int(f[1]): f[4] for f in dc["ld"] if f[0] == "5"}
            ld2 = {int(f[1]): f[5] for f in dc["ld"] if f[0] == "2"}
            good = bool(radial) and all(
                printed_equal(g["radius"], kern) for g in dc["gw"] if g["tag"] in radial
            )
            good = good and all(
                t in ld2 and printed_equal(ld2[t], l_ins(a, b, eps)) for t in radial
            )
            good = good and not (set(ld2) & other) and not (set(ld5) & other)
            if sig is None:
                good = good and not (set(ld5) & radial)
            else:
                want = sig * (a / kern) ** 2 if pair else sig
                good = good and all(
                    t in ld5 and printed_equal(ld5[t], want) for t in radial
                )
            k0.append((label, good))
        else:
            kr = rec.get("kernel_radius")
            mast = MAST_RADIUS[rec["deck"]]
            if not kr:
                k0.append((label, False))
                continue
            good = any(abs(k / kern - 1) <= 1e-12 for k in kr) and all(
                abs(k / kern - 1) <= 1e-12 or abs(k / mast - 1) <= 1e-12 for k in kr
            )
            k0.append((label, good))
    if not rows:
        k0.append(("rows", None))
    checks["K0"] = verdict(k0, "FAIL")

    # ------------------------------------------------------------ K1
    k1, k1_table = [], []
    for cell in sorted({c for c, arm in rows if arm == "nec5_pre"}):
        zl, zp = z(cell, "nec5_lonly"), z(cell, "nec5_pre")
        d = None if None in (zl, zp) else abs(zl - zp)
        k1.append((cell, cmp(d, lambda v: v <= 5e-3)))
        k1_table.append((cell, zl, zp, d))
    if not k1:
        k1.append(("nec5_pre rows", None))
    checks["K1"] = verdict(k1, "FAIL")

    # ------------------------------------------------------------ A0, A1
    a0, a1 = [], []
    for (cell, arm), rec in sorted(rows.items()):
        if arm.startswith("nec5"):
            zz = z(cell, arm)
            a0.append(
                (
                    f"{cell} {arm}",
                    False
                    if rec.get("status") != "ok"
                    else cmp(zz, lambda v: math.isfinite(abs(v)) and 0 < v.real < 2000),
                )
            )
        else:
            a1.append((f"{cell} {arm} served", rec.get("status") == "ok"))
    advisory_cells = {}
    for (cell, arm), rec in rows.items():
        if arm.startswith("nec5") or cell.endswith("20a"):
            continue
        if rec["h_eff"] / rec["a"] >= 20.0:
            continue
        text = json.dumps(rec.get("advisories", []))
        hit = "SurfaceRadialHeight" in text or "a conductor lies within" in text.lower()
        advisory_cells.setdefault(cell, []).append((arm, hit))
    for cell, arms in sorted(advisory_cells.items()):
        a1.append((f"{cell} advisory", any(h for _arm, h in arms)))
    extra["advisory_by_arm"] = {c: dict(v) for c, v in advisory_cells.items()}
    preds["A0"] = verdict(a0)
    preds["A1"] = verdict(a1)

    # ------------------------------------------------------------ Q1
    b1, b1o, b2a, b2b, b3 = [], [], [], [], []
    sh = {}
    for wt in WIRE_TYPES:
        cell = f"q1-{wt}"
        sh[wt] = shift(cell, "nec5")
        b1.append((wt, cmp(sh[wt], lambda v: v >= 0.05)))
        gp, gl = gap(cell, "nec5"), gap(cell, "nec5_lonly")
        b2a.append((wt, None if None in (gp, gl) else gp < gl))
        b2b.append((wt, cmp(gp, lambda v: v > 0.003)))
        dn = (
            None
            if None in (z(cell, "nec5"), z(cell, "nec5_lonly"))
            else abs(z(cell, "nec5") - z(cell, "nec5_lonly"))
        )
        dr = (
            None
            if None in (z(cell, "razor"), z(cell, "razor_lonly"))
            else abs(z(cell, "razor") - z(cell, "razor_lonly"))
        )
        ratio = None if None in (dn, dr) or dr == 0 else dn / dr
        extra.setdefault("B3_ratio", {})[wt] = ratio
        b3.append((wt, cmp(ratio, lambda v: 0.75 <= v <= 1.25)))
    s18, s22, s28 = (sh[w] for w in WIRE_TYPES)
    b1o.append(("28 > 22 > 18", None if None in (s18, s22, s28) else s28 > s22 > s18))
    preds.update(
        B1=verdict(b1),
        B1o=verdict(b1o),
        B2a=verdict(b2a),
        B2b=verdict(b2b),
        B3=verdict(b3),
    )

    # ------------------------------------------------------------ Q2
    gb, g5, g20 = (
        gap("q1-18-awg-pvc", "nec5"),
        gap("q2-5b", "nec5"),
        gap("q2-20a", "nec5"),
    )
    c1 = [("20a below b", None if None in (gb, g20) else g20 < gb)]
    c1.append(("20a <= 1 %", cmp(g20, lambda v: v <= 0.01)))
    c2 = [("5b <= b/5", None if None in (gb, g5) else g5 <= gb / 5)]
    c3 = []
    for arm in ("bs2", "razor", "nec5"):
        z1, z2 = z("q1-18-awg-pvc", arm), z("q2-2b", arm)
        d = None if None in (z1, z2) else z2 - z1
        c3.append((arm, None if d is None else (abs(d) >= 5.0 and d.imag < 0)))
    sb, s20 = shift("q1-18-awg-pvc", "nec5"), shift("q2-20a", "nec5")
    c4 = [("shift 20a < b", None if None in (sb, s20) else s20 < sb)]
    preds.update(C1=verdict(c1), C2=verdict(c2), C3=verdict(c3), C4=verdict(c4))

    # ------------------------------------------------------------ M
    m, m_table = [], []
    more = {"razor": 0, "nec5": 0}
    complete = True
    for fine, base in MESH:
        mv = {arm: rel(z(fine, arm), z(base, arm)) for arm in PAIR_ARMS}
        m.append((f"{fine} bs2 <= 1 %", cmp(mv["bs2"], lambda v: v <= 0.01)))
        for arm in ("razor", "nec5"):
            if None in (mv[arm], mv["bs2"]):
                complete = False
            elif mv[arm] > mv["bs2"]:
                more[arm] += 1
        m_table.append((fine, base, mv, gap(base, "nec5"), gap(fine, "nec5")))
    for arm in ("razor", "nec5"):
        m.append(
            (
                f"{arm} moves more than bs2 on >= 2 cells",
                more[arm] >= 2 if complete else None,
            )
        )
    preds["M"] = verdict(m)

    # ------------------------------------------------------------ Severns
    zb = z("severns", "bs2")
    s1 = [
        (
            "bs2 vs momwire docstring",
            None if zb is None else abs(zb - MOMWIRE_DOC_PAIR) <= 5.0,
        )
    ]
    s2 = []
    for arm in PAIR_ARMS:
        zz = z("severns", arm)
        s2.append(
            (
                arm,
                None
                if zz is None
                else abs(zz.real - SEVERNS_MEASURED.real) <= 18.0
                and abs(zz.imag - SEVERNS_MEASURED.imag) <= 18.0,
            )
        )
    zn, znl = z("severns", "nec5"), z("severns", "nec5_lonly")
    s3 = [("X_lonly > X_pair", None if None in (zn, znl) else znl.imag > zn.imag)]
    preds.update(S1=verdict(s1), S2=verdict(s2), S3=verdict(s3))

    # ------------------------------------------------------------ answer rule
    if checks["K0"]["verdict"] != "hit" or checks["K1"]["verdict"] != "hit":
        failed = [q for q in ("K0", "K1") if checks[q]["verdict"] != "hit"]
        rule = f"stop: {', '.join(failed)} did not pass"
    elif preds["A0"]["verdict"] != "hit":
        rule = "stop: NEC-5 did not serve every cell (A0); see the refusals"
    elif preds["B2a"]["verdict"] == "hit" and preds["B2b"]["verdict"] == "hit":
        rule = (
            "near ground the pair narrows but does not close razor-2p vs NEC-5; "
            "the near-ground signature is gap_pair"
        )
    elif preds["B2a"]["verdict"] == "hit" and preds["B2b"]["verdict"] == "MISS":
        rule = "the pair closes the gap near ground as in free space"
    elif preds["B2a"]["verdict"] == "MISS":
        rule = "near ground the pair does not narrow the gap: a different signature"
    else:
        rule = "incomplete"

    # ------------------------------------------------------------ tables
    def fz(v):
        return "—" if v is None else f"{v.real:.3f}{v.imag:+.3f}j"

    def fp(v, digits=2):
        return "—" if v is None else f"{100 * v:.{digits}f}"

    def fx(v, fmt=".3f"):
        return "—" if v is None else format(v, fmt)

    mm = metas.get("main", {})
    mp = metas.get("pre", {})
    out = [
        "# AK#1523 surface option: #1532's pair near ground",
        "",
        "Registration: `PLAN.md`. Records: `rows_main.jsonl`, `rows_pre.jsonl` "
        "(`study_surface.py`).",
        f"antennaknobs main `{mm.get('antennaknobs_head')}`, pre-#1532 "
        f"`{mp.get('antennaknobs_head')}`; momwire `{mm.get('momwire_head')}`; "
        f"NEC-5 sha256 `{(mm.get('nec5_sha256') or '')[:8]}`.",
        "",
        "## Checks and predictions",
        "",
        "| id | verdict | instances | failing |",
        "|---|---|---:|---|",
    ]
    for q, res in [*checks.items(), *preds.items()]:
        fails = res["fails"] + [f"{x} (missing)" for x in res["missing"]]
        shown = ", ".join(fails[:8]) + (
            f" … (+{len(fails) - 8})" if len(fails) > 8 else ""
        )
        out.append(f"| {q} | {res['verdict']} | {res['instances']} | {shown or '—'} |")
    out += ["", f"**Answer rule:** {rule}.", "", "## Q0: every row", ""]
    out += [
        "| cell | arm | status | segments | Z Ω | advisories | warnings | s |",
        "|---|---|---|---:|---|---:|---:|---:|",
    ]
    for (cell, arm), rec in sorted(rows.items()):
        out.append(
            f"| {cell} | {arm} | {rec['status']} | {rec.get('meshed', '—')} | "
            f"{fz(z(cell, arm))} | {len(rec.get('advisories', [])) if 'advisories' in rec else '—'} | "
            f"{len(rec.get('warnings', []))} | {rec.get('secs')} |"
        )
    refusals = [(k, r) for k, r in sorted(rows.items()) if r.get("status") != "ok"]
    out += ["", "### Refusals, verbatim", ""]
    if not refusals:
        out.append("None.")
    for (cell, arm), rec in refusals:
        out += [f"- {cell} {arm}, `{rec.get('error_type')}`:", "", "  ```text"]
        out += [f"  {ln}" for ln in str(rec.get("error", "")).splitlines()]
        out += ["  ```", ""]
    out += ["", "### momwire advisories and warnings, verbatim (first of each)", ""]
    seen = set()
    for (cell, arm), rec in sorted(rows.items()):
        for item in rec.get("advisories", []) + rec.get("warnings", []):
            text = json.dumps(item) if not isinstance(item, str) else item
            key = text[:120]
            if key in seen:
                continue
            seen.add(key)
            out += [f"- first seen on {cell} {arm}:", "", "  ```text"]
            out += [f"  {ln}" for ln in text[:1500].splitlines()]
            out += ["  ```", ""]
    out += [
        "",
        "## Q1: the three PVC wires at h = b, nominal_nsegs 21",
        "",
        "| wire | nec5 | nec5_lonly | nec5_pre | razor | bs2 | razor_lonly | bs2_lonly |",
        "|---|---|---|---|---|---|---|---|",
    ]
    for wt in WIRE_TYPES:
        cell = f"q1-{wt}"
        out.append(f"| {wt} | " + " | ".join(fz(z(cell, a)) for a in ALL_ARMS) + " |")
    out += [
        "",
        "gap_t = \\|Z_nec5,t − Z_razor\\|/\\|Z_razor\\|; shift_e = \\|Z_e − Z_e,Lonly\\|/\\|Z_e,Lonly\\|.",
        "",
        "| wire | shift nec5 % | shift razor % | shift bs2 % | B3 ratio | gap_pair % | "
        "gap_Lonly % | nec5 vs bs2 % | razor vs bs2 % |",
        "|---|---:|---:|---:|---:|---:|---:|---:|---:|",
    ]
    for wt in WIRE_TYPES:
        cell = f"q1-{wt}"
        out.append(
            f"| {wt} | {fp(shift(cell, 'nec5'))} | {fp(shift(cell, 'razor'))} | "
            f"{fp(shift(cell, 'bs2'))} | {fx(extra['B3_ratio'].get(wt))} | "
            f"{fp(gap(cell, 'nec5'), 3)} | {fp(gap(cell, 'nec5_lonly'), 3)} | "
            f"{fp(rel(z(cell, 'nec5'), z(cell, 'bs2')), 3)} | "
            f"{fp(rel(z(cell, 'razor'), z(cell, 'bs2')), 3)} |"
        )
    out += [
        "",
        "## Q2: 18-awg-pvc stand-off ladder, nominal_nsegs 21",
        "",
        "| h | h mm | h/a | h/a′ | nec5 | nec5_lonly | razor | bs2 | gap_pair % | "
        "gap_Lonly % | nec5 vs bs2 % | razor vs bs2 % | shift nec5 % |",
        "|---|---:|---:|---:|---|---|---|---|---:|---:|---:|---:|---:|",
    ]
    for tag, cell in Q2:
        rec = rows.get((cell, "nec5")) or rows.get((cell, "bs2")) or {}
        he, a, b, eps = rec.get("h_eff"), rec.get("a"), rec.get("b"), rec.get("eps_r")
        ratio_a = None if None in (he, a) else he / a
        ratio_ae = None if None in (he, a, b, eps) else he / a_eq(a, b, eps)
        out.append(
            f"| {tag} | {fx(None if he is None else he * 1e3)} | {fx(ratio_a, '.2f')} | "
            f"{fx(ratio_ae, '.2f')} | {fz(z(cell, 'nec5'))} | {fz(z(cell, 'nec5_lonly'))} | "
            f"{fz(z(cell, 'razor'))} | {fz(z(cell, 'bs2'))} | {fp(gap(cell, 'nec5'), 3)} | "
            f"{fp(gap(cell, 'nec5_lonly'), 3)} | {fp(rel(z(cell, 'nec5'), z(cell, 'bs2')), 3)} | "
            f"{fp(rel(z(cell, 'razor'), z(cell, 'bs2')), 3)} | {fp(shift(cell, 'nec5'))} |"
        )
    out += [
        "",
        "## Mesh: nominal_nsegs 21 → 42",
        "",
        "| cell | bs2 move % | razor move % | nec5 move % | gap_pair at 21 % | gap_pair at 42 % |",
        "|---|---:|---:|---:|---:|---:|",
    ]
    for fine, _base, mv, g_base, g_fine in m_table:
        out.append(
            f"| {fine} | {fp(mv['bs2'], 3)} | {fp(mv['razor'], 3)} | {fp(mv['nec5'], 3)} | "
            f"{fp(g_base, 3)} | {fp(g_fine, 3)} |"
        )
    out += [
        "",
        "## Severns surface deck (N = 16, h = 1.6 mm)",
        "",
        f"Measured {fz(SEVERNS_MEASURED)}; momwire's docstring a′ + L {fz(MOMWIRE_DOC_PAIR)}.",
        "",
        "| arm | Z | R − 56.1 | X − 6.2 | \\|Z − docstring\\| |",
        "|---|---|---:|---:|---:|",
    ]
    for arm in ("nec5", "nec5_lonly", "nec5_pre", "razor", "bs2"):
        zz = z("severns", arm)
        out.append(
            f"| {arm} | {fz(zz)} | "
            f"{fx(None if zz is None else zz.real - SEVERNS_MEASURED.real, '+.2f')} | "
            f"{fx(None if zz is None else zz.imag - SEVERNS_MEASURED.imag, '+.2f')} | "
            f"{fx(None if zz is None else abs(zz - MOMWIRE_DOC_PAIR), '.2f')} |"
        )
    out += [
        "",
        "## K1: the monkeypatched inductance-only spelling against pre-#1532",
        "",
        "| cell | nec5_lonly (main) | nec5_pre | \\|Δ\\| Ω |",
        "|---|---|---|---:|",
    ]
    for cell, zl, zp, d in k1_table:
        out.append(f"| {cell} | {fz(zl)} | {fz(zp)} | {fx(d, '.4f')} |")
    out.append("")
    (here / "README.md").write_text("\n".join(out))
    (here / "analysis.json").write_text(
        json.dumps(
            {"checks": checks, "predictions": preds, "extra": extra, "rule": rule},
            indent=1,
        )
    )
    print("\n".join(out[: 14 + len(checks) + len(preds)]))


if __name__ == "__main__":
    main()
