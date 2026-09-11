"""#956 Phase B, gate 1's second half: does the on-axis term SCALE WITH THE RISE?

+0.4561 ohm on the 0.15 m deck is a number. The residual's signature is
"scales with the rise, no intercept" — flat in radial count, flat in radial
length, 2.1 -> 23.6 ohm as the hub goes 0.15 -> 1.2 m. So the on-axis dR has to
be laddered in the SAME variable before it can be called a piece of the same
term. If it tracks the rise it is; if it is flat in rise length it is a
different term and must not be netted against the residual.

The off-axis dR is carried beside it on every rung as the control that the
instrument has not started reporting something else.

One deck per rung, whole cross block, q = 6 — quadrature stability to four
digits was established on the 0.15 m deck across q = 6/12/24 (probe10), so the
ladder buys nothing here and the rung cost is the block.
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
    solve_with,
    solver_of,
)
from probe5_partition import basis_support  # noqa: E402
from probe8_substitute import on_axis  # noqa: E402

THR = 0.25


def rung(depth, workers):
    b = build(depth=depth)
    s = solver_of(b)
    geom, supp_seg, polys, a_idx, b_idx = parts(s)
    mw = momwire_block(s, geom, supp_seg, polys, a_idx, b_idx)
    z0, _ = solve_with(solver_of(b))

    t0 = time.time()
    obs_a, t_a, W_a = s._buried_nodes(geom, a_idx)
    obs_b, t_b, W_b = s._buried_nodes(geom, b_idx)
    proj = PO.make_proj(FREQ, *SOIL_A, workers=workers)
    ob = s._field_galerkin_block(
        supp_seg, polys, proj, a_idx, b_idx, obs_a, t_a, W_a, obs_b, t_b, W_b
    )
    dt = time.time() - t0
    out = Path(__file__).resolve().parent / "blocks"
    out.mkdir(exist_ok=True)
    np.save(out / f"oracle_rise_{depth}.npy", ob)
    np.save(out / f"mw_rise_{depth}.npy", mw)

    sup_a = basis_support(geom, supp_seg, a_idx, polys)
    sup_b = basis_support(geom, supp_seg, b_idx, polys)
    D = np.full(mw.shape, np.inf)
    AX = np.zeros(mw.shape, bool)
    for m in range(len(sup_a)):
        if not len(sup_a[m]):
            continue
        for n in range(len(sup_b)):
            if not len(sup_b[n]):
                continue
            D[m, n] = np.linalg.norm(
                sup_a[m][:, None, :] - sup_b[n][None, :, :], axis=-1
            ).min()
            AX[m, n] = on_axis(sup_a[m]) and on_axis(sup_b[n])

    def sub(mask):
        blk = mw.copy()
        blk[mask] = ob[mask]
        z, ncall = solve_with(solver_of(b), block=blk)
        assert ncall == 1
        return z.real - z0.real, int(mask.sum())

    far = np.isfinite(D) & (D >= THR)
    d_on, n_on = sub(far & AX)
    d_off, n_off = sub(far & ~AX)
    n_rise = int(
        np.count_nonzero(
            np.abs(np.asarray(geom["seg_l"])[b_idx][:, :2]).max(axis=1) < 1e-9
        )
    )
    print(
        f"  rise {depth:6.3f} m  segs {len(a_idx):3d}/{len(b_idx):3d}  "
        f"rise-segs {n_rise:2d}  R0 {z0.real:8.3f}  "
        f"ON-AXIS dR {d_on:+8.4f} ({n_on:4d})   "
        f"off-axis dR {d_off:+9.5f} ({n_off:5d})   [{dt / 60:.1f} min]"
    )
    sys.stdout.flush()
    return depth, d_on, d_off


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--depths", type=float, nargs="+", default=[0.075, 0.15, 0.30])
    ap.add_argument("--workers", type=int, default=7)
    args = ap.parse_args()
    print(f"on-axis / off-axis dR at separation >= {THR} m, q = 6")
    rows = [rung(d, args.workers) for d in args.depths]
    print("\nrise-length scaling of the ON-AXIS term:")
    for i in range(1, len(rows)):
        d0, a0, _ = rows[i - 1]
        d1, a1, _ = rows[i]
        if a0 and d0:
            p = np.log(abs(a1 / a0)) / np.log(d1 / d0)
            print(
                f"  {d0:.3f} -> {d1:.3f} m : dR {a0:+.4f} -> {a1:+.4f}  "
                f"ratio {a1 / a0:6.3f}  exponent {p:+.2f}"
            )
    print("  (the residual itself: 2.1 -> 23.6 ohm over 0.15 -> 1.2 m, ~d^1.1)")


if __name__ == "__main__":
    main()
