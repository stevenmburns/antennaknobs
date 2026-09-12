"""Why Population B is empty: the corpus's Sommerfeld decks reach momwire as refl-coef.

    python scratch/956-census/gn_ground_probe.py

Three facts, each measured here rather than argued:

1. `translate` REWRITES `GN 2` to `GN 0` on 1,104 of the 1,105 raw decks that
   carry it -- against the corpus tool's own documented contract, which says
   "GN -1 / GN 1 / GN 2 pass".
2. The two engines read `GN 0` differently, and both are self-consistent. NEC-5
   has no reflection-coefficient option, so `GN 0` there IS a Sommerfeld ground
   (the tool notes this per deck). momwire's portal honours the NEC-2 meaning:
   `GN 0` -> the reflection-coefficient approximation, `GN 2` -> Sommerfeld. Run
   the same deck under each spelling and the portal says which in its own
   ENVIRONMENT block.
3. So on 930 of the census's comparable decks, the published comparison is
   momwire refl-coef against NEC-5 Sommerfeld -- two ground MODELS, not two
   formulations of one problem.

AND THE TEMPTING CONCLUSION IS WRONG, which is why the sample was run: fixing
the spelling does NOT explain the census's disagreement. On a seeded 120-deck
sample re-solved under `GN 2`, the median |dZ|/max against NEC-5 moves 0.0994 ->
0.0907, Sommerfeld is closer on 63 of 118, and the reactance-SIGN disagreement
count does not move at all (28 -> 28). A real defect with a small effect.
"""

from __future__ import annotations

import json
import re
import statistics
import sys
from pathlib import Path

H = Path.home() / "nec5-timing"
ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scripts" / "nec5_corpus"))

from nec5_corpus import _DEGENERATE_OHMS, _first_z  # noqa: E402


def load(p: Path) -> dict:
    rows = {}
    for line in Path(p).open(encoding="utf-8"):
        r = json.loads(line)
        if r.get("file"):
            rows[r["file"]] = r
    return rows


def main() -> int:
    # fact 1: the rewrite
    origin = {}
    for line in (H / "nec5-1430" / "translate-report.jsonl").open(encoding="utf-8"):
        rec = json.loads(line)
        if "_meta" not in rec:
            for w in rec.get("written") or []:
                origin[w] = rec["file"]

    def first_gn(p: Path) -> str | None:
        for line in p.read_text(encoding="latin-1", errors="replace").splitlines():
            if line.upper().startswith("GN"):
                return line.strip()
        return None

    raw_gn2 = rewritten = 0
    for rel, raw in origin.items():
        tp, rp = H / "nec5-1430" / rel, H / "raw" / raw
        if not (tp.is_file() and rp.is_file()):
            continue
        rg = first_gn(rp)
        if rg and re.match(r"^GN[\s,]+2", rg, re.I):
            raw_gn2 += 1
            tg = first_gn(tp)
            if tg and re.match(r"^GN[\s,]+0", tg, re.I):
                rewritten += 1
    print(f"raw decks whose first GN card is `GN 2`: {raw_gn2}")
    print(f"   of those, translated to `GN 0`:       {rewritten}")

    # fact 3 / the sample
    refl = load(ROOT / "docs/status/data/2026-09-11-corpus-census-momwire.jsonl")
    somm = load(H / "gn2-sample-momwire.jsonl")
    nec5 = load(H / "check-1430-nec5.jsonl")
    sample = json.loads(
        (Path(__file__).resolve().parent / "gn2-sample.json").read_text()
    )

    kept = []
    for f in sample:
        za, zb, z5 = (
            _first_z(refl.get(f, {})),
            _first_z(somm.get(f, {})),
            _first_z(nec5.get(f, {})),
        )
        if None in (za, zb, z5):
            continue
        za, zb, z5 = complex(za), complex(zb), complex(z5)
        if min(abs(za), abs(zb), abs(z5)) < _DEGENERATE_OHMS:
            continue
        kept.append((f, za, zb, z5))

    def rel_(a, b):
        return abs(a - b) / max(abs(a), abs(b))

    d_refl = [rel_(a, n) for _f, a, _b, n in kept]
    d_somm = [rel_(b, n) for _f, _a, b, n in kept]
    qs = lambda v, p: statistics.quantiles(v, n=100)[p - 1]  # noqa: E731
    print(
        f"\nsample: {len(kept)} of {len(sample)} decks with three impedances and none degenerate"
    )
    print(
        f"{'momwire ground model':40s} {'median':>8s} {'p75':>8s} {'p90':>8s} {'>1%':>5s} {'>10%':>5s}"
    )
    for name, v in (
        ("refl-coef (GN 0, as censused)", d_refl),
        ("Sommerfeld (GN 2)", d_somm),
    ):
        print(
            f"{name:40s} {statistics.median(v):8.4f} {qs(v, 75):8.4f} {qs(v, 90):8.4f} "
            f"{sum(1 for x in v if x > 0.01):5d} {sum(1 for x in v if x > 0.10):5d}"
        )
    better = sum(1 for i in range(len(kept)) if d_somm[i] < d_refl[i])
    print(
        f"\nSommerfeld closer to NEC-5 than refl-coef on {better} of {len(kept)} decks"
    )
    sg = lambda idx: sum(1 for r in kept if (r[idx].imag > 0) != (r[3].imag > 0))  # noqa: E731
    print(
        f"reactance-sign disagreements with NEC-5: refl-coef {sg(1)}, Sommerfeld {sg(2)} (of {len(kept)})"
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
