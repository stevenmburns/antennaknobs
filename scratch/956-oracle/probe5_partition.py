"""#956 Phase B: where the oracle and momwire disagree, by pair separation.

The whole-block substitution read dR = +5769 ohm, which is not a finding about
#956 — it is the oracle being the wrong instrument for part of the block. The
rise and the radiator are COLLINEAR and SHARE the node, so the field-form
point-dipole superposition over two touching collinear segments carries the
ln(a)-class content `_crossing_fill`'s docstring names, and evaluating it
on-axis is its zero-radius limit: divergent, by construction. momwire's by-parts
ends and corner exist precisely to hold that content.

So the block must be partitioned by pair separation before anything is read off
it. The oracle's warrant (G4, 3.0e-04 against empymod) is for well-separated
pairs; #956's residual is DISTRIBUTED and proportional to buried length with no
intercept, so it should live in exactly those pairs, not in the node-adjacent
ones. This measures the disagreement as a function of separation, on blocks
already computed.
"""

import sys
import warnings
from pathlib import Path

import numpy as np

warnings.filterwarnings("ignore")
sys.path.insert(0, str(Path(__file__).resolve().parent))

from probe3_cross_block import build, parts, solver_of  # noqa: E402


def basis_support(geom, supp_seg, idx_set, polys):
    """For each basis, the endpoints of every segment in its support that lies
    in `idx_set` — so a pair distance is a support-to-support distance.

    **`polys` is not optional and the first version of this was wrong without
    it.** A basis near a wire end has fewer than `d+1` wings, and the missing
    ones are PADDED in `supp_seg` — 26 of 765 wings here, every one carrying an
    all-zero polynomial, 9 of them a repeat of a real wing and 17 of them the
    literal index 0. Padding is harmless in the assembly (`_field_galerkin_
    block` multiplies by `polys[m, a, :]`, so a zero polynomial contributes
    nothing) and poisonous to a geometric read of the same array: segment 0 on
    this deck is a RADIAL AT THE HUB, so every padded basis appeared to have
    support 0.15 m from the plane and manufactured a four-fold symmetric
    population of "pairs at exactly the hub depth" that are not pairs at all.
    """
    seg_l = np.asarray(geom["seg_l"])
    seg_r = np.asarray(geom["seg_r"])
    inset = np.zeros(seg_l.shape[0], bool)
    inset[idx_set] = True
    live = ~np.all(np.abs(polys) == 0.0, axis=2)
    out = []
    for m in range(supp_seg.shape[0]):
        pts = []
        for a in range(supp_seg.shape[1]):
            sg = supp_seg[m, a]
            if live[m, a] and inset[sg]:
                pts.append(seg_l[sg])
                pts.append(seg_r[sg])
        out.append(np.asarray(pts) if pts else np.zeros((0, 3)))
    return out


def main():
    b = build()
    s = solver_of(b)
    geom, supp_seg, polys, a_idx, b_idx = parts(s)
    here = Path(__file__).resolve().parent / "blocks"
    tag = f"r{b.n_radials}_d{b.depth}"
    mw = np.load(here / f"mw_{tag}.npy")
    ob = np.load(here / f"oracle_{tag}_q1.npy")
    print(
        f"blocks {mw.shape}   |mw|max {np.abs(mw).max():.4e}   "
        f"|oracle|max {np.abs(ob).max():.4e}"
    )

    sup_a = basis_support(geom, supp_seg, a_idx, polys)
    sup_b = basis_support(geom, supp_seg, b_idx, polys)
    rows = [m for m in range(len(sup_a)) if len(sup_a[m])]
    cols = [n for n in range(len(sup_b)) if len(sup_b[n])]
    print(f"above-supported bases {len(rows)}, below-supported {len(cols)}")

    D = np.full((len(rows), len(cols)), np.inf)
    for i, m in enumerate(rows):
        pa = sup_a[m]
        for j, n in enumerate(cols):
            pb = sup_b[n]
            D[i, j] = np.linalg.norm(pa[:, None, :] - pb[None, :, :], axis=-1).min()

    sub_m = mw[np.ix_(rows, cols)]
    sub_o = ob[np.ix_(rows, cols)]
    diff = np.abs(sub_o - sub_m)
    print(f"\nsupport-separation range [{D.min():.4e}, {D.max():.4e}] m")
    print(f"wire radius {s.wire_radius if hasattr(s, 'wire_radius') else 5e-4}")
    print(
        f"\n{'separation >=':>14} {'pairs':>7} {'|o-m|max':>12} {'|m|max':>12} "
        f"{'rel':>10} {'median rel':>11}"
    )
    for thr in (0.0, 1e-3, 5e-3, 1e-2, 2.5e-2, 5e-2, 0.1, 0.25, 0.5, 1.0):
        msk = D >= thr
        if not msk.any():
            continue
        sc = float(np.abs(sub_m[msk]).max())
        if sc <= 0:
            continue
        # per-entry relative, graded against that entry's own magnitude, on the
        # entries big enough for a ratio to mean anything
        big = msk & (np.abs(sub_m) > 1e-3 * np.abs(sub_m[msk]).max())
        per = np.abs(sub_o[big] - sub_m[big]) / np.abs(sub_m[big])
        print(
            f"{thr:14.4e} {int(msk.sum()):7d} {float(diff[msk].max()):12.4e} "
            f"{sc:12.4e} {float(diff[msk].max()) / sc:10.4e} "
            f"{float(np.median(per)) if per.size else float('nan'):11.4e}"
        )

    # where the worst entries are
    k = np.unravel_index(np.argsort(diff.ravel())[::-1][:8], diff.shape)
    print(f"\n{'rank':>4} {'sep (m)':>10} {'|o-m|':>12} {'|mw|':>12} {'rel':>10}")
    for r, (i, j) in enumerate(zip(*k, strict=True)):
        print(
            f"{r:>4} {D[i, j]:10.4e} {diff[i, j]:12.4e} "
            f"{abs(sub_m[i, j]):12.4e} {diff[i, j] / max(abs(sub_m[i, j]), 1e-300):10.4e}"
        )


if __name__ == "__main__":
    main()
