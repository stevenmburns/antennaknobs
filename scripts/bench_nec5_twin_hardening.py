"""Hardening the NEC-5 identification — and measuring what it buys bs1/bs2.

Step 1 of the communication plan for the formulation-twin result, with two
jobs on every geometry:

1. HARDENING: the identification claim ("NEC-5 = tent basis + razor-blade
   testing + centroid-trapezoid ∫A·dl") predicts that NEC-5 minus
   RazorSolver(nec5_quadrature=True) is CONSTANT down each ladder — an
   N-independent kernel nuance, not discretization. One geometry
   (ByDipole1) is a fit; four geometries with different shapes (bend,
   junction loop, fat wire) make it an identification.

2. THE bs STORY: on the same ladders, how many segments does each lane
   need to sit within 0.5 Ω of its own converged value? The twin is the
   controlled experiment — same tent basis as bs1, only the testing rule
   differs — so the N* table quantifies what momwire's Galerkin testing
   (bs1) and higher-order basis (bs2) buy over NEC-5's formulation.

All free space (RazorSolver's domain; keeps Michalski ground out), 14 MHz.

Usage:  NEC5_EXE=... .venv/bin/python scripts/bench_nec5_twin_hardening.py
Writes scratch/nec5-twin-hardening.json and prints the two claim tables.
"""

from __future__ import annotations

import json
import math
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "scratch" / "nec5-twin-hardening.json"

FREQ = 14.0
WL = 299792458.0 / (FREQ * 1e6)

# Ladders are TOTAL segment counts; every rung has a center/apex knot.
DIP_NS = (12, 16, 24, 32, 48, 64, 96)
LOOP_SIDE_NS = (4, 6, 8, 12, 16, 24)  # per side; total = 4x

INVVEE_ARM = 5.35  # m, ~quarter-wave arms, 90 deg included angle
LOOP_SIDE = 6.05  # m, perimeter 24.2 m ~ 1.13 wavelength


def _dipole_wires(length, radius):
    return [np.array([[0.0, 0.0, 0.0], [0.0, length, 0.0]])], radius


def _invvee_wires():
    c = INVVEE_ARM / math.sqrt(2.0)
    pl = np.array([[-c, 0.0, -c], [0.0, 0.0, 0.0], [c, 0.0, -c]])
    return [pl], 1.0e-3


def _loop_wires():
    s = LOOP_SIDE
    pl = np.array(
        [[0.0, 0.0, 0.0], [s, 0.0, 0.0], [s, s, 0.0], [0.0, s, 0.0], [0.0, 0.0, 0.0]]
    )
    return [pl], 2.0e-3


def _gw(tag, n, p0, p1, rad):
    return (
        f"GW {tag} {n} "
        f"{p0[0]:.6E} {p0[1]:.6E} {p0[2]:.6E} "
        f"{p1[0]:.6E} {p1[1]:.6E} {p1[2]:.6E} {rad:.6E}\n"
    )


def _deck(header, gws, ex_tag, ex_seg):
    return (
        f"CM {header}\nCE\n"
        + "".join(gws)
        + "GE 0\n"
        + f"EX 0 {ex_tag} {ex_seg} 2 1.000000E+00 0.000000E+00\n"
        + f"FR 0 1 0 0 {FREQ:.6E} 0.000000E+00\nXQ 0\nEN\n"
    )


# Geometry table: name -> (momwire wires+radius+feed kwargs, nec5 deck fn,
# ladder, bspline lanes on/off). Feeds always at a plain knot the NEC-5 EX
# card addresses identically (segment end 2 = the knot at that segment's
# far end).
def _nec5_dipole_deck(n, length, radius, tag_note):
    wires, _ = _dipole_wires(length, radius)
    p = wires[0]
    return _deck(
        f"twin-hardening {tag_note}",
        [_gw(1, n, p[0], p[1], radius)],
        1,
        n // 2,
    )


