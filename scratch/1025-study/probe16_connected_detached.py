"""AK#1025 follow-up: the connected-vs-detached argument, under BOTH flags.

The interface-node adjudication rests on NEC-5 reading nearly the SAME
impedance whether the radials are connected to the rise or detached from it —
49.78+20.95j against 50.11+21.46j. Those were taken under ground flag 1. If
flag -1 separates them, that argument needs re-examining; if it does not, the
argument survives the flag question intact.
"""

import os
import re
import subprocess
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, "tests")
from test_buried_catalog import SOIL_A, _detached  # noqa: E402

from antennaknobs.designs.verticals.buried_radial_vertical import Builder  # noqa: E402
from antennaknobs.engines.momwire import MomwireEngine  # noqa: E402
from antennaknobs.engines.nec5 import NEC5Engine  # noqa: E402

EXE = os.environ["NEC5_EXE"]


def run(deck):
    with tempfile.TemporaryDirectory(prefix="nec5_cd_") as td:
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


rows = {}
for name, b in (("connected (default)", Builder()), ("detached", _detached())):
    eng = NEC5Engine(b, ground=("finite",) + SOIL_A)
    deck = eng.deck([b.freq])
    ge = next(ln for ln in deck.splitlines() if ln.startswith("GE"))
    try:
        zm = complex(MomwireEngine(b, ground=("finite",) + SOIL_A).impedance()[0])
    except Exception:  # noqa: BLE001 - momwire refuses contact+buried; NEC-5 is the point here
        zm = None
    rows[name] = {
        "momwire": zm,
        "GE 1 0": run(deck.replace(ge, "GE 1 0")),
        "GE -1 0": run(deck.replace(ge, "GE -1 0")),
    }

print(f"{'':22s} {'momwire':>21s} {'NEC-5 GE 1 0':>21s} {'NEC-5 GE -1 0':>21s}")
for name, r in rows.items():

    def f(z):
        return f"{z.real:9.3f}{z.imag:+9.3f}j" if z else "        refused"

    print(
        f"{name:22s} {f(r['momwire']):>21s} {f(r['GE 1 0']):>21s} {f(r['GE -1 0']):>21s}"
    )

print("\nconnected MINUS detached — the quantity the adjudication rests on:")
for eng in ("momwire", "GE 1 0", "GE -1 0"):
    a, b_ = rows["connected (default)"][eng], rows["detached"][eng]
    if a and b_:
        print(
            f"   {eng:10s} dR {a.real - b_.real:+8.3f}   dX {a.imag - b_.imag:+8.3f}"
            f"   |d| {abs(a - b_):7.3f} ohm  ({100 * abs(a - b_) / abs(b_):5.2f} %)"
        )
