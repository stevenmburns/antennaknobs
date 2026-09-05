"""AK#1025 follow-up: the SHIPPED contact decks under both ground flags.

Probe 13 showed the contact class has a working -1 spelling whenever the
conductor CONTINUES through the interface, and that "one crossing wire" and
"two wires meeting at z = 0" are identical to the binary. The catalog's
buried_radial_vertical is the second shape: a rise from the hub UP TO z = 0 and
a mast starting AT z = 0. So the shipped deck may already be eligible for -1 —
which #1025 did not test, having only tried -1 on a deck that TERMINATES at the
plane with nothing below it.

Takes the wrapper's own deck text and substitutes the flag, so geometry, mesh
and grading are exactly what ships.
"""

import os
import re
import subprocess
import tempfile
from pathlib import Path

from antennaknobs.designs.verticals.buried_radial_vertical import Builder
from antennaknobs.engines.momwire import MomwireEngine
from antennaknobs.engines.nec5 import NEC5Engine

EXE = os.environ["NEC5_EXE"]
SOIL = ("finite", 13.0, 0.005)


def run(deck):
    with tempfile.TemporaryDirectory(prefix="nec5_cf_") as td:
        (Path(td) / "m.nec").write_text(deck)
        subprocess.run(
            [EXE],
            input="m.nec\nm.out\n\n",
            text=True,
            capture_output=True,
            cwd=td,
            timeout=900,
        )
        out = Path(td) / "m.out"
        if not out.is_file():
            return None, "no printout"
        text = out.read_text(errors="replace")
    m = re.search(
        r"- - - ANTENNA INPUT PARAMETERS - - -(.*?)(?:\n\s*\n\s*\n|$)", text, re.S
    )
    for line in m.group(1).splitlines() if m else []:
        t = line.split()
        if len(t) >= 12 and re.fullmatch(r"\d+", t[0]):
            return complex(float(t[7]), float(t[8])), None
    for line in text.splitlines():
        if re.search(r"ERROR|ILLEGAL|CANNOT|STOP", line, re.I):
            return None, " ".join(line.split())[:66]
    return None, "no impedance row"


b = Builder()
eng = NEC5Engine(b, ground=SOIL)
deck = eng.deck([b.freq])
ge = next(ln for ln in deck.splitlines() if ln.startswith("GE"))
print(f"shipped buried_radial_vertical, wrapper writes {ge!r}\n")

zm = complex(MomwireEngine(b, ground=SOIL).impedance()[0])
print(f"   momwire            {zm.real:9.3f}{zm.imag:+9.3f}j")
for flag in ("GE 1 0", "GE -1 0"):
    z, err = run(deck.replace(ge, flag))
    if z:
        print(
            f"   NEC-5 {flag:8s}     {z.real:9.3f}{z.imag:+9.3f}j"
            f"   dR {100 * abs(z.real - zm.real) / abs(zm.real):6.2f} %"
            f"   dX {100 * abs(z.imag - zm.imag) / abs(zm.imag):6.2f} %"
        )
    else:
        print(f"   NEC-5 {flag:8s}     {err}")
