"""momwire#674/#760 — the quadrature ladder, re-measured now that high q is cheap.

Every earlier rung of this study bought high `n_qp_pair` on the numpy path,
because `_bspline_kernels`' `not in_medium` predicate sent every below-medium
pair there (momwire#778). That made q=64 a 39 s proposition on the buried
radial vertical and q>=96 effectively unaffordable, so the ladders stopped
short of the limit on exactly the decks that needed them.

With #778's COMPLEX_K instantiation the off-edge fill is ~20-40x faster in the
medium, so the ladder can simply be run out to convergence. This probe does
that and reports, per rung: the answer, the wall cost, and the distance from
the finest rung -- plus the step ratios, which say whether the tail is still
first order (the #760 reading at low q) or has entered the exponential regime
Gauss-Legendre gives on a smooth integrand.

Run: prlimit --as=$((8*1024*1024*1024)) \
       .venv/bin/python scratch/674-study/probe5_quadrature_ladder.py \
       [--deck fan|brv] [--case base|n2] [--ladder 4,8,16,32,64,96,128]
"""

from __future__ import annotations

import argparse
import json
import sys
import time
import warnings
from pathlib import Path


sys.path.insert(0, str(Path(__file__).resolve().parent))
sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "momwire" / "tests"))

from momwire.bspline import BSplineSolver

import probe4_sensitivity_ranking as P

HERE = Path(__file__).resolve().parent


def solve(deck, case, q):
    s = BSplineSolver(**P.DECKS[deck](case, q))
    t0 = time.time()
    z, _coeffs = s.compute_impedance()
    return complex(z), time.time() - t0


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--deck", default="brv", choices=sorted(P.DECKS))
    ap.add_argument("--case", default="base")
    ap.add_argument("--ladder", default="4,8,16,32,64,96,128")
    args = ap.parse_args()
    ladder = [int(x) for x in args.ladder.split(",")]

    print(f"[{args.deck}/{args.case}] quadrature ladder {ladder}", flush=True)
    rows = []
    for q in ladder:
        z, dt = solve(args.deck, args.case, q)
        rows.append(dict(q=q, z=f"{z:.6f}", secs=round(dt, 1)))
        print(f"  q={q:<4d} Z = {z:.6f}   ({dt:.1f}s)", flush=True)

    zs = [complex(r["z"]) for r in rows]
    limit = zs[-1]
    print(
        f"\n  {'q':>5} {'|Z - Z(finest)|':>16} {'step |dZ|':>12} {'ratio':>8}"
        f" {'secs':>7}"
    )
    prev_step = None
    for i, (q, z) in enumerate(zip(ladder, zs, strict=True)):
        dist = abs(z - limit)
        step = abs(z - zs[i - 1]) if i else float("nan")
        ratio = (prev_step / step) if (i > 1 and step > 0) else float("nan")
        print(
            f"  {q:>5} {dist:>16.6f} {step:>12.6f} {ratio:>8.2f}"
            f" {rows[i]['secs']:>7.1f}"
        )
        if i:
            prev_step = step
        rows[i]["dist_from_finest"] = round(dist, 6)

    # Cost of the bump, which is the thing #778 changed.
    if 8 in ladder and 32 in ladder:
        c8 = rows[ladder.index(8)]["secs"]
        c32 = rows[ladder.index(32)]["secs"]
        print(
            f"\n  q=8 -> q=32 cost ratio: {c32 / max(c8, 1e-9):.2f}x"
            f"  ({c8:.1f}s -> {c32:.1f}s)"
        )

    path = HERE / "results" / f"probe5-ladder-{args.deck}-{args.case}.json"
    path.parent.mkdir(exist_ok=True)
    path.write_text(
        json.dumps(
            dict(deck=args.deck, case=args.case, ladder=ladder, rows=rows), indent=2
        )
    )
    print(f"\nsaved {path}", flush=True)


if __name__ == "__main__":
    warnings.filterwarnings("ignore")
    main()
