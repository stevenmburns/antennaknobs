"""AK#1661: which capacitor should a fully free T tuner hold at its maximum?

Tune a grid of loads with C1 pinned at c_max and again with C2 pinned, with
realistic Q's, and compare reach (how many loads each can match) and loss.
"""

import math

import numpy as np

from antennaknobs.auto_match import NoMatch, Ranges, design_t_match

LOADS = [
    complex(r, x)
    for r in np.geomspace(5, 2000, 25)
    for x in np.linspace(-1500, 1500, 25)
]


def run(f_mhz, c_max_pF, ql, qc):
    rng = Ranges(c_max=c_max_pF * 1e-12, c_min=10e-12, l_max=30e-6)
    both = only1 = only2 = neither = c1_better = c2_better = 0
    deltas = []
    for z in LOADS:
        eff = {}
        for pin in ("c1", "c2"):
            try:
                eff[pin] = design_t_match(
                    z, 50.0, f_mhz, pin=pin, qc=qc, ql=ql, ranges=rng
                ).efficiency
            except NoMatch:
                pass
        if len(eff) == 2:
            both += 1
            d = 10 * math.log10(eff["c2"] / eff["c1"])  # dB; > 0: C2 pin less lossy
            deltas.append(d)
            if d > 1e-3:
                c2_better += 1
            elif d < -1e-3:
                c1_better += 1
        elif "c1" in eff:
            only1 += 1
        elif "c2" in eff:
            only2 += 1
        else:
            neither += 1
    d = np.array(deltas) if deltas else np.array([0.0])
    print(
        f"{f_mhz:5g} MHz cmax {c_max_pF:4g} pF Ql {ql:4g} Qc {qc:5g} | "
        f"both {both:3d} only-C1 {only1:3d} only-C2 {only2:3d} neither {neither:3d} | "
        f"where both: C2 less lossy {c2_better:3d}, C1 less lossy {c1_better:3d}, "
        f"median {np.median(d):+.3f} dB, max {d.max():+.3f} dB, min {d.min():+.3f} dB"
    )


if __name__ == "__main__":
    print(
        f"{len(LOADS)} loads, R 5-2000 ohm x X +-1500 ohm, target 50 ohm, c_min 10 pF, l_max 30 uH"
    )
    for f in (3.6, 7.1, 14.1, 28.5):
        for cmax in (250.0, 500.0):
            run(f, cmax, 150.0, 1000.0)
    run(14.1, 250.0, 75.0, 500.0)
    run(14.1, 250.0, 300.0, 5000.0)
