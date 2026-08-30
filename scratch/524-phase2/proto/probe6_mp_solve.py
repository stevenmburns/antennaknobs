"""A-2: full crossing solves with the MP cross block swapped in.

Uses the blocks probe5 computed (results/probe5-blocks.npz):
  mp_main     = MP block + source-side boundary terms (below-end at z'=0)
  mp_bnd_test = the above-side (contact) endpoint-charge term

Spelling grid = {A: main+bnd_test (field form), B: main (drop the above
endpoint charge)} x {none, V (continuity), VS (continuity + AGARD slope)}.
Both cross blocks are swapped: t_ab = spelling, t_ba = t_ab^T.

Run: .venv/bin/python scratch/524-phase2/proto/probe6_mp_solve.py
"""

from __future__ import annotations

import json
from pathlib import Path

import numpy as np

HERE = Path(__file__).resolve().parent
import sys  # noqa: E402

sys.path.insert(0, str(HERE))
sys.path.insert(0, str(Path(__file__).resolve().parents[3] / "momwire" / "tests"))

from momwire.bspline import BSplineSolver  # noqa: E402
from probe1_baseline import crossing_deck, seeded  # noqa: E402
from probe2_crossing import node_rows  # noqa: E402

ANCHOR_X1 = 74.761 - 57.730j


def solve(t_ab, rows):
    s = seeded(crossing_deck(1))
    geom = s._build_geometry()
    below = s._below_segments(geom)
    b_seg = np.sort(np.nonzero(below)[0])
    a_seg = np.sort(np.nonzero(~below)[0])
    t_ba = t_ab.T

    orig_blk = BSplineSolver._field_galerkin_block

    def wrap_blk(self, supp_seg, polys, proj_fn, obs_idx, src_idx, *rest):
        o = np.sort(np.asarray(obs_idx))
        sr = np.sort(np.asarray(src_idx))
        if np.array_equal(o, a_seg) and np.array_equal(sr, b_seg):
            return t_ab.copy()
        if np.array_equal(o, b_seg) and np.array_equal(sr, a_seg):
            return t_ba.copy()
        return orig_blk(self, supp_seg, polys, proj_fn, obs_idx, src_idx, *rest)

    orig_kcl = BSplineSolver._solve_with_kcl

    def wrap_kcl(self, Z, v, kcl_A, overwrite=False):
        if rows:
            add = np.stack(rows)
            kcl_A = np.vstack([kcl_A.astype(add.dtype), add])
        return orig_kcl(self, Z, v, kcl_A, overwrite=False)

    BSplineSolver._field_galerkin_block = wrap_blk
    BSplineSolver._solve_with_kcl = wrap_kcl
    try:
        z, _ = s.compute_impedance()
    finally:
        BSplineSolver._field_galerkin_block = orig_blk
        BSplineSolver._solve_with_kcl = orig_kcl
    return z


def main():
    d = np.load(HERE.parent / "results" / "probe5-blocks.npz")
    blocks = {
        "A_field": d["mp_main"] + d["mp_bnd_test"],
        "B_dropq": d["mp_main"],
    }

    s = seeded(crossing_deck(1))
    geom = s._build_geometry()
    row_v, der_a, der_b = node_rows(s, geom)
    eps_t, *_ = s._buried_medium()
    r = 1.0 / eps_t
    rowsets = {
        "none": [],
        "V": [row_v],
        "VS": [row_v, der_a - r * der_b],
    }

    out = {}
    for bname, t_ab in blocks.items():
        for rname, rows in rowsets.items():
            z = solve(t_ab, rows)
            miss = abs(z - ANCHOR_X1)
            key = f"{bname}+{rname}"
            out[key] = dict(z=f"{z:.4f}", miss_ohm=round(float(miss), 3))
            print(f"  {key:>14}: Z = {z:9.4f}   miss vs x1 = {miss:8.3f} ohm")

    (HERE.parent / "results" / "probe6-mp.json").write_text(json.dumps(out, indent=1))


if __name__ == "__main__":
    main()
