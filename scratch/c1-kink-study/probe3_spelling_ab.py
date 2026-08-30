"""C1-kink study, probe 3 — the thought-identical spellings, measured.

On the CATALOG buried-radial geometry (N=21 defaults, soil A), A/B each
formulation pair that reads as "the same antenna":

  X1 hub bend    A: run + rise separate wires, 8-member hub junction
                    (C0 bend) — the shipped catalog spelling.
                 B: each radial ONE polyline tip->hub->graded rise->node
                    (C1 through the bend, hub junction gone) — the
                    momwire fan_rise_deck spelling.
  X2 rise grade  A: graded interior knots (C1 inside the rise) — shipped.
                 B: split sub-wires at the same points (C0 panel edges,
                    plus the coincident bundle's shared-point junctions).
  X3 mono chain  A: gap + radiator one polyline (C1 at the 0.05 knot) —
                    shipped. B: split at 0.05 (C0 there).

Run: prlimit --as=$((8*1024*1024*1024)) .venv/bin/python \
       scratch/c1-kink-study/probe3_spelling_ab.py
"""

from __future__ import annotations

import json
import sys
import time
from pathlib import Path

import numpy as np

HERE = Path(__file__).resolve().parent
AK = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(HERE.parent / "buried-quality-post"))

from momwire.bspline import BSplineSolver  # noqa: E402
from probe1_ladders import harvested_kwargs, mw_engine  # noqa: E402

RISE_Z = (-0.15, -0.05, -0.0125, 0.0)


def solve(kw, tag):
    s = BSplineSolver(**kw)
    t0 = time.time()
    z, _ = s.compute_impedance()
    print(f"  [{tag}] Z = {z:.4f}  ({time.time() - t0:.1f}s)", flush=True)
    return z


def base_kw():
    e, b = mw_engine(nsegs=21)
    return harvested_kwargs(e, b)


def is_rise(pts):
    zl = [round(float(p[2]), 4) for p in pts]
    return zl == list(RISE_Z)


def is_run(pts):
    return (
        len(pts) == 2 and abs(pts[0][2] + 0.15) < 1e-9 and abs(pts[1][2] + 0.15) < 1e-9
    )


def x1_bend_c1(kw):
    """B spelling: fuse each run with its rise into one polyline
    tip -> hub -> graded rise -> node (C1 bend). The hub junction
    disappears; the node junction keeps the 4 radial polyline ENDS +
    the mono start. Runs are re-authored tip-first so the polyline
    walks tip -> node (interior hub vertex)."""
    runs, rises, others = [], [], []
    for pts, c in zip(kw["wires"], kw["n_per_edge_per_wire"]):
        p = [tuple(float(x) for x in q) for q in pts]
        (runs if is_run(pts) else rises if is_rise(pts) else others).append(
            (p, list(c))
        )
    assert len(runs) == 4 and len(rises) == 4
    wires, npe = [], []
    for (rp, rc), (sp, sc) in zip(runs, rises):
        tip = rp[1] if rp[0] == (0.0, 0.0, -0.15) else rp[0]
        wires.append(np.array([tip] + [(0.0, 0.0, z) for z in RISE_Z]))
        npe.append([rc[0]] + sc)
    mono_i = len(wires)
    for p, c in others:
        wires.append(np.array(p))
        npe.append(c)
    out = dict(kw)
    out["wires"] = wires
    out["n_per_edge_per_wire"] = npe
    out["junctions"] = [[(i, "end") for i in range(4)] + [(mono_i, "start")]]
    out["feeds"] = [(mono_i, kw["feeds"][0][1], kw["feeds"][0][2])]
    return out


def x2_rise_split(kw):
    """B spelling: each rise as three separate sub-wires (C0 at panel
    edges); the walk-level junction derivation is emulated by declaring
    the shared-point junctions the AK walk would create (8-member at
    -0.05 and -0.0125). Keeps everything else identical."""
    wires, npe, rise_slots = [], [], []
    for pts, c in zip(kw["wires"], kw["n_per_edge_per_wire"]):
        if is_rise(pts):
            rise_slots.append(len(wires))
            for z0, z1 in zip(RISE_Z, RISE_Z[1:]):
                wires.append(np.array([(0.0, 0.0, z0), (0.0, 0.0, z1)]))
                npe.append([2])
            continue
        wires.append(np.array([tuple(float(x) for x in q) for q in pts]))
        npe.append(list(c))
    # Re-derive all junctions from coincident endpoints (the walk's rule).
    ends = {}
    for i, pts in enumerate(wires):
        for which, p in (("start", pts[0]), ("end", pts[-1])):
            key = tuple(round(float(x), 9) for x in p)
            ends.setdefault(key, []).append((i, which))
    junctions = [g for g in ends.values() if len(g) > 1]
    out = dict(kw)
    out["wires"] = wires
    out["n_per_edge_per_wire"] = npe
    out["junctions"] = junctions
    # feeds reference the mono polyline — find it (starts at node, goes up)
    mono_i = next(
        i
        for i, p in enumerate(wires)
        if tuple(round(float(x), 6) for x in p[0]) == (0.0, 0.0, 0.0) and p[1][2] > 0
    )
    out["feeds"] = [(mono_i, kw["feeds"][0][1], kw["feeds"][0][2])]
    return out


def x3_mono_split(kw):
    """B spelling: cut the mono polyline at the 0.05 knot — gap wire and
    radiator become separate wires with a 2-member junction (C0)."""
    wires, npe = [], []
    for pts, c in zip(kw["wires"], kw["n_per_edge_per_wire"]):
        p = [tuple(float(x) for x in q) for q in pts]
        if p[0] == (0.0, 0.0, 0.0) and len(p) > 2 and p[1][2] > 0:
            wires.append(np.array(p[:2]))
            npe.append([c[0]])
            wires.append(np.array(p[1:]))
            npe.append(c[1:])
            continue
        wires.append(np.array(p))
        npe.append(list(c))
    ends = {}
    for i, pts in enumerate(wires):
        for which, p in (("start", pts[0]), ("end", pts[-1])):
            key = tuple(round(float(x), 9) for x in p)
            ends.setdefault(key, []).append((i, which))
    junctions = [g for g in ends.values() if len(g) > 1]
    out = dict(kw)
    out["wires"] = wires
    out["n_per_edge_per_wire"] = npe
    out["junctions"] = junctions
    gap_i = next(
        i
        for i, p in enumerate(wires)
        if tuple(round(float(x), 6) for x in p[0]) == (0.0, 0.0, 0.0)
        and len(p) == 2
        and abs(p[1][2] - 0.05) < 1e-9
    )
    out["feeds"] = [(gap_i, kw["feeds"][0][1], kw["feeds"][0][2])]
    return out


def main():
    out = {}
    kw = base_kw()
    zA = solve(kw, "shipped (hub C0, rise C1-knots, mono C1-chain)")
    out["shipped"] = f"{zA:.4f}"
    for name, mk in (
        ("X1-bend-C1", x1_bend_c1),
        ("X2-rise-split-C0", x2_rise_split),
    ):
        z = solve(mk(base_kw()), name)
        print(f"  -> {name}: |dZ vs shipped| = {abs(z - zA):.4f} ohm", flush=True)
        out[name] = dict(z=f"{z:.4f}", dz=round(float(abs(z - zA)), 4))
    (HERE / "results-probe3.json").write_text(json.dumps(out, indent=2))
    print("saved", flush=True)


if __name__ == "__main__":
    main()
