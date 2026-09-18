"""Fold the two corpus passes into the before/after table AK#1579 reports."""

import argparse
import json
from pathlib import Path


def load(p):
    return {
        r["id"]: r for r in (json.loads(x) for x in Path(p).read_text().splitlines())
    }


def cell(rec, eng):
    errs = rec.get(eng + "_err")
    if errs:
        return f"{max(errs) * 100:.2f} %"
    why = rec.get(eng + "_fail") or rec.get("reason") or ""
    if "node_gaps" in why:
        return "refuse: lone-end node gap"
    if "claimed by more than one" in why:
        return "refuse: #824 one piece"
    if "not reciprocal" in why:
        return "refuse: multiport Y"
    if "reflection-coefficient" in why:
        return "refuse: GN 0 fast ground"
    return "refuse"


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--before", default="corpus_before.jsonl")
    ap.add_argument("--after", default="corpus_after.jsonl")
    args = ap.parse_args()
    B, A = load(args.before), load(args.after)

    print("| deck | nec5 before | nec5 after | bspline before | bspline after |")
    print("|---|---|---|---|---|")
    moved = 0
    for i in sorted(B):
        row = [
            cell(B[i], "nec5"),
            cell(A[i], "nec5"),
            cell(B[i], "bspline"),
            cell(A[i], "bspline"),
        ]
        if row[0] == row[1] and row[2] == row[3]:
            continue
        moved += 1
        print(f"| {A[i]['deck']} | " + " | ".join(row) + " |")
    print(
        f"\n{moved} of {len(B)} decks moved; the rest are identical before and after.\n"
    )

    for eng in ("nec5", "bspline"):
        counts = dict(
            improved=0, unchanged=0, worsened=0, newly=0, lost=0, still_refused=0
        )
        worst = (0.0, None)
        for i in sorted(B):
            be, ae = B[i].get(eng + "_err"), A[i].get(eng + "_err")
            if be is None and ae is None:
                counts["still_refused"] += 1
            elif be is None:
                counts["newly"] += 1
            elif ae is None:
                counts["lost"] += 1
            else:
                bm, am = max(be), max(ae)
                if abs(am - bm) < 1e-9:
                    counts["unchanged"] += 1
                elif am < bm:
                    counts["improved"] += 1
                else:
                    counts["worsened"] += 1
                    if am - bm > worst[0]:
                        worst = (am - bm, i)
        print(
            eng,
            counts,
            "worst mover:",
            worst[1],
            f"+{worst[0] * 100:.2f} pts" if worst[1] else "",
        )


if __name__ == "__main__":
    main()