def _nec5_invvee_deck(n):
    c = INVVEE_ARM / math.sqrt(2.0)
    gws = [
        _gw(1, n // 2, (-c, 0.0, -c), (0.0, 0.0, 0.0), 1.0e-3),
        _gw(2, n // 2, (0.0, 0.0, 0.0), (c, 0.0, -c), 1.0e-3),
    ]
    # end 2 of wire 1's last segment = the apex knot (the K=2 junction).
    return _deck("twin-hardening invvee", gws, 1, n // 2)


def _nec5_loop_deck(n_side):
    s = LOOP_SIDE
    corners = [(0.0, 0.0, 0.0), (s, 0.0, 0.0), (s, s, 0.0), (0.0, s, 0.0)]
    gws = [
        _gw(t + 1, n_side, corners[t], corners[(t + 1) % 4], 2.0e-3) for t in range(4)
    ]
    # center knot of the bottom side.
    return _deck("twin-hardening loop", gws, 1, n_side // 2)


GEOMS = {
    "dipole": {
        "wires": lambda: _dipole_wires(10.18946, 1.0262e-3),
        "deck": lambda n: _nec5_dipole_deck(n, 10.18946, 1.0262e-3, "dipole"),
        "ladder": DIP_NS,
        "total": lambda n: n,
        "bspline": True,
        "feed": {},
    },
    "fat-dipole": {
        "wires": lambda: _dipole_wires(10.18946, 1.0e-2),
        "deck": lambda n: _nec5_dipole_deck(n, 10.18946, 1.0e-2, "fat"),
        "ladder": DIP_NS,
        "total": lambda n: n,
        "bspline": True,
        "feed": {},
    },
    "invvee": {
        "wires": _invvee_wires,
        "deck": _nec5_invvee_deck,
        "ladder": DIP_NS,
        "total": lambda n: n,
        "bspline": True,
        "feed": {},
    },
    "loop": {
        "wires": _loop_wires,
        "deck": _nec5_loop_deck,
        "ladder": LOOP_SIDE_NS,
        "total": lambda n: 4 * n,
        # BSplineSolver needs an explicit junction spec for a closed loop;
        # the hardening claim doesn't need bs lanes here, so keep the loop
        # to the nec5/razor lanes rather than grow the instrument.
        "bspline": False,
        "feed": {"feed_arclength": LOOP_SIDE / 2},
    },
}


def _seg_split(geom_name, n):
    """Per-edge segment counts for the momwire polyline spelling."""
    if geom_name == "invvee":
        return [[n // 2, n // 2]]
    if geom_name == "loop":
        return [[n, n, n, n]]
    return [[n]]


def _razor_z(geom_name, g, n, **mode):
    from momwire import RazorSolver

    wires, radius = g["wires"]()
    z, _ = RazorSolver(
        wires=wires,
        n_per_edge_per_wire=_seg_split(geom_name, n),
        wire_radius=radius,
        wavelength=WL,
        **g["feed"],
        **mode,
    ).compute_impedance()
    return z


def _bspline_z(geom_name, g, n, degree):
    from momwire.bspline import BSplineSolver

    wires, radius = g["wires"]()
    z, _ = BSplineSolver(
        wires=wires,
        n_per_edge_per_wire=_seg_split(geom_name, n),
        degree=degree,
        wire_radius=radius,
        wavelength=WL,
        **g["feed"],
    ).compute_impedance()
    return z


def _ri(z):
    return [round(z.real, 4), round(z.imag, 4)]


def main() -> None:
    from antennaknobs.engines.nec5 import NEC5Engine

    import sys

    sys.path.insert(0, str(ROOT / "scripts"))
    from bench_nec5_walk_why import make_dipole

    eng5 = NEC5Engine(
        make_dipole(20),
        ground=None,
        capture_dir=Path.home() / ".antennaknobs" / "nec5-captures",
    )

    data: dict = {}
    for name, g in GEOMS.items():
        lanes: dict = {k: [] for k in ("nec5", "n5q", "razor", "bs1", "bs2")}
        for n in g["ladder"]:
            zn = eng5.run_deck(g["deck"](n))[0][0][2]
            lanes["nec5"].append([n, *_ri(zn)])
            lanes["n5q"].append([n, *_ri(_razor_z(name, g, n, nec5_quadrature=True))])
            lanes["razor"].append([n, *_ri(_razor_z(name, g, n))])
            if g["bspline"]:
                lanes["bs1"].append([n, *_ri(_bspline_z(name, g, n, 1))])
                lanes["bs2"].append([n, *_ri(_bspline_z(name, g, n, 2))])
            print(f"{name} n={n} done", flush=True)
        data[name] = {k: v for k, v in lanes.items() if v}
    OUT.write_text(json.dumps(data, indent=1))

    # ---- claim 1: residual constancy
    print("\n== claim 1: nec5 − razor(nec5_quadrature) residual per geometry ==")
    for name, lanes in data.items():
        res = [
            complex(a[1], a[2]) - complex(b[1], b[2])
            for a, b in zip(lanes["nec5"], lanes["n5q"])
        ]
        mean = sum(res) / len(res)
        spread = max(abs(r - mean) for r in res)
        rungs = "  ".join(f"{r.real:+.4f}{r.imag:+.4f}j" for r in res)
        print(
            f"  {name:11s} mean {mean.real:+.4f}{mean.imag:+.4f}j spread {spread:.4f}"
        )
        print(f"    rungs: {rungs}")

    # ---- claim 2: segments each lane needs (within 0.5 ohm of its limit)
    print(
        "\n== claim 2: N* = total segments to sit within 0.5 Ω of the lane's "
        "converged value =="
    )
    for name, lanes in data.items():
        g = GEOMS[name]
        row = [f"  {name:11s}"]
        for lane in ("bs2", "bs1", "razor", "n5q", "nec5"):
            if lane not in lanes:
                row.append(f"{lane}: —")
                continue
            pts = [(r[0], complex(r[1], r[2])) for r in lanes[lane]]
            # First-order lanes get a Richardson limit from the two finest
            # rungs (they form an exact (N, 2N) pair on these ladders);
            # bs1/bs2 converge fast enough that the finest read IS the limit
            # at this table's 0.5 Ω resolution.
            if lane in ("razor", "n5q", "nec5"):
                limit = 2.0 * pts[-1][1] - pts[-3][1]
            else:
                limit = pts[-1][1]
            n_star = next(
                (g["total"](n) for n, z in pts if abs(z - limit) <= 0.5), None
            )
            row.append(
                f"{lane}: {n_star if n_star is not None else '>' + str(g['total'](pts[-1][0]))}"
            )
        print("  ".join(row))


if __name__ == "__main__":
    main()
