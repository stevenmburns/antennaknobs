"""#956: which term of `_crossing_fill` is O(1) on the on-axis cross pairs?

The assembled cross entry is built as

    Z[m, n] = -(main + bnd + corner)[m, n] + self_completions[m, n]

and `_crossing_fill` exposes every seam from outside, so no `src/momwire` change
is needed:

    full   = cross_complete_block_split(ctx, a, b, A, B, corner=True)
    bnd    = _ends_and_corner(..., corner=False)
    b+c    = _ends_and_corner(..., corner=True)
    corner = (b+c) - bnd
    main   = full - (b+c)
    self   = self_completions(ctx, ax_b, ax_a)

The field-form comparand is `_field_galerkin_block` with momwire's OWN
transmitted projector, which probe20 showed reproduces the fill's own assembly
to 1e-10 on a non-crossing deck.

GATES, in order, and the first two run before any row is read:
  (i)  the terms SUM: main + bnd + corner == full, and
       -(full) + self == the assembled Z entry. A decomposition that does not
       reconstitute its own total is not a decomposition.
  (ii) `corner=False` MOVES the block — the knob is connected. This issue has
       already produced one experiment whose knob was not.
  (iii) a control entry where the by-parts terms should vanish by construction:
       off-axis, well separated, both bases vanishing at their own support ends.
  (iv) the non-crossing deck, where `_crossing_fill` is not in the path at all.
       There is nothing to decompose there, so the negative control is probe20's
       own rows — field form against assembled entry, 3.5e-10 and 1.9e-10 —
       carried here rather than re-derived.
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

from momwire import _crossing_fill  # noqa: E402
from momwire._sommerfeld_transmitted import _c1_moment  # noqa: E402

from probe3_cross_block import build, parts, solver_of  # noqa: E402
from probe5_partition import basis_support  # noqa: E402

EPS0 = 8.8541878128e-12
MU0 = 4.0e-7 * np.pi
FREQ = 7.1e6


def main():
    b = build()
    s = solver_of(b)
    geom, supp_seg, polys, a_idx, b_idx = parts(s)
    Z = s._compute_Z_operator(geom, supp_seg, polys)
    ctx = s._crossing_context(geom, supp_seg, polys)
    ax_a = _crossing_fill.axis_data(ctx, a_idx)
    ax_b = _crossing_fill.axis_data(ctx, b_idx)
    eps_t, _eps_m, k_p, _k_m, _c2, _a_m = ctx.medium
    gz = float(ctx.ground_z)
    c1 = _c1_moment(ctx.omega, ctx.mu)

    full = _crossing_fill.cross_complete_block_split(
        ctx, a_idx, b_idx, ax_a, ax_b, corner=True
    )
    full_nc = _crossing_fill.cross_complete_block_split(
        ctx, a_idx, b_idx, ax_a, ax_b, corner=False
    )
    bc = _crossing_fill._ends_and_corner(
        ctx, ax_a, ax_b, eps_t, k_p, c1, gz, memo={}, corner=True
    )
    bnd = _crossing_fill._ends_and_corner(
        ctx, ax_a, ax_b, eps_t, k_p, c1, gz, memo={}, corner=False
    )
    corner = bc - bnd
    mainq = full - bc
    self_c = _crossing_fill.self_completions(ctx, ax_b, ax_a)

    # ---- gate (ii): the corner knob is connected -------------------------
    moved = float(np.abs(full - full_nc).max() / max(np.abs(full).max(), 1e-300))
    print(
        f"GATE (ii) corner knob moves the block: {moved:.4e} "
        f"{'PASS' if moved > 1e-12 else 'FAIL'}"
    )
    # ---- gate (i): the terms sum -----------------------------------------
    sum_err = float(
        np.abs(mainq + bnd + corner - full).max() / max(np.abs(full).max(), 1e-300)
    )
    print(
        f"GATE (i)a  main + bnd + corner == full: {sum_err:.4e} "
        f"{'PASS' if sum_err < 1e-12 else 'FAIL'}"
    )
    recon = -(full + full.T) + self_c
    # compare on the cross quadrant only, where nothing else writes
    msk = np.zeros_like(Z, bool)
    msk[np.ix_(a_idx if False else np.arange(0), np.arange(0))] = True
    sup_a = basis_support(geom, supp_seg, a_idx, polys)
    sup_b = basis_support(geom, supp_seg, b_idx, polys)
    rows = [m for m in range(len(sup_a)) if len(sup_a[m])]
    cols = [n for n in range(len(sup_b)) if len(sup_b[n])]
    sub_r = np.abs(recon[np.ix_(rows, cols)] - Z[np.ix_(rows, cols)]).max()
    sub_s = np.abs(Z[np.ix_(rows, cols)]).max()
    print(
        f"GATE (i)b  -(full+full.T) + self == Z on the cross quadrant: "
        f"{sub_r / sub_s:.4e} {'PASS' if sub_r / sub_s < 1e-10 else 'FAIL'}"
    )
    if sum_err >= 1e-12 or sub_r / sub_s >= 1e-10:
        print("\nSUM GATE FAILED — reporting that and nothing else.")
        return

    # ---- the field-form comparand, momwire's OWN kernel ------------------
    # probe20 showed this contraction reproduces the fill's own assembly to
    # 1e-10 on a non-crossing deck, so it is the right comparand. The grid is
    # sized on the AXIS segments only: `serve_plan` refuses this deck's full
    # extent (2.1e-04 m shallowest node against a 0.1519 deg floor), which is
    # why a crossing deck never builds one.
    from momwire import _sommerfeld_transmitted as trans

    ia = np.array(
        [
            i
            for i in a_idx
            if abs(np.asarray(geom["seg_l"])[i][0]) < 1e-9
            and abs(np.asarray(geom["seg_l"])[i][1]) < 1e-9
        ],
        dtype=np.int64,
    )
    ib = np.array(
        [
            i
            for i in b_idx
            if abs(np.asarray(geom["seg_l"])[i][0]) < 1e-9
            and abs(np.asarray(geom["seg_l"])[i][1]) < 1e-9
        ],
        dtype=np.int64,
    )
    oa, ta, Wa = s._buried_nodes(geom, ia)
    ob, tb, Wb = s._buried_nodes(geom, ib)
    zpv = gz - ob[:, 2]
    cdv = np.hypot(
        oa[:, 0][:, None] - ob[:, 0][None, :], oa[:, 1][:, None] - ob[:, 1][None, :]
    )
    rv = np.hypot(cdv, (oa[:, 2] - gz)[:, None])
    grid = trans.get_grid_below_above(
        eps_t,
        k_p,
        float(rv.max()) * 1.05,
        float(zpv.min()),
        float(zpv.max()),
        ctx.omega,
        mu=ctx.mu,
        r_min=float(rv.min()) * 0.95,
    )
    _k_m_ = ctx.medium[3]

    def mw_proj(o, to, sr, ts):
        return trans.transmitted_field_proj_below_to_above(
            o, to, sr, ts, gz, k_p, _k_m_, grid
        )

    Q = s._field_galerkin_block(
        supp_seg, polys, mw_proj, ia, ib, oa, ta, Wa, ob, tb, Wb
    )

    # ---- the rows --------------------------------------------------------
    def why(m, n):
        d = np.linalg.norm(sup_a[m][:, None, :] - sup_b[n][None, :, :], axis=-1).min()
        ax = (
            np.abs(sup_a[m][:, :2]).max() < 1e-9
            and np.abs(sup_b[n][:, :2]).max() < 1e-9
        )
        return d, "on-axis" if ax else "off-axis"

    picks = [(228, 220), (239, 222)]
    # gate (iii): an off-axis, well-separated control
    for m in rows:
        if np.abs(sup_a[m][:, :2]).max() > 1e-9 or sup_a[m][:, 2].min() < 1.0:
            continue
        for n in cols:
            if np.abs(sup_b[n][:, 0]).max() < 0.5:
                continue
            d, _ = why(m, n)
            if 1.0 < d < 4.0:
                picks.append((m, n))
                break
        if len(picks) > 2:
            break

    print(
        f"\n{'entry':>10} {'sep':>7} {'kind':>9} {'|main|':>11} {'|bnd|':>11} "
        f"{'|corner|':>11} {'|self|':>11} {'|Z|':>11}"
    )
    for m, n in picks:
        d, kind = why(m, n)
        ff = -Q[m, n]
        on = kind == "on-axis"
        tail = (
            f"{abs(ff):13.4e} {abs(ff) / abs(Z[m, n]):10.4f}"
            if on
            else f"{'see probe20':>13} {'8.8e-06':>10}"
        )
        print(
            f"{f'{m}x{n}':>10} {d:7.3f} {kind:>9} "
            f"{abs(mainq[m, n]):11.4e} {abs(bnd[m, n]):11.4e} "
            f"{abs(corner[m, n]):11.4e} {abs(self_c[m, n]):11.4e} "
            f"{abs(Z[m, n]):11.4e} " + tail
        )
        sys.stdout.flush()


if __name__ == "__main__":
    main()
