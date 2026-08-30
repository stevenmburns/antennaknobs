"""A-2: the B_dropq+none spelling down the mesh ladder.

Builds the MP cross block at segment multiplier `mult` (odd — feed centre
preserved, the phase-0 ladder rule) with the z'=0 clamp, solves with both
cross blocks swapped (t_ba = t_ab^T), no constraint rows, and scores
against the engine's same-rung print.

Run (detached; table fill scales with pair count):
  .venv/bin/python scratch/524-phase2/proto/probe7_ladder.py 3
"""

from __future__ import annotations

import json
import sys
import time
from pathlib import Path

import numpy as np

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "567-phase0" / "proto"))
sys.path.insert(0, str(Path(__file__).resolve().parents[3] / "momwire" / "tests"))

import mp_cross  # noqa: E402
from momwire.bspline import BSplineSolver  # noqa: E402
from probe1_baseline import LADDER, crossing_deck, seeded  # noqa: E402

_orig_mp_tables = mp_cross.mp_tables


def _mp_tables_clamped(eps_t, k_p, rho, z, zp, rtol=1e-10):
    zp = np.minimum(np.asarray(zp, dtype=np.float64), -1e-9)
    return _orig_mp_tables(eps_t, k_p, rho, z, zp, rtol=rtol)


mp_cross.mp_tables = _mp_tables_clamped


def main():
    mult = int(sys.argv[1]) if len(sys.argv) > 1 else 3
    ref = LADDER[mult]

    s = seeded(crossing_deck(mult))
    t0 = time.time()
    mp = mp_cross.mp_cross_block(s, rtol=1e-10, boundary="drop")
    print(f"x{mult}: MP block built in {time.time() - t0:.0f}s")
    t_ab = mp["main"]  # main + bnd_src_W; above endpoint charge dropped
    t_ba = t_ab.T

    geom = s._build_geometry()
    below = s._below_segments(geom)
    b_seg = np.sort(np.nonzero(below)[0])
    a_seg = np.sort(np.nonzero(~below)[0])

    orig_blk = BSplineSolver._field_galerkin_block

    def wrap_blk(self, supp_seg, polys, proj_fn, obs_idx, src_idx, *rest):
        o = np.sort(np.asarray(obs_idx))
        sr = np.sort(np.asarray(src_idx))
        if np.array_equal(o, a_seg) and np.array_equal(sr, b_seg):
            return t_ab.copy()
        if np.array_equal(o, b_seg) and np.array_equal(sr, a_seg):
            return t_ba.copy()
        return orig_blk(self, supp_seg, polys, proj_fn, obs_idx, src_idx, *rest)

    BSplineSolver._field_galerkin_block = wrap_blk
    try:
        t0 = time.time()
        z, _ = s.compute_impedance()
        secs = time.time() - t0
    finally:
        BSplineSolver._field_galerkin_block = orig_blk

    miss = abs(z - ref)
    print(
        f"x{mult}: Z = {z:.4f}   engine(x{mult}) = {ref:.4f}   "
        f"miss = {miss:.3f} ohm   ({secs:.0f}s)"
    )
    res = HERE.parent / "results"
    out = {}
    fp = res / "probe7-ladder.json"
    if fp.exists():
        out = json.loads(fp.read_text())
    out[f"x{mult}"] = dict(
        z=f"{z:.4f}", ref=f"{ref:.4f}", miss_ohm=round(float(miss), 3)
    )
    fp.write_text(json.dumps(out, indent=1))


if __name__ == "__main__":
    main()
