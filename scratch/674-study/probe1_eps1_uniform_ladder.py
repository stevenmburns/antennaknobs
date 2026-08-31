"""momwire#674 probe 1 — the clean ε̃=1 uniform-refinement ladder.

The fan widening's residual (probe38: 0.2269 Ω at the base mesh) is a
node-mesh convergence class; the OLD grading rungs mixed refinement
ratios (run x1.4 vs rise x2), so the issue's "roughly first order" was
never a fit. This probe runs a SELF-SIMILAR ladder — every edge's npe
scaled by one integer s — so h shrinks uniformly and the order p in
|fan − truth| = C·h^p is a two-point fit per adjacent rung pair.

At ε̃ = 1 the interface vanishes and the SAME wires/junction/feed with
no ground is the independent free-space truth (native junction
machinery); truth and fan refine TOGETHER — the diff is the quantity
under test.

Run: prlimit --as=$((8*1024*1024*1024)) .venv/bin/python \
       scratch/674-study/probe1_eps1_uniform_ladder.py [s ...]
     (default rungs 1 2 3 4)
"""

from __future__ import annotations

import itertools
import json
import math
import sys
import time
from pathlib import Path

import numpy as np  # noqa: F401 — kept: imported for its import-time effect / to document the probe's inputs

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "momwire" / "tests"))

from momwire.bspline import BSplineSolver  # noqa: E402
from test_crossing_serve_524 import fan_rise_deck  # noqa: E402

DEPTH = 0.15  # fan_rise_deck default; rise edge npe = 2s -> h_node = DEPTH/(2s)


def _solve(build, tag):
    s = BSplineSolver(**build)
    t0 = time.time()
    z, _ = s.compute_impedance()
    dt = time.time() - t0
    print(f"[{tag}] Z = {z:.4f}   ({dt:.1f}s)", flush=True)
    return z, dt


def free_space_truth(build):
    return {
        k: v
        for k, v in build.items()
        if k not in ("ground_z", "ground_eps", "ground_model")
    }


def run_rung(s_mult, out):
    build = fan_rise_deck(ground_eps=(1.0, 0.0))
    build["n_per_edge_per_wire"] = [[10 * s_mult, 2 * s_mult] for _ in range(4)] + [
        [15 * s_mult]
    ]
    z_truth, dt_t = _solve(free_space_truth(build), f"s{s_mult}-truth")
    z, dt = _solve(build, f"s{s_mult}-fan")
    diff = abs(z - z_truth)
    h_node = DEPTH / (2 * s_mult)
    print(
        f"[s{s_mult}] |fan - truth| = {diff:.4f} ohm  (h_node {h_node * 1000:.1f} mm)",
        flush=True,
    )
    out["rungs"][str(s_mult)] = dict(
        z=f"{z:.4f}",
        truth=f"{z_truth:.4f}",
        diff_ohm=round(float(diff), 4),
        h_node_mm=round(h_node * 1000, 2),
        secs=round(dt + dt_t, 1),
    )


def fit_orders(out):
    rungs = sorted((int(k) for k in out["rungs"]), key=int)
    rows = [(s, out["rungs"][str(s)]["diff_ohm"]) for s in rungs]
    print("\n[fit] adjacent-pair orders (diff = C h^p, h ~ 1/s):", flush=True)
    pairs = []
    for (s1, d1), (s2, d2) in itertools.pairwise(rows):
        if d1 <= 0 or d2 <= 0:
            continue
        p = math.log(d1 / d2) / math.log(s2 / s1)
        pairs.append(dict(pair=f"s{s1}->s{s2}", p=round(p, 3)))
        print(f"  s{s1}->s{s2}: p = {p:.3f}", flush=True)
    out["order_fit"] = pairs
    # Richardson on the fan Z itself, finest three rungs, assuming the
    # fitted order of the finest pair: Z(h) = Z* + A h^p
    if len(rows) >= 2 and pairs:
        p = pairs[-1]["p"]
        (s1, _), (s2, _) = rows[-2], rows[-1]
        z1 = complex(out["rungs"][str(s1)]["z"])
        z2 = complex(out["rungs"][str(s2)]["z"])
        r = s2 / s1  # h1/h2
        z_star = z2 + (z2 - z1) / (r**p - 1)
        out["richardson_fan"] = dict(p_used=round(p, 3), z_star=f"{z_star:.4f}")
        print(f"[richardson] fan Z* = {z_star:.4f}  (p = {p:.3f})", flush=True)
        t1 = complex(out["rungs"][str(s1)]["truth"])
        t2 = complex(out["rungs"][str(s2)]["truth"])
        t_star = t2 + (t2 - t1) / (r**p - 1)
        out["richardson_truth"] = f"{t_star:.4f}"
        print(
            f"[richardson] truth Z* = {t_star:.4f}  |fan* - truth*| = "
            f"{abs(z_star - t_star):.4f}",
            flush=True,
        )


def main():
    out = {"rungs": {}}
    path = HERE / "results" / "probe1-eps1-uniform-ladder.json"
    path.parent.mkdir(exist_ok=True)
    if path.exists():
        out = json.loads(path.read_text())
    rungs = [int(a) for a in sys.argv[1:]] or [1, 2, 3, 4]
    for s_mult in rungs:
        run_rung(s_mult, out)
        path.write_text(json.dumps(out, indent=2))
    fit_orders(out)
    path.write_text(json.dumps(out, indent=2))
    print(f"saved {path}", flush=True)


if __name__ == "__main__":
    main()
