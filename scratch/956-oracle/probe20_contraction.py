"""#956: is `_field_galerkin_block` over supp_seg/polys the fill's own assembly?

On a NON-CROSSING mixed deck the cross block goes through the transmitted grid
and `compute_Z_operator_buried` does exactly:

    Z -= f.field_galerkin_block(supp_seg, polys, proj_ab, a_idx, b_idx, ...)

Nothing else writes the above x below quadrant, so the assembled entry there IS
minus that contraction's output. Driving MY contraction with MOMWIRE's projector
must therefore reproduce it — to grid accuracy, since I size my own grid.

If it does: my contraction is the fill's assembly, and the departure seen on the
crossing deck belongs to `_crossing_fill`'s spelling (reading 1). The +0.4119
ohm stands.
If it does not: my contraction was never the entry (reading 2), and everything
measured through it — the +0.4119 included — is void pending a correct one.

Third row costs nothing and is the control the table needs: a well-separated
OFF-AXIS pair on the CROSSING deck, where the oracle already agrees to a median
of 1.05e-08, so the table shows the contraction agreeing somewhere on the very
deck it disagrees on.
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

from momwire import BSplineSolver  # noqa: E402
from momwire import _sommerfeld_transmitted as trans  # noqa: E402

from probe3_cross_block import build, solver_of  # noqa: E402
from probe5_partition import basis_support  # noqa: E402
from probe15_assembled_gate import live_wings  # noqa: E402

C0 = 299792458.0
FREQ = 7.1e6
SOIL_A = (13.0, 0.005)
EPS0 = 8.8541878128e-12
MU0 = 4.0e-7 * np.pi


def medium():
    w = 2.0 * np.pi * FREQ
    eps_t = complex(SOIL_A[0]) - 1j * SOIL_A[1] / (w * EPS0)
    k_p = w / C0
    k_m = k_p * np.sqrt(eps_t)
    if k_m.imag > 0:
        k_m = np.conj(k_m)
    return eps_t, k_p, complex(k_m), w


def noncrossing_deck():
    """Wires either side of the plane, none ending in it, no junction — D2's
    shape, on BSplineSolver so it reaches `compute_Z_operator_buried`."""
    above = np.array([(0.0, 0.0, 0.25), (0.0, 0.0, 1.25)])
    below_axis = np.array([(0.0, 0.0, -1.15), (0.0, 0.0, -0.15)])
    below_off = np.array([(3.0, 0.0, -0.30), (3.0 + 1.0, 0.0, -0.30)])
    return BSplineSolver(
        wires=[above, below_axis, below_off],
        n_per_edge_per_wire=[[9], [9], [9]],
        feeds=[(0, 0.5, 1 + 0j)],
        wavelength=C0 / FREQ,
        wire_radius=0.001,
        ground_z=0.0,
        ground_eps=SOIL_A,
        ground_model="sommerfeld",
    )


def three_way(s, tag_rows, label, restrict=None):
    eps_t, k_p, k_m, w = medium()
    geom = s._build_geometry()
    supp_seg, polys, *_ = s._build_basis_polynomials(geom)
    below = s._below_segments(geom)
    a_idx = np.nonzero(~below)[0]
    b_idx = np.nonzero(below)[0]
    Z = s._compute_Z_operator(geom, supp_seg, polys)
    oa, ta, Wa = s._buried_nodes(geom, a_idx)
    ob, tb, Wb = s._buried_nodes(geom, b_idx)
    try:
        plan = s._buried_serve_plan(geom, a_idx, oa, ob, k_p, k_m)
        r_hi, r_lo = plan["r_cross_max"], plan["r_cross_min"]
        zp_lo, zp_hi = plan["zp_min"], plan["zp_max"]
    except ValueError as exc:
        # `serve_plan` REFUSES the crossing deck's full extent: its shallowest
        # buried node is 2.1e-04 m and the transmitted tail cannot be paid for
        # at that grazing angle. That is exactly why a crossing deck never
        # builds this grid. For the control row the grid is sized on the
        # SELECTED pair's own nodes instead, which is inside the payable band.
        print(f"    (serve_plan refused the full extent: {str(exc)[:60]}...)")
        keep_a, keep_b = restrict(geom, supp_seg, polys, a_idx, b_idx)
        a_idx, b_idx = keep_a, keep_b
        oa, ta, Wa = s._buried_nodes(geom, a_idx)
        ob, tb, Wb = s._buried_nodes(geom, b_idx)
        zpv = s.ground_z - ob[:, 2]
        cd = np.hypot(
            oa[:, 0][:, None] - ob[:, 0][None, :],
            oa[:, 1][:, None] - ob[:, 1][None, :],
        )
        r_obs = np.hypot(cd, (oa[:, 2] - s.ground_z)[:, None])
        r_hi, r_lo = float(r_obs.max()) * 1.05, float(r_obs.min()) * 0.95
        zp_lo, zp_hi = float(zpv.min()), float(zpv.max())
    grid = trans.get_grid_below_above(
        eps_t, k_p, r_hi, zp_lo, zp_hi, w, mu=MU0, r_min=r_lo
    )

    def mw_proj(o, to, sr, ts):
        return trans.transmitted_field_proj_below_to_above(
            o, to, sr, ts, s.ground_z, k_p, k_m, grid
        )

    Q = s._field_galerkin_block(
        supp_seg, polys, mw_proj, a_idx, b_idx, oa, ta, Wa, ob, tb, Wb
    )
    sup_a = basis_support(geom, supp_seg, a_idx, polys)
    sup_b = basis_support(geom, supp_seg, b_idx, polys)
    out = []
    _kw = (
        {}
        if restrict is None
        else {"keep": (set(map(int, a_idx)), set(map(int, b_idx)))}
    )
    for m, n, why in tag_rows(sup_a, sup_b, geom, supp_seg, polys, **_kw):
        a_, c_ = -Q[m, n], Z[m, n]
        rel = abs(a_ - c_) / max(abs(c_), 1e-300)
        print(
            f"{label + ' ' + why:>34} {m:4d}x{n:<4d} "
            f"{a_.real:12.5e}{a_.imag:+12.5e}j "
            f"{c_.real:12.5e}{c_.imag:+12.5e}j {rel:11.4e}"
        )
        sys.stdout.flush()
        out.append(rel)
    return out


def main():
    print(
        f"{'deck / pair':>34} {'entry':>10} {'(a) my contraction':>26} "
        f"{'(c) assembled Z':>26} {'rel':>11}"
    )

    s = noncrossing_deck()

    def rows_nc(sup_a, sup_b, geom, supp_seg, polys):
        onx = [
            m
            for m in range(len(sup_a))
            if len(sup_a[m]) and np.abs(sup_a[m][:, :2]).max() < 1e-9
        ]
        axb = [
            n
            for n in range(len(sup_b))
            if len(sup_b[n]) and np.abs(sup_b[n][:, :2]).max() < 1e-9
        ]
        offb = [
            n
            for n in range(len(sup_b))
            if len(sup_b[n]) and np.abs(sup_b[n][:, 0]).min() > 1.0
        ]
        return [
            (onx[len(onx) // 2], axb[len(axb) // 2], "ON-AXIS cross"),
            (onx[len(onx) // 2], offb[len(offb) // 2], "off-axis cross"),
        ]

    three_way(s, rows_nc, "non-crossing")

    # the crossing deck, an off-axis well-separated pair
    b = build()
    sc = solver_of(b)

    def rows_cr(sup_a, sup_b, geom, supp_seg, polys, keep=None):
        """A pair whose FULL live support is inside the restricted segment set.

        `basis_support` silently truncates a support to the segments it is
        given, so a basis reaching outside the restriction yields a PARTIAL
        entry that cannot be compared with the assembled one. The first version
        of this row did exactly that and read 9.4e-01 — a number about my
        scoping, not about momwire.
        """
        ok_a, ok_b = keep
        best = None
        for m in range(len(sup_a)):
            if not len(sup_a[m]):
                continue
            if not all(t in ok_a for t in live_wings(polys, supp_seg, m)):
                continue
            for n in range(len(sup_b)):
                if not len(sup_b[n]):
                    continue
                if not all(t in ok_b for t in live_wings(polys, supp_seg, n)):
                    continue
                d = np.linalg.norm(
                    sup_a[m][:, None, :] - sup_b[n][None, :, :], axis=-1
                ).min()
                if 0.5 < d < 6.0:
                    best = (m, n, f"off-axis, sep {d:.2f} m")
                    break
            if best:
                break
        return [best]

    def restrict_cr(geom, supp_seg, polys, a_idx, b_idx):
        """The radiator's upper segments against one radial — a pair the
        transmitted grid can actually be built for."""
        sl = np.asarray(geom["seg_l"])
        sr = np.asarray(geom["seg_r"])
        ka = [i for i in a_idx if min(sl[i][2], sr[i][2]) > 1.0]
        kb = [
            i
            for i in b_idx
            if max(abs(sl[i][0]), abs(sr[i][0])) > 0.05 and abs(sl[i][1]) < 1e-9
        ]
        return np.array(ka, dtype=np.int64), np.array(kb, dtype=np.int64)

    three_way(sc, rows_cr, "CROSSING", restrict=restrict_cr)


if __name__ == "__main__":
    main()
