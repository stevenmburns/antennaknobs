"""#956: which entries carry Phase 1's +164.7 ohm?

The premise of the near-node unit was that including ALL THREE pair classes
among the node-touching set would let the free-end charges cancel as they do in
the real assembly. Phase 1 says otherwise: with self, adjacent AND touching-
support pairs excluded, dR is still +164.7 — the same figure probe8 got for
"on-axis pairs >= 0.1 m" months of reasoning ago. So the premise is falsified
and the question is which entries do it.
"""

import os
import sys

for _v in ("OMP_NUM_THREADS", "OPENBLAS_NUM_THREADS", "MKL_NUM_THREADS"):
    os.environ[_v] = "1"

import warnings  # noqa: E402
from pathlib import Path  # noqa: E402

import numpy as np  # noqa: E402

warnings.filterwarnings("ignore")
sys.path.insert(0, str(Path(__file__).resolve().parent))

from probe3_cross_block import build, parts, solver_of  # noqa: E402
from probe5_partition import basis_support  # noqa: E402
from probe15_assembled_gate import live_wings  # noqa: E402
from probe16_phase1 import axis_segs, solve_with_Z  # noqa: E402

Z_TOL = 1e-9
A = 5e-4


def main():
    b = build()
    s = solver_of(b)
    geom, supp_seg, polys, a_idx, b_idx = parts(s)
    Z = s._compute_Z_operator(geom, supp_seg, polys)
    Q = np.load(Path(__file__).resolve().parent / "blocks" / "phase1_Q_a0.0005_q1.npy")
    sup_a = basis_support(geom, supp_seg, a_idx, polys)
    sup_b = basis_support(geom, supp_seg, b_idx, polys)
    sup = [sup_a[m] if len(sup_a[m]) else sup_b[m] for m in range(len(sup_a))]
    above = np.array([len(sup_a[m]) > 0 for m in range(len(sup_a))])

    rise = set(map(int, axis_segs(geom, b_idx)))
    rad = set(map(int, axis_segs(geom, a_idx)))

    def touches(m):
        return len(sup[m]) and np.any(np.abs(sup[m][:, 2]) < Z_TOL)

    rows = [m for m in range(len(sup)) if touches(m)]
    cols = [
        m
        for m in range(len(sup))
        if len(sup[m])
        and all(t in (rad | rise) for t in live_wings(polys, supp_seg, m))
    ]
    recs = []
    for m in rows:
        wm = set(live_wings(polys, supp_seg, m))
        for n in cols:
            if m == n or (wm & set(live_wings(polys, supp_seg, n))):
                continue
            d = np.linalg.norm(sup[m][:, None, :] - sup[n][None, :, :], axis=-1).min()
            if d < A:
                continue
            diff = abs(-Q[m, n] - Z[m, n])
            recs.append((diff, d, m, n, above[m], above[n]))
    recs.sort(reverse=True)
    print(
        f"{'|-Q - Z|':>11} {'sep':>9} {'m':>4} {'n':>4} {'class':>13} "
        f"{'|Z|':>11} {'|-Q|/|Z|':>10}  dR alone"
    )
    z0, _ = solve_with_Z(b, lambda M: M)
    for diff, d, m, n, am, an in recs[:10]:
        cls = ("above", "below")[not am] + "x" + ("above", "below")[not an]
        msk = np.zeros_like(Z, bool)
        msk[m, n] = msk[n, m] = True
        z1, _ = solve_with_Z(b, lambda M, msk=msk: np.where(msk, -Q, M))
        print(
            f"{diff:11.4e} {d:9.4f} {m:4d} {n:4d} {cls:>13} "
            f"{abs(Z[m, n]):11.4e} {abs(Q[m, n]) / max(abs(Z[m, n]), 1e-300):10.4e} "
            f"{z1.real - z0.real:+10.4f}"
        )
        sys.stdout.flush()


if __name__ == "__main__":
    main()
