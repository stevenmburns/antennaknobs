"""A-2 follow-up, probe 41 — the AGARD slope ratio read from the SHIPPED solver.

§6 row 31 / §7 adjudicator 1 graded probe31's junction slope ratio
I'(0+)/I'(0-) against 1/eps_t by MAGNITUDE ("0.0450 g1 -> 0.0532 g2 vs
0.0547"). The ratio is complex; graded as |ratio - 1/eps_t| / |1/eps_t| the
same banked numbers read 48 % -> 102 % off, moving away. And probe31 reads
the ratio through the phase-2 probe composition, which today fails its own
eps = 1 adjudicator (probe29) by 35 % on every commit.

This probe bypasses both: probe31's deck (2 m below, 10 m above, feed at
4.3333 m on the above arm, soil A, 7 MHz, a = 1 mm) solved by a plain
BSplineSolver.compute_impedance(), with I and I' taken from
currents_at_knots / current_slopes (the exact spline value and derivative)
at the two wire ends meeting at z = 0. Both wires run +z, so arc = z - z0.

Controls, all printed per rung:
  * ground_eps = (1, 0): the interface is fictitious, the ratio must be 1+0j;
  * a counter on _crossing_fill.cross_complete_block_split, so a rung that
    skipped the crossing serve cannot pass as a measurement;
  * a one-sided finite difference of the current against current_slopes;
  * --variant corner0 / selfcomp0 remove one piece of the complete fill.
    The ratio must LEAVE 1/eps_t and Z must move, or the observable cannot
    fail and the knob is unplumbed.

Writes nothing unless --out is given (probe31 overwrote its own bank).

Run (momwire at the commit under test, its extension built):
  python scratch/524-phase2/proto/probe41_production_slope.py \
      --ground soilA [--variant complete] [--out FILE.json] 1 2 3 2x2
"""

from __future__ import annotations

import argparse
import cmath
import json
import math
import subprocess
import time
import warnings
from pathlib import Path

import numpy as np

import momwire
from momwire import _crossing_fill
from momwire.bspline import BSplineSolver

C0 = 299792458.0
F7 = 7e6
WL7 = C0 / F7
GROUNDS = {"soilA": (13.0, 0.005), "eps1": (1.0, 0.0)}

# (breakpoints, segment counts) per arm. g1/g2 are probe18's GRADES verbatim;
# g3/g4 add one 4x-finer interface layer each, the same step g1 -> g2 took.
# "NxM" multiplies every count of rung N (uniform refinement, fixed grading).
GRADES = {
    "1": dict(
        below=([-2.0, -0.5, -0.1], [3, 2, 2]),
        above=([0.1, 0.5, 10.0], [2, 2, 19]),
    ),
    "2": dict(
        below=([-2.0, -0.5, -0.1, -0.025], [3, 2, 3, 2]),
        above=([0.025, 0.1, 0.5, 10.0], [2, 3, 2, 19]),
    ),
    "3": dict(
        below=([-2.0, -0.5, -0.1, -0.025, -0.00625], [3, 2, 3, 3, 2]),
        above=([0.00625, 0.025, 0.1, 0.5, 10.0], [2, 3, 3, 2, 19]),
    ),
    "4": dict(
        below=([-2.0, -0.5, -0.1, -0.025, -0.00625, -0.0015625], [3, 2, 3, 3, 3, 2]),
        above=([0.0015625, 0.00625, 0.025, 0.1, 0.5, 10.0], [2, 3, 3, 3, 2, 19]),
    ),
}
BELOW_LEN = 2.0
FEED_Z = 4.3333333333
A_WIRE = 0.001


def grade(level):
    if "x" in level:
        base, mult = level.split("x")
        g = GRADES[base]
        m = int(mult)
        return dict(
            below=(g["below"][0], [n * m for n in g["below"][1]]),
            above=(g["above"][0], [n * m for n in g["above"][1]]),
        )
    return GRADES[level]


def deck(level, ground_eps):
    g = grade(level)
    below_pts = np.array([(0.0, 0.0, z) for z in [*g["below"][0], 0.0]])
    above_pts = np.array([(0.0, 0.0, z) for z in [0.0, *g["above"][0]]])
    return dict(
        wires=[below_pts, above_pts],
        n_per_edge_per_wire=[g["below"][1], g["above"][1]],
        junctions=[[(0, "end"), (1, "start")]],
        feeds=[(1, FEED_Z, 1 + 0j)],
        wavelength=WL7,
        wire_radius=A_WIRE,
        ground_z=0.0,
        ground_eps=ground_eps,
        ground_model="sommerfeld",
    )


CALLS = {"cross": 0}


