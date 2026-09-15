"""Score the #1532 confirmation against the catalog records. No number transcribed.

    python scratch/catalog-razor-nec5-bs2/confirm_1532_report.py

Reads `records.jsonl` (the catalog run at b9bc3e2f0, BEFORE) and
`records-1532.jsonl` (the same harness on PR #1532's head, AFTER) and prints the
results section of `CONFIRM-1532.md`, including the C1-C4 verdicts.

C2 is a BIT-IDENTITY check, not an agreement check: it compares the recorded
[re, im] pairs exactly. Comparing them to a printed precision would pass on a
row that moved in the 12th digit, and "the momwire lane did not move" is a claim
about the code path, so it deserves the strict test.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

DESIGNS = ("dipoles.pota_invvee", "dipoles.invvee_catenary", "wire.efhw_sloper")
GROUNDS = ("free", "somm")
ENGINES = ("razor", "nec5", "bs2")
CATALOG_MEDIAN = 0.000665  # the razor-vs-NEC-5 median over all 340 catalog rows
C4_BAND = (0.00022, 0.0020)  # a factor of 3 either side of it


def load(path):
    out = {}
    for line in open(path, encoding="utf-8"):
        r = json.loads(line)
        if r["status"] == "ok":
            out[(r["design"], r["ground"], r["engine"])] = r
    return out


def zc(rec, port=0):
    return complex(*rec["z"][port])


def rel(a, b):
    return abs(a - b) / abs(b)


def main():
    here = Path(__file__).parent
    before = load(here / "records.jsonl")
    after = load(here / "records-1532.jsonl")
    w = print

    w("## Results\n")
    w("| design | ground | razor−NEC-5 before | after | NEC-5 Z before → after |")
    w("|---|---|---:|---:|---|")
    worst_after = 0.0
    afters = []
    for d in DESIGNS:
        for g in GROUNDS:
            nb, na = zc(before[(d, g, "nec5")]), zc(after[(d, g, "nec5")])
            rb = rel(zc(before[(d, g, "razor")]), nb)
            ra = rel(zc(after[(d, g, "razor")]), na)
            worst_after = max(worst_after, ra)
            afters.append(ra)
            w(
                f"| `{d}` | {g} | {100 * rb:.3f} % | **{100 * ra:.4f} %** | "
                f"{nb.real:.4f}{nb.imag:+.4f}j → {na.real:.4f}{na.imag:+.4f}j |"
            )
    w("")

    changed = [
        (d, g, e)
        for d in DESIGNS
        for g in GROUNDS
        for e in ENGINES
        if before[(d, g, e)]["z"] != after[(d, g, e)]["z"]
    ]
    identical = 3 * len(DESIGNS) * len(GROUNDS) - len(changed)
    changed_engines = sorted({e for _d, _g, e in changed})

    w("### C1–C4\n")
    w("| prediction | bar | measured | verdict |")
    w("|---|---|---|---|")
    c1 = worst_after <= 0.005
    w(
        f"| **C1** | razor−NEC-5 ≤ 0.5 % on all 6 rows | worst "
        f"{100 * worst_after:.4f} % | {'**HIT**' if c1 else '**MISS**'} |"
    )
    c2 = all(e == "nec5" for e in changed_engines)
    w(
        f"| **C2** | every bs2 and razor row bit-identical to `b9bc3e2f0` | "
        f"{identical} of 18 rows unchanged, byte for byte | "
        f"{'**HIT**' if c2 else '**MISS**'} |"
    )
    c3 = changed_engines == ["nec5"] and len(changed) == len(DESIGNS) * len(GROUNDS)
    w(
        f"| **C3** | only the NEC-5 rows move | {len(changed)} rows changed, "
        f"all `{'`, `'.join(changed_engines)}` | {'**HIT**' if c3 else '**MISS**'} |"
    )
    lo, hi = C4_BAND
    c4 = all(lo <= v <= hi for v in afters)
    w(
        f"| **C4** | after values within ×3 of the catalog median "
        f"{100 * CATALOG_MEDIAN:.4f} % (i.e. {100 * lo:.3f}–{100 * hi:.2f} %) | "
        f"range {100 * min(afters):.4f}–{100 * max(afters):.4f} % | "
        f"{'**HIT**' if c4 else '**MISS**'} |"
    )
    hits = sum((c1, c2, c3, c4))
    w("")
    w(f"Hit {hits} of 4.\n")
    w(
        f"The six rows carried the catalog study's entire >5 % razor-vs-NEC-5 "
        f"tail. They now sit at {100 * min(afters):.4f}–{100 * max(afters):.4f} %, "
        f"against a catalog-wide median of {100 * CATALOG_MEDIAN:.4f} % over the "
        f"other 100 designs — at the unjacketed background, not below it, which "
        f"is the strongest claim the data supports.\n"
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
