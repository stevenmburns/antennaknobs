"""AK buried_radial_vertical DEFAULT geometry (7.1 MHz, soil A) in NEC-5: hub-connected vs detached."""

import sys

sp = sys.argv[1]
N = 4
wl = 299.792458 / 7.1
H = 0.25 * wl
R = 0.6 * H
d = 0.15
a = 0.0005
L = [f"CM AK brv default geometry, {sp}", "CE"]
L.append(f"GW 2,10,0.,0.,{-d},{R:.6f},0.,{-d},{a}")
L.append(f"GR 0,{N}")
if sp == "hub":
    L.append(f"GW 1,1,0.,0.,{-d},0.,0.,0.,{a}")
L.append(f"GW 3,15,0.,0.,0.,0.,0.,{H:.6f},{a}")
L += [
    "GE 1,-1",
    "FR 0,1,0,0,7.1",
    "GN 0,0,0,0,13.,.005",
    "EX 0,3,1,0,1.,0.",
    "PQ 0",
    "XQ 0",
    "EN",
]
print("\n".join(L))