def install(variant):
    """Count crossing-serve entries; apply the negative-control variant."""
    orig_cross = _crossing_fill.cross_complete_block_split

    def counting_cross(*args, **kwargs):
        CALLS["cross"] += 1
        if variant == "corner0":
            kwargs["corner"] = False
        return orig_cross(*args, **kwargs)

    _crossing_fill.cross_complete_block_split = counting_cross

    if variant == "selfcomp0":
        orig_self = _crossing_fill.self_completions

        def zero_self(*args, **kwargs):
            return np.zeros_like(orig_self(*args, **kwargs))

        _crossing_fill.self_completions = zero_self


def cfmt(z):
    return f"{z.real:+.6f}{z.imag:+.6f}j"


def run(level, ground_eps):
    g = grade(level)
    s = BSplineSolver(**deck(level, ground_eps))
    CALLS["cross"] = 0
    t0 = time.time()
    with warnings.catch_warnings(record=True) as wlog:
        warnings.simplefilter("always")
        z, coeffs = s.compute_impedance()
    secs = time.time() - t0

    at_node = [np.array([BELOW_LEN]), np.array([0.0])]
    cur = s.currents_at_knots(coeffs, s_array=at_node)
    slo = s.current_slopes(coeffs, s_array=at_node)
    i_m, i_p = complex(cur[0][0]), complex(cur[1][0])
    d_m, d_p = complex(slo[0][0]), complex(slo[1][0])

    h_node = abs(g["below"][0][-1]) / g["below"][1][-1]
    step = h_node * 1e-4
    near = s.currents_at_knots(
        coeffs, s_array=[np.array([BELOW_LEN - step]), np.array([step])]
    )
    fd_m = (i_m - complex(near[0][0])) / step
    fd_p = (complex(near[1][0]) - i_p) / step

    target = 1.0 / s._buried_medium()[0]
    ratio = d_p / d_m
    rec = dict(
        level=level,
        ground_eps=list(ground_eps),
        n_seg=sum(g["below"][1]) + sum(g["above"][1]),
        h_node_mm=h_node * 1000,
        n_coeffs=int(np.asarray(coeffs).shape[0]),
        secs=round(secs, 1),
        crossing_calls=CALLS["cross"],
        z=str(complex(z)),
        I0_minus=str(i_m),
        I0_plus=str(i_p),
        kcl_rel=abs(i_p - i_m) / abs(i_p),
        dI_minus=str(d_m),
        dI_plus=str(d_p),
        fd_rel_minus=abs(fd_m - d_m) / abs(d_m),
        fd_rel_plus=abs(fd_p - d_p) / abs(d_p),
        ratio=str(ratio),
        ratio_abs=abs(ratio),
        ratio_deg=math.degrees(cmath.phase(ratio)),
        target=str(complex(target)),
        target_abs=abs(target),
        target_deg=math.degrees(cmath.phase(target)),
        rel_dist=abs(ratio - target) / abs(target),
        warnings=[str(w.message)[:160] for w in wlog],
    )
    print(
        f"g{level:>4} segs={rec['n_seg']:3d} h_node={h_node * 1000:6.2f}mm "
        f"{secs:5.1f}s cross={CALLS['cross']}  Z={cfmt(complex(z))}\n"
        f"      I0-={cfmt(i_m)} I0+={cfmt(i_p)} kcl_rel={rec['kcl_rel']:.1e}\n"
        f"      I'-={cfmt(d_m)} I'+={cfmt(d_p)}  "
        f"fd_rel -/+ {rec['fd_rel_minus']:.1e}/{rec['fd_rel_plus']:.1e}\n"
        f"      ratio={cfmt(ratio)} |{abs(ratio):.5f}| {rec['ratio_deg']:+7.2f}deg"
        f"   1/eps_t={cfmt(target)} |{abs(target):.5f}| "
        f"{rec['target_deg']:+6.2f}deg   dist={rec['rel_dist']:.4f}",
        flush=True,
    )
    return rec


def momwire_commit():
    pkg = Path(momwire.__file__).resolve().parent
    res = subprocess.run(
        ["git", "-C", str(pkg), "rev-parse", "--short", "HEAD"],
        capture_output=True,
        text=True,
        check=False,
    )
    return res.stdout.strip() or "unknown"


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--ground", choices=sorted(GROUNDS), default="soilA")
    ap.add_argument(
        "--variant", choices=["complete", "corner0", "selfcomp0"], default="complete"
    )
    ap.add_argument("--out", type=Path, default=None)
    ap.add_argument("levels", nargs="*", default=["1", "2", "3", "2x2"])
    args = ap.parse_args()

    install(args.variant)
    commit = momwire_commit()
    print(
        f"momwire {commit} ({Path(momwire.__file__).parent}); "
        f"ground={args.ground} variant={args.variant}",
        flush=True,
    )
    rungs = [run(lv, GROUNDS[args.ground]) for lv in args.levels]
    if args.out is not None:
        args.out.write_text(
            json.dumps(
                dict(
                    momwire_commit=commit,
                    ground=args.ground,
                    variant=args.variant,
                    rungs=rungs,
                ),
                indent=1,
            )
        )
        print(f"saved {args.out}")


if __name__ == "__main__":
    main()
