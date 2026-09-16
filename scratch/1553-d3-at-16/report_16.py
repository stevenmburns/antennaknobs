"""d=3 at 16 beside d=3 at 12. No number transcribed.

    python scratch/1553-d3-at-16/report_16.py > section.md

Same reference (bs2@160 from the AK#1525 ladder), same one-third admissibility
rule stated on ΔΓ, both metrics side by side. ΔΓ is the vector norm over ports,
which is what compares with the |ΔZ| norm the earlier records used.
"""

from __future__ import annotations

import json
import math
import statistics
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
HERE = Path(__file__).resolve().parent
Z0 = 50.0
GR = ("free", "somm")
TAILS = ("dipoles.short_dipole_loaded", "specialty.continuous_helix", "wire.zepp")


def load(p):
    d, prov = {}, None
    for line in open(p, encoding="utf-8"):
        r = json.loads(line)
        if "design" not in r:
            prov = r
            continue
        d[(r["design"], r["ground"], r["rung"], r["engine"])] = r
    return d, prov


def zv(r):
    return (
        [complex(*p) for p in r["z"]]
        if r and r.get("z") and r["status"] == "ok"
        else None
    )


def G(z):
    return (z - Z0) / (z + Z0)


def dgam(a, b):
    if a is None or b is None or len(a) != len(b):
        return None
    return math.sqrt(sum(abs(G(x) - G(y)) ** 2 for x, y in zip(a, b, strict=True)))


def dzrel(a, b):
    if a is None or b is None or len(a) != len(b):
        return None
    n = math.sqrt(sum(abs(x - y) ** 2 for x, y in zip(a, b, strict=True)))
    den = math.sqrt(sum(abs(y) ** 2 for y in b))
    return (n / den) if den else None


def q(v, p):
    s = sorted(v)
    return s[min(len(s) - 1, int(p * len(s)))] if s else None


def f(x, n=4):
    return "—" if x is None else f"{x:.{n}f}"


def score(recs, lad, engine, rung):
    adm, unres = [], []
    for d in sorted({k[0] for k in recs}):
        for g in GR:
            ref = zv(lad.get((d, g, 160, "bs2")))
            prev = zv(lad.get((d, g, 80, "bs2")))
            c = zv(recs.get((d, g, rung, engine)))
            if ref is None or prev is None or c is None:
                continue
            gm, mv = dgam(c, ref), dgam(prev, ref)
            rel = dzrel(c, ref)
            if gm is None:
                continue
            (unres if (gm > 0 and mv is not None and mv > gm / 3) else adm).append(
                (d, g, gm, rel)
            )
    return adm, unres


def cost(recs, engine, rung):
    cold = [
        c["cold_s"]
        for k, c in recs.items()
        if k[3] == engine and k[2] == rung and c["status"] == "ok" and c.get("cold_s")
    ]
    rss = [
        c["peak_rss_mb"]
        for k, c in recs.items()
        if k[3] == engine and k[2] == rung and c["status"] == "ok"
    ]
    return sum(cold), statistics.median(cold), max(cold), max(rss)


