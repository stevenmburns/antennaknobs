"""BLE 1937 Fig. 36/37 geometry in NEC-5, hub spelling: 3 MHz, mast 77 deg (2.5 in dia), radials No. 8 wire buried 6 in."""

import sys

N = int(sys.argv[1])
Lft = float(sys.argv[2])
eps = float(sys.argv[3]) if len(sys.argv) > 3 else 15.0
wl = 299.792458 / 3.0
H = 77.0 / 360.0 * wl
R = Lft * 0.3048
d = 6 * 0.0254
a_mast = 2.5 * 0.0254 / 2
a_wire = 0.001628  # No. 8 AWG radius
sigma = 2e-3
nseg = 23
mseg = 23
L = [f"CM BLE Fig36/37 N={N} L={Lft}ft eps={eps}", "CE"]
L.append(f"GW 2,{nseg},0.,0.,{-d:.4f},{R:.4f},0.,{-d:.4f},{a_wire}")
L.append(f"GR 0,{N}")
L.append(f"GW 1,1,0.,0.,{-d:.4f},0.,0.,0.,{a_wire}")
L.append(f"GW 3,{mseg},0.,0.,0.,0.,0.,{H:.4f},{a_mast}")
L += [
    "GE 1,-1",
    "FR 0,1,0,0,3.0",
    f"GN 0,0,0,0,{eps},{sigma}",
    "EX 0,3,1,0,1.,0.",
    "PQ 0",
    "XQ 0",
    "EN",
]
print("\n".join(L))
