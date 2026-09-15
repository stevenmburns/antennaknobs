"""AK#1523: the checks, predictions, verdict and tables PLAN.md registers.

  python scratch/1523-insulated-wire/analyze_1523.py scratch/1523-insulated-wire

Reads reference.json (tm0_mode.py) and rows.jsonl (study_1523.py) from that
directory. Written, and committed with the registration, before either exists.
A missing or errored input is reported as missing, never passed. Writes
README.md and analysis.json beside the records.

A read-back value printed in a deck is compared with its expected value to the
deck's printed resolution (half a unit in its last digit), widened by 1e-8
relative for the mu0 spelling momwire and scipy may differ in.
"""

from __future__ import annotations

import itertools
import json
import math
import sys
from pathlib import Path

from scipy import stats

sys.path.insert(0, str(Path(__file__).resolve().parent))

from jackets import BARE, JACKETS, bare_of

FINE, COARSE = 161, 41
ENGINES = ("bs2", "razor", "nec5")
NAMES = list(JACKETS)


def key(name):
    _a, b, eps = JACKETS[name]
    return (1.0 - 1.0 / eps) * math.log(b / JACKETS[name][0])


def verdict(cs, miss="MISS"):
    fails = [lab for lab, v in cs if v is False]
    gaps = [lab for lab, v in cs if v is None]
    word = miss if fails else ("incomplete (inputs missing)" if gaps else "hit")
    return {"verdict": word, "fails": fails, "missing": gaps, "instances": len(cs)}


def resolution(s):
    mant, _, exp = s.lower().partition("e")
    dec = len(mant.split(".")[1]) if "." in mant else 0
    return 0.5 * 10.0 ** ((int(exp) if exp else 0) - dec)


def printed_equal(s, expected):
    return abs(float(s) - expected) <= resolution(s) * (1 + 1e-9) + 1e-8 * abs(expected)


