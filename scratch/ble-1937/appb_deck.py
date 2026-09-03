"""NEC-5 Validation Manual App. B screen: N radials, sloping-first-segment (manual) or hub (vertical rise) spelling."""

import math
import os
import sys

N = int(sys.argv[1])
spell = sys.argv[2]
ex = sys.argv[3] if len(sys.argv) > 3 else "ex0"
mseg = int(sys.argv[4]) if len(sys.argv) > 4 else 23
f = 1.0
wl = 299.792458 / f

H = 0.25 * wl
R = float(os.environ.get("RFAC", "1.0")) * H
d = float(os.environ.get("DEPTH", 1e-4 * wl))
a = float(os.environ.get("RAD", 1e-5 * wl))
eps = 15.0
sigma = 15.0 * 2 * math.pi * f * 1e6 * 8.8541878128e-12
nseg = 23
dl = R / nseg
L = [f"CM App B screen N={N} {spell} {ex}", "CE"]
if spell == "slope":
    L.append(f"GW 1,1,0.,0.,0.,{dl:.6f},0.,{-d:.6f},{a:.6f}")
    L.append(f"GW 2,{nseg - 1},{dl:.6f},0.,{-d:.6f},{R:.6f},0.,{-d:.6f},{a:.6f}")
    L.append(f"GR 0,{N}")
    mono = 3
elif spell == "hub":
    L.append(f"GW 2,{nseg},0.,0.,{-d:.6f},{R:.6f},0.,{-d:.6f},{a:.6f}")
    L.append(f"GR 0,{N}")
    L.append(f"GW 1,1,0.,0.,{-d:.6f},0.,0.,0.,{a:.6f}")
    mono = 3
L.append(f"GW {mono},{mseg},0.,0.,0.,0.,0.,{H:.6f},{a:.6f}")
L.append("GE 1,-1")
L.append(f"FR 0,1,0,0,{f}")
L.append(f"GN 0,0,0,0,{eps},{sigma:.6e}")
if ex == "ex0":
    L.append(f"EX 0,{mono},1,0,1.,0.")
else:
    L.append(f"EX 4,{mono},1,0,1.,0.")
L += ["PQ 0", "RP 0,19,1,1001,0.,0.,5.,0.", "XQ 0", "EN"]
print("\n".join(L))
