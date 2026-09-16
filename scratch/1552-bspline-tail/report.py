"""Read `records.jsonl` and write README.md. No number transcribed.

    python scratch/1552-bspline-tail/report.py

One verdict per design -- density / reference / placement -- decided from three
measurements the plan registered in advance:

  * does the ABSOLUTE ohm error fall with N?          (density behaving normally)
  * does the reference itself move at 240 / 320?      (reference not settled)
  * does the FED SEGMENT refine across the ladder?    (placement)

The third is why `fed_segments()` is recorded at every rung: a ladder that
refines the radiator while leaving the feed wire at one segment is not a density
ladder for the driving point, however many segments the total count reports.
"""

from __future__ import annotations

import json
import math
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
REF_RUNG = 160
GROUNDS = ("free", "somm")
GL = {"free": "free space", "somm": "Sommerfeld"}
LADDERS = {"bs3": (12, 15, 20, 30), "bs2": (15, 20, 30)}
DEEP = (240, 320)
DESIGNS = ("dipoles.short_dipole_loaded", "specialty.continuous_helix", "wire.zepp")


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


def dz(a, b):
    if a is None or b is None or len(a) != len(b):
        return None, None
    n = math.sqrt(sum(abs(x - y) ** 2 for x, y in zip(a, b, strict=True)))
    d = math.sqrt(sum(abs(y) ** 2 for y in b))
    return n, (n / d if d else None)


def feed_len(rec):
    fs = rec.get("fed_segments") if rec else None
    return fs[0].get("length_m") if isinstance(fs, list) and fs else None


def main():
    recs, prov = load(HERE / "records.jsonl")
    out = []
    w = out.append
    w("# AK#1552 — the bspline tail: density, reference, or placement?\n")
    w(
        f"**Builds.** antennaknobs `{prov['ak_sha'][:9]}`; momwire "
        f"`{prov['momwire_sha'][:9]}` (`{prov['momwire_describe']}`), rebuilt; "
        f"accelerator `{prov['accelerator_variant']['_accelerators'].split('.')[0]}`. "
        f"Metric and reference are AK#1525's: `|ΔZ|` over all ports as a vector, "
        f"relative over `|Z_ref|`, reference **bs2@160**. `PLAN.md` registers "
        f"H1–H3 before the first cell.\n"
    )

    verdicts = {}
    for d in DESIGNS:
        w(f"## `{d}`\n")
        for g in GROUNDS:
            ref = zv(recs.get((d, g, REF_RUNG, "bs2")))
            if ref is None:
                continue
            w(
                f"**{GL[g]}** — bs2@160 = `{ref[0].real:.4f}{ref[0].imag:+.4f}j`, "
                f"|Z| = {abs(ref[0]):.2f} Ω\n"
            )
            w("| basis | N | fed segment | \\|ΔZ\\| Ω | relative |")
            w("|---|---:|---:|---:|---:|")
            for e, rungs in LADDERS.items():
                for n in rungs:
                    c = recs.get((d, g, n, e))
                    o, r = dz(zv(c), ref)
                    fl = feed_len(c)
                    w(
                        f"| {e} | {n} | "
                        f"{f'{fl:.5f} m' if fl else '—'} | "
                        f"{o:.2f} | {100 * r:.0f} % |"
                        if o is not None
                        else f"| {e} | {n} | — | — | — |"
                    )
            w("")
            w("| arbitration | value | vs bs2@160 |")
            w("|---|---|---:|")
            for deep in DEEP:
                o, r = dz(zv(recs.get((d, g, deep, "bs2"))), ref)
                if o is not None:
                    fl = feed_len(recs.get((d, g, deep, "bs2")))
                    w(
                        f"| bs2@{deep} | fed segment {fl:.5f} m | "
                        f"{o:.3f} Ω = {100 * r:.2f} % |"
                    )
            for e, n in (("razor", 160), ("razor", 320), ("nec5", 160)):
                c = recs.get((d, g, n, e))
                if c is None:
                    continue
                if c["status"] != "ok":
                    w(f"| {e}@{n} | {c['status']} | — |")
                    continue
                o, r = dz(zv(c), ref)
                z = zv(c)[0]
                w(
                    f"| {e}@{n} | `{z.real:.4f}{z.imag:+.4f}j` | "
                    f"{o:.2f} Ω = {100 * r:.1f} % |"
                )
            w("")

        # ---- the three tests, on free space
        ref = zv(recs.get((d, "free", REF_RUNG, "bs2")))
        lad = LADDERS["bs3"] if recs.get((d, "free", 12, "bs3")) else LADDERS["bs2"]
        lo, _ = dz(zv(recs.get((d, "free", lad[0], "bs3"))), ref)
        hi, _ = dz(zv(recs.get((d, "free", lad[-1], "bs3"))), ref)
        fell = (1 - hi / lo) if (lo and hi) else None
        _o320, r320 = dz(zv(recs.get((d, "free", 320, "bs2"))), ref)
        f_lo, f_hi = (
            feed_len(recs.get((d, "free", lad[0], "bs3"))),
            feed_len(recs.get((d, "free", lad[-1], "bs3"))),
        )
        feed_refines = f_lo is not None and f_hi is not None and f_hi < 0.9 * f_lo
        # PRECEDENCE MATTERS, and getting it wrong once is what caught this:
        # a feed that never refines only EXPLAINS a row whose error also fails to
        # fall. `continuous_helix`'s feed is fixed at one segment too, and its
        # error still falls 78 % -- the radiator's refinement dominates there, so
        # it is a density row, not a placement one. Density is therefore tested
        # first, and placement only claims the rows refinement did not move.
        if fell is not None and fell >= 0.60 and r320 is not None and r320 < 0.02:
            v = "density"
        elif fell is not None and fell < 0.20 and not feed_refines:
            v = "placement"
        elif r320 is not None and r320 >= 0.10:
            v = "reference"
        elif fell is not None and fell >= 0.40:
            v = "reference"
        else:
            v = "unexplained"
        verdicts[d] = (v, fell, r320, f_lo, f_hi)
        w(
            f"**Verdict: {v.upper()}.** Absolute error across the d=3 ladder "
            f"({lad[0]} → {lad[-1]}) "
            f"{'fell ' + format(100 * fell, '.0f') + ' %' if fell is not None else 'not measurable'}; "
            f"the reference moved {100 * r320:.2f} % between 160 and 320; the fed "
            f"segment went {f_lo:.5f} m → {f_hi:.5f} m across the ladder"
            f"{' (unchanged — the feed never refines)' if not feed_refines else ''}.\n"
        )

    w("## Verdicts\n")
    w(
        "| design | verdict | error fall 12→30 | reference move 160→320 | fed segment across the ladder |"
    )
    w("|---|---|---:|---:|---|")
    for d, (v, fell, r320, f_lo, f_hi) in verdicts.items():
        fall = "—" if fell is None else f"{100 * fell:.0f} %"
        move = "—" if r320 is None else f"{100 * r320:.2f} %"
        feed = f"{f_lo:.5f} → {f_hi:.5f} m" + (
            " (unchanged)" if f_hi >= 0.9 * f_lo else ""
        )
        w(f"| `{d}` | **{v}** | {fall} | {move} | {feed} |")
    w("")

    notes = HERE / "hypotheses.md"
    if notes.is_file():
        w(notes.read_text(encoding="utf-8").rstrip())
        w("")
    text = "\n".join(out) + "\n"
    (HERE / "README.md").write_text(text, encoding="utf-8")
    sys.stdout.write(text)
    return 0


if __name__ == "__main__":
    sys.exit(main())
