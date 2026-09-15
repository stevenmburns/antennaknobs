"""Part D's analysis: PD1-PD5 as PLAN.md's Part D registers them, and the tables.

  python scratch/1511-bs2-split/analyze_d.py scratch/1511-bs2-split/rows_d.jsonl

Written from the registered bars alone, before any Part D result exists. A
check whose input row is missing or errored is reported as missing, never
passed. Writes README_D.md and analysis_d.json beside the records.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import numpy as np

SWEEPS = (
    ("D2", "k1_031", "free", (41, 81, 161)),
    ("D3", "k2", "free", (41, 81, 161)),
    ("D3", "k3", "free", (41, 81, 161)),
    ("D4", "k2", "somm13", (81,)),
)


def load(path):
    rows, meta = {}, {}
    for line in Path(path).read_text().splitlines():
        rec = json.loads(line)
        if rec.get("_meta"):
            meta = rec
            continue
        rows[(rec["case"], rec["ground"], rec["n"], rec["path"])] = rec
    return meta, rows


def ok(rec):
    return rec is not None and rec.get("status") == "ok" and "z" in rec


def z_of(rec):
    return complex(*rec["z"])


def fz(z):
    return "—" if z is None else f"{z.real:.4f}{z.imag:+.4f}j"


def fx(x, digits=4):
    return "—" if x is None else f"{x:.{digits}g}"


def verdict(checks):
    fails = [lab for lab, v in checks if v is False]
    gaps = [lab for lab, v in checks if v is None]
    if not checks:
        return "not evaluable (no instance)", fails, gaps
    if fails:
        return "MISS", fails, gaps
    if gaps:
        return "incomplete (inputs missing)", fails, gaps
    return "hit", fails, gaps


def fit_trend(ns, zs):
    """Least squares Z = a + b / n**2, real and imaginary parts separately."""
    x = 1.0 / np.asarray(ns, dtype=float) ** 2
    design = np.column_stack([np.ones_like(x), x])
    zs = np.asarray(zs)
    coef_re, *_ = np.linalg.lstsq(design, zs.real, rcond=None)
    coef_im, *_ = np.linalg.lstsq(design, zs.imag, rcond=None)
    return design @ coef_re + 1j * (design @ coef_im)


def main():
    path = Path(sys.argv[1])
    meta, rows = load(path)
    missing = set()

    def get(*key):
        rec = rows.get(key)
        if not ok(rec):
            missing.add(key)
            return None
        return rec

    res = {}
    out = ["# Part D: bs2's continuous feed at fixed density (#1519)", ""]
    out.append(
        "Records: `rows_d.jsonl`. Registration: `PLAN.md`, Part D. Z in ohms at the "
        "feed, loads in place; bs2 = BSplineSolver degree 2. `cont` is the authored "
        "mesh with each port at its exact arclength; `old` is antennaknobs' placement "
        "as it stands (parity bump and positioned-port re-count)."
    )
    out.append("")

    # ---------------------------------------------------------------- D1
    pd1 = []
    out += ["## D1: the feed at 0.5, even (knot) against odd (segment centre)", ""]
    out.append(
        "| m | n even / odd / 4m+1 (engine counts) | Z_even | Z_odd | \\|Z_even − Z_odd\\| | step \\|Z_odd − Z_odd(4m+1)\\| |"
    )
    out.append("|---:|---|---|---|---:|---:|")
    for m in (10, 20, 40, 80):
        re_, ro, r4 = (
            get("centre", "free", n, "cont") for n in (2 * m, 2 * m + 1, 4 * m + 1)
        )
        ze, zo, z4 = (z_of(r) if r else None for r in (re_, ro, r4))
        diff = abs(ze - zo) if None not in (ze, zo) else None
        stp = abs(zo - z4) if None not in (zo, z4) else None
        counts = " / ".join(str(r["segments"]) if r else "—" for r in (re_, ro, r4))
        out.append(f"| {m} | {counts} | {fz(ze)} | {fz(zo)} | {fx(diff)} | {fx(stp)} |")
        if m >= 20:
            pd1.append((f"m={m}", None if None in (diff, stp) else diff <= stp))
    out.append("")

    # ---------------------------------------------------------------- D2-D4
    pd2, pd3, pd4, pd5 = [], [], [], []
    ptp_by = {}
    for part, case, ground, bases in SWEEPS:
        for base in bases:
            label = f"{part} {case}/{ground} N={base}"
            ns = list(range(base - 5, base + 6))
            recs = [get(case, ground, n, "cont") for n in ns]
            step_rec = get(case, ground, 2 * base - 1, "cont")
            out += [f"## {label}", ""]
            if any(r is None for r in recs) or step_rec is None:
                out += ["Inputs missing; see the list at the end.", ""]
                check = (label, None)
                (pd4 if part == "D4" else pd2).append(check)
                continue
            zs = [z_of(r) for r in recs]
            trend = fit_trend(ns, zs)
            resid = np.asarray(zs) - trend
            ptp = max(abs(a - b) for a in resid for b in resid)
            z_base = z_of(get(case, ground, base, "cont"))
            step = abs(z_base - z_of(step_rec))
            ptp_by[(case, ground, base)] = ptp
            bar_step, bar_rel = 0.25 * step, 0.0005 * abs(z_base)
            check = (label, bool(ptp <= bar_step and ptp <= bar_rel))
            (pd4 if part == "D4" else pd2).append(check)
            worst = int(np.argmax(np.abs(resid)))
            names = [p["name"] for p in recs[0]["ports"]]
            worst_xi = ", ".join(
                f"{nm} {recs[worst]['ports'][i]['xi']:.3f}"
                for i, nm in enumerate(names)
            )
            out.append(
                f"Step at N, \\|Z({base}) − Z({2 * base - 1})\\| = {step:.4g} Ω; residual "
                f"peak-to-peak {ptp:.4g} Ω against 0.25 × step = {bar_step:.4g} Ω and "
                f"0.05 % of \\|Z\\| = {bar_rel:.4g} Ω. Largest \\|residual\\| at n = {ns[worst]} "
                f"(ξ: {worst_xi})."
            )
            out.append("")
            head = " | ".join(f"ξ {nm}" for nm in names)
            out.append(
                f"| n | segs | {head} | Z | trend | residual | \\|residual\\| | old segs | old Z | \\|old − cont\\| (matched ±5 %) |"
            )
            out.append(
                "|---:|---:|" + "---:|" * len(names) + "---|---|---|---:|---:|---|---:|"
            )
            for i, n in enumerate(ns):
                r = recs[i]
                old = get(case, ground, n, "old")
                xi_cells = " | ".join(f"{p['xi']:.3f}" for p in r["ports"])
                matched = old is not None and abs(old["segments"] / n - 1) <= 0.05
                dold = abs(z_of(old) - zs[i]) if matched else None
                if old is not None and matched:
                    pd3.append((f"{case}/{ground} n={n}", bool(dold <= step)))
                out.append(
                    f"| {n} | {r['segments']} | {xi_cells} | {fz(zs[i])} | {fz(trend[i])} | {fz(resid[i])} | "
                    f"{abs(resid[i]):.4g} | {old['segments'] if old else '—'} | {fz(z_of(old)) if old else '—'} | "
                    f"{fx(dold) if matched else 'n/a'} |"
                )
            out.append("")
        if part != "D4" and all((case, ground, b) in ptp_by for b in (41, 161)):
            pd5.append(
                (
                    f"{case}/{ground}",
                    bool(ptp_by[(case, ground, 161)] < ptp_by[(case, ground, 41)]),
                )
            )

    for name, checks in (
        ("PD1", pd1),
        ("PD2", pd2),
        ("PD3", pd3),
        ("PD4", pd4),
        ("PD5", pd5),
    ):
        v, fails, gaps = verdict(checks)
        res[name] = {
            "verdict": v,
            "instances": len(checks),
            "fails": fails,
            "missing": gaps,
        }

    summary = [
        "## Predictions",
        "",
        "| id | verdict | instances | failing instances |",
        "|---|---|---:|---|",
    ]
    for name, r in res.items():
        cell = ", ".join(r["fails"]) or "—"
        if r["missing"]:
            cell += f" (missing inputs: {', '.join(r['missing'])})"
        summary.append(f"| {name} | {r['verdict']} | {r['instances']} | {cell} |")
    summary.append("")
    out[3:3] = summary
    if missing:
        out += ["## Rows missing or errored", ""]
        out += [
            f"- {k}: {(rows.get(k) or {}).get('error', 'absent')}"
            for k in sorted(missing)
        ]
        out.append("")
    out.append(f"momwire: `{meta.get('momwire', '?')}`")
    (path.parent / "README_D.md").write_text("\n".join(out) + "\n")
    (path.parent / "analysis_d.json").write_text(json.dumps(res, indent=1))
    print(
        json.dumps(
            {k: (v["verdict"], v["instances"], v["fails"][:8]) for k, v in res.items()},
            indent=1,
        )
    )


if __name__ == "__main__":
    main()
