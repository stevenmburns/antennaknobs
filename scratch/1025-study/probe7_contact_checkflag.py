"""AK#1025 probe 7: does GE's SECOND field matter for the CONTACT deck?

On the wholly-buried dipole it was physics-irrelevant (-1 / 0 / 2 identical).
That must be re-measured on the contact class before the wrapper changes it
there, because a validated class must not move on an assumption.
"""

import os
import re
import subprocess
import tempfile
from pathlib import Path

EXE = os.environ["NEC5_EXE"]


def run(deck):
    with tempfile.TemporaryDirectory(prefix="nec5_cf_") as td:
        (Path(td) / "m.nec").write_text(deck)
        subprocess.run(
            [EXE],
            input="m.nec\nm.out\n\n",
            text=True,
            capture_output=True,
            cwd=td,
            timeout=300,
        )
        out = Path(td) / "m.out"
        if not out.is_file():
            return None
        text = out.read_text(errors="replace")
    m = re.search(
        r"- - - ANTENNA INPUT PARAMETERS - - -(.*?)(?:\n\s*\n\s*\n|$)", text, re.S
    )
    if not m:
        return None
    for line in m.group(1).splitlines():
        t = line.split()
        if len(t) >= 12 and re.fullmatch(r"\d+", t[0]):
            return complex(float(t[7]), float(t[8]))
    return None


# the wrapper's own contact deck, cards written out verbatim
GW = (
    "GW 1 14 0.000000E+00 0.000000E+00 1.000000E+01 "
    "0.000000E+00 0.000000E+00 0.000000E+00 1.000000E-03\n"
)
for i, (dx, dy) in enumerate(((1, 0), (0, 1), (-1, 0), (0, -1)), start=2):
    GW += (
        f"GW {i} 10 0.000000E+00 0.000000E+00 -1.500000E-01 "
        f"{5.0 * dx:.6E} {5.0 * dy:.6E} -1.500000E-01 1.000000E-03\n"
    )
GN = "GN 0 0 0 0 1.300000E+01 5.000000E-03 1.000000E+00 0.000000E+00 NOFILE\n"
EX = "EX 0 1 14 2 1.000000E+00 0.000000E+00\n"
FR = "FR 0 1 0 0 7.000000E+00 0.000000E+00\n"

print("AK contact deck (monopole bonded at z=0 + four detached buried radials)")
for ge in ("GE 1 -1", "GE 1 0", "GE 1 2", "GE -1 0"):
    z = run("CM contact\nCE\n" + GW + ge + "\n" + GN + EX + FR + "XQ 0\nEN\n")
    s = f"{z.real:10.4f}{z.imag:+10.4f}j" if z else "FAILED"
    print(f"   {ge:10s} {s}")
