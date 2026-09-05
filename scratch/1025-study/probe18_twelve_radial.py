"""AK#1025 item 1: the 12-radial buried screen under both ground flags.

The recorded pair for this deck is momwire 45.38+31.27j against flag-1 NEC-5
45.47+18.47j. Only the GE card is substituted in the wrapper's own deck text,
so mesh, grading and geometry are exactly what ships.
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
    with tempfile.TemporaryDirectory(prefix="nec5_12_") as td:
        (Path(td) / "m.nec").write_text(deck)
        subprocess.run(
            [EXE],
            input="m.nec\nm.out\n\n",
            text=True,
            capture_output=True,
            cwd=td,
            timeout=1800,
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
            return None, " ".join(line.split())[:60]
    return None, "no impedance row"


for n_rad in (12, 4):
    b = Builder()
    b.n_radials = n_rad
    eng = NEC5Engine(b, ground=SOIL)
    deck = eng.deck([b.freq])
    ge = next(ln for ln in deck.splitlines() if ln.startswith("GE"))
    zm = complex(MomwireEngine(b, ground=SOIL).impedance()[0])
    print(
        f"\n=== buried_radial_vertical, n_radials = {n_rad} (wrapper writes {ge!r}) ==="
    )
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
