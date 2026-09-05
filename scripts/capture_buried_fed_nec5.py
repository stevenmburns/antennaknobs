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

    # The CONTACT class (antennaknobs#1025 follow-up): the connected
    # buried-radial screen, whose conductor crosses the interface. Served and
    # witness, same pair as above — the witness is the flag the wrapper used
    # to write, which is 34.6 % from momwire in R here.
    from antennaknobs.designs.verticals.buried_radial_vertical import (
        Builder as BuriedRadialVertical,
    )

    cb = BuriedRadialVertical()
    ceng = NEC5Engine(cb, ground=SOIL)
    cdeck = ceng.deck([float(cb.freq)])
    cge = next(ln for ln in cdeck.splitlines() if ln.startswith("GE"))
    if cge != "GE -1 0":
        print(f"unexpected contact GE card {cge!r}", file=sys.stderr)
        return 3
    variants["brv_connected_minus1"] = cdeck
    variants["brv_connected_ge1_witness"] = cdeck.replace(cge, "GE 1 0")
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
    manifest["fixtures"]["brv_connected_minus1"] = {
        "deck": "brv_connected_minus1.nec",
        "printout": "brv_connected_minus1.out",
        "note": (
            "verticals.buried_radial_vertical connected: the CONTACT class "
            "whose conductor crosses the interface, on ground flag -1 "
            "(antennaknobs#1025) — 2.6 % from momwire in R"
        ),
    }
    manifest["fixtures"]["brv_connected_ge1_witness"] = {
        "deck": "brv_connected_ge1_witness.nec",
        "printout": "brv_connected_ge1_witness.out",
        "note": (
            "the same deck on the flag the wrapper used to write: the WITNESS "
            "for the 34.6 % contact-class error and the flat-in-radial-count "
            "reading, kept so a revert fails a test"
        ),
    }
    manifest_path.write_text(json.dumps(manifest, indent=2) + "\n")
    print(f"manifest updated: {manifest_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
