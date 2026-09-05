"""AK#1025 probe 11: does the DETACHED buried_radial_vertical variant change
class under the corrected ground flag, and does its impedance move?"""

import os
import re
import subprocess
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, "tests")
from test_buried_catalog import SOIL_A, _detached  # noqa: E402

from antennaknobs.engines.nec5 import NEC5Engine  # noqa: E402

EXE = os.environ["NEC5_EXE"]


def run(deck):
    with tempfile.TemporaryDirectory(prefix="nec5_d_") as td:
        (Path(td) / "m.nec").write_text(deck)
        subprocess.run(
            [EXE],
            input="m.nec\nm.out\n\n",
            text=True,
            capture_output=True,
            cwd=td,
            timeout=600,
        )
        out = Path(td) / "m.out"
        if not out.is_file():
            return None
        text = out.read_text(errors="replace")
    m = re.search(
        r"- - - ANTENNA INPUT PARAMETERS - - -(.*?)(?:\n\s*\n\s*\n|$)", text, re.S
    )
    for line in m.group(1).splitlines() if m else []:
        t = line.split()
        if len(t) >= 12 and re.fullmatch(r"\d+", t[0]):
            return complex(float(t[7]), float(t[8]))
    return None


d = _detached()
eng = NEC5Engine(d, ground=("finite",) + SOIL_A)
zs = [float(w.p0[2]) for w in d.build_wires()] + [
    float(w.p1[2]) for w in d.build_wires()
]
print(
    f"detached variant: zmin={min(zs):.3f} zmax={max(zs):.3f} "
    f"any end at z=0: {any(z == 0.0 for z in zs)}"
)
print(f"   has_buried={eng._has_buried_wires} has_contact={eng._has_ground_contact}")
deck = eng.deck([d.freq])
ge = next(ln for ln in deck.splitlines() if ln.startswith("GE"))
print(f"   GE now: {ge!r}")
print(f"   Z with {ge!r:10s}: {run(deck)}")
print(f"   Z with 'GE 1 -1' : {run(deck.replace(ge, 'GE 1 -1'))}")
print(f"   Z with 'GE 1 0'  : {run(deck.replace(ge, 'GE 1 0'))}")
