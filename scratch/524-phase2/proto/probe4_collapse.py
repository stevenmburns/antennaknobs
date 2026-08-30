"""A-2 P0: the eps~ -> 1 collapse of the crossing deck.

With eps~ = 1 the interface vanishes physically: the seeded crossing solve
(BELOW, ABOVE media, buried code path) must reproduce the FREE-SPACE solve
of the same bonded 12 m wire. Phase 0 measured the contact basis's
cross-medium entries 2.5 RELATIVE off at eps~ = 1 while every other basis
sat at 1e-8 — this runs the same audit on the crossing deck, at Z_in level
and at matrix level (row-wise relative error), naming WHICH bases carry it.

NOTE the collapse is constitutionally blind to W_T (phase 0) — a pass here
is wiring, not agreement; a fail here is a real defect.

Run: .venv/bin/python scratch/524-phase2/proto/probe4_collapse.py
"""

from __future__ import annotations

import sys
from pathlib import Path

import numpy as np

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
sys.path.insert(0, str(Path(__file__).resolve().parents[3] / "momwire" / "tests"))

from momwire.bspline import BSplineSolver  # noqa: E402
from probe1_baseline import crossing_deck, seeded  # noqa: E402

EPS_ONE = (1.0, 1e-30)


def capture_Z(s):
    orig = BSplineSolver._solve_with_kcl
    cap = {}

    def wrap(self, Z, v, kcl_A, overwrite=False):
        cap["Z"] = Z.copy()
        cap["v"] = np.array(v, copy=True)
        return orig(self, Z, v, kcl_A, overwrite=False)

    BSplineSolver._solve_with_kcl = wrap
    try:
        z, _ = s.compute_impedance()
    finally:
        BSplineSolver._solve_with_kcl = orig
    return z, cap["Z"], cap["v"]


def main():
    # Seeded crossing solve at eps~ = 1
    kw = crossing_deck(1)
    kw["ground_eps"] = EPS_ONE
    z_x, Z_x, v_x = capture_Z(seeded(kw))

    # Free-space reference: same wires, same junction, no ground
    kw_f = crossing_deck(1)
    for key in ("ground_z", "ground_eps", "ground_model"):
        kw_f.pop(key, None)
    z_f, Z_f, v_f = capture_Z(BSplineSolver(**kw_f))

    print(f"eps~=1 seeded crossing: Z_in = {z_x:.4f}")
    print(f"free-space reference  : Z_in = {z_f:.4f}")
    print(f"Z_in collapse miss: {abs(z_x - z_f):.4f} ohm")

    if Z_x.shape != Z_f.shape:
        print(
            f"SHAPE MISMATCH: {Z_x.shape} vs {Z_f.shape} — basis sets differ "
            "(free end drops vs junction keeps); collapse audit needs matched "
            "dof sets"
        )
        return
    dv = np.abs(v_x - v_f).max()
    scale = np.abs(Z_f)
    denom = np.where(scale > 1e-12, scale, 1.0)
    rel = np.abs(Z_x - Z_f) / denom
    print(
        f"|v| max diff {dv:.2e};  matrix rel err: median {np.median(rel):.2e}, "
        f"max {rel.max():.2e} at {np.unravel_index(rel.argmax(), rel.shape)}"
    )
    row_worst = rel.max(axis=1)
    bad = np.argsort(row_worst)[::-1][:6]
    for i in bad:
        print(f"  row {i:2d}: worst rel {row_worst[i]:.3e}")


if __name__ == "__main__":
    main()
