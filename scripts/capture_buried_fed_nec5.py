"""Capture the NEC-5 printouts for the fully-buried FED class (#1025).

Banks two fixtures for `specialty.buried_dipole` — a 5.9 m dipole 15 cm down
over eps_r 13 / sigma 0.005 soil at 7.1 MHz, every part of it below the
interface including the excitation:

  buried_dipole_fed_below      the deck the wrapper writes TODAY (ground
                               flag -1), whose impedance tracks momwire
  buried_dipole_fed_below_ge1  the same deck with ground flag 1 — the
                               spelling shipped before #1025 — kept as the
                               WITNESS for why the flag matters, so a silent
                               revert fails a test instead of printing
                               milliohms

The printouts are End-User Reports; NEC-5 is (c) LLNL, LLNL-CODE-746721. The
binary is user-licensed and never distributed with antennaknobs.

Usage:  NEC5_EXE=/path/to/nec5cl python scripts/capture_buried_fed_nec5.py
"""

import json
import sys
from pathlib import Path

from antennaknobs.designs.specialty.buried_dipole import Builder
from antennaknobs.engines.nec5 import NEC5Engine, find_nec5

FIXTURES = Path(__file__).resolve().parent.parent / "tests" / "fixtures" / "nec5"
SOIL = ("finite", 13.0, 0.005)


def main() -> int:
    if find_nec5() is None:
        print("no licensed NEC-5 binary ($NEC5_EXE unset)", file=sys.stderr)
        return 1
    b = Builder()
    eng = NEC5Engine(b, ground=SOIL)
    deck = eng.deck([float(b.default_params["freq"])])
    ge = next(ln for ln in deck.splitlines() if ln.startswith("GE"))
    if ge != "GE -1 0":
        print(
            f"unexpected GE card {ge!r} — has the flag logic changed?", file=sys.stderr
        )
        return 2

    variants = {
        "buried_dipole_fed_below": deck,
        "buried_dipole_fed_below_ge1": deck.replace(ge, "GE 1 -1"),
    }
    manifest_path = FIXTURES / "manifest.json"
    manifest = json.loads(manifest_path.read_text())
    for name, text in variants.items():
        (FIXTURES / f"{name}.nec").write_text(text)
        (FIXTURES / f"{name}.out").write_text(eng._run(text))
        print(f"captured {name}")
    manifest["fixtures"]["buried_dipole_fed_below"] = {
        "deck": "buried_dipole_fed_below.nec",
        "printout": "buried_dipole_fed_below.out",
        "note": (
            "specialty.buried_dipole: the fully-buried FED class (#1025) — "
            "wire and excitation both below the interface, ground flag -1"
        ),
    }
    manifest["fixtures"]["buried_dipole_fed_below_ge1"] = {
        "deck": "buried_dipole_fed_below_ge1.nec",
        "printout": "buried_dipole_fed_below_ge1.out",
        "note": (
            "the same deck with ground flag 1, the pre-#1025 spelling: the "
            "witness for the milliohm print, kept so a revert fails a test"
        ),
    }
    manifest_path.write_text(json.dumps(manifest, indent=2) + "\n")
    print(f"manifest updated: {manifest_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
