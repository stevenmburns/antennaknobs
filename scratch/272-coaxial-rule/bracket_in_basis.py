"""The zero-noise upper bound on the coaxial rule's cost — momwire#272.

`measure_coaxial_rule.py` compares momwire against nec2c. That comparison has
a floor: on a straight wire, where momwire declines NOTHING and the true cost
is zero by construction, the cross-solver metric still reads 1.35 % at
Delta/a = 2. The effect being measured is the same size as that floor, so the
nec2c reading cannot settle the issue's 1 % question on its own.

This script removes the floor by never leaving momwire.

## The trick

`_ek_axis_groups` labels segments coaxial-and-equal-radius; only same-label
pairs get the extended kernel. Force it to return ONE label for everything and
the EK extends EVERY pair. Same solver, same mesh, same quadrature, same
feed -- the only thing that changed is the gate.

    bound = |Z(extend everything) - Z(coaxial only)| / |Z(coaxial only)|

Extending everything is strictly MORE than NEC's per-end gating does (NEC
extends some cross-arm pairs at a bend; this extends all pairs, everywhere).
So `bound` is an UPPER BOUND on what momwire's declined pairs could cost, and
the straight-wire control reads exactly 0.0000 % because there is nothing to
change there. Zero noise, by construction and confirmed numerically.

The bound is not tight -- it also extends far-apart pairs NEC would never
touch -- but the EK correction decays fast with separation, so the slack is
small, and a bound is all the 1 % question needs.

Run from the antennaknobs project root:

    .venv/bin/python scratch/272-coaxial-rule/bracket_in_basis.py
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import numpy as np

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

import momwire.bspline as bs  # noqa: E402
from measure_coaxial_rule import (  # noqa: E402
    DA_RUNGS,
    LAM,
    N_PER_ARM,
    REFINE_NS,
    REFINE_RADIUS,
    _radius_for,
    geometry,
)

_REAL_GROUPS = bs._ek_axis_groups


def _one_label(seg_l, seg_r, tangents, seg_a, tol=1e-6):
    """Every segment in one coaxial group -> the EK extends every pair."""
    return np.zeros(len(np.asarray(seg_l)), dtype=np.int64)


def z(kind: str, radius: float, n: int, extend_all: bool) -> complex:
    polylines, junctions, feed_wire, feed_arc, _arm = geometry(kind, n)
    bs._ek_axis_groups = _one_label if extend_all else _REAL_GROUPS
    try:
        zz, _ = bs.BSplineSolver(
            wires=polylines,
            n_per_edge_per_wire=[[n] * (len(p) - 1) for p in polylines],
            junctions=junctions,
            degree=2,
            wavelength=LAM,
            wire_radius=radius,
            feed_wire_index=feed_wire,
            feed_arclength=feed_arc,
            feed_model="segment",
            extended_kernel=True,
        ).compute_impedance()
    finally:
        bs._ek_axis_groups = _REAL_GROUPS
    return complex(zz)


def bound(kind: str, radius: float, n: int) -> float:
    z_coax = z(kind, radius, n, False)
    return abs(z(kind, radius, n, True) - z_coax) / abs(z_coax)


def main() -> int:
    radius_leg = []
    print("Leg A -- radius sweep, mesh fixed at %d segments/arm" % N_PER_ARM)
    print(f"{'deck':9s} {'D/a':>5s} {'a/lambda':>9s} {'upper bound':>12s}")
    for kind in ("straight", "bent", "k3"):
        _p, _j, _f, _fa, arm = geometry(kind)
        for da in DA_RUNGS:
            a = _radius_for(da, arm)
            b = bound(kind, a, N_PER_ARM)
            radius_leg.append(
                {
                    "geometry": kind,
                    "delta_over_a": da,
                    "radius_m": a,
                    "upper_bound_frac_of_z": b,
                }
            )
            print(f"{kind:9s} {da:5.1f} {a / LAM:9.6f} {100 * b:11.5f}%")

    refine_leg = []
    print(
        f"\nLeg B -- refinement, radius fixed at {REFINE_RADIUS:.6f} (a/lambda constant)"
    )
    print(f"{'deck':9s} {'n':>4s} {'h':>9s} {'D/a':>6s} {'upper bound':>12s}")
    for kind in ("straight", "bent", "k3"):
        for n in REFINE_NS + (31,):
            _p, _j, _f, _fa, arm = geometry(kind, n)
            h = arm / n
            b = bound(kind, REFINE_RADIUS, n)
            refine_leg.append(
                {
                    "geometry": kind,
                    "n_per_arm": n,
                    "h_m": h,
                    "delta_over_a": h / REFINE_RADIUS,
                    "upper_bound_frac_of_z": b,
                }
            )
            print(
                f"{kind:9s} {n:4d} {h:9.5f} {h / REFINE_RADIUS:6.2f} {100 * b:11.5f}%"
            )

    out = HERE / "bracket.json"
    out.write_text(
        json.dumps(
            {
                "issue": "momwire#272",
                "note": (
                    "upper_bound = |Z(EK extends every pair) - Z(EK coaxial "
                    "only)| / |Z(coaxial only)|, both from BSplineSolver with "
                    "only _ek_axis_groups swapped. Extending every pair is "
                    "strictly more than NEC's per-end gating, so this bounds "
                    "what the declined pairs can cost. The straight rows read "
                    "exactly zero: nothing is declined on a straight wire, so "
                    "there is no basis noise in this metric at all."
                ),
                "radius_leg": radius_leg,
                "refinement_leg": refine_leg,
            },
            indent=2,
        )
        + "\n"
    )
    print(f"\nwrote {out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
