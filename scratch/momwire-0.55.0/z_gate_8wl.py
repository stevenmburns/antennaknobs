"""momwire 0.55.0 pre-release gate (scratch/momwire-0.55.0/ZGATE-8WL.md).

The question: is serving the below/below remainder as zero still inside
momwire#1058's bound at about 8 in-medium wavelengths, where two
antennaknobs corners now land? Run against the momwire tree under test:

  PYTHONPATH=<momwire main>/src:<ak>/src python \\
      scratch/momwire-0.55.0/z_gate_8wl.py guard --out F
  PYTHONPATH=<momwire main>/src:<ak>/src python \\
      scratch/momwire-0.55.0/z_gate_8wl.py zgate --deck 1135 --solver bspline --out F

`guard` (G8) checks the extended below/below table against direct integration,
off-node, across 4-8.3 lambda_m at soil B and 7.1 MHz. `zgate` is U4 PT1's
shape on a corner built the way the app builds it:
- shipped (cap 4) against extended (cap 9) at the app's mesh;
- extended at three times the far mesh, for the ladder step.
"""

from __future__ import annotations

import argparse
import inspect
import json
import math
import time
import warnings
from pathlib import Path

import numpy as np

import momwire
from momwire import _below_interface, _ground_refl
from momwire import _sommerfeld_below as below

SOIL_B = ("finite", 20.0, 0.03)
FREQ_MHZ = 7.1
SHIPPED_CAP = 4.0
EXTENDED_CAP = 9.0
BAR = 1e-2
GRID_BAR = 2e-4
DECKS = {
    "1135": {"length_factor": 1.2, "radial_factor": 1.5},
    "1131": {"n_radials": 4, "depth": 0.5, "length_factor": 1.2, "radial_factor": 1.5},
}
NSEGS = {1: 21, 3: 63}


def medium():
    om = 2.0 * math.pi * FREQ_MHZ * 1e6
    eps_t = _ground_refl.eps_tilde((SOIL_B[1], SOIL_B[2]), om, 8.8541878128e-12)
    k2 = om / 299792458.0
    return eps_t, k2, om, below.lambda_medium(eps_t, k2)


def guard():
    eps_t, k2, om, lam = medium()
    below._SOMM_BELOW_R1_CAP_LAMBDA_M = EXTENDED_CAP
    t0 = time.time()
    grid = below.SommerfeldGridBelow(eps_t, k2, EXTENDED_CAP * lam, omega=om)
    r1_wl = np.array([4.137, 4.613, 5.229, 5.871, 6.407, 7.031, 7.659, 8.213])
    th_deg = np.array([0.331, 0.613, 1.071, 1.931, 3.173])
    r1, th = np.meshgrid(r1_wl * lam, np.radians(th_deg), indexing="ij")
    r1, th = r1.ravel(), th.ravel()
    grid._ensure_for(float(r1.max()), float(th.min()), float(th.max()))
    got = grid.eval(r1, th)
    ref = below.iv_surfaces_direct_below(eps_t, k2, r1, th, rtol=1e-9, omega=om)
    worst, at = 0.0, None
    for key in got:
        g = np.asarray(got[key])
        d = np.asarray(ref[key])
        scale = np.maximum(np.abs(d), 1e-10 * float(np.max(np.abs(d))))
        rel = np.abs(g - d) / scale
        i = int(np.argmax(rel))
        if rel[i] > worst:
            worst = float(rel[i])
            at = [key, float(r1[i] / lam), float(np.degrees(th[i]))]
    return dict(
        mode="guard",
        momwire=momwire.__file__,
        lam_m=lam,
        grid_r1_max_wl=grid.r1_max / lam,
        points=int(r1.size),
        worst_rel=worst,
        worst_at=at,
        bar=GRID_BAR,
        verdict="HIT" if worst <= GRID_BAR else "MISS",
        seconds=round(time.time() - t0, 1),
    )


def _builder(deck, nsegs):
    from antennaknobs.designs.verticals.buried_radial_vertical import Builder

    b = Builder()
    for k, v in DECKS[deck].items():
        setattr(b, k, v)
    b.nominal_nsegs = nsegs
    return b


