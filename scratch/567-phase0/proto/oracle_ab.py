"""§4b step 0, done late but before the verdict: the oracle's own uncertainty.

Runs the two anchor decks through the licensed binary twice each — as
shipped, and with the buried-pair asymptotic workaround disabled via
`EZParam.txt` (`EZ5 0,0,0,-1.,-1.`, per the x13 note) — and records the
spread. The card file is placed BOTH next to the executable copy and in the
run CWD, covering either reading of "next to the executable". The binary is
COPIED to scratch; the install dir is never touched.

Baseline runs must reproduce the banked anchors exactly, which also
validates the deck reconstruction (cards from test_eznec_buried_refusal).
"""

from __future__ import annotations

import os
import shutil
import subprocess
import tempfile
from pathlib import Path

from antennaknobs.engines.nec5 import NEC5Engine, find_nec5

ANCHOR = {"lone": 92.130 - 70.141j, "fan": 89.985 - 71.401j}

LONE = (
    "CM 567p0 anchor lone-radial\nCE\n"
    "GW 1,15,0.,0.,10.,0.,0.,0.,.001\n"
    "GW 2,10,0.,0.,-0.15,5.,0.,-0.15,.001\n"
    "GE 1,-1\nFR 0,1,0,0,7.\nGN 0,0,0,0,13.,.005\n"
    "EX 4,1,7,0,1.,0.\nPQ 0\nXQ 0\nEN\n"
)
FAN = (
    "CM 567p0 anchor four-radial\nCE\n"
    "GW 1,15,0.,0.,10.,0.,0.,0.,.001\n"
    "GW 2,10,0.,0.,-0.15,5.,0.,-0.15,.001\n"
    "GW 3,10,0.,0.,-0.15,0.,5.,-0.15,.001\n"
    "GW 4,10,0.,0.,-0.15,-5.,0.,-0.15,.001\n"
    "GW 5,10,0.,0.,-0.15,0.,-5.,-0.15,.001\n"
    "GE 1,-1\nFR 0,1,0,0,7.\nGN 0,0,0,0,13.,.005\n"
    "EX 4,1,7,0,1.,0.\nPQ 0\nXQ 0\nEN\n"
)
EZ_DISABLE = "EZ5 0,0,0,-1.,-1.\n"


def run(exe_dir: Path, deck: str, ez: bool) -> complex:
    with tempfile.TemporaryDirectory(prefix="nec5ab_") as td:
        tdp = Path(td)
        (tdp / "model.nec").write_text(deck)
        ezf_exe = exe_dir / "EZParam.txt"
        ezf_cwd = tdp / "EZParam.txt"
        if ez:
            ezf_exe.write_text(EZ_DISABLE)
            ezf_cwd.write_text(EZ_DISABLE)
        else:
            ezf_exe.unlink(missing_ok=True)
        try:
            subprocess.run(
                [str(exe_dir / "nec5cl")],
                input="model.nec\nmodel.out\n\n",
                text=True,
                capture_output=True,
                cwd=td,
                timeout=300,
            )
            text = (tdp / "model.out").read_text(errors="replace")
        finally:
            ezf_exe.unlink(missing_ok=True)
        rows = NEC5Engine._parse_input_parameters(text)
        if not rows or not rows[0]:
            raise RuntimeError("no input-parameters block parsed:\n" + text[-800:])
        return rows[0][0][2]


def main():
    src = find_nec5(os.environ.get("NEC5_EXE"))
    assert src, "set NEC5_EXE"
    work = Path(__file__).resolve().parents[1] / "results" / "nec5-ab"
    work.mkdir(parents=True, exist_ok=True)
    shutil.copy2(src, work / "nec5cl")
    for name, deck in (("lone", LONE), ("fan", FAN)):
        z0 = run(work, deck, ez=False)
        z1 = run(work, deck, ez=True)
        a = ANCHOR[name]
        print(
            f"{name:>5}: shipped {z0:.4f} (vs anchor {a}: {abs(z0 - a):.4f})   "
            f"workaround-off {z1:.4f}   spread {abs(z1 - z0):.4f} ohm"
        )


if __name__ == "__main__":
    main()
