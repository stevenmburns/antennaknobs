"""AK#1469 amendment 2: score G9a and G9b from the two ladder captures.

    python partB_gates_g9.py <before ladder.jsonl> <after ladder.jsonl>

G9a: |Z_before(9) - Z_after(9)| < |Z_before(1) - Z_after(1)| / 3, on at least 4 of 5.
G9b: with Z_ref = the midpoint of Z_before(9) and Z_after(9), and scored only
where G9a holds, |Z_after(1) - Z_ref| < |Z_before(1) - Z_ref| on at least 80 %.
"""

import json
import sys


def _load(path):
    with open(path, encoding="utf-8") as fh:
        return {(r["deck"], r["r"]): r for r in map(json.loads, fh)}


def main(argv):
    before, after = _load(argv[0]), _load(argv[1])
    decks = sorted({d for d, _r in before})
    a_hits = b_hits = b_scored = 0
    for deck in decks:
        rows = [(before.get((deck, r)), after.get((deck, r))) for r in (1, 3, 9)]
        if any(
            b is None
            or a is None
            or "ok" not in (b["status"], a["status"])
            or b["status"] != a["status"]
            for b, a in rows
        ):
            print(
                f"{deck}: not scorable {[(b and b['status'], a and a['status']) for b, a in rows]}"
            )
            continue
        zb = [complex(*b["z"][0]) for b, _a in rows]
        za = [complex(*a["z"][0]) for _b, a in rows]
        d1, d3, d9 = (abs(zb[i] - za[i]) for i in range(3))
        g9a = d9 < d1 / 3
        a_hits += g9a
        zref = (zb[2] + za[2]) / 2
        eb, ea = abs(zb[0] - zref), abs(za[0] - zref)
        print(f"{deck}")
        for i, r in enumerate((1, 3, 9)):
            print(
                f"    r={r}: before {zb[i]:.5f}  after {za[i]:.5f}  |diff| {abs(zb[i] - za[i]):.3e}"
            )
        print(
            f"    G9a: d9 {d9:.3e} vs d1/3 {d1 / 3:.3e} -> {'HIT' if g9a else 'MISS'}"
        )
        mark = "not scored (G9a miss)"
        if g9a:
            b_scored += 1
            b_hits += ea < eb
            mark = "HIT" if ea < eb else "MISS"
        print(f"    G9b: |after(1)-ref| {ea:.3e} vs |before(1)-ref| {eb:.3e} -> {mark}")
    print(f"G9a: {a_hits}/{len(decks)} (bar 4 of 5)")
    if b_scored:
        print(f"G9b: {b_hits}/{b_scored} = {100 * b_hits / b_scored:.0f} % (bar 80 %)")


if __name__ == "__main__":
    main(sys.argv[1:])
