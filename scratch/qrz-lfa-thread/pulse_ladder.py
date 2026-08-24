"""Roy's coupled-loop model under the two pulse-charge solvers (AK#982 lanes).

Same deck as ladder_dense.py — W7EL's NEC-2/NEC-4 pathology model (500 Hz,
free space, -j404.7 kV at the z=20 knot's segment) — pushed through
PulseSolver (nodal point charges) and HarringtonSolver (dual-cell charge).
Neither takes a junction spec: coincident ends are found from the geometry,
so the three-wire base junction is expressed by the wire list alone.

Two questions, matching the thread:
  1. the k-ladder at 500 Hz: source current + max loop element |I| — does a
     pulse charge model put spurious current in the loop the way NEC-2's
     quadrature error does (162 A on a sub-ampere source), or stay in the
     NEC-5/bspline class (~0.48 A)?
  2. the 1/f sweep (50 kHz .. 5 Hz at fixed k): the loop/source ratio —
     flat = clean, climbing ~10x per decade downward = the NEC-2 defect.

Writes results-pulse.json next to this script:
  {engine: {"ladder": {str(k): [Re I_src, Im I_src, max loop |I|]},
            "fsweep": {str(f_mhz): ratio}}}

Run:  .venv/bin/python scratch/qrz-lfa-thread/pulse_ladder.py
"""

import json
from pathlib import Path

import numpy as np
from momwire import HarringtonSolver
from momwire.pulse import PulseSolver

MHZ = 0.0005
V = -404675.9j
RADIUS = 0.005
HERE = Path(__file__).parent

W = [
    ((20, -40, 300), (20, -40, 0), 15),
    ((40, -40, 0), (40, 40, 0), 4),
    ((40, 40, 0), (-40, 40, 0), 4),
    ((-40, 40, 0), (-40, -40, 0), 4),
    ((-40, -40, 0), (20, -40, 0), 3),
    ((20, -40, 0), (40, -40, 0), 1),
]


def solve(cls, k, mhz):
    wl = 299.8 / mhz
    ws = [np.array([a, b], float) for a, b, _ in W]
    npe = [[n * k] for _, _, n in W]
    s = cls(
        wires=ws,
        n_per_edge_per_wire=npe,
        # the segment whose centroid sits half a segment above the z=20
        # knot — the same feed segment as every other lane's spelling
        feeds=[(0, 280.0 - 10.0 / k, V)],
        wire_radius=RADIUS,
        wavelength=wl,
    )
    z, coeffs = s.compute_impedance()
    geom = s._build_geometry()
    off = geom["seg_offsets"]
    i_src = V / z
    loop = max(float(np.max(np.abs(coeffs[off[w] : off[w + 1]]))) for w in range(1, 6))
    return complex(i_src), loop


def main():
    out = {}
    for name, cls in (("pulse", PulseSolver), ("harrington", HarringtonSolver)):
        ladder = {}
        for k in (1, 2, 4, 8):
            i_src, loop = solve(cls, k, MHZ)
            ladder[str(k)] = [i_src.real, i_src.imag, loop]
            print(
                f"{name:11s} k={k:2d}  I_src {abs(i_src):.4e} A   "
                f"max loop {loop:.4e} A   ratio {loop / abs(i_src):.4f}",
                flush=True,
            )
        fsweep = {}
        for mhz in (0.05, 0.005, 0.0005, 0.00005, 0.000005):
            i_src, loop = solve(cls, 4, mhz)
            fsweep[str(mhz)] = loop / abs(i_src)
            print(
                f"{name:11s} f={mhz * 1e6:>8.1f} Hz  ratio {loop / abs(i_src):.4f}",
                flush=True,
            )
        out[name] = {"ladder": ladder, "fsweep": fsweep}
    (HERE / "results-pulse.json").write_text(json.dumps(out, indent=1))
    print("wrote", HERE / "results-pulse.json")


if __name__ == "__main__":
    main()
