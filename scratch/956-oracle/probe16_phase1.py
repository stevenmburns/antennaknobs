"""#956 near-node unit, Phase 1: the node-touching rows against the axis.

Rows: every basis whose support touches z = 0. Columns: the bases lying wholly
on the rise (below) and the radiator (above). All three pair classes among that
set, compared and substituted at the ASSEMBLED Z level — an assembled entry IS
-<f_m, E(f_n)> and stands alone, which is what makes this work where cross-BLOCK
substitution did not (a block entry's meaning depends on compensating content
elsewhere in the fill).

Gated by probe14 (in-medium kernel at this geometry, 9.6e-05) and probe15 (the
total-field compositions against momwire's assembled Z, 3.0e-06 / 1.0e-06).

EXCLUSIONS, and they are named rather than hidden. Self pairs and same-medium
pairs sharing a segment are left as momwire's own: those are the singular ones,
momwire integrates them with analytic static extraction, and plain Gauss at the
thin-wire stand-off would report my quadrature rather than momwire's fill.
Partial by construction in the other direction too — radial columns are Phase 2.
"""

import argparse
import os
import sys
import time

# Pinned BEFORE numpy is imported: a thread pool already built inside numpy does
# not shrink because an env var changed later. Measured on this box (i7-4770K,
# 4 cores / 8 threads) at 2.94 / 5.73 / 11.11 / 11.45 pairs per second on 1 / 2
# / 4 / 8 workers, so 4 is 97 % of the best and the SMT margin is 3 %.
for _v in (
    "OMP_NUM_THREADS",
    "OPENBLAS_NUM_THREADS",
    "MKL_NUM_THREADS",
    "NUMEXPR_NUM_THREADS",
    "VECLIB_MAXIMUM_THREADS",
):
    os.environ[_v] = "1"
os.environ.setdefault("OPENBLAS_THREAD_TIMEOUT", "1")

import warnings  # noqa: E402
from pathlib import Path  # noqa: E402

import numpy as np  # noqa: E402

warnings.filterwarnings("ignore")
sys.path.insert(0, str(Path(__file__).resolve().parent))

from momwire import BSplineSolver  # noqa: E402

import proj_oracle as PO  # noqa: E402
from probe3_cross_block import FREQ, SOIL_A, build, parts, solver_of  # noqa: E402
from probe5_partition import basis_support  # noqa: E402
from probe15_assembled_gate import live_wings  # noqa: E402

Z_TOL = 1e-9


def axis_segs(geom, idx):
    sl = np.asarray(geom["seg_l"])[idx]
    sr = np.asarray(geom["seg_r"])[idx]
    on = (np.abs(sl[:, :2]).max(axis=1) < Z_TOL) & (
        np.abs(sr[:, :2]).max(axis=1) < Z_TOL
    )
    return idx[on]


