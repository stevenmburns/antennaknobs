"""AK#1520's analysis: Q1-Q9 and the verdict rule as PLAN.md registers them, and
the tables.

  python scratch/1520-near-end-residual/analyze_1520.py scratch/1520-near-end-residual/rows.jsonl

Written from the registered bars alone, before any solve result exists. A check
whose input row is missing or errored is reported as missing, never passed.
Writes README.md and analysis.json beside the records.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

NS = (41, 81, 161, 321)


def main():
    path = Path(sys.argv[1])
    rows, meta = {}, {}
    for line in path.read_text().splitlines():
        rec = json.loads(line)
        if rec.get("_meta"):
            meta = rec
            continue
        rows[(rec["engine"], rec["case"], rec["geometry"], rec["n"])] = rec
    partb = {}
    for line in (path.parent / "partb_rows.jsonl").read_text().splitlines():
        rec = json.loads(line)
        if rec.get("_meta"):
            continue
        if rec["case"] == "k3" and rec["ground"] == "free" and rec["engine"] == "bs2":
            partb[(rec["geometry"], rec["n"])] = complex(*rec["z"])
    missing = set()

    def z(*key):
        rec = rows.get(key)
        if rec is None or rec.get("status") != "ok" or "z" not in rec:
            missing.add(key)
            return None
        return complex(*rec["z"])

    def diff(a, b):
        return None if (a is None or b is None) else abs(a - b)

    def r(case, geom, n):
        return diff(z("bs2", case, geom, n), z("bs2", case, "A", n))

    def check(cond_inputs, fn):
        return None if any(x is None for x in cond_inputs) else bool(fn())

    res, checks = {}, {}
    q1 = []
    for geom in ("A", "B"):
        for n in (41, 81, 161):
            ours, ref = z("bs2", "base", geom, n), partb.get((geom, n))
            q1.append(
                (
                    f"{geom} n={n}",
                    check(
                        (ours, ref), lambda o=ours, p=ref: abs(o - p) <= 1e-9 * abs(p)
                    ),
                )
            )
    checks["Q1"] = q1
    checks["Q2"] = [
        (f"n={n}", check((z("bs2", "base", "B", n), z("bs2", "base", "Bp", n)),
                         lambda n=n: abs(z("bs2", "base", "B", n) - z("bs2", "base", "Bp", n)) <= 1e-12 * abs(z("bs2", "base", "B", n))))
        for n in NS
    ]  # fmt: skip
    rb = {n: r("base", "B", n) for n in NS}
    checks["Q3"] = [
        ("largest at 81, 41 and 321 at most half of it",
         check(tuple(rb.values()), lambda: max(rb, key=lambda k: rb[k]) == 81 and rb[41] <= 0.5 * rb[81] and rb[321] <= 0.5 * rb[81]))
    ]  # fmt: skip
    checks["Q4"] = [
        (
            f"n={n}",
            check(
                (r("base", "Bg", n), rb[81]),
                lambda n=n: r("base", "Bg", n) <= 0.5 * rb[81],
            ),
        )
        for n in (81, 161, 321)
    ]
    checks["Q5"] = [
        (
            f"n={n}",
            check(
                (r("moved", "B", n), rb[81]),
                lambda n=n: r("moved", "B", n) <= 0.5 * rb[81],
            ),
        )
        for n in (81, 161, 321)
    ]
    checks["Q6"] = [
        (
            f"n={n}",
            check(
                (r("noload", "B", n), rb[n]),
                lambda n=n: r("noload", "B", n) <= 0.5 * rb[n],
            ),
        )
        for n in (81, 161)
    ]
    checks["Q7"] = [
        (
            f"n={n}",
            check(
                (r("short", "B", n), rb[n]),
                lambda n=n: r("short", "B", n) <= 0.5 * rb[n],
            ),
        )
        for n in (81, 161)
    ]

    def load_effect(engine, geom, n):
        a, b = z(engine, "base", geom, n), z(engine, "noload", geom, n)
        return None if (a is None or b is None) else a - b

    q8 = []
    for engine in ("pynec", "sin", "nec2"):
        for n in (81, 161):
            le, lb, la = (
                load_effect(engine, "B", n),
                load_effect("bs2", "B", n),
                load_effect("bs2", "A", n),
            )
            q8.append(
                (
                    f"{engine} n={n}",
                    check(
                        (le, lb, la),
                        lambda le=le, lb=lb, la=la: abs(le - lb) < abs(le - la),
                    ),
                )
            )
    checks["Q8"] = q8
    checks["Q9"] = [
        (
            "r(321) at most half of r(81)",
            check((rb[321], rb[81]), lambda: rb[321] <= 0.5 * rb[81]),
        )
    ]

    for name, cs in checks.items():
        fails = [lab for lab, v in cs if v is False]
        gaps = [lab for lab, v in cs if v is None]
        verdict = (
            "MISS" if fails else ("incomplete (inputs missing)" if gaps else "hit")
        )
        res[name] = {
            "verdict": verdict,
            "instances": len(cs),
            "fails": fails,
            "missing": gaps,
        }

    def hit(q):
        return res[q]["verdict"] == "hit"

    def miss(q):
        return res[q]["verdict"] == "MISS"

    if miss("Q4"):
        cause = "the guard's end piece"
    elif miss("Q5"):
        cause = "the load at the end (the residual survives with the load 0.10 in)"
    elif miss("Q6") or miss("Q7"):
        cause = "the junction (mesh next to the piece), with or without the load"
    elif hit("Q3") and hit("Q8"):
        cause = "the load's local discretisation (every engine sees it)"
    elif hit("Q3") and miss("Q8"):
        cause = "the junction beside the load (bs2-specific)"
    else:
        cause = "unexplained"
    res["verdict"] = cause

    def fz(v):
        return "—" if v is None else f"{v.real:.4f}{v.imag:+.4f}j"

    def fx(v):
        return "—" if v is None else f"{v:.4g}"

    def ratios_beside(case, geom, n):
        rec = rows.get(("bs2", case, geom, n))
        if not rec or rec.get("status") != "ok":
            return "—"
        i, cr = rec.get("end_piece_index"), rec["cut_ratios"]
        near = [cr[j] for j in (i - 1, i) if i is not None and 0 <= j < len(cr)]
        return ", ".join(f"{x:.2f}" for x in near) or "—"

    out = ["# AK#1520: bs2's near-end whole-wire vs split residual — results", ""]
    out.append(
        "Records: `rows.jsonl`. Registration: `PLAN.md`. Z in ohms at the feed, loads in place, free space. "
        "r = \\|Z_G − Z_A\\| on bs2 at the same authored n; step_A = \\|Z_A(n) − Z_A(next n)\\| on base."
    )
    out += [
        "",
        "## Predictions",
        "",
        "| id | verdict | instances | failing instances |",
        "|---|---|---:|---|",
    ]
    for name in checks:
        rr = res[name]
        cell = ", ".join(rr["fails"]) or "—"
        if rr["missing"]:
            cell += f" (missing inputs: {', '.join(map(str, rr['missing']))})"
        out.append(f"| {name} | {rr['verdict']} | {rr['instances']} | {cell} |")
    out += ["", f"**Verdict rule:** {cause}.", ""]

    for case, geoms in (
        ("base", ("B", "Bp", "Bg")),
        ("moved", ("B",)),
        ("noload", ("B",)),
        ("short", ("B",)),
    ):
        out += [f"## bs2, {case}", ""]
        head = " | ".join(f"Z_{g} | r_{g} | ratios beside ({g})" for g in geoms)
        out.append(f"| n | Z_A | {head} | step_A (base) |")
        out.append("|---:|---|" + "---|---:|---|" * len(geoms) + "---:|")
        for i, n in enumerate(NS):
            step = (
                diff(z("bs2", "base", "A", n), z("bs2", "base", "A", NS[i + 1]))
                if i + 1 < len(NS)
                else None
            )
            cells = " | ".join(
                f"{fz(z('bs2', case, g, n))} | {fx(r(case, g, n))} | {ratios_beside(case, g, n)}"
                for g in geoms
            )
            out.append(f"| {n} | {fz(z('bs2', case, 'A', n))} | {cells} | {fx(step)} |")
        out.append("")

    out += [
        "## The load's effect at 0.04, L = Z(base) − Z(noload), by engine and geometry",
        "",
    ]
    out.append(
        "| n | engine | geometry | Z base | Z noload | L | \\|L − L_bs2,B\\| | \\|L − L_bs2,A\\| |"
    )
    out.append("|---:|---|---|---|---|---|---:|---:|")
    for n in NS:
        lb, la = load_effect("bs2", "B", n), load_effect("bs2", "A", n)
        for engine, geom in (
            ("bs2", "A"),
            ("bs2", "B"),
            ("pynec", "A"),
            ("pynec", "B"),
            ("sin", "A"),
            ("sin", "B"),
            ("nec2", "B"),
        ):
            le = load_effect(engine, geom, n)
            out.append(
                f"| {n} | {engine} | {geom} | {fz(z(engine, 'base', geom, n))} | {fz(z(engine, 'noload', geom, n))} | {fz(le)} | "
                f"{fx(diff(le, lb))} | {fx(diff(le, la))} |"
            )
    out.append("")
    out += ["## Centre engines on base, all geometries (A snaps where labelled)", ""]
    out.append("| n | engine | Z_A (snap mm) | Z_B | Z_Bp | Z_Bg |")
    out.append("|---:|---|---|---|---|---|")
    for n in NS:
        for engine in ("pynec", "sin"):
            rec = rows.get((engine, "base", "A", n)) or {}
            out.append(
                f"| {n} | {engine} | {fz(z(engine, 'base', 'A', n))} ({rec.get('snap_mm') or '—'}) | {fz(z(engine, 'base', 'B', n))} | "
                f"{fz(z(engine, 'base', 'Bp', n))} | {fz(z(engine, 'base', 'Bg', n))} |"
            )
    out.append("")
    if missing:
        out += ["## Rows missing or errored", ""]
        out += [
            f"- {k}: {(rows.get(k) or {}).get('error', 'absent')}"
            for k in sorted(missing)
        ]
        out.append("")
    out.append(f"momwire: `{meta.get('momwire', '?')}`; nec2c: `{meta.get('nec2c')}`")
    (path.parent / "README.md").write_text("\n".join(out) + "\n")
    (path.parent / "analysis.json").write_text(json.dumps(res, indent=1))
    print(
        json.dumps(
            {
                k: (v["verdict"], v["instances"], v["fails"][:6])
                if isinstance(v, dict)
                else v
                for k, v in res.items()
            },
            indent=1,
        )
    )


if __name__ == "__main__":
    main()
