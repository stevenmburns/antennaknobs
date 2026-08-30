"""A-2 session 5, probe 26: DECOMPOSE the merged node diagonal by family.

probe25 eliminated outer quadrature + image truncation + cross kernels
(all resolved; blow-up unchanged). Remaining suspect: the two Sommerfeld
REMAINDER blocks' node entries (grid field projections at the R1 -> 0 /
z, z' -> 0 corner). This probe measures, per grading level:

    D_merged = (MPd_aa - IMG_aa - R_aa)[na,na]
             + (MPd_bb - IMG_bb - R_bb)[nb,nb]
             - 2 t_ab[na,nb]           (Z -= cross; t_ba = t_ab^T)

piece by piece, plus the mono deck's contact-node diagonal as the
validated reference. A piece whose node entry DRIFTS between g1/g2 (or
scales like the tent, not like physics) is the defective family.

Run: prlimit --as=$((8*1024*1024*1024)) .venv/bin/python \
       scratch/524-phase2/proto/probe26_node_decomp.py [level ...]
"""

from __future__ import annotations

import sys
import time
from pathlib import Path

import numpy as np

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "567-phase0" / "proto"))
sys.path.insert(0, str(Path(__file__).resolve().parents[3] / "momwire" / "tests"))

import corner_tables as ct  # noqa: E402
from momwire.bspline import BSplineSolver  # noqa: E402
from probe1_baseline import seeded  # noqa: E402
from probe13_x3 import node_indices  # noqa: E402
from probe18_graded import mono_graded  # noqa: E402
from probe19_graded_mpb import crossing_graded  # noqa: E402
from probe23_designed_gate2 import pieces_designed  # noqa: E402

A_WIRE = 0.001
ct.install(wire_radius=A_WIRE)


def capture_blocks(s):
    """Assemble the buried Z while capturing every _field_galerkin_block
    call keyed by (axis(obs), axis(src)); also returns the direct/image
    pieces recomputed exactly as the fill composes them."""
    geom = s._build_geometry()
    below = s._below_segments(geom)
    b_idx = np.nonzero(below)[0]
    a_idx = np.nonzero(~below)[0]
    supp_seg, polys, *_ = s._build_basis_polynomials(geom)
    eps_t, eps_m, k_p, k_m, c2, a_m = s._buried_medium()

    cap = {}
    orig = BSplineSolver._field_galerkin_block

    def wrap(self, ss, pl, proj_fn, obs_idx, src_idx, *rest):
        out = orig(self, ss, pl, proj_fn, obs_idx, src_idx, *rest)
        o = np.sort(np.asarray(obs_idx))
        sr = np.sort(np.asarray(src_idx))
        ao = "a" if np.array_equal(o, np.sort(a_idx)) else "b"
        asrc = "a" if np.array_equal(sr, np.sort(a_idx)) else "b"
        cap[ao + asrc] = np.array(out, copy=True)
        return out

    BSplineSolver._field_galerkin_block = wrap
    try:
        Z = s._compute_Z_operator_buried(geom, supp_seg, polys)
    finally:
        BSplineSolver._field_galerkin_block = orig

    td_img = s._image_tangent_dot(geom["tangents"])
    MPd_bb = s._assemble_Z(
        s._build_J_blocks_subset(geom, k_m, b_idx),
        supp_seg,
        polys,
        geom,
        eps=eps_m,
    )
    MPd_aa = s._assemble_Z(
        s._build_J_blocks_subset(geom, k_p, a_idx), supp_seg, polys, geom
    )
    IMG_bb = s._image_Z_weighted(
        s._build_J_blocks_subset(geom, k_m, b_idx, mirror_sources=True),
        supp_seg,
        polys,
        a_m * td_img.astype(np.complex128),
        np.full(td_img.shape, a_m, dtype=np.complex128),
        eps=eps_m,
    )
    IMG_aa = s._image_Z_weighted(
        s._build_J_blocks_subset(geom, k_p, a_idx, mirror_sources=True),
        supp_seg,
        polys,
        c2 * td_img.astype(np.complex128),
        np.full(td_img.shape, c2, dtype=np.complex128),
    )
    return dict(
        Z=Z,
        cap=cap,
        MPd_bb=MPd_bb,
        MPd_aa=MPd_aa,
        IMG_bb=IMG_bb,
        IMG_aa=IMG_aa,
        geom=geom,
    )


def main():
    levels = [int(x) for x in sys.argv[1:]] or [1, 2]
    for lv in levels:
        t0 = time.time()
        s = seeded(crossing_graded(lv))
        blocks = capture_blocks(s)
        geom = blocks["geom"]
        nb, na = node_indices(s, geom)
        R_aa = blocks["cap"]["aa"]
        R_bb = blocks["cap"]["bb"]
        pieces = pieces_designed(lv)
        t_ab = pieces["M"] + pieces["SW"] + pieces["SQ"]

        h_min = float(geom["h_per_seg"].min())
        print(f"\ng{lv} (h_node = {h_min:.4f}, {time.time() - t0:.0f}s):")
        rows = {
            "MPd_aa[na,na]": blocks["MPd_aa"][na, na],
            "IMG_aa[na,na]": blocks["IMG_aa"][na, na],
            "R_aa [na,na]": R_aa[na, na],
            "self_aa net": (blocks["MPd_aa"] - blocks["IMG_aa"] - R_aa)[na, na],
            "MPd_bb[nb,nb]": blocks["MPd_bb"][nb, nb],
            "IMG_bb[nb,nb]": blocks["IMG_bb"][nb, nb],
            "R_bb [nb,nb]": R_bb[nb, nb],
            "self_bb net": (blocks["MPd_bb"] - blocks["IMG_bb"] - R_bb)[nb, nb],
            "t_ab[na,nb] designed": t_ab[na, nb],
        }
        for k, v in rows.items():
            print(f"  {k:>22}: {v:14.4f}")
        D = (
            rows["self_aa net"]
            + rows["self_bb net"]
            - 2.0 * rows["t_ab[na,nb] designed"]
        )
        print(f"  {'D_merged (node diag)':>22}: {D:14.4f}")

        # the validated reference: mono deck's contact-node diagonal
        sm = BSplineSolver(**mono_graded(lv))
        gm = sm._build_geometry()
        ssm, plm, *_ = sm._build_basis_polynomials(gm)
        Zm = sm._compute_Z_operator(gm, ssm, plm)
        # contact node basis = the one with value at z=0: basis 0 by the
        # ground-junction construction; report the largest-diagonal guess
        # plus explicit z=0-support scan
        vals = np.abs(np.diag(Zm))
        print(
            f"  mono deck diag |max| {vals.max():.4f} at {vals.argmax()}"
            f"  (n={len(vals)})"
        )


if __name__ == "__main__":
    main()
