"""AK#1025 / momwire#838: the BLE 1937 Fig. 36/37 ladder under BOTH ground flags.

The 2026-09-02 ladder ran through NEC5Engine, i.e. ground flag 1 — the setting
documented as not usable when wires are buried, which every deck here has. The
public claims built on it ("NEC-5 flat 36 -> 28 over N = 2 -> 113 where BLE
measured >= 50 -> 24", "the radials do not matter to it") are therefore
flag-1 numbers.

The BLE deck's conductor CONTINUES through the interface (a 1-segment rise from
the hub up to z = 0, then the mast from z = 0 up), which is the shape flag -1
serves. So the deck needs no respelling: only the flag is substituted, and the
mesh is byte-identical between the two columns.

Generated from the banked scratch/ble-1937/ble_deck.py, unmodified except the
GE card.
"""

import os
import re
import subprocess
import sys
import tempfile
from pathlib import Path

EXE = os.environ["NEC5_EXE"]
GEN = Path("scratch/ble-1937/ble_deck.py")


def make(n, lft, eps=15.0):
    out = subprocess.run(
        [sys.executable, str(GEN), str(n), str(lft), str(eps)],
        capture_output=True,
        text=True,
        check=True,
    )
    return out.stdout


def run(deck, timeout=1800):
    with tempfile.TemporaryDirectory(prefix="nec5_ble_") as td:
        (Path(td) / "m.nec").write_text(deck)
        try:
            subprocess.run(
                [EXE],
                input="m.nec\nm.out\n\n",
                text=True,
                capture_output=True,
                cwd=td,
                timeout=timeout,
            )
        except subprocess.TimeoutExpired:
            return None, "timeout"
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


BLE_MEASURED = {2: ">=50", 15: "34", 30: "30", 60: "26", 113: "24.3"}
FLAG1_RECORDED = {2: 35.8, 15: 32.7, 30: 30.9, 60: 29.4, 113: 28.3}

for lft, label in (
    (135.0, "Fig. 36 — 135 ft radials"),
    (45.0, "Fig. 37 — 45 ft radials"),
):
    print(f"\n########## {label} (3 MHz, eps 15, sigma 2e-3) ##########", flush=True)
    print(
        f"{'N':>5s} {'GE 1 (as published)':>22s} {'GE -1 0':>22s} "
        f"{'recorded flag-1 R':>18s} {'BLE measured R':>15s}",
        flush=True,
    )
    for n in (2, 15, 30, 60, 113):
        deck = make(n, lft)
        ge = next(ln for ln in deck.splitlines() if ln.startswith("GE"))
        z1, e1 = run(deck)
        zm1, em1 = run(deck.replace(ge, "GE -1,0"))
        f1 = f"{z1.real:9.3f}{z1.imag:+9.3f}j" if z1 else f"  {e1[:20]}"
        fm = f"{zm1.real:9.3f}{zm1.imag:+9.3f}j" if zm1 else f"  {em1[:20]}"
        rec = f"{FLAG1_RECORDED.get(n, '')}" if lft == 135.0 else ""
        print(
            f"{n:5d} {f1:>22s} {fm:>22s} {rec:>18s} "
            f"{BLE_MEASURED.get(n, '') if lft == 135.0 else '':>15s}",
            flush=True,
        )
