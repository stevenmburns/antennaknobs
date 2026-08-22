"""Expand a 4nec2 ``SY`` parametric deck into a plain numeric NEC deck.

The ``SY`` card is a 4nec2 extension (symbolic variables, #417) that
antennaknobs' importer understands and stricter NEC front ends — momwire's
included — do not: to them ``GW 1 25 0. L_REF/2 …`` is a non-numerical
character in a field. Rather than teach every reader the expression
grammar, this translates a deck ONCE into the numbers it already meant.

The substitution is deliberately minimal: cards keep their order, their
spacing and their comments, and a field that was already a plain number is
copied through BYTE FOR BYTE. Only tokens that are actually symbolic get
evaluated, so a diff against the original shows exactly the expressions and
nothing else.

    python scripts/expand_sy_deck.py DECK.nec [-o OUT.nec]
    python scripts/expand_sy_deck.py DECK.nec --in-place
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))

from antennaknobs.nec_import import _define_sy, _value  # noqa: E402


def _format(value: float) -> str:
    """Integral values as bare integers, everything else to ten significant
    figures.

    Readers parse every field as a float, so the integer case is pure
    legibility: a segment count should not read as 2.50000E+01. The ten
    figures are not. The corpus writes its own numbers in a six-figure
    ``0.00000E+00`` style, and matching that here would quantize an
    expanded coordinate by ~5 µm — nothing on a 2 m yagi, but this file
    exists to say what the deck ALREADY MEANT, and rounding is not that.
    Ten figures round-trips the expression's own double to ~1e-10
    relative."""
    if abs(value - round(value)) < 1e-12 and abs(value) < 1e15:
        return str(int(round(value)))
    return f"{value:.9E}"


def expand(text: str) -> str:
    """`text` with its SY cards applied and removed."""
    syms: dict[str, float] = {}
    out = []
    for lineno, line in enumerate(text.splitlines(), 1):
        stripped = line.strip()
        where = f"line {lineno}"
        if not stripped:
            out.append(line)
            continue
        mnemonic = stripped.split()[0].upper()
        if mnemonic == "SY":
            # Consumed, not emitted: its whole content moves into the fields
            # below. Recorded as a comment so the deck still says where its
            # numbers came from.
            _define_sy(stripped[2:], syms, where)
            out.append(f"CM expanded from: {stripped}")
            continue
        if mnemonic in ("CM", "CE"):
            out.append(line)
            continue

        tokens = stripped.split()
        fields = []
        for token in tokens[1:]:
            try:  # already numeric — copy it through untouched
                float(token.replace("D", "E").replace("d", "e"))
                fields.append(token)
            except ValueError:
                fields.append(_format(_value(token, where, syms)))
        out.append(f"{tokens[0]:<4}" + "".join(f" {f:>12}" for f in fields))
    return "\n".join(out) + "\n"


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("deck", type=Path)
    ap.add_argument("-o", "--output", type=Path)
    ap.add_argument("--in-place", action="store_true")
    args = ap.parse_args()

    expanded = expand(args.deck.read_text())
    target = args.deck if args.in_place else args.output
    if target is None:
        sys.stdout.write(expanded)
        return 0
    target.write_text(expanded)
    print(f"wrote {target}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
