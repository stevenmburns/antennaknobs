"""The bs2 split-equivalence study's analysis: P1-P6 as PLAN.md registers them,
and the README tables.

  python scratch/1511-bs2-split/analyze.py scratch/1511-bs2-split/rows.jsonl

Written from PLAN.md's bars alone, and committed before any result was read
(the solves ran fast and had finished, unread, by the time of that commit). A
prediction that needs a row that errored reports that row as missing rather
than passing.
Writes README.md and analysis.json beside the records.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

NS = (10, 21, 41, 81, 161)
CASES = (("k1", "free"), ("k2", "free"), ("k3", "free"), ("k2", "somm13"))
STEP_NS = (21, 41, 81)


def load(path):
    rows = {}
    meta = {}
    for line in Path(path).read_text().splitlines():
        rec = json.loads(line)
        if rec.get("_meta"):
            meta = rec
            continue
        key = (rec["case"], rec["ground"], rec["n"], rec["engine"], rec["geometry"])
        rows[key] = rec
    return meta, rows


class Data:
    def __init__(self, rows):
        self.rows = rows
        self.missing = set()

    def rec(self, case, ground, n, engine, geom):
        r = self.rows.get((case, ground, n, engine, geom))
        if r is None or r.get("status") != "ok" or "z" not in r:
            self.missing.add((case, ground, n, engine, geom))
            return None
        return r

    def z(self, *key):
        r = self.rec(*key)
        return complex(*r["z"]) if r else None

    def offsets(self, *key):
        r = self.rec(*key)
        if not r:
            return None
        return [p.get("offset_mm") for p in r.get("placements") or []]

    def counts(self, *key):
        r = self.rec(*key)
        return [c for _ln, c in r["meshed"]] if r else None


def absdiff(a, b):
    return abs(a - b) if (a is not None and b is not None) else None


def step(d, case, ground, n, engine, geom):
    i = NS.index(n)
    return absdiff(
        d.z(case, ground, n, engine, geom), d.z(case, ground, NS[i + 1], engine, geom)
    )


def rel(a, b):
    return abs(a - b) / abs(b) if (a is not None and b is not None) else None


def fz(z):
    return "—" if z is None else f"{z.real:.4f}{z.imag:+.4f}j"


def fx(x, digits=4):
    return "—" if x is None else f"{x:.{digits}g}"


def verdict(checks):
    """checks: [(label, ok or None)]. None is a missing input and not a hit."""
    fails = [lab for lab, ok in checks if ok is False]
    gaps = [lab for lab, ok in checks if ok is None]
    if not checks:
        return "not evaluable (no instance)", fails, gaps
    if fails:
        return "MISS", fails, gaps
    if gaps:
        return "incomplete (inputs missing)", fails, gaps
    return "hit", fails, gaps


def main():
    path = Path(sys.argv[1])
    meta, rows = load(path)
    d = Data(rows)
    res = {}

    # P1 / P1c / P2 / P6: bs2
    p1, p1c, p2, p6 = [], [], [], []
    for case, ground in CASES:
        for n in STEP_NS:
            zb, za, za0 = (d.z(case, ground, n, "bs2", g) for g in ("B", "A", "A0"))
            sa, sa0 = (
                step(d, case, ground, n, "bs2", "A"),
                step(d, case, ground, n, "bs2", "A0"),
            )
            dba, dba0 = absdiff(zb, za), absdiff(zb, za0)
            p1.append(
                (f"{case}/{ground} n={n}", None if None in (dba, sa) else dba <= sa)
            )
            p1c.append(
                (f"{case}/{ground} n={n}", None if None in (dba0, sa0) else dba0 <= sa0)
            )
        d161 = absdiff(
            d.z(case, ground, 161, "bs2", "B"), d.z(case, ground, 161, "bs2", "A")
        )
        d161c = absdiff(
            d.z(case, ground, 161, "bs2", "B"), d.z(case, ground, 161, "bs2", "A0")
        )
        d41c = absdiff(
            d.z(case, ground, 41, "bs2", "B"), d.z(case, ground, 41, "bs2", "A0")
        )
        sa81 = step(d, case, ground, 81, "bs2", "A")
        sa081 = step(d, case, ground, 81, "bs2", "A0")
        sb81 = step(d, case, ground, 81, "bs2", "B")
        inputs = (d161, d161c, d41c, sa81, sa081, sb81)
        ok = (
            None
            if None in inputs
            else (
                d161 <= max(sa81, sb81) and d161c <= max(sa081, sb81) and d161c < d41c
            )
        )
        p2.append((f"{case}/{ground}", ok))
        if case == "k2":
            for n in (41, 81):
                dd = absdiff(
                    d.z(case, ground, n, "bs2", "A"), d.z(case, ground, n, "bs2", "A0")
                )
                s0 = step(d, case, ground, n, "bs2", "A0")
                p6.append(
                    (f"{case}/{ground} n={n}", None if None in (dd, s0) else dd <= s0)
                )

    # P3 / P3c: sinusoidal against bs2 at 161
    p3, p3c = [], []
    for case, ground in CASES:
        ref = d.z(case, ground, 161, "bs2", "A")
        for n in NS:
            zbs = d.z(case, ground, n, "sin", "B")
            for geom, bucket in (("A", p3), ("A0", p3c)):
                offs = d.offsets(case, ground, n, "sin", geom)
                if offs is None:
                    bucket.append((f"{case}/{ground} n={n}", None))
                    continue
                if not offs:
                    continue  # no snap reported: not an instance
                za = d.z(case, ground, n, "sin", geom)
                ea, eb = absdiff(za, ref), absdiff(zbs, ref)
                bucket.append(
                    (f"{case}/{ground} n={n}", None if None in (ea, eb) else ea > eb)
                )

    # D5, P4 / P4c, P5 / P5c: razor and NEC-5
    d5 = {}
    for ground in ("free", "somm13"):
        for n in NS:
            d5[(ground, n)] = rel(
                d.z("d5", ground, n, "razor", "D5"), d.z("d5", ground, n, "nec5", "D5")
            )
    p4, p4c, p5, p5c = [], [], [], []
    for case, ground in CASES:
        for n in NS:
            bar = None if d5[(ground, n)] is None else 2 * d5[(ground, n)] + 0.001
            rce = rel(
                d.z(case, ground, n, "razor", "Ce"), d.z(case, ground, n, "nec5", "Ce")
            )
            p4.append(
                (f"{case}/{ground} n={n}", None if None in (rce, bar) else rce <= bar)
            )
            cr, cn = (
                d.counts(case, ground, n, "razor", "C"),
                d.counts(case, ground, n, "nec5", "C"),
            )
            if cr is not None and cn is not None and cr != cn:
                rc = rel(
                    d.z(case, ground, n, "razor", "C"),
                    d.z(case, ground, n, "nec5", "C"),
                )
                p4c.append(
                    (f"{case}/{ground} n={n}", None if None in (rc, bar) else rc > bar)
                )
            zce_r = d.z(case, ground, n, "razor", "Ce")
            dce = absdiff(zce_r, d.z(case, ground, n, "nec5", "Ce"))
            for geom, bucket in (("A", p5), ("A0", p5c)):
                offs = d.offsets(case, ground, n, "razor", geom)
                if offs is None:
                    bucket.append((f"{case}/{ground} n={n}", None))
                    continue
                if not offs:
                    continue
                snap = absdiff(d.z(case, ground, n, "razor", geom), zce_r)
                bucket.append(
                    (
                        f"{case}/{ground} n={n}",
                        None if None in (snap, dce) else snap > dce,
                    )
                )

    for name, checks in (
        ("P1", p1), ("P1c", p1c), ("P2", p2), ("P3", p3), ("P3c", p3c),
        ("P4", p4), ("P4c", p4c), ("P5", p5), ("P5c", p5c), ("P6", p6),
    ):  # fmt: skip
        v, fails, gaps = verdict(checks)
        res[name] = {
            "verdict": v,
            "instances": len(checks),
            "fails": fails,
            "missing": gaps,
        }

    # ----------------------------------------------------------------- tables
    out = ["# The bs2 split-equivalence study: results", ""]
    out.append(
        f"Records: `rows.jsonl` (momwire {meta.get('momwire_version', '?')} at "
        f"`{meta.get('momwire', '?')}`; NEC-5 sha256 {str(meta.get('nec5_sha256'))[:8]}). "
        "Registration: `PLAN.md`. Z in ohms at the feed, loads in place."
    )
    out.append("")
    out.append("## Predictions")
    out.append("")
    out.append("| id | verdict | instances | failing instances |")
    out.append("|---|---|---:|---|")
    for name, r in res.items():
        fails = ", ".join(r["fails"]) or "—"
        if r["missing"]:
            fails += f" (missing inputs: {', '.join(r['missing'])})"
        out.append(f"| {name} | {r['verdict']} | {r['instances']} | {fails} |")
    out.append("")
    for case, ground in CASES:
        ref = d.z(case, ground, 161, "bs2", "A")
        out.append(f"## {case}, {ground}")
        out.append("")
        out.append("### bs2")
        out.append("")
        out.append(
            "| n | segs A / A0 / B | Z_A | Z_A0 | Z_B | \\|Z_B − Z_A\\| | step_A | \\|Z_B − Z_A0\\| | step_A0 | B cut ratios |"
        )
        out.append("|---:|---|---|---|---|---:|---:|---:|---:|---|")
        for n in NS:
            za, za0, zb = (d.z(case, ground, n, "bs2", g) for g in ("A", "A0", "B"))
            segs = " / ".join(
                str(sum(c)) if (c := d.counts(case, ground, n, "bs2", g)) else "—"
                for g in ("A", "A0", "B")
            )
            rb = d.rec(case, ground, n, "bs2", "B")
            ratios = ", ".join(f"{x:.2f}" for x in rb["junction_ratios"]) if rb else "—"
            sa = step(d, case, ground, n, "bs2", "A") if n != 161 else None
            sa0 = step(d, case, ground, n, "bs2", "A0") if n != 161 else None
            out.append(
                f"| {n} | {segs} | {fz(za)} | {fz(za0)} | {fz(zb)} | {fx(absdiff(zb, za))} | {fx(sa)} | "
                f"{fx(absdiff(zb, za0))} | {fx(sa0)} | {ratios} |"
            )
        out.append("")
        out.append("### sinusoidal (against bs2's Z_A at n = 161)")
        out.append("")
        out.append(
            "| n | Z_A (snap mm) | Z_A0 (snap mm) | Z_B | \\|A − bs2∞\\| | \\|A0 − bs2∞\\| | \\|B − bs2∞\\| |"
        )
        out.append("|---:|---|---|---|---:|---:|---:|")
        for n in NS:
            za, za0, zb = (d.z(case, ground, n, "sin", g) for g in ("A", "A0", "B"))
            oa, oa0 = (
                d.offsets(case, ground, n, "sin", "A"),
                d.offsets(case, ground, n, "sin", "A0"),
            )
            out.append(
                f"| {n} | {fz(za)} ({oa or '—'}) | {fz(za0)} ({oa0 or '—'}) | {fz(zb)} | "
                f"{fx(absdiff(za, ref))} | {fx(absdiff(za0, ref))} | {fx(absdiff(zb, ref))} |"
            )
        out.append("")
        out.append("### razor-2p and NEC-5")
        out.append("")
        out.append(
            "| n | razor Z_A (snap mm) | razor Z_A0 (snap mm) | razor Z_C | razor Z_Ce | NEC-5 Z_C | NEC-5 Z_Ce | "
            "segs C razor / NEC-5 | r(C) | r(Ce) | 2·D5 + 0.001 | \\|razor A − bs2∞\\| | \\|razor Ce − bs2∞\\| |"
        )
        out.append("|---:|---|---|---|---|---|---|---|---:|---:|---:|---:|---:|")
        for n in NS:
            ra, ra0, rc, rce = (
                d.z(case, ground, n, "razor", g) for g in ("A", "A0", "C", "Ce")
            )
            nc, nce = (
                d.z(case, ground, n, "nec5", "C"),
                d.z(case, ground, n, "nec5", "Ce"),
            )
            oa, oa0 = (
                d.offsets(case, ground, n, "razor", "A"),
                d.offsets(case, ground, n, "razor", "A0"),
            )
            cr, cn = (
                d.counts(case, ground, n, "razor", "C"),
                d.counts(case, ground, n, "nec5", "C"),
            )
            bar = None if d5[(ground, n)] is None else 2 * d5[(ground, n)] + 0.001
            out.append(
                f"| {n} | {fz(ra)} ({oa or '—'}) | {fz(ra0)} ({oa0 or '—'}) | {fz(rc)} | {fz(rce)} | {fz(nc)} | {fz(nce)} | "
                f"{cr} / {cn} | {fx(rel(rc, nc))} | {fx(rel(rce, nce))} | {fx(bar)} | {fx(absdiff(ra, ref))} | {fx(absdiff(rce, ref))} |"
            )
        out.append("")
    out.append("## D5: razor-2p against NEC-5, centre-fed, no loads")
    out.append("")
    out.append("| ground | n | razor | NEC-5 | relative |")
    out.append("|---|---:|---|---|---:|")
    for ground in ("free", "somm13"):
        for n in NS:
            out.append(
                f"| {ground} | {n} | {fz(d.z('d5', ground, n, 'razor', 'D5'))} | "
                f"{fz(d.z('d5', ground, n, 'nec5', 'D5'))} | {fx(d5[(ground, n)])} |"
            )
    out.append("")
    if d.missing:
        out.append("## Rows missing or errored")
        out.append("")
        for key in sorted(d.missing):
            r = rows.get(key)
            out.append(f"- {key}: {r.get('error') if r else 'absent'}")
        out.append("")
    (path.parent / "README.md").write_text("\n".join(out))
    (path.parent / "analysis.json").write_text(json.dumps(res, indent=1))
    print(
        json.dumps(
            {k: (v["verdict"], v["instances"], v["fails"][:6]) for k, v in res.items()},
            indent=1,
        )
    )


if __name__ == "__main__":
    main()
