"""Session-lead independent review probe for momwire#553 U2 (blind).

Generated BEFORE the U2 builder's implementation was seen. Off-lattice
below/below composed-field references from the phase-0 prototype's
field_in_medium (gate G4c: 3.16e-4 vs empymod well-conditioned, 420x sign
margin). Deliberately odd (rho, z, z') values so they cannot coincide with
any golden lattice the builder commits.

At review: the U2 composition (direct + A_m*image + remainder through the
product machinery) must reproduce these to the same class of agreement the
builder pins against its own goldens.

Run: python scratch/553-arc/review-probe-u2.py  (from repo root, venv on)
"""

import json
import os
import sys

import numpy as np

sys.path.insert(
    0,
    os.path.join(
        os.path.dirname(os.path.abspath(__file__)), "..", "524-phase0", "proto"
    ),
)
from buried_proto import HalfSpace, field_in_medium  # noqa: E402

SOILS = {"A": (13.0, 0.005), "B": (20.0, 0.03), "C": (5.0, 0.001)}
FREQS = {"7MHz": 7.0e6, "21MHz": 21.0e6}

# (rho, phi, z_obs, z_src) — both below; odd values, off any 0.05/0.15 lattice.
POINTS = [
    (1.7, 0.0, -0.33, -0.08),
    (6.3, 0.7, -0.11, -0.13),
]
KINDS = ["HED", "VED"]

out = {
    "meta": {
        "written": "2026-08-22",
        "source": "field_in_medium (phase-0 prototype, G4c)",
    }
}
for s_id, (eps_r, sigma) in SOILS.items():
    for f_id, freq in FREQS.items():
        hs = HalfSpace(freq=freq, eps_r=eps_r, sigma=sigma)
        cell = {"k_m": [hs.km.real, hs.km.imag], "points": {}}
        for rho, phi, z, zp in POINTS:
            obs = np.array([rho * np.cos(phi), rho * np.sin(phi), z])
            for kind in KINDS:
                e, _rel, _q = field_in_medium(hs, obs, zp, kind, err=False)
                e = np.asarray(e, dtype=complex)
                cell["points"][f"{kind}_rho{rho}_z{z}_zp{zp}"] = [
                    [c.real, c.imag] for c in e
                ]
        out[f"{s_id}_{f_id}"] = cell

path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "review-probe-u2.json")
with open(path, "w") as fh:
    json.dump(out, fh, indent=1)
print("wrote", path)
for key in sorted(k for k in out if k != "meta"):
    p = out[key]["points"]
    name = next(iter(p))
    v = p[name]
    print(f"{key} {name}: Ex = {v[0][0]:+.6e}{v[0][1]:+.6e}j")
