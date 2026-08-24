"""The right referee: two-conductor gap capacitance at the feed node.

Conductor A: wire 1 above the feed (20,-40,300)->(20,-40,20), 280 m.
Conductor B: wire 1 below the feed (20 m) + the whole closed loop (300 m).
Maxwell capacitance matrix from two unit-potential solves; the gap sees
C_gap = (C11*C22 - C12^2) / (C11 + C22 + 2*C12).
"""

import numpy as np

EPS0 = 8.8541878128e-12
A = 0.005
COND_A = [((20, -40, 300), (20, -40, 20), 280.0)]
COND_B = [
    ((20, -40, 20), (20, -40, 0), 20.0),
    ((40, -40, 0), (40, 40, 0), 80.0),
    ((40, 40, 0), (-40, 40, 0), 80.0),
    ((-40, 40, 0), (-40, -40, 0), 80.0),
    ((-40, -40, 0), (20, -40, 0), 60.0),
    ((20, -40, 0), (40, -40, 0), 20.0),
]


def mesh(conds, seg_len):
    S, E, owner = [], [], []
    for ci, group in enumerate(conds):
        for a3, b3, L in group:
            n = max(1, round(L / seg_len))
            a3, b3 = np.array(a3, float), np.array(b3, float)
            for i in range(n):
                S.append(a3 + (b3 - a3) * i / n)
                E.append(a3 + (b3 - a3) * (i + 1) / n)
                owner.append(ci)
    return np.array(S), np.array(E), np.array(owner)


def cap_matrix(seg_len):
    S, E, owner = mesh((COND_A, COND_B), seg_len)
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
    d1 = obs[:, None, :] - S[None, :, :]
    d2 = obs[:, None, :] - E[None, :, :]
    r1 = np.linalg.norm(d1, axis=2)
    r2 = np.linalg.norm(d2, axis=2)
    Lm = L[None, :]
    P = np.log((r1 + r2 + Lm) / (np.maximum(r1 + r2 - Lm, 1e-30))) / (4 * np.pi * EPS0)
    C = np.zeros((2, 2))
    for j, v in enumerate(
        (np.where(owner == 0, 1.0, 0.0), np.where(owner == 1, 1.0, 0.0))
    ):
        q = np.linalg.solve(P, v)
        C[0, j] = np.sum((q * L)[owner == 0])
        C[1, j] = np.sum((q * L)[owner == 1])
    return C, len(S)


for sl in (4.0, 2.0, 1.0, 0.5, 0.25):
    C, n = cap_matrix(sl)
    cg = (C[0, 0] * C[1, 1] - C[0, 1] * C[1, 0]) / (
        C[0, 0] + C[1, 1] + C[0, 1] + C[1, 0]
    )
    X = -1 / (2 * np.pi * 500 * cg)
    print(
        f"seg {sl:5.2f} m  N={n:5d}  C_gap = {cg * 1e12:8.3f} pF   X(500 Hz) = {X / 1e3:9.3f} kOhm"
    )
