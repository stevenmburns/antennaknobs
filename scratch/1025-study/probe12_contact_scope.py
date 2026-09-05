"""AK#1025 / #1167: is there a buried sub-class nec5 cannot take?

The contact class asks for two things at once — a wire END bonded at z=0 AND
wires below the surface. Ground flag 1 gives the bond; flag -1 is the one
compatible with burial. This records exactly what the binary does with each,
so the #1167 boolean is not over-promised.
"""

import os
import re
import subprocess
import tempfile
from pathlib import Path

EXE = os.environ["NEC5_EXE"]

GW = ("GW 1 14 0.000000E+00 0.000000E+00 1.000000E+01 "
      "0.000000E+00 0.000000E+00 0.000000E+00 1.000000E-03\n")
for i, (dx, dy) in enumerate(((1, 0), (0, 1), (-1, 0), (0, -1)), start=2):
    GW += (f"GW {i} 10 0.000000E+00 0.000000E+00 -1.500000E-01 "
           f"{5.0 * dx:.6E} {5.0 * dy:.6E} -1.500000E-01 1.000000E-03\n")
GN = "GN 0 0 0 0 1.300000E+01 5.000000E-03 1.000000E+00 0.000000E+00 NOFILE\n"
EX = "EX 0 1 14 2 1.000000E+00 0.000000E+00\n"
FR = "FR 0 1 0 0 7.000000E+00 0.000000E+00\n"


def run(ge):
    deck = "CM contact scope\nCE\n" + GW + ge + "\n" + GN + EX + FR + "XQ 0\nEN\n"
    with tempfile.TemporaryDirectory(prefix="nec5_sc_") as td:
        (Path(td) / "m.nec").write_text(deck)
        p = subprocess.run([EXE], input="m.nec\nm.out\n\n", text=True,
                           capture_output=True, cwd=td, timeout=300)
        out = Path(td) / "m.out"
        text = out.read_text(errors="replace") if out.is_file() else ""
        stdout = (p.stdout or "") + (p.stderr or "")
    z = None
    m = re.search(r"- - - ANTENNA INPUT PARAMETERS - - -(.*?)(?:\n\s*\n\s*\n|$)", text, re.S)
    for line in (m.group(1).splitlines() if m else []):
        t = line.split()
        if len(t) >= 12 and re.fullmatch(r"\d+", t[0]):
            z = complex(float(t[7]), float(t[8]))
            break
    return z, text, stdout


for ge in ("GE 1 0", "GE -1 0"):
    z, text, stdout = run(ge)
    print(f"\n===== {ge} =====")
    print(f"   Z: {z}")
    print(f"   printout produced: {bool(text)}  ({len(text)} chars)")
    tail = [ln for ln in stdout.splitlines() if ln.strip()][-3:]
    print(f"   runner said: {tail}")
    for ln in text.splitlines():
        if re.search(r"ERROR|STOP|ILLEGAL|FATAL|CANNOT|NOT ALLOWED", ln, re.I):
            print(f"   >> {ln.strip()[:110]}")
