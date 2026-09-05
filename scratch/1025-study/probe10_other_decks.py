"""AK#1025 probe 10: the other buried catalog decks under the fix.

`elevated_buried_counterpoise` also has buried wires with no z=0 contact, so
the ground flag changes for it too — that must be MEASURED, not assumed.
`buried_radial_vertical` is the CONTACT class and should be untouched; it is
also the deck #1167 wants, and Skylake found PyNEC refuses it for a
GRADED-MESH reason unrelated to burial, so nec5 is checked for the same limit.
"""

import os
import re
import subprocess
import tempfile
from pathlib import Path

from antennaknobs.engines.momwire import MomwireEngine
from antennaknobs.engines.nec5 import NEC5Engine

EXE = os.environ["NEC5_EXE"]
SOIL = ("finite", 13.0, 0.005)


def raw(deck):
    with tempfile.TemporaryDirectory(prefix="nec5_o_") as td:
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


for modname, label in (
    ("verticals.elevated_buried_counterpoise", "elevated_buried_counterpoise"),
    ("verticals.buried_radial_vertical", "buried_radial_vertical (CONTACT)"),
):
    mod = __import__(f"antennaknobs.designs.{modname}", fromlist=["Builder"])
    b = mod.Builder()
    print(f"\n===== {label} =====")
    try:
        eng = NEC5Engine(b, ground=SOIL)
    except Exception as e:  # noqa: BLE001 - a refusal IS a result in a probe
        print(f"   NEC-5 REFUSES at construction: {type(e).__name__}: {e}")
        continue
    deck = eng.deck([float(b.default_params.get("freq", 7.0))])
    ge = [ln for ln in deck.splitlines() if ln.startswith("GE")][0]
    print(f"   GE card now: {ge!r}")
    z_new = raw(deck)
    z_old = raw(deck.replace(ge, "GE 1 -1"))
    print(f"   NEC-5 new spelling : {z_new}")
    print(f"   NEC-5 old spelling : {z_old}")
    try:
        zm = complex(MomwireEngine(b, ground=SOIL).impedance()[0])
        print(f"   momwire            : {zm:.4f}")
        if z_new is not None:
            print(
                f"   dR new {100 * abs(z_new.real - zm.real) / abs(zm.real):6.2f}%   "
                f"dR old {100 * abs(z_old.real - zm.real) / abs(zm.real):6.2f}%"
                if z_old
                else ""
            )
    except Exception as e:  # noqa: BLE001 - a refusal IS a result in a probe
        print(f"   momwire failed: {type(e).__name__}: {e}")
