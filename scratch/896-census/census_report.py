"""AK#896: join the momwire and NEC-5 corpus reports into the status-doc tables.

    python scratch/896-census/census_report.py \
        --nec5 ~/nec5-timing/check-base.jsonl \
        --momwire ~/nec5-timing/check-momwire.jsonl

Prints markdown. Every table is computed here; nothing is transcribed by hand.

THE JOIN IS `nec5_corpus._first_z`, imported rather than reimplemented. A deck
with a multi-point `FR` sweep prints one ANTENNA INPUT PARAMETERS section per
frequency, and comparing one report's LAST row against another's FIRST once read
a 72 % disagreement into two builds that agreed to the last digit. A census is
exactly the workload that springs that trap at scale, so it uses the function
that has the docstring and the test rather than a local copy that does not.

THE THRESHOLD IS NOT 1e-4. That is the corpus tool's default and it is right for
its own job — diffing two builds of ONE engine, where the last printed digit is
the noise floor. Two DIFFERENT formulations agree to no such thing: on a 60-deck
smoke run, 38 of 39 jointly-solved decks "moved" at 1e-4, which is a statistic
about floating point rather than about antennas. So the headline here is the
DISTRIBUTION of |dZ|/|Z| with its quantiles, and the named cases are the tail.
"""

from __future__ import annotations

import argparse
import json
import statistics
import sys
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scripts" / "nec5_corpus"))

from nec5_corpus import _DEGENERATE_OHMS, _first_z  # noqa: E402

# Bands for the agreement table. Chosen to be read, not to be passed: 1 % is
# tighter than any mesh-convergence claim either engine makes at corpus
# densities, and 10 % is where two solvers are answering different questions.
BANDS = ((1e-3, "< 0.1 %"), (1e-2, "< 1 %"), (0.1, "< 10 %"), (float("inf"), ">= 10 %"))


def load(path: Path) -> tuple[dict, dict]:
    meta, rows = {}, {}
    with open(path, encoding="utf-8") as fh:
        for line in fh:
            rec = json.loads(line)
            if "_meta" in rec:
                meta = rec["_meta"]
                continue
            key = rec.get("file")
            if key:
                rows[key] = rec
    return meta, rows


def rel_dz(a: dict, b: dict):
    """|dZ|/|Z| between two reports' FIRST impedance rows, or None.

    `_DEGENERATE_OHMS` is the corpus tool's own floor, reused: without it a deck
    whose |Z| is milliohms manufactures a colossal relative difference out of an
    absolute one nobody would notice.
    """
    za, zb = _first_z(a), _first_z(b)
    if za is None or zb is None:
        return None
    scale = max(abs(za), abs(zb), _DEGENERATE_OHMS)
    return abs(za - zb) / scale, za, zb