def main():
    here = Path(sys.argv[1])
    ref_path = here / "reference.json"
    ref = json.loads(ref_path.read_text()) if ref_path.exists() else None
    jref = ref["jackets"] if ref else {}
    rows, meta = {}, {}
    rows_path = here / "rows.jsonl"
    if rows_path.exists():
        for line in rows_path.read_text().splitlines():
            rec = json.loads(line)
            if rec.get("_meta"):
                meta = rec
            else:
                rows[rec["jacket"], rec["treatment"], rec["engine"], rec["n"]] = rec

    def ok(name, t, e, n):
        rec = rows.get((name, t, e, n))
        return rec if rec is not None and rec.get("status") == "ok" else None

    def lres(name, t, e, n):
        rec = ok(name, t, e, n)
        return rec["L_res"] if rec and rec.get("converged") else None

    def z(name, t, e, n):
        rec = ok(name, t, e, n)
        return complex(*rec["z_L0"]) if rec and "z_L0" in rec else None

    def sub(u, v):
        return None if u is None or v is None else u - v

    def gap(name, e, n=FINE):
        return sub(z(name, "pair", e, n), z(name, "lonly", e, n))

    checks, preds, extra = {}, {}, {}

    # ------------------------------------------------------------ C1, P0
    c1 = []
    if ref:
        for name, m in jref.items():
            c1.append((name, abs(m["z0_exact_vi_quad"] / m["z0_exact_vi"] - 1) <= 1e-6))
        lim = ref["limit_eps_1.001"]
        c1.append(
            (
                "eps_r 1.001",
                lim["s_exact"] > 0
                and abs(lim["beta_over_k0_pair"] / lim["beta_over_k0_exact"] - 1)
                <= 1e-6,
            )
        )
    else:
        c1.append(("reference.json", None))
    checks["C1"] = verdict(c1, "FAIL")

    p0 = []
    for (name, t, e, n), rec in sorted(rows.items()):
        label = f"{name} {t} {e} n={n}"
        if rec.get("status") != "ok":
            p0.append((label, None))
            continue
        a = rec["a"]
        if t == "pair":
            expect_r = jref[name]["a_eq"] if name in jref else None
        else:
            expect_r = a
        for rb_key in ("readback_res", "readback"):
            rb = rec.get(rb_key)
            if rb is None:
                continue
            if "error" in rb or expect_r is None:
                p0.append((f"{label} {rb_key}", None if expect_r is None else False))
                continue
            if e == "nec5":
                good = bool(rb["gw_radius"]) and all(
                    printed_equal(g, expect_r) for g in rb["gw_radius"]
                )
                if t == "bare":
                    good = good and not rb["ld2_l"]
                else:
                    l_ins = jref[name]["L_ins"] if name in jref else None
                    good = (
                        good
                        and l_ins is not None
                        and bool(rb["ld2_l"])
                        and all(printed_equal(v, l_ins) for v in rb["ld2_l"])
                    )
            else:
                good = bool(rb["kernel_radius"]) and all(
                    abs(k / expect_r - 1) <= 1e-12 for k in rb["kernel_radius"]
                )
            p0.append((f"{label} {rb_key}", good))
    if not rows:
        p0.append(("rows.jsonl", None))
    checks["P0"] = verdict(p0, "FAIL")

    # ------------------------------------------------------------ R1, R2
    r1, r2 = [], []
    for name in NAMES:
        m = jref.get(name)
        if m is None:
            r1.append((name, None))
            r2.append((name, None))
            continue
        be = m["beta_over_k0_exact"]
        ep = abs(m["beta_over_k0_pair"] / be - 1)
        el = abs(m["beta_over_k0_lonly"] / be - 1)
        r1.append((name, ep <= 1e-4 and el >= ep))
        r2.append((f"{name} pair", abs(m["z0_pair"] / m["z0_exact_vi"] - 1) <= 5e-3))
    if ref:
        m22 = jref["22-awg-pvc"]
        r2.append(
            (
                "22-awg-pvc L-only >= 1 %",
                m22["z0_lonly"] / m22["z0_exact_vi"] - 1 >= 0.01,
            )
        )
        rho = stats.spearmanr(
            [jref[n]["z0_lonly"] / jref[n]["z0_exact_vi"] - 1 for n in NAMES],
            [key(n) for n in NAMES],
        ).statistic
        extra["R2_rho"] = float(rho)
        r2.append(("L-only excess rank", bool(rho >= 0.9)))
        extra["R2_lonly_matches"] = all(
            abs(jref[n]["z0_lonly"] / jref[n]["z0_exact_vi"] - 1) <= 5e-3 for n in NAMES
        )
    preds["R1"] = verdict(r1)
    preds["R2"] = verdict(r2)
    r2_pair_hit = all(v is True for lab, v in r2 if lab.endswith(" pair"))

    # ------------------------------------------------------------ D1
    d1, d1_table = [], []
    for name in NAMES:
        c = bare_of(name)
        dz = {
            (t, e): sub(z(name, t, e, FINE), z(c, "bare", e, FINE))
            for t in ("pair", "lonly")
            for e in ENGINES
        }
        g = {e: gap(name, e) for e in ENGINES}
        worst = {}
        for t in ("pair", "lonly"):
            base = dz[t, "bs2"]
            worst[t] = None
            for e1, e2 in itertools.combinations(ENGINES, 2):
                if None in (dz[t, e1], dz[t, e2], base):
                    d1.append((f"{name} {t} {e1}-{e2}", None))
                    continue
                r = abs(dz[t, e1] - dz[t, e2]) / abs(base)
                worst[t] = r if worst[t] is None else max(worst[t], r)
                d1.append((f"{name} {t} {e1}-{e2}", r <= 0.10))
        worst["gap"] = None
        for e1, e2 in itertools.combinations(ENGINES, 2):
            if None in (g[e1], g[e2], g["bs2"]):
                d1.append((f"{name} gap {e1}-{e2}", None))
                continue
            r = abs(g[e1] - g[e2]) / abs(g["bs2"])
            worst["gap"] = r if worst["gap"] is None else max(worst["gap"], r)
            d1.append((f"{name} gap {e1}-{e2}", r <= 0.25))
        d1_table.append((name, worst))
    preds["D1"] = verdict(d1)

    # ------------------------------------------------------------ D2
    d2 = []
    extra["D2_rho"] = {}
    for e in ENGINES:
        g22, zl = gap("22-awg-pvc", e), z("22-awg-pvc", "lonly", e, FINE)
        d2.append(
            (
                f"{e} 22-awg-pvc",
                None if None in (g22, zl) else abs(g22) / abs(zl) >= 0.01,
            )
        )
        gs = [gap(n, e) for n in NAMES]
        if any(v is None for v in gs):
            d2.append((f"{e} rank", None))
            continue
        rho = float(
            stats.spearmanr([abs(v) for v in gs], [key(n) for n in NAMES]).statistic
        )
        extra["D2_rho"][e] = rho
        d2.append((f"{e} rank", rho >= 0.9))
    preds["D2"] = verdict(d2)

    # ------------------------------------------------------------ D3, D5
    d3, d5 = [], []
    for e in ENGINES:
        for name in NAMES:
            lp, ll = lres(name, "pair", e, FINE), lres(name, "lonly", e, FINE)
            lb = lres(bare_of(name), "bare", e, FINE)
            if None in (lp, ll, lb):
                d3.append((f"{e} {name}", None))
                continue
            shorten = 1 - ll / lb
            d3.append((f"{e} {name}", lp < ll and (1 - lp / ll) <= 0.25 * shorten))
        ll, lb = (
            lres("22-awg-pvc", "lonly", e, FINE),
            lres(bare_of("22-awg-pvc"), "bare", e, FINE),
        )
        d3.append(
            (
                f"{e} 22-awg-pvc shortens",
                None if None in (ll, lb) else 1 - ll / lb >= 0.01,
            )
        )
    for name in NAMES:
        lp = lres(name, "pair", "bs2", FINE)
        lb = lres(bare_of(name), "bare", "bs2", FINE)
        if None in (lp, lb) or name not in jref:
            d5.append((name, None))
            continue
        ratio = (1 - lp / lb) / jref[name]["s_mode"]
        d5.append((name, 0.9 <= ratio <= 1.5))
    preds["D3"] = verdict(d3)

    # ------------------------------------------------------------ D4
    d4, d4_table = [], []
    combos = [(c, "bare") for c in BARE] + [
        (n, t) for n in NAMES for t in ("pair", "lonly")
    ]
    for name, t in combos:
        for e in ENGINES:
            lc, lf = lres(name, t, e, COARSE), lres(name, t, e, FINE)
            label = f"{name} {t} {e}"
            if None in (lc, lf):
                d4.append((label, None))
                d4_table.append((name, t, e, lc, lf, None))
                continue
            change = abs(lf / lc - 1)
            d4.append((label, change <= (0.002 if e == "bs2" else 0.01)))
            d4_table.append((name, t, e, lc, lf, change))
    preds["D4"] = verdict(d4)
    preds["D5"] = verdict(d5)

    # ------------------------------------------------------------ verdict rule
    if checks["C1"]["verdict"] != "hit" or checks["P0"]["verdict"] != "hit":
        failed = [q for q in ("C1", "P0") if checks[q]["verdict"] != "hit"]
        rule = f"stop: {', '.join(failed)} did not pass; nothing else is read"
    elif preds["R2"]["verdict"] == "hit" and preds["D1"]["verdict"] == "hit":
        rule = (
            "the pair (momwire's path) matches the exact coated-line physics; LD 2 on "
            "the bare radius has the right velocity to first order but overstates the "
            "line impedance by about x"
        )
    elif not r2_pair_hit and extra.get("R2_lonly_matches"):
        rule = "L-only (the NEC-5 spelling) matches"
    elif preds["D1"]["verdict"] == "MISS":
        rule = (
            "the engines disagree within a treatment; the gap is not only the treatment"
        )
    else:
        rule = "unexplained"

    # ------------------------------------------------------------ tables
    def fz(v):
        return "—" if v is None else f"{v.real:.3f}{v.imag:+.3f}j"

    def fp(v, digits=3):
        return "—" if v is None else f"{100 * v:.{digits}f}"

    def fx(v, fmt=".4g"):
        return "—" if v is None else format(v, fmt)

    out = [
        "# AK#1523: insulated-wire treatments against the exact coated-line mode",
        "",
        "Registration: `PLAN.md`. Records: `reference.json` (`tm0_mode.py`) and "
        "`rows.jsonl` (`study_1523.py`).",
        f"momwire {meta.get('momwire_version', '?')} at `{meta.get('momwire_head')}`; "
        f"NEC-5 sha256 `{(meta.get('nec5_sha256') or '')[:8]}`.",
        "",
        "## Checks and predictions",
        "",
        "| id | verdict | instances | failing |",
        "|---|---|---:|---|",
    ]
    for q, res in [*checks.items(), *preds.items()]:
        fails = res["fails"] + [f"{m} (missing)" for m in res["missing"]]
        shown = ", ".join(fails[:8]) + (
            f" … (+{len(fails) - 8})" if len(fails) > 8 else ""
        )
        out.append(f"| {q} | {res['verdict']} | {res['instances']} | {shown or '—'} |")
    out += [
        "",
        f"Spearman ρ: R2 {fx(extra.get('R2_rho'), '.3f')}; D2 "
        + ", ".join(f"{e} {fx(v, '.3f')}" for e, v in extra["D2_rho"].items()),
        "",
        f"**Verdict rule:** {rule}.",
        "",
        "## The reference: the exact TM₀ mode against the two lines",
        "",
        "x = (1 − 1/εr) ln(b/a) / (Λ + ln(b/a)). Z₀ exact is V/I; 2P/I² is shown "
        "as its relative difference from V/I.",
        "",
        "| jacket | a mm | b mm | εr | a′ mm | L′ nH/m | Λ | x | s_mode % | "
        "β_pair/β − 1 | β_Lonly/β − 1 | Z₀ exact Ω | 2P/I² vs V/I | "
        "Z₀,pair/Z₀ − 1 | Z₀,Lonly/Z₀ − 1 |",
        "|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|",
    ]
    for name in NAMES:
        m = jref.get(name)
        if m is None:
            continue
        be, ze = m["beta_over_k0_exact"], m["z0_exact_vi"]
        out.append(
            f"| {name} | {1e3 * m['a']:.3f} | {1e3 * m['b']:.3f} | {m['eps_r']} | "
            f"{1e3 * m['a_eq']:.3f} | {1e9 * m['L_ins']:.2f} | {m['Lambda']:.3f} | "
            f"{m['x']:.4f} | {fp(m['s_mode'])} | "
            f"{m['beta_over_k0_pair'] / be - 1:.2e} | "
            f"{m['beta_over_k0_lonly'] / be - 1:.2e} | {ze:.2f} | "
            f"{m['z0_exact_pi'] / ze - 1:.1e} | {fp(m['z0_pair'] / ze - 1, 3)} % | "
            f"{fp(m['z0_lonly'] / ze - 1, 2)} % |"
        )
    out += [
        "",
        "## Resonant length, finer mesh",
        "",
        "Shortening = 1 − L_Lonly/L_bare. Split = 1 − L_pair/L_Lonly (positive: the "
        "pair is shorter). s_dip = 1 − L_pair/L_bare.",
        "",
        "| jacket | engine | L_bare m | L_pair m | L_Lonly m | shortening % | "
        "split % | split / shortening | s_dip / s_mode |",
        "|---|---|---:|---:|---:|---:|---:|---:|---:|",
    ]
    for name in NAMES:
        for e in ENGINES:
            lp, ll = lres(name, "pair", e, FINE), lres(name, "lonly", e, FINE)
            lb = lres(bare_of(name), "bare", e, FINE)
            sh = None if None in (ll, lb) else 1 - ll / lb
            sp = None if None in (lp, ll) else 1 - lp / ll
            sd = (
                None
                if None in (lp, lb) or name not in jref
                else (1 - lp / lb) / jref[name]["s_mode"]
            )
            out.append(
                f"| {name} | {e} | {fx(lb, '.5f')} | {fx(lp, '.5f')} | {fx(ll, '.5f')} | "
                f"{fp(sh)} | {fp(sp)} | {fx(None if None in (sh, sp) else sp / sh, '.3f')} | "
                f"{fx(sd, '.3f')} |"
            )
    out += [
        "",
        "## Z at L₀, finer mesh",
        "",
        "ΔZ = Z(jacket) − Z(bare), both at L₀; g = Z_pair − Z_Lonly.",
        "",
        "| jacket | engine | L₀ m | Z bare | Z pair | Z L-only | ΔZ pair | ΔZ L-only | "
        "g | \\|g\\|/\\|Z_Lonly\\| % |",
        "|---|---|---:|---|---|---|---|---|---|---:|",
    ]
    for name in NAMES:
        c = bare_of(name)
        for e in ENGINES:
            rec = ok(name, "lonly", e, FINE) or ok(name, "pair", e, FINE)
            zb, zp, zl = (
                z(c, "bare", e, FINE),
                z(name, "pair", e, FINE),
                z(name, "lonly", e, FINE),
            )
            g = sub(zp, zl)
            out.append(
                f"| {name} | {e} | {fx(rec.get('L0') if rec else None, '.5f')} | "
                f"{fz(zb)} | {fz(zp)} | {fz(zl)} | {fz(sub(zp, zb))} | {fz(sub(zl, zb))} | "
                f"{fz(g)} | {fp(None if None in (g, zl) else abs(g) / abs(zl), 2)} |"
            )
    out += [
        "",
        "## Cross-engine agreement, finer mesh (D1)",
        "",
        "Worst pairwise disagreement among the three engines, relative to bs2's own "
        "magnitude.",
        "",
        "| jacket | ΔZ pair | ΔZ L-only | g |",
        "|---|---:|---:|---:|",
    ]
    for name, worst in d1_table:
        out.append(
            f"| {name} | {fp(worst['pair'], 2)} % | {fp(worst['lonly'], 2)} % | "
            f"{fp(worst['gap'], 2)} % |"
        )
    out += [
        "",
        "Context, not graded: the bare wire at L₀ across engines.",
        "",
        "| conductor | engine | Z bare | \\|Z − Z_bs2\\| Ω |",
        "|---|---|---|---:|",
    ]
    for c in BARE:
        zb2 = z(c, "bare", "bs2", FINE)
        for e in ENGINES:
            zb = z(c, "bare", e, FINE)
            d = sub(zb, zb2)
            out.append(
                f"| {c} | {e} | {fz(zb)} | {fx(None if d is None else abs(d), '.4f')} |"
            )
    out += [
        "",
        "## Mesh (D4)",
        "",
        f"| conductor or jacket | treatment | engine | L_res n={COARSE} | L_res n={FINE} | change % |",
        "|---|---|---|---:|---:|---:|",
    ]
    for name, t, e, lc, lf, change in d4_table:
        out.append(
            f"| {name} | {t} | {e} | {fx(lc, '.5f')} | {fx(lf, '.5f')} | {fp(change)} |"
        )
    out.append("")
    (here / "README.md").write_text("\n".join(out))
    (here / "analysis.json").write_text(
        json.dumps(
            {"checks": checks, "predictions": preds, "extra": extra, "rule": rule},
            indent=1,
        )
    )
    print("\n".join(out))


if __name__ == "__main__":
    main()
