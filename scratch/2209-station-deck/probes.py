"""Black-box probes of the licensed NEC-5 (and momwire's NEC-5 drop-in) that
the AK#2209 station writer's constants rest on. Small hand decks, a 7 MHz
dipole (20 segments, fed at its centre knot) or an inverted V (fed at its
vertex knot), and a 4-segment phantom wire (tag 9, knots at segments 1-3
end 2) 8.6 km away.

Run: PYTHONPATH=<worktree>/src python probes.py > probes.out
"""

import pathlib
import subprocess
import sys
import tempfile

from antennaknobs.engines.nec5 import NEC5Error, NEC5Engine

LICENSED = "/home/smburns/bin/nec5-licensed"
DROPIN = str(pathlib.Path(sys.executable).parent / "momwire-nec5-bspline")

DIP = "GW 1 20 0 -10.7 10 0 10.7 10 0.001\n"
VEE = "GW 1 10 0 -10 5 0 0 10 0.001\nGW 2 10 0 0 10 0 10 5 0.001\n"
PHANTOM = "GW 9 4 0 0 8600 0.214 0 8600 0.0000535\n"
PINS = "".join(f"LD 4 9 {k} 2 1e10 0 0\n" for k in (1, 2, 3))
GEN = "EX 0 9 1 2 1 0\n"


def deck(geom, loads="", net="", ex=GEN):
    return f"CM probe\nCE\n{geom}{PHANTOM}GE 0\n{loads}{net}{ex}FR 0 1 0 0 7.0 0\nXQ 0\nEN\n"


def run(text, exe=LICENSED):
    with tempfile.TemporaryDirectory() as td:
        p = pathlib.Path(td)
        (p / "m.nec").write_text(text)
        subprocess.run(
            [exe],
            input="m.nec\nm.out\n\n",
            cwd=td,
            capture_output=True,
            text=True,
            timeout=300,
        )
        out = (
            (p / "m.out").read_text(errors="replace") if (p / "m.out").exists() else ""
        )
    try:
        (row,) = NEC5Engine._parse_input_parameters(out)[0]
    except NEC5Error:
        return "REFUSED"
    z = row[2]
    return f"Z = {z.real:.5g} {z.imag:+.5g}j   Y = {1 / z:.5g}"


lam = 299.8 / 7.0
cases = [
    ("dipole, EX at the centre knot", deck(DIP, ex="EX 0 1 10 2 1 0\n")),
    (
        "dipole via NT series 10 ohm from an UNPINNED phantom knot",
        deck(DIP, net="NT 9 1 1 10 .1 0 -.1 0 .1 0\n"),
    ),
    (
        "dipole via NT series 10 ohm from a PINNED phantom knot",
        deck(DIP, PINS, "NT 9 1 1 10 .1 0 -.1 0 .1 0\n"),
    ),
    (
        "residual: pinned generator knot -1 ohm- pinned knot, nothing else",
        deck(DIP, PINS, "NT 9 1 9 2 1 0 -1 0 1 0\n"),
    ),
    ("residual: the same, UNPINNED", deck(DIP, net="NT 9 1 9 2 1 0 -1 0 1 0\n")),
    (
        "residual: pins of 1e12",
        deck(DIP, PINS.replace("1e10", "1e12"), "NT 9 1 9 2 1 0 -1 0 1 0\n"),
    ),
    (
        "lambda/4 pair 100 then 50 ohm, lambda = 299.792458/f (expect 4 x Z_dipole)",
        deck(
            DIP,
            PINS,
            f"TL 9 1 9 2 100 {299.792458 / 7 / 4!r} 0 0 0 0\n"
            f"TL 9 2 1 10 50 {299.792458 / 7 / 4!r} 0 0 0 0\n",
        ),
    ),
    (
        "lambda/4 pair, lambda = 299.8/f",
        deck(
            DIP,
            PINS,
            f"TL 9 1 9 2 100 {lam / 4!r} 0 0 0 0\nTL 9 2 1 10 50 {lam / 4!r} 0 0 0 0\n",
        ),
    ),
    (
        "lambda/4 pair, second card transposed (negative Z0)",
        deck(
            DIP,
            PINS,
            f"TL 9 1 9 2 100 {lam / 4!r} 0 0 0 0\nTL 9 2 1 10 -50 {lam / 4!r} 0 0 0 0\n",
        ),
    ),
    (
        "inverted V, EX at the vertex knot (1 10 end 2)",
        deck(VEE, ex="EX 0 1 10 2 1 0\n"),
    ),
    (
        "inverted V via NT series 10 ohm, vertex addressed 1 10",
        deck(VEE, PINS, "NT 9 1 1 10 .1 0 -.1 0 .1 0\n"),
    ),
    (
        "inverted V via NT series 10 ohm, vertex addressed 2 -1",
        deck(VEE, PINS, "NT 9 1 2 -1 .1 0 -.1 0 .1 0\n"),
    ),
    (
        "token -1.23456789012345e-1 (mantissa 17 characters with its sign)",
        deck(DIP, PINS, "NT 9 1 1 10 .1 0 -1.23456789012345e-1 0 .1 0\n"),
    ),
    (
        "token 1.234567890123456e-1 (mantissa 17 characters)",
        deck(DIP, PINS, "NT 9 1 1 10 .1 0 1.234567890123456e-1 0 .1 0\n"),
    ),
    (
        "token -1.234567890123456e-1 (mantissa 18 characters with its sign)",
        deck(DIP, PINS, "NT 9 1 1 10 .1 0 -1.234567890123456e-1 0 .1 0\n"),
    ),
    (
        "token -0.0000123456789012345678 (no exponent, 26 characters)",
        deck(DIP, PINS, "NT 9 1 1 10 .1 0 -0.0000123456789012345678 0 .1 0\n"),
    ),
    (
        "NT then TL in one deck",
        deck(DIP, PINS, "NT 9 1 9 2 .1 0 -.1 0 .1 0\nTL 9 2 1 10 50 5 0 0 0 0\n"),
    ),
]
for exe, label in ((LICENSED, "licensed NEC-5"), (DROPIN, "momwire-nec5-bspline")):
    print(f"=== {label}")
    for name, text in cases:
        print(f"  {name}\n      {run(text, exe)}")
