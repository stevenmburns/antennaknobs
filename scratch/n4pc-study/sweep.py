"""N4PC Loop: frequency sweep + mesh ladder, seam vs licensed nec5cl.

GD variant (capture 0083) — the deviation is ground-independent, and GD's
currents solve over a perfect image, so this isolates the loop solve.
EX 4,w,-1 node addressing survives refinement (the favored end is a node at
every mesh), so the mesh ladder needs no feed bookkeeping.
Writes sweep.json: {"freq": {engine: [[MHz, R1, X1], ...]},
                    "mesh": {engine: [[k, R1, X1], ...]}}
"""

import json
import subprocess
import sys
from pathlib import Path

HERE = Path(__file__).parent
PY = sys.executable
NEC5CL = Path.home() / "antennas/NEC5-downloads/nec5-linux/nec5cl"

BASE = """CM N4PC GD study
CE
GW 1,{n},0.,0.,15.24,0.,15.5448,15.24,.0010262
GW 2,{n},0.,15.5448,15.24,15.5448,15.5448,15.24,.0010262
GW 3,{n},15.5448,15.5448,15.24,15.5448,0.,15.24,.0010262
GW 4,{n},15.5448,0.,15.24,0.,0.,15.24,.0010262
GE 1,-1
FR 0,1,0,0,{mhz}
GD 0,0,0,0,13.,.005,1.,0.
EX 4,1,-1,0,1.414214,0.
EX 4,3,-1,0,1.414214,0.
PQ 0
XQ 0
EN
"""


def run_engine(engine, deck_text, room):
    room.mkdir(parents=True, exist_ok=True)
    deck = room / "EZN5.NEC"
    deck.write_text(deck_text)
    if engine == "seam":
        cmd = [PY, "-m", "momwire.eznec", "EZN5.NEC", "OUT.txt"]
    else:
        cmd = [str(NEC5CL), "EZN5.NEC", "OUT.txt"]
    subprocess.run(cmd, cwd=room, capture_output=True, timeout=600)
    rows, take = [], 0
    for line in (room / "OUT.txt").read_text(encoding="latin-1").splitlines():
        if "ANTENNA INPUT PARAMETERS" in line:
            take = 1
            continue
        if take:
            p = line.split()
            if p and p[0].isdigit():
                rows.append((float(p[7]), float(p[8])))  # R, X after tag,seg,node
            elif rows:
                break
    return rows  # [(R1, X1), (R2, X2)]


def main():
    out = {"freq": {}, "mesh": {}}
    freqs = [13.5 + 0.05 * i for i in range(29)]  # 13.5 .. 14.9 MHz
    for engine in ("seam", "nec5cl"):
        out["freq"][engine] = []
        for mhz in freqs:
            rows = run_engine(
                engine, BASE.format(n=16, mhz=round(mhz, 3)), HERE / f"room-{engine}"
            )
            if rows:
                out["freq"][engine].append([round(mhz, 3), rows[0][0], rows[0][1]])
                print(
                    f"{engine} {mhz:.2f} MHz: Z1 = {rows[0][0]:9.1f} + "
                    f"j{rows[0][1]:9.1f}",
                    flush=True,
                )
    for engine in ("seam", "nec5cl"):
        out["mesh"][engine] = []
        for k in (1, 2, 4, 8):
            rows = run_engine(
                engine, BASE.format(n=16 * k, mhz=14.1), HERE / f"room-{engine}"
            )
            if rows:
                out["mesh"][engine].append([k, rows[0][0], rows[0][1]])
                print(
                    f"{engine} mesh x{k} (n={16 * k}/side): Z1 = "
                    f"{rows[0][0]:9.1f} + j{rows[0][1]:9.1f}",
                    flush=True,
                )
    (HERE / "sweep.json").write_text(json.dumps(out, indent=1))
    print("written", HERE / "sweep.json")


if __name__ == "__main__":
    main()
