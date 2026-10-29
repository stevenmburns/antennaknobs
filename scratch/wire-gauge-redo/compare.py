"""Wire-gauge redo: 12-28 AWG, bare and PVC, on dipoles.pota_invvee.

Drives the app's own solve (the registered example's momwire_solve, server
defaults: Sommerfeld average ground, the served basis), over every wire in
the WIRES catalog from 28 to 12 AWG. Two readings per wire: at the stock length
(the dropdown flipped, everything else held) and re-cut so X = 0 at 14.1 MHz.
"""

import json
import math
import sys

import numpy as np

from antennaknobs.web.examples import REGISTRY

EX = REGISTRY["dipoles.pota_invvee"]
F0 = 14.1


def solve(wire, lf, f):
    return EX.momwire_solve(
        {
            "measurement_freq_mhz": f,
            "design_freq_mhz": F0,
            "ground": True,
            "params": {"wire_type": wire, "length_factor": lf},
        }
    )


def z(wire, lf, f):
    o = solve(wire, lf, f)
    return complex(o["z_in_re"], o["z_in_im"])


def retune(wire, lf=0.9395):
    # Secant on length_factor for X = 0 at F0.
    a, b = lf, lf * 1.01
    xa, xb = z(wire, a, F0).imag, z(wire, b, F0).imag
    for _ in range(12):
        c = b - xb * (b - a) / (xb - xa)
        xc = z(wire, c, F0).imag
        if abs(xc) < 0.01:
            return c
        a, xa, b, xb = b, xb, c, xc
    return c


def swr_window(wire, lf, z0=50.0):
    fs = np.arange(13.0, 15.3001, 0.01)
    swr = []
    for f in fs:
        zz = z(wire, lf, float(f))
        g = abs((zz - z0) / (zz + z0))
        swr.append((1 + g) / (1 - g))
    swr = np.array(swr)
    ok = swr <= 2.0
    if not ok.any():
        return None, None, float(swr.min()), float(fs[swr.argmin()])
    # Contiguous run holding the minimum.
    m = int(swr.argmin())
    lo = hi = m
    while lo - 1 >= 0 and ok[lo - 1]:
        lo -= 1
    while hi + 1 < len(fs) and ok[hi + 1]:
        hi += 1
    return float(fs[lo]), float(fs[hi]), float(swr.min()), float(fs[m])


def row(wire, lf):
    o = solve(wire, lf, F0)
    eff = o["radiation_efficiency"]
    lo, hi, smin, fmin = swr_window(wire, lf)
    return {
        "wire": wire,
        "length_factor": lf,
        "length_m": o["wire_length_m"],
        "weight_g": o["wire_weight_g"],
        "z": [o["z_in_re"], o["z_in_im"]],
        "eff": eff,
        "loss_db": 10 * math.log10(eff),
        "swr2_lo": lo,
        "swr2_hi": hi,
        "swr2_khz": None if lo is None else round((hi - lo) * 1000),
        "swr_min": smin,
        "f_swr_min": fmin,
    }


if __name__ == "__main__":
    out = []
    for g in (28, 22, 18, 16, 14, 12):
        for suffix in ("-pvc", ""):
            w = f"{g}-awg{suffix}"
            stock = row(w, 0.9395)
            tuned = row(w, retune(w))
            out.append({"stock": stock, "tuned": tuned})
            print(w, json.dumps({"stock": stock, "tuned": tuned}), flush=True)
    json.dump(out, open(sys.argv[1], "w"), indent=1)