def main():
    new, prov = load(HERE / "records.jsonl")
    old, _ = load(ROOT / "scratch/1543-bspline-served-density/records.jsonl")
    lad, _ = load(ROOT / "scratch/1525-razor-density/records.jsonl")
    o = []
    w = o.append
    w("\n## d=3 at 16 — 2026-09-16\n")
    w(
        f"AK PR #1553 moves bspline d=3's served density from **12 to 16**. That was "
        f"a decision; this is the measurement. Same 103 designs × 2 grounds, same "
        f"bs2@160 reference, same one-third rule on ΔΓ. momwire "
        f"`{prov['momwire_sha'][:9]}` (`{prov['momwire_describe']}`), rebuilt; the "
        f"reference was re-validated bit-for-bit on this build first. `density.py` "
        f"is untouched — the harness takes the density directly.\n"
    )
    a16, u16 = score(new, lad, "bs3", 16)
    a12, u12 = score(old, lad, "bs3", 12)
    w(
        "| d=3 rung | admissible | median ΔΓ | p90 ΔΓ | worst ΔΓ | median rel-Z | worst rel-Z |"
    )
    w("|---:|---:|---:|---:|---:|---:|---:|")
    for lab, adm in ((12, a12), (16, a16)):
        gm = [x[2] for x in adm]
        rl = [x[3] for x in adm if x[3] is not None]
        w(
            f"| **{lab}** | {len(adm)} | {f(statistics.median(gm))} | "
            f"{f(q(gm, 0.90))} | {f(q(gm, 1.0))} | "
            f"{100 * statistics.median(rl):.3g} % | {100 * q(rl, 1.0):.3g} % |"
        )
    w("")
    w(f"Unresolved under the one-third rule: {len(u12)} at 12, {len(u16)} at 16.\n")

    w("### The three tail designs\n")
    w("| design | ground | ΔΓ at 12 | ΔΓ at 16 | change | rel-Z at 12 | rel-Z at 16 |")
    w("|---|---|---:|---:|---:|---:|---:|")
    for d in TAILS:
        for g in GR:
            ref = zv(lad.get((d, g, 160, "bs2")))
            g12 = dgam(zv(old.get((d, g, 12, "bs3"))), ref)
            g16 = dgam(zv(new.get((d, g, 16, "bs3"))), ref)
            r12 = dzrel(zv(old.get((d, g, 12, "bs3"))), ref)
            r16 = dzrel(zv(new.get((d, g, 16, "bs3"))), ref)
            if g12 is None or g16 is None:
                continue
            w(
                f"| `{d}` | {g} | {f(g12)} | **{f(g16)}** | "
                f"{100 * (g16 / g12 - 1):+.0f} % | {100 * r12:.0f} % | "
                f"{100 * r16:.0f} % |"
            )
    w("")

    w("### The price of 12 → 16\n")
    w("| d=3 rung | catalog cold total | median cold | worst single | worst peak RSS |")
    w("|---:|---:|---:|---:|---:|")
    c12, c16 = cost(old, "bs3", 12), cost(new, "bs3", 16)
    for lab, c in ((12, c12), (16, c16)):
        w(f"| **{lab}** | {c[0]:.1f} s | {c[1]:.3f} s | {c[2]:.2f} s | {c[3]:.0f} MB |")
    w("")
    w(f"Cold-total ratio 16/12: **{c16[0] / c12[0]:.2f}×**.\n")

    # predictions
    gm16 = [x[2] for x in a16]
    med = statistics.median(gm16)
    sdl = max(
        v
        for v in (
            dgam(
                zv(new.get(("dipoles.short_dipole_loaded", g, 16, "bs3"))),
                zv(lad.get(("dipoles.short_dipole_loaded", g, 160, "bs2"))),
            )
            for g in GR
        )
        if v is not None
    )
    ratio = c16[0] / c12[0]
    w("### K1–K3, scored\n")
    w("| prediction | bar | measured | verdict |")
    w("|---|---|---|---|")
    w(
        f"| **K1** | catalog median ΔΓ in 0.0025–0.0040 | {f(med)} | "
        f"{'**HIT**' if 0.0025 <= med <= 0.0040 else '**MISS**'} |"
    )
    w(
        f"| **K2** | `short_dipole_loaded` worst falls to 0.70–0.82 | {f(sdl)} | "
        f"{'**HIT**' if 0.70 <= sdl <= 0.82 else '**MISS**'} |"
    )
    w(
        f"| **K3** | catalog cold total rises 1.2–1.8× | {ratio:.2f}× | "
        f"{'**HIT**' if 1.2 <= ratio <= 1.8 else '**MISS**'} |"
    )
    w("")
    sys.stdout.write("\n".join(o) + "\n")
    (HERE / "section.md").write_text("\n".join(o) + "\n", encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
