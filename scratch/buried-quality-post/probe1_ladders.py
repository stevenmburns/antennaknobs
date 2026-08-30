"""Buried-quality post — the data: two convergence ladders, a sigma sweep,
and the eps1 truth anchor, all on the AK catalog buried-radial vertical.

  mw-ladder    momwire on the CONNECTED screen (its served convention):
               nominal_nsegs ladder + node-graded top rungs (the #674
               matched grading spliced into the harvested solver kwargs).
  nec5-ladder  NEC-5 on the DETACHED variant (its served convention):
               the same nominal_nsegs values through the wrapper.
  sigma        the convention gap vs soil conductivity (capped at 1 S/m,
               below the #647 sea-class residual), best mesh each side.
  eps1         the catalog-geometry collapse: mixed-medium machinery vs
               an independent free-space solve of the same wires.

Run: NEC5_EXE=~/antennas/NEC5-downloads/nec5-linux/nec5cl \
     prlimit --as=$((8*1024*1024*1024)) .venv/bin/python \
     scratch/buried-quality-post/probe1_ladders.py [mw-ladder|nec5-ladder|sigma|eps1 ...]
"""

from __future__ import annotations

import json
import sys
import time
from pathlib import Path

import numpy as np

HERE = Path(__file__).resolve().parent

from antennaknobs.designs.verticals.buried_radial_vertical import (  # noqa: E402
    Builder as BRV,
)
from antennaknobs.engines.momwire import MomwireEngine  # noqa: E402
from momwire.bspline import BSplineSolver  # noqa: E402

SOIL_A = (13.0, 0.005)
C_LIGHT = 299792458.0
LADDER = (11, 21, 31, 42)


def brv(nsegs=21, **overrides):
    return BRV({**BRV.default_params, "nominal_nsegs": nsegs, **overrides})


def mw_engine(nsegs=21, sigma=0.005, **overrides):
    b = brv(nsegs, **overrides)
    return MomwireEngine(b, ground=("finite", 13.0, sigma), ground_z=0.0), b


def harvested_kwargs(engine, b, ground=True):
    """The exact kwargs `_make_solver` would pass, harvested so the graded
    rungs can splice vertices into the polylines (scratch-quality private
    access, same fields _make_solver reads)."""
    kw = dict(
        wires=[np.array(p, dtype=float) for p in engine._polylines],
        n_per_edge_per_wire=[list(e) for e in engine._edge_segments],
        feeds=engine._solver_feeds(),
        wavelength=C_LIGHT / (b.freq * 1e6),
        wire_radius=engine._wire_radius,
        junctions=engine._junctions or None,
        **engine._loading_kwargs,
        **engine._kernel_solver_kwargs(None),
        **engine._solver_kwargs,
    )
    if ground:
        kw["ground_z"] = engine._ground_z
        kw.update(engine._ground_solver_kwargs())
    return kw


# Node-grading rungs (the #674 recipe on the walked catalog geometry).
# The RISES are the coarse arm here (default mesh = ONE segment over the
# whole 15 cm rise; auto_mesh's max(1, round) floor keeps it there at any
# nominal_nsegs — a uniform density ladder can never converge this deck's
# node class). The mono's node-adjacent edge is the 5 cm eps base-gap
# FEED edge (npe 1, feed at its center) — NEVER re-meshed, that would
# change the feed model; the long edge's node end gets a fixed split
# (0.05 -> 0.125 -> 0.5 -> tip) on every graded rung. Only the rise
# h_node steps down the ladder: g1 25 mm, g2 6.25 mm, g3 1.56 mm.
RISE_RUNGS = {
    "g1": ((-0.15, -0.05, 0.0), [2, 2]),
    "g2": ((-0.15, -0.05, -0.0125, 0.0), [2, 2, 2]),
    "g3": ((-0.15, -0.05, -0.0125, -0.0031, 0.0), [2, 2, 2, 2]),
}
H_NODE_MM = {"g1": 25.0, "g2": 6.25, "g3": 1.5625}


def graded(kw, depth, rung="g2"):
    rise_z, rise_npe = RISE_RUNGS[rung]
    wires, npe = [], []
    for pts, counts in zip(kw["wires"], kw["n_per_edge_per_wire"]):
        pts = [tuple(float(c) for c in p) for p in pts]
        if (
            len(pts) == 2
            and pts[0] == (0.0, 0.0, -depth)
            and pts[1]
            == (
                0.0,
                0.0,
                0.0,
            )
        ):
            wires.append(np.array([(0.0, 0.0, z) for z in rise_z]))
            npe.append(list(rise_npe))
        elif pts[0] == (0.0, 0.0, 0.0) and len(pts) >= 3 and pts[1][2] > 0:
            tip_z = pts[-1][2]
            wires.append(
                np.array([(0.0, 0.0, z) for z in (0.0, 0.05, 0.125, 0.5, tip_z)])
            )
            npe.append([counts[0], 2, 3, counts[-1]])
        else:
            wires.append(np.array(pts))
            npe.append(list(counts))
    out = dict(kw)
    out["wires"] = wires
    out["n_per_edge_per_wire"] = npe
    return out


