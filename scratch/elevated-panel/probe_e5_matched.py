"""Elevated-panel probe E5 — the E1/E2 re-derivation at the MATCHED feed
(the #706 erratum: `EX 4,tag,k` drives the far NODE, arc k·h from the
wire start; E1 fed momwire at 4.3333 against a drifting engine node, and
E3's "knot feed closes the 28 Ω" was two errors cancelling).

Corrected frame, fixed physical feed point at every rung on both sides:

- E1 family (insulated-base class, 10 m vertical, base h): feed at the
  4.6667 node — engine `EX 4,1,7m` (integral for EVERY multiplier, no
  odd-only restriction, no drift), momwire point feed at 4.6667 and the
  knot feed split 4.6667/5.3333 = 7d/8d segments (uniform h, cleaner
  than E3's 4.3333 split ever was).
- E2 family (resonant 21 m dipole, lower tip at h): mesh respelled
  22m segments so the CENTER is a node (21m made 10.5 a segment
  center: the old engine ladder drifted 10.5 + 0.5/m). Engine
  `EX 4,1,11m`, momwire feed at 10.5 on [22d] meshes.

Run:
  NEC5_EXE=~/antennas/NEC5-downloads/nec5-linux/nec5cl \
    prlimit --as=$((8*1024*1024*1024)) .venv/bin/python \
    scratch/elevated-panel/probe_e5_matched.py engine
  prlimit --as=$((8*1024*1024*1024)) .venv/bin/python \
    scratch/elevated-panel/probe_e5_matched.py momwire
  .venv/bin/python scratch/elevated-panel/probe_e5_matched.py panel
"""

from __future__ import annotations

import json
import sys
import time
from pathlib import Path

import numpy as np

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
RESULTS = HERE / "results" / "probe-e5.json"

WL7 = 42.827494
FEED_FROM_TOP = 4.6666666667
HEIGHTS = (0.25, 0.5, 1.0)
RADIAL_DIRS = {
    "ref": [],
    "lone": [(1, 0)],
    "fan": [(1, 0), (0, 1), (-1, 0), (0, -1)],
}
E1_MULTS = (1, 3, 5, 8)
E2_MULTS = (1, 3, 5, 8)
E2_LEN = 21.0


def e1_engine_deck(geom, h, mult):
    nv, nr = 15 * mult, 10 * mult
    lines = [
        f"CM e5 elevated-detached {geom} h={h}",
        "CE",
        f"GW 1,{nv},0.,0.,{10 + h},0.,0.,{h},.001",
    ]
    for i, (dx, dy) in enumerate(RADIAL_DIRS[geom]):
        lines.append(f"GW {i + 2},{nr},0.,0.,-0.15,{5 * dx}.,{5 * dy}.,-0.15,.001")
    lines += [
        "GE 1,-1",
        "FR 0,1,0,0,7.",
        "GN 0,0,0,0,13.,.005",
        f"EX 4,1,{7 * mult},0,1.,0.",
        "PQ 0",
        "XQ 0",
        "EN",
    ]
    return "\n".join(lines) + "\n"


def e2_engine_deck(geom, h, mult):
    nv, nr = 22 * mult, 10 * mult
    lines = [
        f"CM e5 resonant dipole {geom} h={h}",
        "CE",
        f"GW 1,{nv},0.,0.,{E2_LEN + h},0.,0.,{h},.001",
    ]
    for i, (dx, dy) in enumerate(RADIAL_DIRS[geom]):
        lines.append(f"GW {i + 2},{nr},0.,0.,-0.15,{5 * dx}.,{5 * dy}.,-0.15,.001")
    lines += [
        "GE 1,-1",
        "FR 0,1,0,0,7.",
        "GN 0,0,0,0,13.,.005",
        f"EX 4,1,{11 * mult},0,1.,0.",
        "PQ 0",
        "XQ 0",
        "EN",
    ]
    return "\n".join(lines) + "\n"


def _radial_wires(geom, wires, npe, dens):
    for dx, dy in RADIAL_DIRS[geom]:
        wires.append(np.array([(0.0, 0.0, -0.15), (5.0 * dx, 5.0 * dy, -0.15)]))
        npe.append([10 * dens])


def _ground():
    return dict(
        wavelength=WL7,
        wire_radius=0.001,
        ground_z=0.0,
        ground_eps=(13.0, 0.005),
        ground_model="sommerfeld",
    )


def e1_point_build(geom, h, dens=1):
    wires = [np.array([(0.0, 0.0, 10.0 + h), (0.0, 0.0, h)])]
    npe = [[15 * dens]]
    _radial_wires(geom, wires, npe, dens)
    build = dict(
        wires=wires,
        n_per_edge_per_wire=npe,
        feeds=[(0, FEED_FROM_TOP, 1 + 0j)],
        **_ground(),
    )
    if geom == "fan":
        build["junctions"] = [[(1, "start"), (2, "start"), (3, "start"), (4, "start")]]
    return build


