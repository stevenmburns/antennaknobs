"""Capture the card-field witness pairs for antennaknobs#1190.

The #1025 lesson is that a value in the wrong field still prints a plausible
number. The audit found no further transposition, but three fields would be
SILENT if they were ever got wrong, so each is banked as a pair: the intended
spelling and the plausible wrong one, differing in exactly one field.

  ex_end1 / ex_end2          EX's I4 selects the segment END. #1025 recorded
                             this field as physics-irrelevant, having measured
                             it on a deck that was already degenerate.
  ld_end1 / ld_end2          LD's LDTAGT is a range endpoint for DISTRIBUTED
                             loads and the segment END for discrete ones — one
                             slot, two meanings, chosen by the type digit.
  ld_hpm / ld_h_per_segment  LDTYP=2 takes henries per METRE. A per-segment
                             value also solves, and its error scales with the
                             mesh, so it would read as a convergence effect.

The printouts are End-User Reports; NEC-5 is (c) LLNL, LLNL-CODE-746721. The
binary is user-licensed and never distributed.

Usage:  NEC5_EXE=/path/to/nec5cl python scripts/capture_card_witnesses_nec5.py
"""

import json
import sys
from pathlib import Path

from antennaknobs.engines.nec5 import NEC5Engine, find_nec5

ROOT = Path(__file__).resolve().parent.parent
FIXTURES = ROOT / "tests" / "fixtures" / "nec5"

HALF, GAP, RAD = 2.9557, 0.025, 5.0e-4
GN = "GN 0 0 0 0 1.300000E+01 5.000000E-03 1.000000E+00 0.000000E+00 NOFILE\n"
FR = "FR 0 1 0 0 7.100000E+00 0.000000E+00\n"
SEG_LEN = (HALF - GAP) / 25.0
L_PER_M = 2.5e-7


def _gw(z):
    return (
        f"GW 1 25 {-HALF:.6E} 0. {z:.6E} {-GAP:.6E} 0. {z:.6E} {RAD:.6E}\n"
        f"GW 2 2 {-GAP:.6E} 0. {z:.6E} {GAP:.6E} 0. {z:.6E} {RAD:.6E}\n"
        f"GW 3 25 {GAP:.6E} 0. {z:.6E} {HALF:.6E} 0. {z:.6E} {RAD:.6E}\n"
    )


def ex_deck(end):
    """Buried, documented ground card — a HEALTHY deck, which is the point."""
    return (
        "CM 1190 EX end witness\nCE\n"
        + _gw(-0.15)
        + "GE -1 0\n"
        + GN
        + f"EX 0 2 1 {end} 1.000000E+00 0.000000E+00\n"
        + FR
        + "XQ 0\nEN\n"
    )


def ld_deck(ld):
    return (
        "CM 1190 LD witness\nCE\n"
        + _gw(0.15)
        + "GE 1 0\n"
        + GN
        + ld
        + "EX 0 2 1 2 1.000000E+00 0.000000E+00\n"
        + FR
        + "XQ 0\nEN\n"
    )


VARIANTS = {
    "witness_ex_end1": ex_deck(1),
    "witness_ex_end2": ex_deck(2),
    "witness_ld_discrete_end1": ld_deck("LD 4 1 13 1 5.000000E+01 0.000000E+00 0.\n"),
    "witness_ld_discrete_end2": ld_deck("LD 4 1 13 2 5.000000E+01 0.000000E+00 0.\n"),
    "witness_ld_henries_per_m": ld_deck(f"LD 2 0 0 0 0. {L_PER_M:.6E} 0.\n"),
    "witness_ld_henries_per_seg": ld_deck(
        f"LD 2 0 0 0 0. {L_PER_M * SEG_LEN:.6E} 0.\n"
    ),
}

NOTES = {
    "witness_ex_end1": "EX I4=1: source at end 1. Pairs with end2 — #1190 EX row.",
    "witness_ex_end2": "EX I4=2: source at end 2, the wrapper's spelling.",
    "witness_ld_discrete_end1": "LD type 4 at LDTAGT=1 (segment end 1).",
    "witness_ld_discrete_end2": "LD type 4 at LDTAGT=2 (segment end 2).",
    "witness_ld_henries_per_m": "LDTYP=2 with henries per METRE, the intended unit.",
    "witness_ld_henries_per_seg": (
        "the same jacket inductance as henries per SEGMENT in the per-metre "
        "slot: wrong by the segment length, so the error SCALES WITH THE MESH "
        "and reads as a convergence effect rather than a units bug"
    ),
}


def main():
    if find_nec5() is None:
        print("no licensed NEC-5 binary ($NEC5_EXE unset)", file=sys.stderr)
        return 1
    eng = NEC5Engine.__new__(NEC5Engine)
    eng._exe = find_nec5()
    eng._timeout = 900.0
    eng._capture_dir = None
    eng.run_log = []
    manifest_path = FIXTURES / "manifest.json"
    manifest = json.loads(manifest_path.read_text())
    for name, deck in VARIANTS.items():
        (FIXTURES / f"{name}.nec").write_text(deck)
        (FIXTURES / f"{name}.out").write_text(eng._run(deck))
        manifest["fixtures"][name] = {
            "deck": f"{name}.nec",
            "printout": f"{name}.out",
            "note": NOTES[name],
        }
        print(f"captured {name}")
    manifest_path.write_text(json.dumps(manifest, indent=2) + "\n")
    print(f"manifest updated: {manifest_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
