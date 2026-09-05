"""AK#1025 probe 3: hand-written decks, run straight through the binary.

Black-box only: the executable is invoked, nothing from the licensed source
tree is read. Each variant changes ONE thing against the wrapper's own buried
deck, so a variant that recovers a sane impedance names the cause.
"""

import os
import re
import subprocess
import tempfile
from pathlib import Path

EXE = os.environ["NEC5_EXE"]
HALF, EPSG, RAD, FREQ = 2.9557, 0.025, 5.0e-4, 7.1


def run(deck):
    with tempfile.TemporaryDirectory(prefix="nec5_hand_") as td:
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
            return None, "no printout"
        text = out.read_text(errors="replace")
    m = re.search(
        r"- - - ANTENNA INPUT PARAMETERS - - -(.*?)(?:\n\s*\n\s*\n|$)", text, re.S
    )
    if not m:
        return None, "no ANTENNA INPUT PARAMETERS section"
    for line in m.group(1).splitlines():
        t = line.split()
        if len(t) >= 12 and re.fullmatch(r"\d+", t[0]):
            return complex(float(t[7]), float(t[8])), None
        if len(t) == 11 and re.fullmatch(r"\d+", t[0]):
            return complex(float(t[6]), float(t[7])), None
    return None, "no numeric row"


def three_wire(z, ge, ex, order="gn_first"):
    gw = (
        f"GW 1 25 {-HALF:.6E} 0. {z:.6E} {-EPSG:.6E} 0. {z:.6E} {RAD:.6E}\n"
        f"GW 2 2 {-EPSG:.6E} 0. {z:.6E} {EPSG:.6E} 0. {z:.6E} {RAD:.6E}\n"
        f"GW 3 25 {EPSG:.6E} 0. {z:.6E} {HALF:.6E} 0. {z:.6E} {RAD:.6E}\n"
    )
    gn = "GN 0 0 0 0 1.300000E+01 5.000000E-03 1.000000E+00 0.000000E+00 NOFILE\n"
    fr = f"FR 0 1 0 0 {FREQ:.6E} 0.000000E+00\n"
    body = (gn + ex + fr) if order == "gn_first" else (fr + gn + ex)
    return "CM hand\nCE\n" + gw + ge + body + "XQ 0\nEN\n"


def one_wire(z, nseg, ex, ge):
    gw = f"GW 1 {nseg} {-HALF:.6E} 0. {z:.6E} {HALF:.6E} 0. {z:.6E} {RAD:.6E}\n"
    gn = "GN 0 0 0 0 1.300000E+01 5.000000E-03 1.000000E+00 0.000000E+00 NOFILE\n"
    fr = f"FR 0 1 0 0 {FREQ:.6E} 0.000000E+00\n"
    return "CM hand\nCE\n" + gw + ge + gn + ex + fr + "XQ 0\nEN\n"


Z = -0.15
CASES = [
    (
        "V0 wrapper's own deck, buried",
        three_wire(Z, "GE 1 -1\n", "EX 0 2 1 2 1.000000E+00 0.000000E+00\n"),
    ),
    (
        "V1 same, EX I4=0",
        three_wire(Z, "GE 1 -1\n", "EX 0 2 1 0 1.000000E+00 0.000000E+00\n"),
    ),
    (
        "V2 same, EX I4=1",
        three_wire(Z, "GE 1 -1\n", "EX 0 2 1 1 1.000000E+00 0.000000E+00\n"),
    ),
    (
        "V3 same, current source EX 4",
        three_wire(Z, "GE 1 -1\n", "EX 4 2 1 0 1.000000E+00 0.000000E+00\n"),
    ),
    (
        "V4 same, anchor card order (FR,GN,EX)",
        three_wire(
            Z, "GE 1 -1\n", "EX 0 2 1 2 1.000000E+00 0.000000E+00\n", "fr_first"
        ),
    ),
    (
        "V5 same, GE 1 0 (diagnostic, wrong for buried)",
        three_wire(Z, "GE 1 0\n", "EX 0 2 1 2 1.000000E+00 0.000000E+00\n"),
    ),
    (
        "V6 ONE wire 51 seg, EX at centre seg 26, buried",
        one_wire(Z, 51, "EX 0 1 26 2 1.000000E+00 0.000000E+00\n", "GE 1 -1\n"),
    ),
    (
        "V7 ONE wire 51 seg, EX I4=0, buried",
        one_wire(Z, 51, "EX 0 1 26 0 1.000000E+00 0.000000E+00\n", "GE 1 -1\n"),
    ),
    (
        "V8 ONE wire 51 seg, EX 4 current, buried",
        one_wire(Z, 51, "EX 4 1 26 0 1.000000E+00 0.000000E+00\n", "GE 1 -1\n"),
    ),
    (
        "C1 CONTROL one wire 51 seg ABOVE +0.15, EX I4=2",
        one_wire(+0.15, 51, "EX 0 1 26 2 1.000000E+00 0.000000E+00\n", "GE 1 0\n"),
    ),
    (
        "C2 CONTROL three-wire ABOVE +0.15, wrapper spelling",
        three_wire(+0.15, "GE 1 0\n", "EX 0 2 1 2 1.000000E+00 0.000000E+00\n"),
    ),
]

for name, deck in CASES:
    z, err = run(deck)
    s = f"{z.real:12.4f}{z.imag:+12.4f}j" if z is not None else f"  {err}"
    print(f"{name:48s} {s}")
