"""A-2 next-experiments #2 (scout): WHERE can the missing -2.8 ohm live?

Captures the fully-assembled (Z, v, kcl_A) of the B_dropAboveQ+none crossing
solve (MP cross blocks swapped) plus the mono solve, then re-solves under
targeted perturbations of the below-arm entries WITHOUT re-filling:

  - scale the below/below SELF block (rows/cols of the below-arm bases,
    self part only)
  - scale the node basis self entry Z[nb,nb] alone
  - scale the interior below/below entries vs the node row/col separately
  - scale the (already-MP) cross entries

For each: Delta = Z_in(perturbed crossing) - Z_in(mono), vs engine Delta
x1 = -2.3260 - 0.7130j. The point is sensitivity structure, not a fit —
which block CAN carry a -3 ohm correction with an O(1) change.

Run: .venv/bin/python scratch/524-phase2/proto/probe9_sense.py
"""

from __future__ import annotations

import sys
from pathlib import Path

import numpy as np

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "567-phase0" / "proto"))
sys.path.insert(0, str(Path(__file__).resolve().parents[3] / "momwire" / "tests"))

from momwire.bspline import BSplineSolver  # noqa: E402
from probe1_baseline import crossing_deck, seeded  # noqa: E402
from probe8_split import build_pieces, mono_deck  # noqa: E402

ENGINE_DELTA_X1 = -2.3260 - 0.7130j


def capture(s, t_ab=None, a_seg=None, b_seg=None, z_hook=None):
    """Run compute_impedance while stashing (Z, v, kcl_A); optionally swap
    the cross blocks with t_ab / t_ab.T as probe6/7/8 do. `z_hook(Z) -> Z'`
    perturbs the assembled matrix just before the production solve."""
    stash = {}
    orig_blk = BSplineSolver._field_galerkin_block
    orig_kcl = BSplineSolver._solve_with_kcl

    def wrap_blk(self, supp_seg, polys, proj_fn, obs_idx, src_idx, *rest):
        o = np.sort(np.asarray(obs_idx))
        sr = np.sort(np.asarray(src_idx))
        if t_ab is not None and np.array_equal(o, a_seg) and np.array_equal(sr, b_seg):
            return t_ab.copy()
        if t_ab is not None and np.array_equal(o, b_seg) and np.array_equal(sr, a_seg):
            return t_ab.T.copy()
        return orig_blk(self, supp_seg, polys, proj_fn, obs_idx, src_idx, *rest)

    def wrap_kcl(self, Z, v, kcl_A, overwrite=False):
        stash["Z"] = Z.copy()
        stash["v"] = v.copy()
        stash["kcl"] = None if kcl_A is None else np.array(kcl_A, copy=True)
        if z_hook is not None:
            Z = z_hook(Z.copy())
        return orig_kcl(self, Z, v, kcl_A, overwrite=False)

    BSplineSolver._field_galerkin_block = wrap_blk
    BSplineSolver._solve_with_kcl = wrap_kcl
    try:
        z, _ = s.compute_impedance()
    finally:
        BSplineSolver._field_galerkin_block = orig_blk
        BSplineSolver._solve_with_kcl = orig_kcl
    stash["z_in"] = z
    return stash


def main():
    pieces = build_pieces(1)
    t_ab = pieces["M"] + pieces["SW"] + pieces["SQ"]  # B_dropAboveQ

    s = seeded(crossing_deck(1))
    geom = s._build_geometry()
    below = s._below_segments(geom)
    b_seg = np.sort(np.nonzero(below)[0])
    a_seg = np.sort(np.nonzero(~below)[0])

    st = capture(s, t_ab=t_ab, a_seg=a_seg, b_seg=b_seg)

    z0 = st["z_in"]

    sm = capture(BSplineSolver(**mono_deck(1)))
    z_mono = sm["z_in"]
    print(f"crossing B+none = {z0:.4f}   mono = {z_mono:.4f}")
    print(f"Delta0 = {z0 - z_mono:.4f}   engine = {ENGINE_DELTA_X1:.4f}\n")

    Z = st["Z"]
    n = Z.shape[0]

    # Basis index bookkeeping: below arm has 4 segments -> bases 0..4 with
    # the node (value-1) basis LAST of the below set; above node basis is
    # the first above basis. probe3 named them 4 and 5 at x1.
    nb, na = 4, 5
    bset = np.arange(0, 5)
    aset = np.arange(5, n)
    interior_b = np.array([i for i in bset if i != nb])

    print(
        f"Z[{nb},{nb}] = {Z[nb, nb]:.1f}   Z[{na},{na}] = {Z[na, na]:.1f}   "
        f"Z[{nb},{na}] = {Z[nb, na]:.1f}   Z[{na},{nb}] = {Z[na, nb]:.1f}\n"
    )

    def pert(name, f):
        def hook(Zp):
            f(Zp)
            return Zp

        sp = seeded(crossing_deck(1))
        stp = capture(sp, t_ab=t_ab, a_seg=a_seg, b_seg=b_seg, z_hook=hook)
        z = stp["z_in"]
        d = z - z_mono
        print(
            f"  {name:>34}: Z_in = {z:9.4f}   Delta = {d:8.4f}   "
            f"dist = {abs(d - ENGINE_DELTA_X1):7.3f}",
            flush=True,
        )

    for fac in (0.5, 0.8, 1.2, 2.0):
        pert(
            f"below/below self x {fac}",
            lambda Zp, fac=fac: Zp.__setitem__(
                np.ix_(bset, bset), Zp[np.ix_(bset, bset)] * fac
            ),
        )
    print()
    for fac in (0.25, 0.5, 0.8, 1.2, 2.0, 4.0):
        pert(
            f"Z[nb,nb] x {fac}",
            lambda Zp, fac=fac: Zp.__setitem__((nb, nb), Zp[nb, nb] * fac),
        )
    print()
    for fac in (0.5, 0.8, 1.2, 2.0):
        pert(
            f"interior below block x {fac}",
            lambda Zp, fac=fac: Zp.__setitem__(
                np.ix_(interior_b, interior_b), Zp[np.ix_(interior_b, interior_b)] * fac
            ),
        )
    print()
    for fac in (0.0, 0.5, 1.5, 2.0, -1.0):
        pert(
            f"cross blocks x {fac}",
            lambda Zp, fac=fac: (
                Zp.__setitem__(np.ix_(aset, bset), Zp[np.ix_(aset, bset)] * fac),
                Zp.__setitem__(np.ix_(bset, aset), Zp[np.ix_(bset, aset)] * fac),
            ),
        )
    print()
    # The two node bases specifically: their mutual entries carry the
    # coincident-end physics.
    for fac in (0.0, 0.5, 2.0):
        pert(
            f"Z[nb,na],Z[na,nb] x {fac}",
            lambda Zp, fac=fac: (
                Zp.__setitem__((nb, na), Zp[nb, na] * fac),
                Zp.__setitem__((na, nb), Zp[na, nb] * fac),
            ),
        )


if __name__ == "__main__":
    main()
