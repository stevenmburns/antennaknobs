"""Elevated-detached panel, probe E1 — engine captures, momwire solves,
and the cross-engine table. See PLAN.md beside this file.

The deck family is the banked #567 anchor geometry with the base lifted
by h (feed stays 4.3333 m from the TOP; h -> 0 joins the banked contact
anchors). Same-convention class: no contact node in either engine.

Run (engine side needs the binary):
  NEC5_EXE=~/antennas/NEC5-downloads/nec5-linux/nec5cl \
    prlimit --as=$((8*1024*1024*1024)) .venv/bin/python \
    scratch/elevated-panel/probe_e1.py engine
  prlimit --as=$((8*1024*1024*1024)) .venv/bin/python \
    scratch/elevated-panel/probe_e1.py momwire
  .venv/bin/python scratch/elevated-panel/probe_e1.py panel
"""

from __future__ import annotations

import json
import sys
import time
from pathlib import Path

import numpy as np

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
RESULTS = HERE / "results" / "probe-e1.json"

WL7 = 42.827494
SOIL = (13.0, 0.005)
HEIGHTS = (0.25, 0.5, 1.0)
RADIAL_DIRS = {
    "ref": [],  # no radials — the difference-of-columns reference
    "lone": [(1, 0)],
    "fan": [(1, 0), (0, 1), (-1, 0), (0, -1)],
}
ENGINE_MULTS = (1, 3, 5)


def feed_seg(mult):
    # Fed-segment center at 4.3333 m from the top: seg (6.5*m + 0.5) of
    # 15*m — integral for ODD m only (why the ladder is x1/x3/x5).
    k = 6.5 * mult + 0.5
    assert abs(k - round(k)) < 1e-9, mult
    return int(round(k))


def engine_deck(geom, h, mult):
    nv, nr = 15 * mult, 10 * mult
    lines = [
        f"CM elevated-detached {geom} h={h}",
        "CE",
        f"GW 1,{nv},0.,0.,{10 + h},0.,0.,{h},.001",
    ]
    for i, (dx, dy) in enumerate(RADIAL_DIRS[geom]):
        lines.append(f"GW {i + 2},{nr},0.,0.,-0.15,{5 * dx}.,{5 * dy}.,-0.15,.001")
    lines += [
        "GE 1,-1",
        "FR 0,1,0,0,7.",
        "GN 0,0,0,0,13.,.005",
        f"EX 4,1,{feed_seg(mult)},0,1.,0.",
        "PQ 0",
        "XQ 0",
        "EN",
    ]
    return "\n".join(lines) + "\n"


def momwire_build(geom, h, dens=1):
    wires = [np.array([(0.0, 0.0, 10.0 + h), (0.0, 0.0, h)])]
    npe = [[15 * dens]]
    for dx, dy in RADIAL_DIRS[geom]:
        wires.append(np.array([(0.0, 0.0, -0.15), (5.0 * dx, 5.0 * dy, -0.15)]))
        npe.append([10 * dens])
    build = dict(
        wires=wires,
        n_per_edge_per_wire=npe,
        feeds=[(0, 4.3333333333, 1 + 0j)],
        wavelength=WL7,
        wire_radius=0.001,
        ground_z=0.0,
        ground_eps=SOIL,
        ground_model="sommerfeld",
    )
    if geom == "fan":
        build["junctions"] = [[(1, "start"), (2, "start"), (3, "start"), (4, "start")]]
    return build


def load():
    return json.loads(RESULTS.read_text()) if RESULTS.exists() else {}


def save(out):
    RESULTS.parent.mkdir(exist_ok=True)
    old = load()
    old.update(out)
    RESULTS.write_text(json.dumps(old, indent=1))
    print(f"saved {RESULTS}")


def run_engine():
    from antennaknobs.engines.nec5 import NEC5Engine

    sys.path.insert(0, str(ROOT / "scripts"))
    from bench_nec5_walk_why import make_dipole

    captures = HERE / "results" / "nec5-cap"
    captures.mkdir(parents=True, exist_ok=True)
    eng = NEC5Engine(make_dipole(20), ground=None, capture_dir=captures)

    out = {}
    for geom in RADIAL_DIRS:
        for h in HEIGHTS:
            for m in ENGINE_MULTS:
                z = complex(eng.run_deck(engine_deck(geom, h, m))[0][0][2])
                key = f"nec5 {geom} h={h} x{m}"
                print(f"  {key}: {z:.4f}", flush=True)
                out[key] = f"{z:.4f}"
    save(out)


def run_momwire():
    from momwire.bspline import BSplineSolver

    out = {}
    for geom in RADIAL_DIRS:
        for h in HEIGHTS:
            for dens in (1, 2):
                t0 = time.time()
                s = BSplineSolver(**momwire_build(geom, h, dens))
                z, _ = s.compute_impedance()
                key = f"momwire {geom} h={h} d{dens}"
                print(f"  {key}: {z:.4f}  ({time.time() - t0:.0f}s)", flush=True)
                out[key] = f"{z:.4f}"
    save(out)


