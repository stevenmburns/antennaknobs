"""Elevated-panel probe E2 — the RESONANT deck family (raw
apples-to-apples).

E1 measured the raw cross-engine gap on the insulated-base family as a
near-constant -28 ohm X offset and identified the mechanism: feed-region
parasitic capacitance, whose impedance effect scales as Z^2
(dZ ~ -j w C Z^2, C ~ 0.6 pF between formulations). At |Z| ~ 1000 that
is 28 ohm; at |Z| ~ 80 it is milliohm-class. So the raw-number panel
belongs on a RESONANT deck: a center-fed ~half-wave vertical dipole
(21 m at 7 MHz), lower tip at h over the detached buried radials.

Ladder conventions as E1: engine odd multipliers (center-fed segment
stays centered: 21m segs, feed seg 10.5m+0.5), momwire d1/d2.

Run:
  NEC5_EXE=~/antennas/NEC5-downloads/nec5-linux/nec5cl \
    prlimit --as=$((8*1024*1024*1024)) .venv/bin/python \
    scratch/elevated-panel/probe_e2_dipole.py engine
  prlimit --as=$((8*1024*1024*1024)) .venv/bin/python \
    scratch/elevated-panel/probe_e2_dipole.py momwire
  .venv/bin/python scratch/elevated-panel/probe_e2_dipole.py panel
"""

from __future__ import annotations

import json
import sys
import time
from pathlib import Path

import numpy as np

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
RESULTS = HERE / "results" / "probe-e2.json"

WL7 = 42.827494
LEN = 21.0
NSEG = 21
HEIGHTS = (0.25, 0.5, 1.0)
RADIAL_DIRS = {
    "ref": [],
    "lone": [(1, 0)],
    "fan": [(1, 0), (0, 1), (-1, 0), (0, -1)],
}
ENGINE_MULTS = (1, 3, 5)


def feed_seg(mult):
    k = (NSEG / 2) * mult + 0.5
    assert abs(k - round(k)) < 1e-9, mult
    return int(round(k))


def engine_deck(geom, h, mult):
    nv, nr = NSEG * mult, 10 * mult
    lines = [
        f"CM elevated dipole {geom} h={h}",
        "CE",
        f"GW 1,{nv},0.,0.,{h + LEN},0.,0.,{h},.001",
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
    wires = [np.array([(0.0, 0.0, h + LEN), (0.0, 0.0, h)])]
    npe = [[NSEG * dens]]
    for dx, dy in RADIAL_DIRS[geom]:
        wires.append(np.array([(0.0, 0.0, -0.15), (5.0 * dx, 5.0 * dy, -0.15)]))
        npe.append([10 * dens])
    build = dict(
        wires=wires,
        n_per_edge_per_wire=npe,
        feeds=[(0, LEN / 2, 1 + 0j)],
        wavelength=WL7,
        wire_radius=0.001,
        ground_z=0.0,
        ground_eps=(13.0, 0.005),
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
                key = f"e2 nec5 {geom} h={h} x{m}"
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
                key = f"e2 momwire {geom} h={h} d{dens}"
                print(f"  {key}: {z:.4f}  ({time.time() - t0:.0f}s)", flush=True)
                out[key] = f"{z:.4f}"
    save(out)


def panel():
    r = load()

    def g(k):
        return complex(r[k]) if k in r else None

    fmt = lambda z: f"{z:18.4f}" if z is not None else " " * 17 + "-"  # noqa: E731 — kept: the probe reads as the algebra it is checking
    print("RAW (resonant family — the apples-to-apples panel):")
    print(
        f"{'geom':>5} {'h':>5} | {'nec5 x3':>18} {'x5':>18} | "
        f"{'momwire d1':>18} {'d2':>18} | {'|gap| x5-d2':>11}"
    )
    for geom in RADIAL_DIRS:
        for h in HEIGHTS:
            n = [g(f"e2 nec5 {geom} h={h} x{m}") for m in (3, 5)]
            mw = [g(f"e2 momwire {geom} h={h} d{d}") for d in (1, 2)]
            gap = (
                f"{abs(n[1] - mw[1]):11.4f}"
                if n[1] is not None and mw[1] is not None
                else "          -"
            )
            print(
                f"{geom:>5} {h:>5} | "
                + " ".join(fmt(z) for z in n)
                + " | "
                + " ".join(fmt(z) for z in mw)
                + f" | {gap}"
            )
    print("\nDELTA vs ref (the buried-coupling instrument):")
    for geom in ("lone", "fan"):
        for h in HEIGHTS:
            dn = (
                g(f"e2 nec5 {geom} h={h} x5") - g(f"e2 nec5 ref h={h} x5")
                if g(f"e2 nec5 {geom} h={h} x5") is not None
                else None
            )
            dm = (
                g(f"e2 momwire {geom} h={h} d2") - g(f"e2 momwire ref h={h} d2")
                if g(f"e2 momwire {geom} h={h} d2") is not None
                else None
            )
            if dn is None or dm is None:
                continue
            print(
                f"{geom:>5} {h:>5} | nec5 {dn:9.4f}  momwire {dm:9.4f}  "
                f"|diff| {abs(dn - dm):.4f}"
            )


if __name__ == "__main__":
    mode = sys.argv[1] if len(sys.argv) > 1 else "panel"
    {"engine": run_engine, "momwire": run_momwire, "panel": panel}[mode]()
