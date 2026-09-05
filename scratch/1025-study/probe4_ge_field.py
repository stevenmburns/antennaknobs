"""AK#1025 probe 4: the GE card's two fields.

Verified against our licensed materials: GE's FIRST field is the ground flag
and its SECOND is the segment-check flag. The wrapper writes `GE 1 -1`, i.e.
ground-flag 1 with checking disabled -- and ground-flag 1 is the setting that
is not usable when wires go below the surface. This runs the same buried deck
across both fields to see which spelling recovers a physical impedance.
"""

import os
import re
import subprocess
import tempfile
from pathlib import Path

EXE = os.environ["NEC5_EXE"]
HALF, EPSG, RAD, FREQ = 2.9557, 0.025, 5.0e-4, 7.1


def run(deck):
    with tempfile.TemporaryDirectory(prefix="nec5_ge_") as td:
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
            return None, None, "no printout"
        text = out.read_text(errors="replace")
    m = re.search(
        r"- - - ANTENNA INPUT PARAMETERS - - -(.*?)(?:\n\s*\n\s*\n|$)", text, re.S
    )
    z = None
    if m:
        for line in m.group(1).splitlines():
            t = line.split()
            if len(t) >= 12 and re.fullmatch(r"\d+", t[0]):
                z = complex(float(t[7]), float(t[8]))
                break
    # peak |I| anywhere on the wire, to see the source-segment spike
    spike = None
    cur = re.search(r"- - - Wire Currents - - -(.*?)- - -", text, re.S)
    if cur:
        mags = [
            float(t[8])
            for t in (ln.split() for ln in cur.group(1).splitlines())
            if len(t) >= 10 and re.fullmatch(r"\d+", t[0])
        ]
        if mags:
            srt = sorted(mags)
            spike = srt[-1] / srt[-2] if len(srt) > 1 and srt[-2] else float("nan")
    return z, spike, None


def deck(z, ge):
    gw = (
        f"GW 1 25 {-HALF:.6E} 0. {z:.6E} {-EPSG:.6E} 0. {z:.6E} {RAD:.6E}\n"
        f"GW 2 2 {-EPSG:.6E} 0. {z:.6E} {EPSG:.6E} 0. {z:.6E} {RAD:.6E}\n"
        f"GW 3 25 {EPSG:.6E} 0. {z:.6E} {HALF:.6E} 0. {z:.6E} {RAD:.6E}\n"
    )
    return (
        "CM ge probe\nCE\n"
        + gw
        + ge
        + "GN 0 0 0 0 1.300000E+01 5.000000E-03 1.000000E+00 0.000000E+00 NOFILE\n"
        + "EX 0 2 1 2 1.000000E+00 0.000000E+00\n"
        + f"FR 0 1 0 0 {FREQ:.6E} 0.000000E+00\nXQ 0\nEN\n"
    )


print(f"{'GE card':22s} {'depth':>8s} {'Z printed':>26s}   I-spike ratio")
for ge in ("GE 1 -1", "GE 1 0", "GE -1 -1", "GE -1 0", "GE -1 2"):
    for zd in (-0.15, -1.0, -2.0):
        z, spike, err = run(deck(zd, ge + "\n"))
        s = f"{z.real:12.4f}{z.imag:+12.4f}j" if z else f"  {err}"
        sp = f"{spike:8.1f}x" if spike == spike and spike else "     -"
        print(f"{ge:22s} {zd:8.2f} {s:>26s}   {sp}")
