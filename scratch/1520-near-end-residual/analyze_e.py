"""AK#1520, Amendment 1: E1-E3 as PLAN.md registers them.

  python scratch/1520-near-end-residual/analyze_e.py scratch/1520-near-end-residual/rows_e.jsonl

Reads bs2's base A and B from rows.jsonl and AF and AL from rows_e.jsonl.
Written, and committed with the amendment, before any AF or AL solve. A missing
or errored input is reported as missing, never passed. Writes README_E.md and
analysis_e.json beside the records.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

NS = (41, 81, 161, 321)


def load(path):
    rows = {}
    for line in Path(path).read_text().splitlines():
        rec = json.loads(line)
        if not rec.get("_meta"):
            rows[(rec["engine"], rec["case"], rec["geometry"], rec["n"])] = rec
    return rows


def main():
    here = Path(sys.argv[1]).resolve().parent
    rows = load(here / "rows.jsonl")
    rows.update(load(Path(sys.argv[1])))

    def z(geom, n):
        rec = rows.get(("bs2", "base", geom, n))
        if rec is None or rec.get("status") != "ok" or "z" not in rec:
            return None
        return complex(*rec["z"])

    def d(a, b):
        return None if (a is None or b is None) else abs(a - b)

    checks = {"E1": [], "E2": [], "E3": []}
    table = [
        "| n | feed ξ on A | Z_A | Z_B | Z_AF | Z_AL | r_B = \\|B − A\\| | \\|AF − B\\| | \\|AL − A\\| | \\|AF − A\\| |",
        "|---:|---:|---|---|---|---|---:|---:|---:|---:|",
    ]

    def fz(v):
        return "—" if v is None else f"{v.real:.4f}{v.imag:+.4f}j"

    def fx(v):
        return "—" if v is None else f"{v:.4g}"

    for n in NS:
        za, zb, zf, zl = (z(g, n) for g in ("A", "B", "AF", "AL"))
        rb, af_b, al_a, af_a = d(zb, za), d(zf, zb), d(zl, za), d(zf, za)
        table.append(
            f"| {n} | {(0.31 * n) % 1.0:.2f} | {fz(za)} | {fz(zb)} | {fz(zf)} | {fz(zl)} | "
            f"{fx(rb)} | {fx(af_b)} | {fx(al_a)} | {fx(af_a)} |"
        )
        if n in (81, 161):
            checks["E1"].append(
                (f"n={n}", None if None in (af_b, rb) else af_b <= 0.25 * rb)
            )
            checks["E2"].append(
                (f"n={n}", None if None in (al_a, rb) else al_a <= 0.25 * rb)
            )
            checks["E3"].append(
                (f"n={n}", None if None in (af_a, rb) else af_a >= 0.75 * rb)
            )

    res = {}
    for name, cs in checks.items():
        fails = [lab for lab, v in cs if v is False]
        gaps = [lab for lab, v in cs if v is None]
        verdict = (
            "MISS" if fails else ("incomplete (inputs missing)" if gaps else "hit")
        )
        res[name] = {"verdict": verdict, "fails": fails, "missing": gaps}
    all_hit = all(res[q]["verdict"] == "hit" for q in checks)
    res["verdict"] = (
        "the feed's position within its segment on the whole wire (Part D's ripple), which the split removes"
        if all_hit
        else "unexplained by these candidates"
    )
    out = [
        "# AK#1520, Amendment 1: which split carries the residual",
        "",
        *table,
        "",
        "| id | verdict | failing |",
        "|---|---|---|",
    ]
    out += [
        f"| {q} | {res[q]['verdict']} | {', '.join(res[q]['fails']) or '—'} |"
        for q in checks
    ]
    out += ["", f"**Amendment 1 verdict:** {res['verdict']}.", ""]
    (here / "README_E.md").write_text("\n".join(out))
    (here / "analysis_e.json").write_text(json.dumps(res, indent=1))
    print("\n".join(out))


if __name__ == "__main__":
    main()