def _solve(deck, refine, solver, seen):
    from antennaknobs.engines.momwire import MomwireEngine

    real_plan = _below_interface.serve_plan
    real_grid = below.get_grid_below
    sig = inspect.signature(real_plan)

    def plan(*a, **kw):
        out = real_plan(*a, **kw)
        k_m = sig.bind(*a, **kw).arguments["k_m"]
        seen.setdefault("plan_r1_wl", []).append(
            out["r1_below"] * abs(k_m) / (2.0 * math.pi)
        )
        return out

    def grid(*a, **kw):
        g = real_grid(*a, **kw)
        seen.setdefault("grid_r1_wl", []).append(g.r1_max / g.lam_m)
        seen.setdefault("grids", []).append(g)
        return g

    _below_interface.serve_plan = plan
    below.get_grid_below = grid
    try:
        kw = {}
        if solver == "sg":
            from momwire import SinusoidalGalerkinSolver

            kw["solver"] = SinusoidalGalerkinSolver
        with warnings.catch_warnings():
            warnings.simplefilter("ignore")
            t0 = time.time()
            eng = MomwireEngine(_builder(deck, NSEGS[refine]), ground=SOIL_B, **kw)
            z = complex(eng.impedance()[0])
            seen.setdefault("seconds", []).append(round(time.time() - t0, 1))
            return z
    finally:
        _below_interface.serve_plan = real_plan
        below.get_grid_below = real_grid


def _evict(grids):
    cache = below._GRID_CACHE
    for key in [k for k, g in cache.items() if any(g is x for x in grids)]:
        del cache[key]


def zgate(deck, solver):
    assert below._SOMM_BELOW_R1_CAP_LAMBDA_M == SHIPPED_CAP
    rec = dict(mode="zgate", momwire=momwire.__file__, deck=deck, solver=solver)
    shipped, extended, ext3 = {}, {}, {}
    try:
        z_ship = _solve(deck, 1, solver, shipped)
        _evict(shipped["grids"])
        below._SOMM_BELOW_R1_CAP_LAMBDA_M = EXTENDED_CAP
        z_ext1 = _solve(deck, 1, solver, extended)
        z_ext3 = _solve(deck, 3, solver, ext3)
    except (ValueError, NotImplementedError) as exc:
        rec.update(verdict="REFUSED", error=f"{type(exc).__name__}: {exc}"[:600])
        return rec
    finally:
        below._SOMM_BELOW_R1_CAP_LAMBDA_M = SHIPPED_CAP
    delta = abs(z_ship - z_ext1)
    step = abs(z_ext3 - z_ext1)
    guards = dict(
        plan_past_cap=max(shipped["plan_r1_wl"]) > SHIPPED_CAP,
        shipped_grid_at_cap=max(shipped["grid_r1_wl"]) <= SHIPPED_CAP * (1 + 1e-12),
        extended_grid_covers_plan=max(extended["grid_r1_wl"])
        >= max(extended["plan_r1_wl"]),
        delta_not_bit_zero=delta > 1e-9 * abs(z_ext1),
    )
    if not all(guards.values()):
        verdict = "GUARD-MISS"
    else:
        verdict = "HIT" if delta <= BAR * step else "MISS"
    for d in (shipped, extended, ext3):
        d.pop("grids", None)
    rec.update(
        z_shipped_n21=repr(z_ship),
        z_extended_n21=repr(z_ext1),
        z_extended_n63=repr(z_ext3),
        delta_ohm=delta,
        ladder_step_ohm=step,
        delta_over_step=delta / step if step else None,
        delta_over_abs_z=delta / abs(z_ext1),
        guards=guards,
        shipped=shipped,
        extended=extended,
        extended_n63=ext3,
        bar=BAR,
        verdict=verdict,
    )
    return rec


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("mode", choices=("guard", "zgate"))
    ap.add_argument("--deck", choices=sorted(DECKS))
    ap.add_argument("--solver", choices=("bspline", "sg"), default="bspline")
    ap.add_argument("--out", type=Path, required=True)
    args = ap.parse_args()
    rec = guard() if args.mode == "guard" else zgate(args.deck, args.solver)
    args.out.write_text(json.dumps(rec, indent=1))
    print(json.dumps(rec))


if __name__ == "__main__":
    main()
