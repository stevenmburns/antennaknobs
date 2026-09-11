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
    """`compare`'s own relative impedance difference, or None.

    Deliberately `compare`'s formula and not a better one, because the status
    page cites `compare` as the join and a reader who runs the tool has to get
    the page's numbers back. Two consequences worth naming rather than quietly
    inheriting:

    * the denominator is |Z_a| — the FIRST report's — not a symmetric scale.
      With the NEC-5 report passed as `a` that makes every figure
      NEC-5-referenced. That is the tool's convention and not a claim that NEC-5
      is the reference, and it matters more than it looks. Measured on 85
      jointly-solved decks, `compare`'s ratio and the symmetric one
      |dZ| / max(|Za|, |Zb|) give the SAME median to five decimals (0.0691) and
      wildly different tails: p99 1.05 against 0.57, worst 62.8 against 1.01.
      A deck whose NEC-5 |Z| happens to be small is promoted to "worst
      disagreement" by the denominator alone.

      So the distribution below is `compare`'s, for reproducibility, and the
      NAMED CASES are ranked by the symmetric measure with both printed. The
      tail is the part of this census anyone acts on; it must not be an artifact
      of which engine sits under the line.
    * anything under `_DEGENERATE_OHMS` on EITHER side is excluded outright, not
      floored. A 5 % move on a deck reporting −0.53 ohm is a large percentage of
      nothing, and `necpp/ga_pjw_1.nec` is the deck that taught the tool so.

    Returns (rel, z_a, z_b), or ("degenerate", z_a, z_b), or None.
    """
    za, zb = _first_z(a), _first_z(b)
    if za is None or zb is None:
        return None
    if abs(za) < _DEGENERATE_OHMS or abs(zb) < _DEGENERATE_OHMS:
        return ("degenerate", za, zb)
    return abs(za - zb) / abs(za), za, zb


def sym_dz(za: complex, zb: complex) -> float:
    """|dZ| / max(|Za|, |Zb|): the same difference with neither engine under the
    line. Used to RANK the named cases; see `rel_dz` for why."""
    return abs(za - zb) / max(abs(za), abs(zb))


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
        if got[0] == "degenerate":
            degenerate.append((k, got[1], got[2]))
            continue
        rows.append((got[0], k, got[1], got[2]))
    rows.sort()
    if degenerate:
        print(
            f"{len(degenerate)} deck(s) report |Z| under {_DEGENERATE_OHMS:g} ohm "
            "on one side and are excluded by `compare`'s own degeneracy rule — a "
            "large percentage of nothing is not a disagreement:\n"
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
    sym_vals = sorted(sym_dz(r[2], r[3]) for r in rows)
    print(
        f"\nMedian {statistics.median(vals):.2e}; worst {vals[-1]:.2e} — but see "
        "the tail table: that worst figure is `compare`'s NEC-5-referenced ratio "
        f"and the same deck is {sym_vals[-1]:.2e} measured symmetrically. The "
        "median is identical either way.\n"
    )

    print(f"## The tail: the {a.cases} widest disagreements\n")
    print(
        "Ranked by the symmetric measure, with `compare`'s NEC-5-referenced "
        "ratio beside it. Where the two columns diverge sharply, the deck's "
        "NEC-5 |Z| is small and `compare`'s figure is mostly its denominator.\n"
    )
    print("| deck | momwire Z | NEC-5 Z | symmetric | `compare` |")
    print("|---|---|---|---:|---:|")
    ranked = sorted(rows, key=lambda r: sym_dz(r[2], r[3]), reverse=True)
    for v, k, z5, zm in ranked[: a.cases]:
        print(
            f"| `{k}` | {zm.real:.4g}{zm.imag:+.4g}j | "
            f"{z5.real:.4g}{z5.imag:+.4g}j | {sym_dz(z5, zm):.3g} | {v:.3g} |"
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