def solve_with_Z(b, transform):
    """Solve with `_compute_Z_operator` post-processed by `transform`."""
    real = BSplineSolver._compute_Z_operator
    calls = []

    def patched(self, geom, supp_seg, polys, same_edge_prep=None):
        Z = real(self, geom, supp_seg, polys, same_edge_prep=same_edge_prep)
        calls.append(1)
        return transform(Z)

    BSplineSolver._compute_Z_operator = patched
    try:
        with warnings.catch_warnings():
            warnings.simplefilter("ignore")
            z, _ = solver_of(b).compute_impedance()
    finally:
        BSplineSolver._compute_Z_operator = real
    return complex(z), len(calls)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--workers", type=int, default=4)
    ap.add_argument("--stand-off", type=float, default=5e-4)
    ap.add_argument("--q-factor", type=int, default=1)
    args = ap.parse_args()
    PO.set_stand_off(args.stand_off)

    b = build()
    s = solver_of(b)
    geom, supp_seg, polys, a_idx, b_idx = parts(s)
    Z = s._compute_Z_operator(geom, supp_seg, polys)
    sup_a = basis_support(geom, supp_seg, a_idx, polys)
    sup_b = basis_support(geom, supp_seg, b_idx, polys)

    rise = set(map(int, axis_segs(geom, b_idx)))
    rad = set(map(int, axis_segs(geom, a_idx)))

    def touches(sup, m):
        return len(sup[m]) and np.any(np.abs(sup[m][:, 2]) < Z_TOL)

    rows_a = [m for m in range(len(sup_a)) if touches(sup_a, m)]
    rows_b = [m for m in range(len(sup_b)) if touches(sup_b, m)]
    cols_a = [
        m
        for m in range(len(sup_a))
        if len(sup_a[m]) and all(t in rad for t in live_wings(polys, supp_seg, m))
    ]
    cols_b = [
        m
        for m in range(len(sup_b))
        if len(sup_b[m]) and all(t in rise for t in live_wings(polys, supp_seg, m))
    ]
    print(f"rows: {len(rows_a)} above {rows_a}, {len(rows_b)} below {rows_b}")
    print(f"cols: {len(cols_a)} radiator, {len(cols_b)} rise")
    print(f"stand-off {args.stand_off:.2e} m, q_factor {args.q_factor}")

    ia = np.array(sorted(rad), dtype=np.int64)
    ib = np.array(sorted(rise), dtype=np.int64)
    oa, ta, Wa = s._buried_nodes(geom, ia, q_factor=args.q_factor)
    ob, tb, Wb = s._buried_nodes(geom, ib, q_factor=args.q_factor)
    print(
        f"nodes: radiator {len(oa)}, rise {len(ob)}  -> "
        f"{len(oa) ** 2 + len(ob) ** 2 + 2 * len(oa) * len(ob):,} evaluations"
    )

    cache = (
        Path(__file__).resolve().parent
        / "blocks"
        / (f"phase1_Q_a{args.stand_off:g}_q{args.q_factor}.npy")
    )
    if cache.exists():
        Q = np.load(cache)
        print(f"  Q loaded from {cache.name} (quadrature unchanged)")
        _assemble = False
    else:
        _assemble = True
    t0 = time.time()
    if not _assemble:
        pass
    else:
        Q = np.zeros_like(Z)
        Q += s._field_galerkin_block(
            supp_seg,
            polys,
            PO.make_proj_total_above(FREQ, *SOIL_A, workers=args.workers),
            ia,
            ia,
            oa,
            ta,
            Wa,
            oa,
            ta,
            Wa,
        )
        print(f"  above x above done {time.time() - t0:.0f}s")
        sys.stdout.flush()
        Q += s._field_galerkin_block(
            supp_seg,
            polys,
            PO.make_proj_total_below(FREQ, *SOIL_A, workers=args.workers),
            ib,
            ib,
            ob,
            tb,
            Wb,
            ob,
            tb,
            Wb,
        )
        print(f"  below x below done {time.time() - t0:.0f}s")
        sys.stdout.flush()
        cross = PO.make_proj(FREQ, *SOIL_A, workers=args.workers)
        Q += s._field_galerkin_block(
            supp_seg,
            polys,
            cross,
            ia,
            ib,
            oa,
            ta,
            Wa,
            ob,
            tb,
            Wb,
        )
        Q += s._field_galerkin_block(
            supp_seg,
            polys,
            cross,
            ib,
            ia,
            ob,
            tb,
            Wb,
            oa,
            ta,
            Wa,
        )
        print(f"  cross both directions done {time.time() - t0:.0f}s")
        np.save(cache, Q)

    rows = rows_a + rows_b
    cols = cols_a + cols_b
    sup_all = [sup_a[m] if len(sup_a[m]) else sup_b[m] for m in range(len(sup_a))]
    drop = np.zeros((len(rows), len(cols)), bool)
    n_share = n_touch = 0
    for i, m in enumerate(rows):
        wm = set(live_wings(polys, supp_seg, m))
        for j, n in enumerate(cols):
            share = (m == n) or bool(wm & set(live_wings(polys, supp_seg, n)))
            # TOUCHING supports, which "shares a segment" cannot catch for a
            # CROSS pair: an above basis and a below basis never share one, and
            # the pair meeting at z = 0 is exactly the divergent collinear case.
            # The first Phase 1 run missed this and ONE entry — |o-m| =
            # 4.3861e+03, the same entry probe5 ranked first on the whole block
            # — carried +5858 of a +5859 ohm answer.
            touch = False
            if not share and len(sup_all[m]) and len(sup_all[n]):
                touch = bool(
                    np.linalg.norm(
                        sup_all[m][:, None, :] - sup_all[n][None, :, :], axis=-1
                    ).min()
                    < args.stand_off
                )
            n_share += int(share)
            n_touch += int(touch)
            drop[i, j] = share or touch
    mask = np.zeros_like(Z, bool)
    mask[np.ix_(rows, cols)] = ~drop
    mask |= mask.T
    print(
        f"substituting {int(mask.sum())} entries ({n_share} self/adjacent + "
        f"{n_touch} touching-support left as momwire's)"
    )

    z0, n0 = solve_with_Z(b, lambda M: M)
    print(f"\nplumbing: identity transform Z = {z0!r} (calls {n0})")
    z_id, _ = solve_with_Z(b, lambda M: np.where(mask, Z, M))
    print(
        f"plumbing: momwire's own entries substituted -> {z_id!r}  "
        f"bit-identical {z_id == z0}"
    )
    z_sub, _ = solve_with_Z(b, lambda M: np.where(mask, -Q, M))
    print(f"\nPhase 1 substituted Z = {z_sub!r}")
    print(f"  dR {z_sub.real - z0.real:+10.4f} ohm    dX {z_sub.imag - z0.imag:+10.4f}")
    # first-order cross-check
    d = np.where(mask, -Q - Z, 0.0)
    print(
        f"  substituted-entry difference: max {np.abs(d).max():.4e}, "
        f"median {np.median(np.abs(d[mask])):.4e}"
    )


if __name__ == "__main__":
    main()
