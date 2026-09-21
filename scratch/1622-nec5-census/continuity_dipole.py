"""The drive-point continuity question with nothing else in it (AK#1622).

The corpus decks cannot settle whether antennaknobs' and serve's spellings of a
drive point converge to one answer: their conductors are fat enough that the
top rungs of a ladder leave the thin-wire regime (0028 is below h/a = 2 from
r = 16), and the routes also mesh differently. So this is the same question on
a thin centre-fed dipole, with the mesh IDENTICAL both ways and only the drive
point spelled differently:

* `continuous` - one polyline, a positioned delta gap at the centre knot:
                 antennaknobs' spelling, the degree-2 basis running through it;
* `cut`        - two polylines joined at the centre, a node gap at the join:
                 serve's spelling, the basis clamped there.

Degree-2 B-spline and razor-2p (+ nec5_quadrature), the extended kernel on and
off. L = 0.48 lambda. At a = 2e-5 lambda h/a is 5.9 at N = 4096, close enough
to the thin-wire limit that the last rungs slow; a = 2e-6 keeps h/a at 58.6 there.

    python continuity_dipole.py                                   # a = 2e-5, EK on and off
    python continuity_dipole.py --radius 2e-6 --ek on \
        --ns 64,256,1024,2048,4096 --out continuity_dipole_thin.jsonl
"""

from __future__ import annotations

import argparse
import json
import pathlib
import time
import warnings

warnings.filterwarnings("ignore")

import numpy as np  # noqa: E402
from momwire import BSplineSolver  # noqa: E402
from momwire.razor import RazorSolver  # noqa: E402

LENGTH = 0.48
RADIUS = 2e-5
NS = (16, 32, 64, 128, 256, 512, 1024, 2048, 4096)
P0 = np.array([0.0, -LENGTH / 2, 0.0])
P1 = np.array([0.0, LENGTH / 2, 0.0])
PC = np.zeros(3)


def spelled(kind: str, n: int) -> dict:
    """Solver kwargs for the centre-fed dipole on `n` segments."""
    if kind == "continuous":
        return dict(
            wires=[np.array([P0, P1])],
            n_per_edge_per_wire=[[n]],
            feeds=[(0, LENGTH / 2, 1 + 0j)],
        )
    return dict(
        wires=[np.array([P0, PC]), np.array([PC, P1])],
        n_per_edge_per_wire=[[n // 2], [n // 2]],
        feeds=[],
        node_gaps=[(1, "start", 1 + 0j)],
        junctions=[[(0, "end"), (1, "start")]],
    )


def z(solver_cls, extra: dict, kind: str, n: int, ek: bool) -> complex:
    s = solver_cls(
        **spelled(kind, n),
        wavelength=1.0,
        wire_radius=RADIUS,
        extended_kernel=ek,
        **extra,
    )
    # (driving-point Z, basis coefficients); one port here, so Z is a scalar.
    z_in = s.compute_impedance()[0]
    return complex(np.asarray(z_in).reshape(-1)[0])


LANES = {
    "bs2": (BSplineSolver, {}),
    "razor": (RazorSolver, {"nec5_quadrature": True}),
}


def main() -> None:
    global RADIUS
    ap = argparse.ArgumentParser()
    ap.add_argument("--radius", type=float, default=RADIUS)
    ap.add_argument("--ns", default=",".join(str(n) for n in NS))
    ap.add_argument("--ek", choices=("on", "off", "both"), default="both")
    ap.add_argument("--out", default="continuity_dipole.jsonl")
    args = ap.parse_args()
    RADIUS = args.radius
    kernels = {"on": (True,), "off": (False,), "both": (True, False)}[args.ek]
    here = pathlib.Path(__file__).resolve().parent
    rows = []
    for ek in kernels:
        for lane, (cls, extra) in LANES.items():
            for n in (int(x) for x in args.ns.split(",")):
                t0 = time.perf_counter()
                zc = z(cls, extra, "continuous", n, ek)
                zk = z(cls, extra, "cut", n, ek)
                rec = {
                    "ek": ek,
                    "lane": lane,
                    "n": n,
                    "radius": RADIUS,
                    "h_over_a": LENGTH / n / RADIUS,
                    "continuous": [zc.real, zc.imag],
                    "cut": [zk.real, zk.imag],
                    "seconds": time.perf_counter() - t0,
                }
                rows.append(rec)
                print(
                    f"EK={'on ' if ek else 'off'} {lane:<5} N={n:>5} h/a={rec['h_over_a']:>7.1f}"
                    f"  continuous {zc:.6f}  cut {zk:.6f}  |diff| {abs(zc - zk):.3e} ohm"
                    f"  ({rec['seconds']:.1f} s)",
                    flush=True,
                )
    (here / args.out).write_text("\n".join(json.dumps(r) for r in rows) + "\n")


if __name__ == "__main__":
    main()
