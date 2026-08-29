"""Session-lead independent review probe for momwire#553 U3 (blind).

Off-lattice below->above transmitted-field references from the phase-0
prototype's field_transmitted (gates G4b: 3.0e-4 well-conditioned vs
empymod; G7: three-way E_x agreement to the engine's noise floor).
Odd (rho, z, z') values, z' chosen OFF any plausible log-spaced ladder
node, so the z'-interpolation is genuinely exercised.

Run: python scratch/553-arc/review-probe-u3.py  (repo root, venv on)
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
from buried_proto import HalfSpace, field_transmitted

SOILS = {"A": (13.0, 0.005), "B": (20.0, 0.03), "C": (5.0, 0.001)}
FREQS = {"7MHz": 7.0e6, "21MHz": 21.0e6}

# (rho, phi, z_obs>0, z_src<0): observer above, source below.
# phi != 0 exercises the full azimuth combination incl. E_phi^H (7d);
# z' = -0.037 and -0.61 sit off any {0.02, ...} log ladder's nodes.
POINTS = [
    (2.3, 0.6, 0.85, -0.037),
    (11.0, 2.1, 2.4, -0.61),
]
KINDS = ["HED", "VED"]

out = {
    "meta": {
        "written": "2026-08-22",
        "source": "field_transmitted (phase-0 prototype, G4b/G7)",
    }
}
for s_id, (eps_r, sigma) in SOILS.items():
    for f_id, freq in FREQS.items():
        hs = HalfSpace(freq=freq, eps_r=eps_r, sigma=sigma)
        cell = {"k_m": [hs.km.real, hs.km.imag], "points": {}}
        for rho, phi, z, zp in POINTS:
            obs = np.array([rho * np.cos(phi), rho * np.sin(phi), z])
            for kind in KINDS:
                e, _rel, _q = field_transmitted(hs, obs, zp, kind, err=False)
                e = np.asarray(e, dtype=complex)
                cell["points"][f"{kind}_rho{rho}_z{z}_zp{zp}"] = [
                    [c.real, c.imag] for c in e
                ]
        out[f"{s_id}_{f_id}"] = cell

path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "review-probe-u3.json")
with open(path, "w") as fh:
    json.dump(out, fh, indent=1)
print("wrote", path)
for key in sorted(k for k in out if k != "meta"):
    p = out[key]["points"]
    name = next(iter(p))
    v = p[name]
    print(f"{key} {name}: Ex = {v[0][0]:+.6e}{v[0][1]:+.6e}j")
