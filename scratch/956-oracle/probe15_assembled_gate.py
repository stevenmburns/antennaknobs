"""#956 near-node unit, gate 2: the TOTAL-field projectors against momwire's
ASSEMBLED Z, on well-separated pairs.

The near-node comparison rests on "an assembled entry IS -<f_m, E(f_n)>". That
is a claim about momwire's formulation AND about my compositions at once — the
C2 coefficient and image convention for above/above, A_m and the remainder sign
for below/below. Both are measured here rather than asserted, on pairs far
enough apart that quadrature is not in question, before anything near the node
is touched. A wrong coefficient or sign is O(1) and cannot hide.

Scope discipline, learned the expensive way: `_field_galerkin_block` assembles
over whatever segment sets it is given, so asking for a few entries out of the
FULL below x below block is 1.77M pair evaluations for sixteen numbers. The
segment set here is the union of the picked bases' own supports and nothing
else, which is what makes those bases' entries complete and the cost small.
"""

import sys
import warnings
from pathlib import Path

import numpy as np

warnings.filterwarnings("ignore")
sys.path.insert(0, str(Path(__file__).resolve().parent))

import proj_oracle as PO  # noqa: E402
from probe3_cross_block import FREQ, SOIL_A, build, parts, solver_of  # noqa: E402
from probe5_partition import basis_support  # noqa: E402


def live_wings(polys, supp_seg, m):
    live = ~np.all(np.abs(polys[m]) == 0.0, axis=1)
    return [int(supp_seg[m, a]) for a in range(supp_seg.shape[1]) if live[a]]


def pick(sup, polys, supp_seg, seg_ok, n, zmin, sep_min):
    """`n` bases fully inside `seg_ok`, at least `zmin` off the plane, and
    mutually separated by at least `sep_min` so every reported pair is far."""
    cands = [
        m
        for m in range(len(sup))
        if len(sup[m])
        and np.min(np.abs(sup[m][:, 2])) >= zmin
        and all(s in seg_ok for s in live_wings(polys, supp_seg, m))
    ]
    out = []
    for m in cands:
        if all(
            np.linalg.norm(sup[m][:, None, :] - sup[k][None, :, :], axis=-1).min()
            >= sep_min
            for k in out
        ):
            out.append(m)
        if len(out) == n:
            break
    return out


def check(tag, s, geom, supp_seg, polys, Z, sup, rows, maker, workers):
    segs = sorted({t for m in rows for t in live_wings(polys, supp_seg, m)})
    idx = np.array(segs, dtype=np.int64)
    obs, t, W = s._buried_nodes(geom, idx)
    print(
        f"\n--- {tag}: {len(rows)} bases over {len(idx)} segments "
        f"({len(obs)} nodes, {len(obs) ** 2} pair evaluations)"
    )
    Q = s._field_galerkin_block(
        supp_seg,
        polys,
        maker(FREQ, *SOIL_A, workers=workers),
        idx,
        idx,
        obs,
        t,
        W,
        obs,
        t,
        W,
    )
    print(
        f"{'m':>5} {'n':>5} {'sep':>9} {'momwire Z':>26} "
        f"{'-Q (field form)':>26} {'rel':>10}"
    )
    worst = 0.0
    for m in rows:
        for n in rows:
            if m >= n:
                continue
            d = np.linalg.norm(sup[m][:, None, :] - sup[n][None, :, :], axis=-1).min()
            zz, qq = Z[m, n], -Q[m, n]
            rel = abs(zz - qq) / max(abs(zz), 1e-300)
            worst = max(worst, rel)
            print(
                f"{m:>5} {n:>5} {d:9.4f} {zz.real:12.5e}{zz.imag:+12.5e}j "
                f"{qq.real:12.5e}{qq.imag:+12.5e}j {rel:10.3e}"
            )
            sys.stdout.flush()
    print(f"  worst {tag}: {worst:.4e}")
    return worst


def main():
    workers = int(sys.argv[1]) if len(sys.argv) > 1 else 7
    b = build()
    s = solver_of(b)
    geom, supp_seg, polys, a_idx, b_idx = parts(s)
    Z = s._compute_Z_operator(geom, supp_seg, polys)
    sup_a = basis_support(geom, supp_seg, a_idx, polys)
    sup_b = basis_support(geom, supp_seg, b_idx, polys)
    seg_a, seg_b = set(map(int, a_idx)), set(map(int, b_idx))

    rows_a = pick(sup_a, polys, supp_seg, seg_a, 3, 0.6, 0.8)
    rows_b = pick(sup_b, polys, supp_seg, seg_b, 3, 0.02, 0.6)
    print(f"above bases {rows_a}   below bases {rows_b}")
    wa = check(
        "above x above",
        s,
        geom,
        supp_seg,
        polys,
        Z,
        sup_a,
        rows_a,
        PO.make_proj_total_above,
        workers,
    )
    wb = check(
        "below x below",
        s,
        geom,
        supp_seg,
        polys,
        Z,
        sup_b,
        rows_b,
        PO.make_proj_total_below,
        workers,
    )
    print(f"\nGATE 2: above {wa:.4e}, below {wb:.4e}")


if __name__ == "__main__":
    main()
