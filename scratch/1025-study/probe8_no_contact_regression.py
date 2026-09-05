"""AK#1025 probe 8: the wrapper's OWN contact deck, old spelling vs new."""

import os
import re
import subprocess
import tempfile
from pathlib import Path

from antennaknobs import AntennaBuilder
from antennaknobs.engines.nec5 import NEC5Engine
from antennaknobs.wire_catalog import Wire

EXE = os.environ["NEC5_EXE"]


class Contact(AntennaBuilder):
    default_params = {"freq": 7.0}

    def build_wires(self):
        return [Wire((0, 0, 10.0), (0, 0, 0.0), n_seg=14, ex=1 + 0j)] + [
            Wire((0, 0, -0.15), (5 * dx, 5 * dy, -0.15), n_seg=10)
            for dx, dy in ((1, 0), (0, 1), (-1, 0), (0, -1))
        ]


def run(deck):
    with tempfile.TemporaryDirectory(prefix="nec5_reg_") as td:
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
    for line in m.group(1).splitlines() if m else []:
        t = line.split()
        if len(t) >= 12 and re.fullmatch(r"\d+", t[0]):
            return complex(float(t[7]), float(t[8]))
    return None


deck_new = NEC5Engine(Contact(), ground=("finite", 13.0, 0.005)).deck([7.0])
deck_old = deck_new.replace("GE 1 0", "GE 1 -1")
assert deck_old != deck_new
zn, zo = run(deck_new), run(deck_old)
print(f"wrapper contact deck, new 'GE 1 0'  : {zn}")
print(f"wrapper contact deck, old 'GE 1 -1' : {zo}")
print(f"identical: {zn == zo}")
