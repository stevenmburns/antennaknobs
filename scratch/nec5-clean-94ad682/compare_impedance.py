"""The strict half of the unit-2 gate: ANTENNA INPUT PARAMETERS, byte for byte.

    python scratch/nec5-clean-94ad682/compare_impedance.py <dir_a> <dir_b>

Unit 2 changes the pattern and near-field paths and leaves the solve alone, so
**every impedance row must be byte-identical** and any difference is a
regression rather than a tolerance question. That is the opposite of the rule for
the field tables (`compare_tables.py`), and the two gates are separate files so
neither can be loosened by accident.

WHOLE SECTIONS, not one number per deck. `run_set.sh`'s timing.tsv carries a
single impedance per deck taken with `grep -A4 | tail -1`, which on a multi-FR
deck is the LAST frequency's row -- the mirror image of the `_first_z` trap. It
is consistent across builds, so it is fine as a timing-table sanity column, but
it is not a gate: a deck with 500 frequencies has 500 impedance rows and all of
them have to hold.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

HEADER = "- - - ANTENNA INPUT PARAMETERS - - -"


def sections(text: str) -> list[str]:
    """Every ANTENNA INPUT PARAMETERS block, verbatim, as one string each."""
    out = []
    chunks = text.split(HEADER)[1:]
    for ch in chunks:
        rows = []
        for line in ch.splitlines():
            if not line.strip():
                if rows:
                    break
                continue
            if "TAG" in line.upper() or "NO." in line.upper() or "OHMS" in line.upper():
                continue  # the column headers
            if line.lstrip().startswith("-"):
                break  # the next section's rule
            rows.append(line.rstrip())
        out.append("\n".join(rows))
    return out


def main(argv=None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("dir_a")
    ap.add_argument("dir_b")
    a = ap.parse_args(argv)
    A, B = Path(a.dir_a), Path(a.dir_b)
    decks = sorted(p.stem for p in A.glob("*.out") if (B / p.name).is_file())
    only_a = sorted(p.stem for p in A.glob("*.out") if not (B / p.name).is_file())
    only_b = sorted(p.stem for p in B.glob("*.out") if not (A / p.name).is_file())
    print(f"{A.name} vs {B.name}: ANTENNA INPUT PARAMETERS, byte for byte\n")
    hdr = f"{'deck':30s} {'blocks a/b':>11s} {'rows':>7s}  verdict"
    print(hdr)
    print("-" * len(hdr))
    fails = []
    for d in decks:
        sa = sections((A / f"{d}.out").read_text(errors="replace"))
        sb = sections((B / f"{d}.out").read_text(errors="replace"))
        rows = sum(len(s.splitlines()) for s in sa)
        if len(sa) != len(sb):
            print(
                f"{d:30s} {len(sa):5d}/{len(sb):<5d} {rows:7d}  FAIL — block count differs"
            )
            fails.append(d)
            continue
        diff = [i for i, (x, y) in enumerate(zip(sa, sb, strict=False)) if x != y]
        if diff:
            print(
                f"{d:30s} {len(sa):5d}/{len(sb):<5d} {rows:7d}  FAIL — blocks {diff[:5]} differ"
            )
            for i in diff[:1]:
                xa, xb = sa[i].splitlines(), sb[i].splitlines()
                for j, (la, lb) in enumerate(zip(xa, xb, strict=False)):
                    if la != lb:
                        print(
                            f"{'':32s}block {i} row {j}:\n{'':34s}a: {la.strip()}\n{'':34s}b: {lb.strip()}"
                        )
                        break
            fails.append(d)
        else:
            print(f"{d:30s} {len(sa):5d}/{len(sb):<5d} {rows:7d}  identical")
    if only_a or only_b:
        print(f"\ndecks only in {A.name}: {only_a or 'none'}")
        print(f"decks only in {B.name}: {only_b or 'none'}")
    print(
        "\nVERDICT:",
        "PASS — every impedance row byte-identical"
        if not fails
        else f"FAIL on {len(fails)} deck(s): {', '.join(fails)}",
    )
    return 1 if fails else 0


if __name__ == "__main__":
    sys.exit(main())
