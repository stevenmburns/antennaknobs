"""Session-lead independent review probe for momwire#553 U1.

Written BEFORE the U1 builder's implementation was seen (2026-08-22), so the
numbers here are independent of whatever the builder codes. Reference values
come from the phase-0 prototype's gated closed form `fs_field` (buried_proto,
gate G4a: 1.46e-9 vs empymod in a homogeneous complex-k whole space).

Emits: review-probe-u1.json — mutual impedances Z12 of unit-current Hertzian
element pairs immersed in an infinite medium with the SPEC soils' k_m, plus
the (eps_t, k_m) used. At review, the builder's widened bspline fill (two
short segments, prefactors composed as in gate G-U1-5) must CONVERGE to
these numbers as segments shorten; disagreement in the converged limit is a
formulation error on one side and must be resolved, not tolerated.

Z12 = -E1(r2) . dl2_hat * dl1 * dl2  with E1 = fs_field(C1, k_m, p1_hat, r2-r1)
(unit current, moment I*dl = dl1). Elemental lengths are carried as symbols
(dl1 = dl2 = 1 here): the JSON stores the COEFFICIENT, i.e. Z12 per unit
dl1*dl2 — the builder-side comparison divides its converged Z by its own
(dl1*dl2) before comparing.

Run: cd scratch/524-phase0/proto && python ../../553-arc/review-probe-u1.py
(needs buried_proto importable from cwd)
"""

import json
import os
import sys

import numpy as np

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "524-phase0", "proto"))
from buried_proto import HalfSpace, fs_field

SOILS = {"A": (13.0, 0.005), "B": (20.0, 0.03), "C": (5.0, 0.001)}
FREQS = {"7MHz": 7.0e6, "21MHz": 21.0e6}

# Geometries: (name, r1, p1_hat, r2, p2_hat). Chosen to exercise the full
# dyad: collinear (pure radial), broadside (pure transverse), skew (mixed),
# and a near cell (0.5 m) where the 1/R^3 near field dominates at 7 MHz.
GEOMS = [
    ("collinear_z_2m", [0, 0, 0], [0, 0, 1], [0, 0, 2.0], [0, 0, 1]),
    ("broadside_x_2m", [0, 0, 0], [0, 0, 1], [2.0, 0, 0], [0, 0, 1]),
    ("skew_1.5m", [0, 0, 0], [1, 0, 0], [1.0, 0.8, 0.6], [0, 0.6, 0.8]),
    ("near_broadside_0.5m", [0, 0, 0], [1, 0, 0], [0, 0.5, 0], [1, 0, 0]),
    ("far_collinear_x_3m", [0, 0, 0], [1, 0, 0], [3.0, 0, 0], [1, 0, 0]),
]

out = {
    "meta": {
        "written": "2026-08-22",
        "source": "fs_field (phase-0 prototype, gate G4a)",
    }
}
for s_id, (eps_r, sigma) in SOILS.items():
    for f_id, freq in FREQS.items():
        hs = HalfSpace(freq=freq, eps_r=eps_r, sigma=sigma)
        hs.assert_decay()
        cell = {
            "eps_t": [hs.eps_t.real, hs.eps_t.imag],
            "k_m": [hs.km.real, hs.km.imag],
            "pairs": {},
        }
        for name, r1, p1, r2, p2 in GEOMS:
            p1 = np.asarray(p1, float)
            p1 = p1 / np.linalg.norm(p1)
            p2 = np.asarray(p2, float)
            p2 = p2 / np.linalg.norm(p2)
            d = np.asarray(r2, float) - np.asarray(r1, float)
            e = fs_field(hs.C1, hs.km, p1, d)
            z12 = -complex(np.dot(e, p2))
            cell["pairs"][name] = [z12.real, z12.imag]
        out[f"{s_id}_{f_id}"] = cell

path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "review-probe-u1.json")
with open(path, "w") as fh:
    json.dump(out, fh, indent=1)
print(f"wrote {path}")
for key in sorted(k for k in out if k != "meta"):
    c = out[key]
    z = c["pairs"]["collinear_z_2m"]
    print(
        f"{key}: k_m = {c['k_m'][0]:+.5f}{c['k_m'][1]:+.5f}j   Z12(collinear 2m) = {z[0]:+.6e}{z[1]:+.6e}j"
    )
