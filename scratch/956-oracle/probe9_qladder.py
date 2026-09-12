"""#956 Phase B gate 1: is the on-axis disagreement converged in MY quadrature?

probe8: substituting the oracle's ON-AXIS rise-x-radiator entries beyond 0.25 m
moves R by +0.46 ohm, while the 5832 off-axis entries move it by -0.0001. The
direction is the same as NEC-5's, which makes it a finding worth having — but
only if it is not my own quadrature error.

It might be. Those pairs are COLLINEAR with the radiator's own 1.2 m segments
against a rise 0.85 m away, so h/separation ~ 1.4, and that is precisely the
regime momwire#1004 measured the calibrated Gauss order to under-resolve. My
oracle assembles on the buried-field rule's q = 6 nodes; momwire's crossing
fill uses its own graded `_NEAR_Q`/`_FAR_Q` axes and is not affected the same
way. So a 9-21 % per-entry gap could be MINE.

The sub-block is 37x cheaper than the whole block (the rise is 6 below
segments against 222), so the ladder is minutes rather than hours. `q_factor`
is momwire#1004's own knob, which is what makes the rungs exact multiples of
the shipped order rather than a second quadrature spelling.
"""

import argparse
import sys
import time
import warnings
from pathlib import Path

import numpy as np

warnings.filterwarnings("ignore")
sys.path.insert(0, str(Path(__file__).resolve().parent))

import proj_oracle as PO  # noqa: E402
from probe3_cross_block import (  # noqa: E402
    FREQ,
    SOIL_A,
    build,
    momwire_block,
    parts,
    solver_of,
)


def axis_segments(geom, idx):
    """Segments in `idx` that lie on the x = y = 0 axis — the rise, and the
    radiator/feed above it."""
    seg_l = np.asarray(geom["seg_l"])[idx]
    seg_r = np.asarray(geom["seg_r"])[idx]
    on = (np.abs(seg_l[:, :2]).max(axis=1) < 1e-9) & (
        np.abs(seg_r[:, :2]).max(axis=1) < 1e-9
    )
    return idx[on]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--q-factors", type=int, nargs="+", default=[1, 2, 4])
    ap.add_argument("--workers", type=int, default=7)
    args = ap.parse_args()

    b = build()
    s = solver_of(b)
    geom, supp_seg, polys, a_idx, b_idx = parts(s)
    aa = axis_segments(geom, a_idx)
    bb = axis_segments(geom, b_idx)
    print(
        f"on-axis segments: above {len(aa)} of {len(a_idx)}, "
        f"below {len(bb)} of {len(b_idx)}"
    )
    mw_full = momwire_block(s, geom, supp_seg, polys, a_idx, b_idx)

    prev = None
    for qf in args.q_factors:
        obs_a, t_a, W_a = s._buried_nodes(geom, aa, q_factor=qf)
        obs_b, t_b, W_b = s._buried_nodes(geom, bb, q_factor=qf)
        proj = PO.make_proj(FREQ, *SOIL_A, workers=args.workers)
        t0 = time.time()
        blk = s._field_galerkin_block(
            supp_seg, polys, proj, aa, bb, obs_a, t_a, W_a, obs_b, t_b, W_b
        )
        dt = time.time() - t0
        np.save(Path(__file__).resolve().parent / "blocks" / f"axis_q{qf}.npy", blk)
        live = np.abs(blk) > 1e-9 * np.abs(blk).max()
        sc = float(np.abs(mw_full[live]).max()) if live.any() else 1.0
        gap = float(np.abs(blk[live] - mw_full[live]).max() / sc)
        med = float(
            np.median(
                np.abs(blk[live] - mw_full[live])
                / np.maximum(np.abs(mw_full[live]), 1e-300)
            )
        )
        line = (
            f"  q_factor {qf:2d} (q={qf * s._n_qp_buried_field():3d})  "
            f"{dt / 60:6.2f} min  live {int(live.sum()):5d}  "
            f"worst-vs-momwire {gap:.4e}  median {med:.4e}"
        )
        if prev is not None:
            d = float(np.abs(blk - prev).max() / max(np.abs(prev).max(), 1e-300))
            line += f"   self-convergence vs previous rung {d:.4e}"
        print(line)
        sys.stdout.flush()
        prev = blk


if __name__ == "__main__":
    main()