def main(argv=None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--nec5", required=True)
    ap.add_argument("--momwire", required=True)
    ap.add_argument("--cases", type=int, default=25, help="named tail cases to print")
    a = ap.parse_args(argv)

    m5, r5 = load(Path(a.nec5).expanduser())
    mm, rm = load(Path(a.momwire).expanduser())
    keys = sorted(set(r5) & set(rm))

    print("## Coverage\n")
    print(f"- decks in the NEC-5 report: **{len(r5)}**")
    print(f"- decks in the momwire report: **{len(rm)}**")
    print(f"- joined on `file`: **{len(keys)}**\n")

    s5 = Counter(r5[k]["status"] for k in keys)
    sm = Counter(rm[k]["status"] for k in keys)
    print("| status | NEC-5 | momwire |")
    print("|---|---:|---:|")
    for st in sorted(set(s5) | set(sm)):
        print(f"| `{st}` | {s5.get(st, 0)} | {sm.get(st, 0)} |")

    both_ok = [k for k in keys if r5[k]["status"] == "ok" and rm[k]["status"] == "ok"]
    print(
        f"\nBoth engines solved and printed an impedance on **{len(both_ok)}** decks.\n"
    )

    # --- is the join comparing the same thing on both sides? ---------------
    # Published as evidence rather than asserted. `_first_z` takes row 0 of the
    # first frequency's section on each side; if the two engines ordered their
    # sources differently, every number below would be a comparison of two
    # different ports and would look exactly like physics. The 72 % phantom
    # `_first_z` exists to prevent was this shape of mistake one level up.
    same_port = sum(
        1
        for k in both_ok
        if r5[k]["z"] and rm[k]["z"] and r5[k]["z"][0][:2] == rm[k]["z"][0][:2]
    )
    same_count = sum(1 for k in both_ok if len(r5[k]["z"]) == len(rm[k]["z"]))
    print("### Is the join sound?\n")
    print(
        f"- row 0 is the same `(tag, seg)` on both sides: "
        f"**{same_port}/{len(both_ok)}**"
    )
    print(
        f"- both reports print the same number of sources: "
        f"**{same_count}/{len(both_ok)}**\n"
    )
    if same_port != len(both_ok) or same_count != len(both_ok):
        print(
            "> **The join is NOT sound on every deck.** Every figure below is "
            "suspect until the mismatched decks are excluded or explained.\n"
        )

    print("## Agreement on the driving-point impedance\n")
    rows, degenerate = [], []
    for k in both_ok:
        got = rel_dz(r5[k], rm[k])
        if got is None:
            continue
        # A reported |Z| of exactly zero is not a disagreement, it is an engine
        # declining to have an opinion. Left in the distribution it scores as a
        # 100 % mover through the degenerate floor and inflates the tail with
        # something that is not a difference of physics.
        if abs(got[1]) == 0.0 or abs(got[2]) == 0.0:
            degenerate.append((k, got[1], got[2]))
            continue
        rows.append((got[0], k, got[1], got[2]))
    rows.sort()
    if degenerate:
        print(
            f"{len(degenerate)} deck(s) report an impedance of exactly zero on "
            "one side and are held out of the distribution below:\n"
        )
        print("| deck | momwire Z | NEC-5 Z |")
        print("|---|---|---|")
        for k, z5, zm in degenerate:
            print(
                f"| `{k}` | {zm.real:.4g}{zm.imag:+.4g}j | "
                f"{z5.real:.4g}{z5.imag:+.4g}j |"
            )
        print()
    if not rows:
        print("**No comparable decks — this is a failure, not a clean pass.**")
        return 2
    vals = [r[0] for r in rows]
    print(f"Comparable decks: **{len(rows)}**\n")
    print("| relative |dZ|/|Z| | decks | share |")
    print("|---|---:|---:|")
    lo = 0.0
    for hi, label in BANDS:
        n = sum(1 for v in vals if lo <= v < hi)
        print(f"| {label} | {n} | {100 * n / len(vals):.1f} % |")
        lo = hi
    qs = [0.5, 0.75, 0.9, 0.95, 0.99]
    print("\n| quantile | " + " | ".join(f"p{int(q * 100)}" for q in qs) + " |")
    print("|---|" + "---:|" * len(qs))
    print(
        "| relative |dZ|/|Z| | "
        + " | ".join(f"{vals[int(q * (len(vals) - 1))]:.2e}" for q in qs)
        + " |"
    )
    print(f"\nMedian {statistics.median(vals):.2e}; worst {vals[-1]:.2e}.\n")

    print(f"## The tail: the {a.cases} widest disagreements\n")
    print("| deck | momwire Z | NEC-5 Z | rel |dZ|/|Z| |")
    print("|---|---|---|---:|")
    for v, k, z5, zm in rows[: -a.cases - 1 : -1]:
        print(
            f"| `{k}` | {zm.real:.4g}{zm.imag:+.4g}j | "
            f"{z5.real:.4g}{z5.imag:+.4g}j | {v:.3g} |"
        )

    print("\n## momwire advisories\n")
    adv = Counter()
    for k in keys:
        for name, n in rm[k].get("advisories") or []:
            adv[name] += n
    if adv:
        print("| advisory | decks |")
        print("|---|---:|")
        for name, n in adv.most_common():
            print(f"| `{name}` | {n} |")
    else:
        print("_None raised._")

    print("\n## Where momwire declined\n")
    why = Counter()
    for k in keys:
        rec = rm[k]
        if rec["status"] in ("ok", "ok-no-source"):
            continue
        msg = (rec.get("error") or rec["status"]).strip()
        why[msg[:90]] += 1
    print("| reason | decks |")
    print("|---|---:|")
    for msg, n in why.most_common(20):
        print(f"| {msg} | {n} |")

    print(
        "\n<sub>Environments — NEC-5: "
        f"`{m5.get('exe', '?')}`, momwire: "
        f"`{mm.get('environment', {}).get('momwire_version', '?')}`, "
        f"seg cap {mm.get('environment', {}).get('seg_cap', '?')}, "
        f"timing_valid {mm.get('timing_valid', '?')}.</sub>"
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
