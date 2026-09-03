"""G1-B probe: bspline degree 1 vs degree 2 on every buried anchor bspline serves.

Per anchor: bs2 at the anchor mesh/quadrature (the reference), then bs1 at
mesh x1 and x3 (odd multipliers: the fed segment's centre stays put), same
quadrature. Prints |bs1 - bs2| per rung and whether it shrinks. JSONL out.
"""

import json
import sys
import time
from pathlib import Path

import numpy as np

MW = Path("/home/smburns/antennas/antennaknobs/momwire")
sys.path.insert(0, str(MW / "tests"))
from momwire.bspline import BSplineSolver  # noqa: E402

import test_buried_serve_553 as t553  # noqa: E402
import test_crossing_serve_524 as t524  # noqa: E402
import test_ble_1937_838 as tble  # noqa: E402

OUT = Path(__file__).with_suffix(".jsonl")


def scale(build, mult):
    b = dict(build)
    b["n_per_edge_per_wire"] = [
        [n * mult for n in w] for w in build["n_per_edge_per_wire"]
    ]
    return b


def solve(build, degree, nqp=None):
    kw = dict(build)
    if nqp is not None:
        kw["n_qp_pair"] = nqp
    t0 = time.time()
    z, _ = BSplineSolver(**kw, degree=degree).compute_impedance()
    return z, time.time() - t0


def served_build(mult=1):
    # the 553 served deck as a build dict (its helper returns a solver)
    n = 15 * mult
    arc = (round(0.4333 * n) - 0.5) / n * 10.0
    return dict(
        wires=[t553._mono(11.0, 1.0), t553._radial(depth=0.15)],
        n_per_edge_per_wire=[[n], [10 * mult]],
        feeds=[(0, arc, 1 + 0j)],
        wavelength=t553.WL7,
        wire_radius=0.001,
        ground_z=0.0,
        ground_eps=t553.SOIL_A,
        ground_model="sommerfeld",
    )


def buried_dipole_build(n, length, vertical):
    depth = 0.15
    if vertical:
        pts = np.array([(0.0, 0.0, -(depth + length)), (0.0, 0.0, -depth)])
    else:
        pts = np.array([(-0.5 * length, 0.0, -depth), (0.5 * length, 0.0, -depth)])
    fed = (n + 1) // 2
    arc = (fed - 0.5) / n * length
    return dict(
        wires=[pts],
        n_per_edge_per_wire=[[n]],
        feeds=[(0, arc, 1 + 0j)],
        wavelength=t553.WL7,
        wire_radius=0.001,
        ground_z=0.0,
        ground_eps=t553.SOIL_A,
        ground_model="sommerfeld",
    )


# name -> (build_fn(mult) for bs1 rungs, bs2 build, nqp, banked or None, mults)
ANCHORS = {
    "crossing_g1": (
        lambda m: scale(t524.crossing_deck(1), m),
        t524.crossing_deck(1),
        t524.CROSSING_G1_QP,
        t524.CROSSING_G1,
        (1, 3),
    ),
    "fan_n2": (
        lambda m: scale(t524.fan_rise_deck_graded("n2"), m),
        t524.fan_rise_deck_graded("n2"),
        t524.FAN_SOIL_A_N2_QP,
        t524.FAN_SOIL_A_N2,
        (1, 3),
    ),
    "hub4": (
        lambda m: scale(t524.hub_deck(4), m),
        t524.hub_deck(4),
        32,
        None,
        (1, 3),
    ),
    "served_553": (
        served_build,
        served_build(1),
        None,
        None,
        (1, 3),
    ),
    "bvd1": (
        lambda m: buried_dipole_build(11 * m, 1.0, True),
        buried_dipole_build(11, 1.0, True),
        None,
        None,
        (1, 3, 5),
    ),
    "bhd10": (
        lambda m: buried_dipole_build(21 * m, 10.0, False),
        buried_dipole_build(21, 10.0, False),
        None,
        None,
        (1, 3),
    ),
    "ble45_n2": (
        lambda m: scale(tble.ble_deck(2), m),
        tble.ble_deck(2),
        None,
        None,
        (1, 3),
    ),
    "ble45_n15": (
        lambda m: scale(tble.ble_deck(15), m),
        tble.ble_deck(15),
        None,
        None,
        (1, 3),
    ),
    "ble45_n30": (
        lambda m: scale(tble.ble_deck(30), m),
        tble.ble_deck(30),
        None,
        None,
        (1,),
    ),
}


def run(name):
    build1, build2, nqp, banked, mults = ANCHORS[name]
    z2, dt2 = solve(build2, 2, nqp)
    row = {
        "anchor": name,
        "nqp": nqp,
        "bs2": [z2.real, z2.imag],
        "bs2_s": round(dt2, 1),
    }
    if banked is not None:
        row["banked"] = [banked.real, banked.imag]
        row["bs2_vs_banked"] = abs(z2 - banked)
    print(
        f"[{name}] bs2 x1  {z2:.4f}  ({dt2:.1f}s)"
        + (
            f"  banked {banked:.4f}  d={abs(z2 - banked):.4f}"
            if banked is not None
            else ""
        )
    )
    # also bs2 at x3 where cheap, to see the reference's own mesh movement
    rungs = []
    for m in mults:
        z1, dt1 = solve(build1(m), 1, nqp)
        d = abs(z1 - z2)
        rungs.append(
            {
                "mult": m,
                "bs1": [z1.real, z1.imag],
                "d_from_bs2x1": d,
                "s": round(dt1, 1),
            }
        )
        print(f"[{name}] bs1 x{m}  {z1:.4f}  |bs1-bs2| = {d:.4f}  ({dt1:.1f}s)")
    if len(mults) > 1 and name not in ("ble45_n15",):
        m = mults[-1]
        z2b, dt2b = solve(
            build1(m) if name != "served_553" else served_build(m), 2, nqp
        )
        row["bs2_hi"] = {
            "mult": m,
            "z": [z2b.real, z2b.imag],
            "d_from_bs2x1": abs(z2b - z2),
            "s": round(dt2b, 1),
        }
        print(
            f"[{name}] bs2 x{m}  {z2b:.4f}  |bs2x{m}-bs2x1| = {abs(z2b - z2):.4f}  ({dt2b:.1f}s)"
            f"   |bs1x{m}-bs2x{m}| = {abs(complex(*rungs[-1]['bs1']) - z2b):.4f}"
        )
    row["bs1"] = rungs
    with OUT.open("a") as f:
        f.write(json.dumps(row) + "\n")


if __name__ == "__main__":
    for n in sys.argv[1:] or list(ANCHORS):
        run(n)
