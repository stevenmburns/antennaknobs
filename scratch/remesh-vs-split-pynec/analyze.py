"""The re-mesh-vs-split PyNEC study's analysis: PS1-PS5, the decision rule, and
the tables, as PLAN.md registers them.

  python scratch/remesh-vs-split-pynec/analyze.py scratch/remesh-vs-split-pynec/rows.jsonl

Written from the registered bars alone, before any solve result exists. A check
whose input row is missing or errored is reported as missing, never passed.
Writes README.md and analysis.json beside the records.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import numpy as np

# (kind, case, ground, reference base N, counts)
SWEEPS = [
    ("window", case, "free", base, tuple(range(base - 5, base + 6)))
    for case in ("k1_031", "k2", "k3")
    for base in (41, 81, 161)
]
SWEEPS.append(("window", "k2", "somm13", 81, tuple(range(76, 87))))
SWEEPS += [
    ("transition", case, "free", base, tuple(ns))
    for case in ("k1_031", "k2")
    for base, ns in ((41, range(45, 56)), (81, range(70, 81)))
]


def load(path):
    rows, meta = {}, {}
    for line in Path(path).read_text().splitlines():
        rec = json.loads(line)
        if rec.get("_meta"):
            meta = rec
            continue
        rows[(rec["case"], rec["ground"], rec["n"], rec["path"])] = rec
    return meta, rows


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


def trend_ptp(ns, zs):
    x = 1.0 / np.asarray(ns, float) ** 2
    design = np.column_stack([np.ones_like(x), x])
    zs = np.asarray(zs)
    fit = design @ np.linalg.lstsq(design, zs.real, rcond=None)[0] + 1j * (
        design @ np.linalg.lstsq(design, zs.imag, rcond=None)[0]
    )
    res = zs - fit
    return max(abs(a - b) for a in res for b in res)


def kind_of(rec):
    if rec["split"]:
        return "split"
    return "snap" if rec["snap_mm"] else "exact"


def main():
    path = Path(sys.argv[1])
    meta, rows = load(path)
    missing = set()

    def get(*key):
        rec = rows.get(key)
        if rec is None or rec.get("status") != "ok" or "z" not in rec:
            missing.add(key)
            return None
        return rec

    def z(rec):
        return complex(*rec["z"])

    ps1, ps2, ps3, ps4, ps5 = [], [], [], [], []
    summary_rows, tables = [], []
    r_max_jump_over_step, s_max_jump_over_step = [], []
    for kind, case, ground, base, ns in SWEEPS:
        label = f"{kind} {case}/{ground} N={base} n={ns[0]}–{ns[-1]}"
        s_n, s_2n = get(case, ground, base, "S"), get(case, ground, 2 * base - 1, "S")
        r_n, r_2n = get(case, ground, base, "R"), get(case, ground, 2 * base - 1, "R")
        step_s = abs(z(s_n) - z(s_2n)) if (s_n and s_2n) else None
        step_r = abs(z(r_n) - z(r_2n)) if (r_n and r_2n) else None
        recs = {p: [get(case, ground, n, p) for n in ns] for p in ("R", "S")}
        if step_s is None or any(r is None for p in recs for r in recs[p]):
            for bucket in (ps1, ps3):
                bucket.append((label, None))
            continue
        stats = {}
        for p in ("R", "S"):
            zs = [z(r) for r in recs[p]]
            jumps = [abs(zs[i + 1] - zs[i]) for i in range(len(zs) - 1)]
            j = int(np.argmax(jumps))
            stats[p] = {
                "max_jump": jumps[j],
                "at": (ns[j], ns[j + 1]),
                "segs_at": (recs[p][j]["segments"], recs[p][j + 1]["segments"]),
                "kinds_at": (kind_of(recs[p][j]), kind_of(recs[p][j + 1])),
                "ptp": trend_ptp(ns, zs),
            }
        both_exact = [
            abs(z(recs["R"][i]) - z(recs["S"][i]))
            for i in range(len(ns))
            if recs["R"][i]["exact"] and recs["S"][i]["exact"]
        ]
        rs_max = max(both_exact) if both_exact else None
        r_snaps = [
            abs(z(recs["R"][i]) - z(recs["S"][i]))
            for i in range(len(ns))
            if not recs["R"][i]["exact"]
        ]
        ps1.append((label, bool(stats["S"]["max_jump"] <= step_s)))
        s_max_jump_over_step.append(stats["S"]["max_jump"] / step_s)
        r_max_jump_over_step.append(stats["R"]["max_jump"] / step_s)
        if kind == "transition":
            ps2.append((label, bool(stats["R"]["max_jump"] > step_s)))
        if rs_max is not None:
            ps3.append((label, bool(rs_max <= step_s)))
        if kind == "window":
            ps4.append((label, bool(stats["S"]["ptp"] <= 0.25 * step_s)))
        if case == "k3" and base in (41, 81) and r_snaps:
            ps5.append((label, bool(max(r_snaps) > step_s)))
        summary_rows.append(
            f"| {label} | {fx(step_s)} | {fx(step_r)} | {fx(stats['R']['max_jump'])} at n={stats['R']['at'][0]}→{stats['R']['at'][1]} "
            f"({stats['R']['segs_at'][0]}→{stats['R']['segs_at'][1]} segs, {stats['R']['kinds_at'][0]}→{stats['R']['kinds_at'][1]}) | "
            f"{fx(stats['S']['max_jump'])} at n={stats['S']['at'][0]}→{stats['S']['at'][1]} | {fx(stats['R']['ptp'])} | {fx(stats['S']['ptp'])} | "
            f"{fx(rs_max)} | {fx(max(r_snaps) if r_snaps else None)} |"
        )
        table = [
            f"### {label}",
            "",
            "| n | R segs / pieces / kind | Z_R | S segs / pieces | Z_S | \\|R − S\\| |",
            "|---:|---|---|---|---|---:|",
        ]
        for i, n in enumerate(ns):
            rr, ss = recs["R"][i], recs["S"][i]
            table.append(
                f"| {n} | {rr['segments']} / {rr['pieces']} / {kind_of(rr)}{(' ' + str(rr['snap_mm'])) if rr['snap_mm'] else ''} | {fz(z(rr))} | "
                f"{ss['segments']} / {ss['pieces']} | {fz(z(ss))} | {abs(z(rr) - z(ss)):.4g} |"
            )
        tables += table + [""]

    res = {}
    for name, checks in (
        ("PS1", ps1),
        ("PS2", ps2),
        ("PS3", ps3),
        ("PS4", ps4),
        ("PS5", ps5),
    ):
        v, fails, gaps = verdict(checks)
        res[name] = {
            "verdict": v,
            "instances": len(checks),
            "fails": fails,
            "missing": gaps,
        }

    s_smooth = bool(s_max_jump_over_step) and max(s_max_jump_over_step) <= 1.0
    r_jumps = bool(r_max_jump_over_step) and max(r_max_jump_over_step) > 1.0
    agree = res["PS3"]["verdict"] == "hit"
    if s_smooth and r_jumps:
        rec = "split-always"
    elif not r_jumps and agree:
        rec = "keep re-mesh-first"
    else:
        rec = "no clear preference on the registered rule"
    res["decision"] = {
        "recommendation": rec,
        "max_S_jump_over_step": max(s_max_jump_over_step)
        if s_max_jump_over_step
        else None,
        "max_R_jump_over_step": max(r_max_jump_over_step)
        if r_max_jump_over_step
        else None,
    }

    out = ["# Re-mesh-first against split-always on PyNEC: results", ""]
    out.append(
        "Records: `rows.jsonl`. Registration: `PLAN.md`. Z in ohms at the feed, loads in place. "
        "R is antennaknobs main's PyNECEngine on the whole wire; S is #1511's centre split built by hand. "
        "step_S = \\|Z_S(N) − Z_S(2N − 1)\\|."
    )
    out += [
        "",
        "## Predictions and the decision rule",
        "",
        "| id | verdict | instances | failing instances |",
        "|---|---|---:|---|",
    ]
    for name in ("PS1", "PS2", "PS3", "PS4", "PS5"):
        r = res[name]
        cell = ", ".join(r["fails"]) or "—"
        if r["missing"]:
            cell += f" (missing inputs: {', '.join(r['missing'])})"
        out.append(f"| {name} | {r['verdict']} | {r['instances']} | {cell} |")
    d = res["decision"]
    out += [
        "",
        f"Decision rule: **{d['recommendation']}** (largest S jump / step_S = {fx(d['max_S_jump_over_step'])}; "
        f"largest R jump / step_S = {fx(d['max_R_jump_over_step'])}).",
        "",
        "## Per sweep",
        "",
        "| sweep | step_S | step_R | R max jump (where) | S max jump (where) | R trend ptp | S trend ptp | max \\|R − S\\|, R exact | max \\|R − S\\|, R snapped |",
        "|---|---:|---:|---|---|---:|---:|---:|---:|",
        *summary_rows,
        "",
        "## Rows",
        "",
        *tables,
    ]
    if missing:
        out += ["## Rows missing or errored", ""]
        out += [
            f"- {k}: {(rows.get(k) or {}).get('error', 'absent')}"
            for k in sorted(missing)
        ]
        out.append("")
    out.append(f"PyNEC: `{meta.get('pynec', '?')}`")
    (path.parent / "README.md").write_text("\n".join(out) + "\n")
    (path.parent / "analysis.json").write_text(json.dumps(res, indent=1))
    print(
        json.dumps(
            {
                k: (v.get("verdict"), v.get("instances"), (v.get("fails") or [])[:6])
                if k != "decision"
                else v
                for k, v in res.items()
            },
            indent=1,
        )
    )


if __name__ == "__main__":
    main()
