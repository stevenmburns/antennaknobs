"""A-2: the MP == field-form identity, re-run on the CROSSING deck.

Phase 0 pinned MP + boundary == shipped field form to 7.0e-5 off-contact —
but only on vertical-above x HORIZONTAL-below pairs. The crossing deck is
vertical x vertical, and its below arm's end at the interface makes the
source-side boundary terms live for the first time. This probe:

  1. captures the SHIPPED cross blocks t_ab (above obs x below src) and
     t_ba from a seeded solve (probe3-of-phase-0 interception pattern);
  2. builds mp_cross_block (spelling 'keep' == field form);
  3. reports relative agreement, split: interior below bases (0..3) vs
     the node value-1 basis (4), and the transpose identity.

Run (detached; ~2-4 min of table fill):
  .venv/bin/python scratch/524-phase2/proto/probe5_mp_identity.py
"""

from __future__ import annotations

import sys
from pathlib import Path

import numpy as np

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "567-phase0" / "proto"))
sys.path.insert(0, str(Path(__file__).resolve().parents[3] / "momwire" / "tests"))

import mp_cross  # noqa: E402
from momwire.bspline import BSplineSolver  # noqa: E402
from mp_cross import mp_cross_block  # noqa: E402
from probe1_baseline import crossing_deck, seeded  # noqa: E402

# The below arm ENDS exactly at the interface (z' = 0), which phase-0's
# strict "source strictly below" table guard refuses. The z' -> 0- limit is
# continuous (e^{-gamma|z'|} -> 1), so clamp the source depth to -1e-9 m for
# the end-evaluation calls only. Error introduced: O(gamma * 1e-9) ~ 1e-10.
_orig_mp_tables = mp_cross.mp_tables


def _mp_tables_clamped(eps_t, k_p, rho, z, zp, rtol=1e-10):
    zp = np.minimum(np.asarray(zp, dtype=np.float64), -1e-9)
    return _orig_mp_tables(eps_t, k_p, rho, z, zp, rtol=rtol)


mp_cross.mp_tables = _mp_tables_clamped


def main():
    s = seeded(crossing_deck(1))
    geom = s._build_geometry()
    below = s._below_segments(geom)
    b_seg = np.sort(np.nonzero(below)[0])
    a_seg = np.sort(np.nonzero(~below)[0])

    cap = {}
    orig = BSplineSolver._field_galerkin_block

    def wrap(self, supp_seg, polys, proj_fn, obs_idx, src_idx, *rest):
        out = orig(self, supp_seg, polys, proj_fn, obs_idx, src_idx, *rest)
        o = np.sort(np.asarray(obs_idx))
        sr = np.sort(np.asarray(src_idx))
        if np.array_equal(o, a_seg) and np.array_equal(sr, b_seg):
            cap["t_ab"] = np.array(out, copy=True)
        elif np.array_equal(o, b_seg) and np.array_equal(sr, a_seg):
            cap["t_ba"] = np.array(out, copy=True)
        return out

    BSplineSolver._field_galerkin_block = wrap
    try:
        z0, _ = s.compute_impedance()
    finally:
        BSplineSolver._field_galerkin_block = orig
    print(f"seeded naive solve reproduced: Z_in = {z0:.4f}")
    print(f"captured blocks: {sorted(cap.keys())}, shape {cap['t_ab'].shape}")

    mp = mp_cross_block(s, rtol=1e-10, boundary="keep")
    t_mp = mp["t_ab"]

    sh = cap["t_ab"]
    scale = max(np.abs(sh).max(), 1e-30)
    rel = np.abs(t_mp - sh) / scale
    below_bases = np.arange(0, 5)  # crossing deck: bases 0..4 on the arm
    interior = below_bases[:-1]
    node = below_bases[-1]
    print(f"|shipped t_ab| max {np.abs(sh).max():.4e}")
    print(f"identity rel (vs max |shipped|): overall max {rel.max():.3e}")
    print(
        f"  src interior below bases {interior.tolist()}: "
        f"max {rel[:, interior].max():.3e}"
    )
    print(f"  src node basis {node}: max {rel[:, node].max():.3e}")
    print(
        f"boundary pieces: |bnd_test| max {np.abs(mp['bnd_test']).max():.3e}, "
        f"|bnd_src_W| max {np.abs(mp['bnd_src_W']).max():.3e}"
    )
    tr = np.abs(cap["t_ba"] - sh.T).max() / scale
    print(f"shipped transpose identity |t_ba - t_ab^T|/scale: {tr:.3e}")

    res = HERE.parent / "results"
    res.mkdir(exist_ok=True)
    np.savez(
        res / "probe5-blocks.npz",
        shipped_ab=sh,
        shipped_ba=cap["t_ba"],
        mp_ab=t_mp,
        mp_main=mp["main"],
        mp_bnd_test=mp["bnd_test"],
        mp_bnd_src_W=mp["bnd_src_W"],
    )
    print("blocks saved to results/probe5-blocks.npz")


if __name__ == "__main__":
    main()
