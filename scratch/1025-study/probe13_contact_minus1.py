"""AK#1025 follow-up: does the CONTACT class have a legal -1 spelling?

My earlier conclusion — "the contact class needs ground flag 1" — was measured
against ONE spelling: a wire ENDING at z = 0. Flag -1 gives no basis function
there, so that deck cannot be fed under -1 and the refusal was structural
rather than informative.

Untested: the deck RESPELLED so the conductor CROSSES the interface with a
segment boundary landing exactly on z = 0. Our wrapper refuses straddling
wires, so that spelling has never reached the binary. Hand decks only,
executable only, nothing read from the licensed source.

Geometry is held IDENTICAL across every arm: hub at -0.15, four radials, and a
vertical meshed at 0.15 m so a boundary lands exactly on the plane. The mast is
10.35 m (not the catalog's 10.5561) precisely so that boundary is exact; every
cell below shares it, so the comparison is spelling x flag x source, never
geometry.
"""

import os
import re
import subprocess
import tempfile
from pathlib import Path

EXE = os.environ["NEC5_EXE"]
DEPTH, MAST, RAD_LEN, A = 0.15, 10.35, 6.3336, 5.0e-4
SEG = 0.15
FREQ = 7.1
GN = "GN 0 0 0 0 1.300000E+01 5.000000E-03 1.000000E+00 0.000000E+00 NOFILE\n"
FR = f"FR 0 1 0 0 {FREQ:.6E} 0.000000E+00\n"


def run(deck):
    with tempfile.TemporaryDirectory(prefix="nec5_c1_") as td:
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
        if re.search(r"ERROR|ILLEGAL|CANNOT|NOT ALLOWED|STOP", line, re.I):
            return None, " ".join(line.split())[:72]
    return None, "no impedance row"


def radials(n, tag0):
    import math

    out, tags = "", []
    for i in range(n):
        th = 2 * math.pi * i / n
        x, y = RAD_LEN * math.cos(th), RAD_LEN * math.sin(th)
        tag = tag0 + i
        out += f"GW {tag} 54 0. 0. {-DEPTH:.6E} {x:.6E} {y:.6E} {-DEPTH:.6E} {A:.6E}\n"
        tags.append(tag)
    return out, tags


def deck_crossing(n_rad, ge, ex):
    """Vertical as ONE wire crossing the interface, boundary exactly at z=0."""
    nseg = int(round((DEPTH + MAST) / SEG))
    gw = f"GW 1 {nseg} 0. 0. {-DEPTH:.6E} 0. 0. {MAST:.6E} {A:.6E}\n"
    r, _ = radials(n_rad, 2)
    return "CM crossing\nCE\n" + gw + r + ge + "\n" + GN + ex + FR + "XQ 0\nEN\n"


def deck_two_wires(n_rad, ge, ex):
    """Vertical as TWO wires joined at z=0 — today's wrapper spelling."""
    n_below = int(round(DEPTH / SEG))
    n_above = int(round(MAST / SEG))
    gw = (
        f"GW 1 {n_below} 0. 0. {-DEPTH:.6E} 0. 0. 0. {A:.6E}\n"
        f"GW 2 {n_above} 0. 0. 0. 0. 0. {MAST:.6E} {A:.6E}\n"
    )
    r, _ = radials(n_rad, 3)
    return "CM two-wire\nCE\n" + gw + r + ge + "\n" + GN + ex + FR + "XQ 0\nEN\n"


N_BELOW = int(round(DEPTH / SEG))  # 1
NSEG_X = int(round((DEPTH + MAST) / SEG))  # 70

# (label, ex card for the crossing spelling, ex card for the two-wire spelling)
SOURCES = [
    (
        "first ABOVE-ground seg",
        f"EX 0 1 {N_BELOW + 1} 0 1.0 0.\n",
        "EX 0 2 1 0 1.0 0.\n",
    ),
    ("first BELOW-ground seg", "EX 0 1 1 0 1.0 0.\n", "EX 0 1 1 0 1.0 0.\n"),
    ("at the z=0 junction", f"EX 0 1 {N_BELOW} 2 1.0 0.\n", "EX 0 1 1 2 1.0 0.\n"),
]

for n_rad in (4, 12):
    print(f"\n########## {n_rad} radials ##########")
    print(f"{'source placement':24s} {'spelling':10s} {'GE -1 0':>24s} {'GE 1 0':>24s}")
    for label, ex_x, ex_2 in SOURCES:
        for sp, mk, ex in (
            ("crossing", deck_crossing, ex_x),
            ("two-wire", deck_two_wires, ex_2),
        ):
            cells = []
            for ge in ("GE -1 0", "GE 1 0"):
                z, err = run(mk(n_rad, ge, ex))
                cells.append(
                    f"{z.real:10.3f}{z.imag:+10.3f}j" if z else f"  {err[:22]}"
                )
            print(f"{label:24s} {sp:10s} {cells[0]:>24s} {cells[1]:>24s}")

print(
    "\n########## control: wholly-buried dipole must still read 146.39+44.38j ##########"
)
HALF, EPSG = 2.9557, 0.025
ctrl = (
    "CM control\nCE\n"
    f"GW 1 25 {-HALF:.6E} 0. -1.500000E-01 {-EPSG:.6E} 0. -1.500000E-01 {A:.6E}\n"
    f"GW 2 2 {-EPSG:.6E} 0. -1.500000E-01 {EPSG:.6E} 0. -1.500000E-01 {A:.6E}\n"
    f"GW 3 25 {EPSG:.6E} 0. -1.500000E-01 {HALF:.6E} 0. -1.500000E-01 {A:.6E}\n"
    "GE -1 0\n" + GN + "EX 0 2 1 2 1.000000E+00 0.000000E+00\n" + FR + "XQ 0\nEN\n"
)
print("   ", run(ctrl))