def e1_knot_build(geom, h, dens=1):
    top = 10.0 + h
    split_z = top - FEED_FROM_TOP
    wires = [
        np.array([(0.0, 0.0, top), (0.0, 0.0, split_z)]),
        np.array([(0.0, 0.0, split_z), (0.0, 0.0, h)]),
    ]
    npe = [[7 * dens], [8 * dens]]
    juncs = [[(0, "end"), (1, "start")]]
    _radial_wires(geom, wires, npe, dens)
    if geom == "fan":
        juncs.append([(2, "start"), (3, "start"), (4, "start"), (5, "start")])
    return dict(
        wires=wires,
        n_per_edge_per_wire=npe,
        junctions=juncs,
        node_gaps=[(0, "end", 1 + 0j)],
        feeds=[],
        **_ground(),
    )


def e2_build(geom, h, dens=1):
    wires = [np.array([(0.0, 0.0, E2_LEN + h), (0.0, 0.0, h)])]
    npe = [[22 * dens]]
    _radial_wires(geom, wires, npe, dens)
    build = dict(
        wires=wires,
        n_per_edge_per_wire=npe,
        feeds=[(0, E2_LEN / 2, 1 + 0j)],
        **_ground(),
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
    for fam, mults, build in (
        ("e1", E1_MULTS, e1_engine_deck),
        ("e2", E2_MULTS, e2_engine_deck),
    ):
        for geom in RADIAL_DIRS:
            for h in HEIGHTS:
                for m in mults:
                    z = complex(eng.run_deck(build(geom, h, m))[0][0][2])
                    key = f"nec5-{fam} {geom} h={h} x{m}"
                    print(f"  {key}: {z:.4f}", flush=True)
                    out[key] = f"{z:.4f}"
    save(out)


def run_momwire():
    from momwire.bspline import BSplineSolver

    out = {}
    jobs = []
    for geom in RADIAL_DIRS:
        for h in HEIGHTS:
            for dens in (1, 2):
                jobs.append(
                    (f"mw-e1-point {geom} h={h} d{dens}", e1_point_build(geom, h, dens))
                )
            for dens in (1, 2, 3):
                jobs.append(
                    (f"mw-e1-knot {geom} h={h} d{dens}", e1_knot_build(geom, h, dens))
                )
            for dens in (1, 2, 3):
                jobs.append((f"mw-e2 {geom} h={h} d{dens}", e2_build(geom, h, dens)))
    for key, build in jobs:
        t0 = time.time()
        z, _ = BSplineSolver(**build).compute_impedance()
        print(f"  {key}: {z:9.4f}  ({time.time() - t0:.0f}s)", flush=True)
        out[key] = f"{z:.4f}"
        save(out)


def panel():
    r = load()
    g = lambda k: complex(r[k]) if k in r else None  # noqa: E731 — kept: the probe reads as the algebra it is checking
    fmt = lambda z: f"{z:18.4f}" if z is not None else " " * 17 + "-"  # noqa: E731 — kept: the probe reads as the algebra it is checking

    for fam, mw_rows in (
        ("e1", (("point", "d2"), ("knot", "d2"), ("knot", "d3"))),
        ("e2", (("", "d2"), ("", "d3"))),
    ):
        print(f"\n=== {fam} raw panel (engine ladder vs momwire rungs) ===")
        for geom in RADIAL_DIRS:
            for h in HEIGHTS:
                n = [g(f"nec5-{fam} {geom} h={h} x{m}") for m in E1_MULTS]
                tag = lambda sp, d: (  # noqa: E731 — kept: the probe reads as the algebra it is checking
                    f"mw-{fam}-{sp} {geom} h={h} {d}"
                    if sp
                    else f"mw-{fam} {geom} h={h} {d}"
                )
                mw = [g(tag(sp, d)) for sp, d in mw_rows]
                gap = (
                    f"{abs(n[-1] - mw[-1]):11.3f}"
                    if n[-1] is not None and mw[-1] is not None
                    else "          -"
                )
                print(
                    f"{geom:>5} {h:>5} | "
                    + " ".join(fmt(z) for z in n)
                    + " | "
                    + " ".join(fmt(z) for z in mw)
                    + f" | {gap}"
                )

        print(f"--- {fam} delta instrument (Z - Z_ref, deepest rungs) ---")
        for geom in ("lone", "fan"):
            for h in HEIGHTS:
                dn = None
                zn, zr = g(f"nec5-{fam} {geom} h={h} x8"), g(f"nec5-{fam} ref h={h} x8")
                if zn is not None and zr is not None:
                    dn = zn - zr
                sp, d = ("knot", "d3") if fam == "e1" else ("", "d3")
                tag = (
                    f"mw-{fam}-{sp} {geom} h={h} {d}"
                    if sp
                    else f"mw-{fam} {geom} h={h} {d}"
                )
                tag_r = (
                    f"mw-{fam}-{sp} ref h={h} {d}" if sp else f"mw-{fam} ref h={h} {d}"
                )
                dm = None
                if g(tag) is not None and g(tag_r) is not None:
                    dm = g(tag) - g(tag_r)
                ratio = (
                    f"{abs(dn) / abs(dm):5.2f}"
                    if dn is not None and dm is not None and abs(dm) > 1e-12
                    else "    -"
                )
                print(
                    f"{geom:>5} {h:>5} | engine {fmt(dn)} | momwire {fmt(dm)}"
                    f" | ratio |n/m| {ratio}"
                )


if __name__ == "__main__":
    mode = sys.argv[1] if len(sys.argv) > 1 else "panel"
    {"engine": run_engine, "momwire": run_momwire, "panel": panel}[mode]()