def solve_kw(kw, tag):
    t0 = time.time()
    z, _ = BSplineSolver(**kw).compute_impedance()
    dt = time.time() - t0
    print(f"[{tag}] Z = {z:.4f}  ({dt:.1f}s)", flush=True)
    return z, dt


def run_mw_ladder(out):
    """The node-graded ladder at the default density (the axis that
    actually converges this deck), plus a far-axis check (N=42 at g2)
    and the untouched default-mesh print for the 'what you get before
    grading' row."""
    rows = {}
    e, b = mw_engine(nsegs=21)
    kw = harvested_kwargs(e, b)
    z, dt = solve_kw(kw, "mw-default")
    rows["default"] = dict(z=f"{z:.4f}", secs=round(dt, 1))
    for rung in ("g1", "g2", "g3"):
        z, dt = solve_kw(graded(kw, b.depth, rung), f"mw-{rung}")
        rows[rung] = dict(z=f"{z:.4f}", secs=round(dt, 1), h_node_mm=H_NODE_MM[rung])
    e42, b42 = mw_engine(nsegs=42)
    z, dt = solve_kw(graded(harvested_kwargs(e42, b42), b42.depth, "g2"), "mw-N42-g2")
    rows["N42-g2"] = dict(z=f"{z:.4f}", secs=round(dt, 1))
    out["mw-ladder"] = rows


def run_nec5_ladder(out):
    from antennaknobs.engines.nec5 import NEC5Engine

    rows = {}
    for n in LADDER + (63,):
        b = brv(n, convention="detached")
        e = NEC5Engine(
            b, ground=("finite", 13.0, 0.005), capture_dir=HERE / "nec5-captures"
        )
        t0 = time.time()
        z = e.impedance()[0]
        rows[f"N{n}"] = dict(z=f"{z:.4f}", secs=round(time.time() - t0, 1))
        print(f"[nec5-N{n}] Z = {z:.4f}", flush=True)
    out["nec5-ladder"] = rows


def run_sigma(out):
    from antennaknobs.engines.nec5 import NEC5Engine

    rows = {}
    for sigma in (0.001, 0.005, 0.03, 0.1, 0.3, 1.0):
        e, b = mw_engine(nsegs=42, sigma=sigma)
        kw = graded(harvested_kwargs(e, b), b.depth)
        z_mw, _ = solve_kw(kw, f"sigma{sigma}-mw")
        b5 = brv(42, convention="detached")
        e5 = NEC5Engine(
            b5, ground=("finite", 13.0, sigma), capture_dir=HERE / "nec5-captures"
        )
        z_n5 = e5.impedance()[0]
        gap = abs(z_mw - z_n5)
        print(
            f"[sigma {sigma}] mw {z_mw:.2f}  nec5 {z_n5:.2f}  gap {gap:.2f}", flush=True
        )
        rows[str(sigma)] = dict(
            mw=f"{z_mw:.4f}", nec5=f"{z_n5:.4f}", gap_ohm=round(float(gap), 2)
        )
    out["sigma"] = rows


def run_eps1(out):
    e, b = mw_engine(nsegs=42)
    e._ground_eps = (1.0, 0.0)  # eps1 soil through the same ground plumbing
    kw = graded(harvested_kwargs(e, b), b.depth)
    kw["ground_eps"] = (1.0, 0.0)
    z, _ = solve_kw(kw, "eps1-mixed")
    kw_free = {
        k: v
        for k, v in kw.items()
        if k not in ("ground_z", "ground_eps", "ground_model")
    }
    z_t, _ = solve_kw(kw_free, "eps1-truth")
    print(f"[eps1] |mixed - truth| = {abs(z - z_t):.4f} ohm", flush=True)
    out["eps1"] = dict(
        mixed=f"{z:.4f}", truth=f"{z_t:.4f}", diff_ohm=round(float(abs(z - z_t)), 4)
    )


def main():
    path = HERE / "results.json"
    out = json.loads(path.read_text()) if path.exists() else {}
    for name in sys.argv[1:] or ["mw-ladder", "nec5-ladder", "sigma", "eps1"]:
        {
            "mw-ladder": run_mw_ladder,
            "nec5-ladder": run_nec5_ladder,
            "sigma": run_sigma,
            "eps1": run_eps1,
        }[name](out)
        path.write_text(json.dumps(out, indent=2))
    print(f"saved {path}", flush=True)


if __name__ == "__main__":
    main()
