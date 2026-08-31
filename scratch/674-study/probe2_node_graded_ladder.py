"""momwire#674 probe 2 — per-arm node grading (probe18 style, at the K=5 node).

probe1 measured the composition error as clean first order under uniform
refinement — but uniform rungs shrink EVERY h at once, so they cannot say
where the error lives. This probe grades geometrically toward the node
at (0,0,0) ONLY — vertices walking toward z = 0 on the rises (from
below) and the monopole (from above), far mesh pinned at base — with
h_node stepping ×4 per rung. If the residual follows h_node at ~first
order, the slow term is node-local; if it stalls, it lives in the far
mesh (rise body / radial runs).

Attribution subcommands grade one side only at the n2 depth:
  mono-only  - monopole graded, rises at base
  rise-only  - rises graded, monopole at base

Run: prlimit --as=$((8*1024*1024*1024)) .venv/bin/python \
       scratch/674-study/probe2_node_graded_ladder.py [n1|n2|n3|mono-only|rise-only ...]
"""

from __future__ import annotations

import itertools
import json
import math
import sys
import time
from pathlib import Path

import numpy as np

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "momwire" / "tests"))

from momwire.bspline import BSplineSolver  # noqa: E402
from test_crossing_serve_524 import fan_rise_deck  # noqa: E402

DEPTH = 0.15

# Grading schedules: vertices walk toward z = 0; npe per edge. h_node
# steps x4 per rung on BOTH sides of the node.
RISE_GRADES = {
    # rung: (z-vertices from -DEPTH up to 0, npe per edge)  h_node
    "n1": ([-0.15, -0.05, 0.0], [2, 2]),  # 25 mm
    "n2": ([-0.15, -0.05, -0.0125, 0.0], [2, 2, 2]),  # 6.25 mm
    "n3": ([-0.15, -0.05, -0.0125, -0.0031, 0.0], [2, 2, 2, 2]),  # ~1.56 mm
}
MONO_GRADES = {
    # monopole polyline runs 10 -> 0; vertices approach 0 from above
    "n1": ([10.0, 0.5, 0.05, 0.0], [19, 2, 2]),  # 25 mm
    "n2": ([10.0, 0.5, 0.05, 0.0125, 0.0], [19, 2, 3, 2]),  # 6.25 mm
    "n3": ([10.0, 0.5, 0.05, 0.0125, 0.0031, 0.0], [19, 2, 3, 2, 2]),  # ~1.56 mm
}
H_NODE_MM = {"n1": 25.0, "n2": 6.25, "n3": 1.5625}


def _graded_build(rise_rung=None, mono_rung=None):
    """fan_rise_deck with per-arm node grading spliced into the wire
    polylines. Radial runs stay [10]; feed arclength is untouched (the
    monopole vertices only subdivide the existing 10 -> 0 line)."""
    build = fan_rise_deck(ground_eps=(1.0, 0.0))
    dirs = ((1, 0), (0, 1), (-1, 0), (0, -1))
    wires, npe = [], []
    if rise_rung is None:
        rise_pts, rise_npe = ([-0.15, 0.0], [2])
    else:
        rise_pts, rise_npe = RISE_GRADES[rise_rung]
    for dx, dy in dirs:
        pts = [(5.0 * dx, 5.0 * dy, -DEPTH)] + [(0.0, 0.0, z) for z in rise_pts]
        wires.append(np.array(pts))
        npe.append([10] + list(rise_npe))
    if mono_rung is None:
        mono_pts, mono_npe = ([10.0, 0.0], [15])
    else:
        mono_pts, mono_npe = MONO_GRADES[mono_rung]
    wires.append(np.array([(0.0, 0.0, z) for z in mono_pts]))
    npe.append(list(mono_npe))
    build["wires"] = wires
    build["n_per_edge_per_wire"] = npe
    return build


def free_space_truth(build):
    return {
        k: v
        for k, v in build.items()
        if k not in ("ground_z", "ground_eps", "ground_model")
    }


def _solve(build, tag):
    s = BSplineSolver(**build)
    t0 = time.time()
    z, _ = s.compute_impedance()
    dt = time.time() - t0
    print(f"[{tag}] Z = {z:.4f}   ({dt:.1f}s)", flush=True)
    return z, dt


def run_case(name, rise_rung, mono_rung, out):
    build = _graded_build(rise_rung=rise_rung, mono_rung=mono_rung)
    z_truth, dt_t = _solve(free_space_truth(build), f"{name}-truth")
    z, dt = _solve(build, f"{name}-fan")
    diff = abs(z - z_truth)
    print(f"[{name}] |fan - truth| = {diff:.4f} ohm", flush=True)
    out["cases"][name] = dict(
        z=f"{z:.4f}",
        truth=f"{z_truth:.4f}",
        diff_ohm=round(float(diff), 4),
        secs=round(dt + dt_t, 1),
    )


def fit(out):
    rungs = [r for r in ("n1", "n2", "n3") if r in out["cases"]]
    print("\n[fit] node-graded orders vs h_node (x4 per rung):", flush=True)
    fits = []
    for r1, r2 in itertools.pairwise(rungs):
        d1, d2 = out["cases"][r1]["diff_ohm"], out["cases"][r2]["diff_ohm"]
        if d1 <= 0 or d2 <= 0:
            continue
        p = math.log(d1 / d2) / math.log(H_NODE_MM[r1] / H_NODE_MM[r2])
        fits.append(dict(pair=f"{r1}->{r2}", p=round(p, 3)))
        print(f"  {r1}->{r2}: p = {p:.3f}", flush=True)
    out["order_fit"] = fits


CASES = {
    "n1": ("n1", "n1"),
    "n2": ("n2", "n2"),
    "n3": ("n3", "n3"),
    "mono-only": (None, "n2"),
    "rise-only": ("n2", None),
}


def main():
    path = HERE / "results" / "probe2-node-graded-ladder.json"
    path.parent.mkdir(exist_ok=True)
    out = json.loads(path.read_text()) if path.exists() else {"cases": {}}
    for name in sys.argv[1:] or ["n1", "n2", "n3", "mono-only", "rise-only"]:
        rise_rung, mono_rung = CASES[name]
        run_case(name, rise_rung, mono_rung, out)
        path.write_text(json.dumps(out, indent=2))
    fit(out)
    path.write_text(json.dumps(out, indent=2))
    print(f"saved {path}", flush=True)


if __name__ == "__main__":
    main()
