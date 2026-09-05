"""AK#1025 probe 5 (READ-ONLY, momwire-side finding): do the momwire#567
banked anchor numbers depend on the GE spelling?

The anchor decks in momwire/tests/golden_buried_anchor_nec5.py carry the same
`GE 1,-1` the AK wrapper wrote. Their source sits ABOVE the interface (contact
class), so they may be unaffected -- but the decks do contain buried radials,
and the first GE field governs whether that is legal. Nothing is modified here.
"""

import os
import re
import subprocess
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, "momwire/tests")
from golden_buried_anchor_nec5 import (  # noqa: E402
    ANCHOR_DECKS,
    ANCHOR_FOUR_RADIAL,
    ANCHOR_LONE_RADIAL,
)

EXE = os.environ["NEC5_EXE"]
PINNED = {"lone-radial": ANCHOR_LONE_RADIAL, "four-radial": ANCHOR_FOUR_RADIAL}


def run(deck):
    with tempfile.TemporaryDirectory(prefix="nec5_anchor_") as td:
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


for name, deck in ANCHOR_DECKS.items():
    pin = PINNED[name]
    as_is = run(deck)
    fixed = run(deck.replace("GE 1,-1", "GE -1,0"))
    print(f"\n{name}")
    print(f"   pinned in momwire   {pin.real:10.4f}{pin.imag:+10.4f}j")
    print(
        f"   re-run as-is        {as_is.real:10.4f}{as_is.imag:+10.4f}j"
        if as_is
        else "   re-run as-is        FAILED"
    )
    print(
        f"   with GE -1,0        {fixed.real:10.4f}{fixed.imag:+10.4f}j"
        if fixed
        else "   with GE -1,0        FAILED"
    )
    if as_is and fixed:
        print(
            f"   |as-is - fixed|     {abs(as_is - fixed):.4f} ohm "
            f"({100 * abs(as_is - fixed) / abs(fixed):.2f}% of |Z|)"
        )