def panel():
    r = load()

    def g(k):
        return complex(r[k].replace("j", "j")) if k in r else None

    # The delta instrument: Z(radials) - Z(ref) per engine, matched
    # rung — cancels the feed-gap convention and every above-ground
    # formulation difference; what remains IS the buried-radial
    # coupling, the implemented thing under test.
    print("delta = Z(deck) - Z(no-radial ref), cross-engine:")
    print(
        f"{'geom':>5} {'h':>5} | {'nec5 dx3':>18} {'dx5':>18} | "
        f"{'momwire dd1':>18} {'dd2':>18} | {'|ddelta| x5-d2':>14}"
    )
    for geom in ("lone", "fan"):
        for h in HEIGHTS:
            dn = [
                g(f"nec5 {geom} h={h} x{m}") - g(f"nec5 ref h={h} x{m}")
                if g(f"nec5 {geom} h={h} x{m}") is not None
                and g(f"nec5 ref h={h} x{m}") is not None
                else None
                for m in (3, 5)
            ]
            dm = [
                g(f"momwire {geom} h={h} d{d}") - g(f"momwire ref h={h} d{d}")
                if g(f"momwire {geom} h={h} d{d}") is not None
                and g(f"momwire ref h={h} d{d}") is not None
                else None
                for d in (1, 2)
            ]
            dd = (
                f"{abs(dn[1] - dm[1]):14.4f}"
                if dn[1] is not None and dm[1] is not None
                else "             -"
            )
            fmt = lambda z: f"{z:18.4f}" if z is not None else " " * 17 + "-"  # noqa: E731 — kept: the probe reads as the algebra it is checking
            print(
                f"{geom:>5} {h:>5} | "
                + " ".join(fmt(z) for z in dn)
                + " | "
                + " ".join(fmt(z) for z in dm)
                + f" | {dd}"
            )
    print()

    print(
        f"{'geom':>5} {'h':>5} | {'nec5 x1':>18} {'x3':>18} {'x5':>18} | "
        f"{'momwire d1':>18} {'d2':>18} | {'|gap| x5-d2':>11}"
    )
    for geom in RADIAL_DIRS:
        for h in HEIGHTS:
            n = [g(f"nec5 {geom} h={h} x{m}") for m in ENGINE_MULTS]
            mw = [g(f"momwire {geom} h={h} d{d}") for d in (1, 2)]
            gap = (
                f"{abs(n[2] - mw[1]):11.3f}"
                if n[2] is not None and mw[1] is not None
                else "          -"
            )
            fmt = lambda z: f"{z:18.4f}" if z is not None else " " * 17 + "-"  # noqa: E731 — kept: the probe reads as the algebra it is checking
            print(
                f"{geom:>5} {h:>5} | "
                + " ".join(fmt(z) for z in n)
                + " | "
                + " ".join(fmt(z) for z in mw)
                + f" | {gap}"
            )


DEPTHS = (0.15, 0.5, 1.0, 2.0)


def depth_engine_deck(h, depth, mult):
    nv, nr = 15 * mult, 10 * mult
    return (
        f"CM elevated depth ladder d={depth}\nCE\n"
        f"GW 1,{nv},0.,0.,{10 + h},0.,0.,{h},.001\n"
        f"GW 2,{nr},0.,0.,{-depth},5.,0.,{-depth},.001\n"
        "GE 1,-1\nFR 0,1,0,0,7.\nGN 0,0,0,0,13.,.005\n"
        f"EX 4,1,{feed_seg(mult)},0,1.,0.\nPQ 0\nXQ 0\nEN\n"
    )


def run_depth():
    """The depth-ladder adjudicator (lone radial, h=0.5): the real
    transmitted illumination decays with depth; the engine's
    fifth-surface defect (depth-flat below E_z, phase-0 record, empymod
    siding with our kernels) predicts its delta falls off too slowly."""
    from antennaknobs.engines.nec5 import NEC5Engine
    from momwire.bspline import BSplineSolver

    sys.path.insert(0, str(ROOT / "scripts"))
    from bench_nec5_walk_why import make_dipole

    captures = HERE / "results" / "nec5-cap"
    captures.mkdir(parents=True, exist_ok=True)
    eng = NEC5Engine(make_dipole(20), ground=None, capture_dir=captures)

    h = 0.5
    out = {}
    for depth in DEPTHS:
        for m in (3, 5):
            z = complex(eng.run_deck(depth_engine_deck(h, depth, m))[0][0][2])
            out[f"nec5 depth={depth} x{m}"] = f"{z:.4f}"
            print(f"  nec5 depth={depth} x{m}: {z:.4f}", flush=True)
        for dens in (1, 2):
            b = momwire_build("lone", h, dens)
            b["wires"][1] = np.array([(0.0, 0.0, -depth), (5.0, 0.0, -depth)])
            z, _ = BSplineSolver(**b).compute_impedance()
            out[f"momwire depth={depth} d{dens}"] = f"{z:.4f}"
            print(f"  momwire depth={depth} d{dens}: {z:.4f}", flush=True)
    save(out)

    r = load()
    print("\ndepth ladder, delta vs the no-radial ref (h=0.5):")
    zr_n = complex(r["nec5 ref h=0.5 x5"])
    zr_m = complex(r["momwire ref h=0.5 d2"])
    for depth in DEPTHS:
        dn = complex(r[f"nec5 depth={depth} x5"]) - zr_n
        dm = complex(r[f"momwire depth={depth} d2"]) - zr_m
        print(
            f"  depth {depth:>4}: nec5 delta = {dn:9.4f}  "
            f"momwire delta = {dm:9.4f}  ratio |n/m| = "
            f"{abs(dn) / abs(dm) if abs(dm) > 1e-12 else float('inf'):.2f}"
        )


if __name__ == "__main__":
    mode = sys.argv[1] if len(sys.argv) > 1 else "panel"
    {
        "engine": run_engine,
        "momwire": run_momwire,
        "panel": panel,
        "depth": run_depth,
    }[mode]()
