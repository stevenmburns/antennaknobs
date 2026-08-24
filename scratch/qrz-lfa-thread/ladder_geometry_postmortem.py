"""momwire#518 postmortem (2026-08-21): the "bspline ~2% gap-capacitance bias"
was a GEOMETRY artifact of the ladder script, not a solver defect.

The overnight ladder's bs1/bs2 models omitted wire 6 (the 20 m stub
(20,-40,0)->(40,-40,0) that closes the loop's bottom side to the vertical's
base) and drove the gap as a node gap on a wire split at z=20.  Razor
auto-detects junctions from the full wire list (its k=1 refusal of the
1-segment wire 6 proves wire 6 was present in ITS model), so the two
families solved DIFFERENT geometries -- hence two clean first-order limits
1.9 % apart, mesh-flat, immune to EK/enrichment knobs.

Three-way verification, all reproduced by this script:
  1. bs1/bs2 WITHOUT wire 6 (split + node gap) reproduce the recorded
     ladder at every rung to <= 0.05 %:
        bs1: -378.857/-378.566/-378.376/-378.248  (rec: -378.890/-378.594/-378.369/-378.200)
        bs2: -378.423/-378.296/-378.201/-378.129  (rec: -378.444/-378.418/-378.300/-378.036)
  2. The SAME config with wire 6 restored converges onto the electrostatic
     referee: bs1 -370.809, bs2 -370.692 at k=8 (referee: -370.5); bs2 at
     Roy's own mesh = -370.904 kOhm == the seam's printed 1.0910 A.
  3. The referee itself, re-run on the no-wire-6 geometry, certifies the
     "biased" number: C_gap = 841.6 pF -> X = -378.2 kOhm.

So: NEC-5, razor, bs1, bs2 and the referee all agree on the full geometry
(-370.5 family); bs1/bs2 and the referee also agree on the stub-less
geometry (-378 family).  There is no basis-family bias on this model.
"""

import numpy as np
from momwire.bspline import BSplineSolver

C0 = 299792458.0
WL = C0 / 500.0
EPS0 = 8.8541878128e-12
A = 0.005

SPLIT_WIRES = [
    [(20, -40, 0), (20, -40, 20)],
    [(20, -40, 20), (20, -40, 300)],
    [(40, -40, 0), (40, 40, 0)],
    [(40, 40, 0), (-40, 40, 0)],
    [(-40, 40, 0), (-40, -40, 0)],
    [(-40, -40, 0), (20, -40, 0)],
    [(20, -40, 0), (40, -40, 0)],  # wire 6, the stub
]
SPLIT_NSEG = [1, 14, 4, 4, 4, 3, 1]
J_FULL = [
    [(0, "end"), (1, "start")],
    [(0, "start"), (5, "end"), (6, "start")],
    [(6, "end"), (2, "start")],
    [(2, "end"), (3, "start")],
    [(3, "end"), (4, "start")],
    [(4, "end"), (5, "start")],
]
J_NOW6 = [
    [(0, "end"), (1, "start")],
    [(0, "start"), (5, "end")],
    [(2, "end"), (3, "start")],
    [(3, "end"), (4, "start")],
    [(4, "end"), (5, "start")],
]


def z_bs(k, degree, with_w6):
    n = len(SPLIT_WIRES) if with_w6 else len(SPLIT_WIRES) - 1
    s = BSplineSolver(
        wires=[np.array(w, float) for w in SPLIT_WIRES[:n]],
        n_per_edge_per_wire=[[m * k] for m in SPLIT_NSEG[:n]],
        feeds=[],
        node_gaps=[(0, "end", 1.0 + 0j)],
        junctions=J_FULL if with_w6 else J_NOW6,
        wavelength=WL,
        wire_radius=0.005,
        degree=degree,
    )
    zz, _ = s.compute_impedance()
    return complex(np.atleast_1d(zz)[0])


def referee_cgap(with_w6, seg_len=0.5):
    CA = [((20, -40, 300), (20, -40, 20), 280.0)]
    CB = [
        ((20, -40, 20), (20, -40, 0), 20.0),
        ((40, -40, 0), (40, 40, 0), 80.0),
        ((40, 40, 0), (-40, 40, 0), 80.0),
        ((-40, 40, 0), (-40, -40, 0), 80.0),
        ((-40, -40, 0), (20, -40, 0), 60.0),
    ]
    if with_w6:
        CB.append(((20, -40, 0), (40, -40, 0), 20.0))
    S, E, owner = [], [], []
    for ci, group in enumerate((CA, CB)):
        for a3, b3, L in group:
            n = max(1, round(L / seg_len))
            a3, b3 = np.array(a3, float), np.array(b3, float)
            for i in range(n):
                S.append(a3 + (b3 - a3) * i / n)
                E.append(a3 + (b3 - a3) * (i + 1) / n)
                owner.append(ci)
    S, E, owner = np.array(S), np.array(E), np.array(owner)
    mids = 0.5 * (S + E)
    tang = E - S
    L = np.linalg.norm(tang, axis=1)
    that = tang / L[:, None]
    ref = np.where(
        np.abs(that[:, 2:3]) < 0.9, np.array([0, 0, 1.0]), np.array([1.0, 0, 0])
    )
    perp = np.cross(that, ref)
    perp /= np.linalg.norm(perp, axis=1)[:, None]
    obs = mids + A * perp
    r1 = np.linalg.norm(obs[:, None, :] - S[None, :, :], axis=2)
    r2 = np.linalg.norm(obs[:, None, :] - E[None, :, :], axis=2)
    P = np.log((r1 + r2 + L[None, :]) / np.maximum(r1 + r2 - L[None, :], 1e-30)) / (
        4 * np.pi * EPS0
    )
    C = np.zeros((2, 2))
    for j, v in enumerate(
        (np.where(owner == 0, 1.0, 0.0), np.where(owner == 1, 1.0, 0.0))
    ):
        q = np.linalg.solve(P, v)
        C[0, j] = np.sum((q * L)[owner == 0])
        C[1, j] = np.sum((q * L)[owner == 1])
    return (C[0, 0] * C[1, 1] - C[0, 1] * C[1, 0]) / (
        C[0, 0] + C[1, 1] + C[0, 1] + C[1, 0]
    )


if __name__ == "__main__":
    rec = {
        1: (-378.890, -378.444),
        2: (-378.594, -378.418),
        4: (-378.369, -378.300),
        8: (-378.200, -378.036),
    }
    print("bs WITHOUT wire 6 (the ladder's geometry) vs recorded ladder:")
    for k in (1, 2, 4, 8):
        z1, z2 = z_bs(k, 1, False), z_bs(k, 2, False)
        print(
            f"  k={k}: bs1 {z1.imag / 1e3:9.3f}  bs2 {z2.imag / 1e3:9.3f}"
            f"   (rec {rec[k][0]:.3f} / {rec[k][1]:.3f})"
        )
    print("same config WITH wire 6 (referee limit -370.5):")
    for k in (1, 2, 4, 8):
        z1, z2 = z_bs(k, 1, True), z_bs(k, 2, True)
        print(f"  k={k}: bs1 {z1.imag / 1e3:9.3f}  bs2 {z2.imag / 1e3:9.3f}")
    for w6 in (True, False):
        cg = referee_cgap(w6)
        print(
            f"referee {'with' if w6 else 'without'} wire 6: "
            f"C_gap = {cg * 1e12:8.3f} pF   X = {-1 / (2 * np.pi * 500 * cg) / 1e3:9.3f} kOhm"
        )
