"""antennaknobs#1485 gates PC3 and PC4 (PLAN.md), on nec_portal's
`dipole_load_ld4.deck` in free space.

Records PyNEC's Z on the loaded deck, PyNEC's Z on the same deck with its LD
card removed, the NEC-2 tab's Z (`NEC2Engine` over `$NEC2_EXE`) on the loaded
deck, and the LD lines `export_nec` writes for it. Run once before the fix and
once after:

  PYTHONPATH=<worktree>/src NEC2_EXE=$(command -v nec2c) \\
      python scratch/1485-export-ld4/nec2tab_gate.py \\
      --out scratch/1485-export-ld4/nec2tab_before.json
"""

from __future__ import annotations

import argparse
import json
import os
import tempfile
from pathlib import Path

import momwire
import numpy as np

from antennaknobs.engines.nec2 import NEC2Engine
from antennaknobs.engines.pynec import PyNECEngine
from antennaknobs.file_designs import builder_from_file
from antennaknobs.nec_export import export_nec

DECK = (
    Path(momwire.__file__).resolve().parents[2]
    / "tests"
    / "fixtures"
    / "nec_portal"
    / "dipole_load_ld4.deck"
)
BAR_OHM = 0.1


def _z(eng):
    return complex(np.atleast_1d(eng.impedance())[0])


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", type=Path, required=True)
    args = ap.parse_args()
    exe = os.environ.get("NEC2_EXE")
    if not exe:
        raise SystemExit("set $NEC2_EXE to a NEC-2 binary")
    text = DECK.read_text()
    bare_text = "".join(
        ln + "\n" for ln in text.splitlines() if ln.split()[:1] != ["LD"]
    )
    with tempfile.TemporaryDirectory() as tmp:
        loaded_path = Path(tmp) / "loaded.nec"
        bare_path = Path(tmp) / "bare.nec"
        loaded_path.write_text(text)
        bare_path.write_text(bare_text)
        loaded = builder_from_file(str(loaded_path))
        bare = builder_from_file(str(bare_path))
        z_pynec_loaded = _z(PyNECEngine(loaded(), ground="free"))
        z_pynec_bare = _z(PyNECEngine(bare(), ground="free"))
        z_nec2_loaded = _z(NEC2Engine(loaded(), ground="free"))
        ld_lines = [
            ln
            for ln in export_nec(loaded(), ground="free", include_rp=False).splitlines()
            if ln.startswith("LD")
        ]
    rec = {
        "nec2_exe": exe,
        "z_pynec_loaded": repr(z_pynec_loaded),
        "z_pynec_bare": repr(z_pynec_bare),
        "z_nec2_loaded": repr(z_nec2_loaded),
        "nec2_minus_pynec_loaded_ohm": abs(z_nec2_loaded - z_pynec_loaded),
        "nec2_minus_pynec_bare_ohm": abs(z_nec2_loaded - z_pynec_bare),
        "export_ld_lines": ld_lines,
        "reads_load_free": abs(z_nec2_loaded - z_pynec_bare) < BAR_OHM
        and abs(z_nec2_loaded - z_pynec_loaded) > 1.0,
        "reads_pynec_loaded": abs(z_nec2_loaded - z_pynec_loaded) < BAR_OHM,
    }
    args.out.write_text(json.dumps(rec, indent=1))
    print(json.dumps(rec, indent=1))


if __name__ == "__main__":
    main()
