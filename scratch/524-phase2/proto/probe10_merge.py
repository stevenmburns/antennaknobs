"""A-2: the MERGED crossing dof — Galerkin reduction, not Lagrange rows.

The two coincident value-1 node bases (below 4, above 5 at x1) have so far
been coupled by (a) the fill alone or (b) Lagrange rows (which over-
constrain and HURT). The untried spelling is the Galerkin-consistent one:
identify the two dofs, testing with the MERGED function too — Z' = P^T Z P.
That IS the C0 crossing basis (value 1 at the interface, both arms), with
the AGARD slope left EMERGENT in the interior bases.

Mechanically (v[4] = v[5] = 0 — the feed sits 4.33 m up the monopole, both
node tents vanish there):  col4 += col5; row4 += row5; dof 5 pinned to 0.

Grid: {naive fill, MP B_dropAboveQ, MP dropBothQ, MP A_keepAll} x
{split (today), merged}. Scored in Delta vs engine x1 = -2.3260 - 0.7130j.
Also prints the node coefficients I4, I5 of the un-merged B+none solution
(is continuity emergent already?).

Run: .venv/bin/python scratch/524-phase2/proto/probe10_merge.py
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
from probe9_sense import capture  # noqa: E402

ENGINE_DELTA_X1 = -2.3260 - 0.7130j
NB, NA = 4, 5


def merge_hook(Zp):
    Zp[:, NB] += Zp[:, NA]
    Zp[NB, :] += Zp[NA, :]
    Zp[NA, :] = 0.0
    Zp[:, NA] = 0.0
    Zp[NA, NA] = 1.0
    return Zp


def main():
    pieces = build_pieces(1)
    M, SW, SQ, BT = (pieces[k] for k in ("M", "SW", "SQ", "BT"))
    cross = {
        "naive_fill": None,
        "MP_B_dropAboveQ": M + SW + SQ,
        "MP_dropBothQ": M + SW,
        "MP_A_keepAll": M + SW + SQ + BT,
    }

    s = seeded(crossing_deck(1))
    geom = s._build_geometry()
    below = s._below_segments(geom)
    b_seg = np.sort(np.nonzero(below)[0])
    a_seg = np.sort(np.nonzero(~below)[0])

    z_mono = capture(BSplineSolver(**mono_deck(1)))["z_in"]
    print(f"mono = {z_mono:.4f}   engine Delta x1 = {ENGINE_DELTA_X1:.4f}\n")

    # Node coefficients of the un-merged B+none solution: stash the solve.
    sol_stash = {}
    orig_kcl = BSplineSolver._solve_with_kcl

    def spy_kcl(self, Z, v, kcl_A, overwrite=False):
        out = orig_kcl(self, Z, v, kcl_A, overwrite=False)
        sol_stash["I"] = np.array(out, copy=True)
        sol_stash["v"] = np.array(v, copy=True)
        return out

    BSplineSolver._solve_with_kcl = spy_kcl
    try:
        capture(
            seeded(crossing_deck(1)),
            t_ab=cross["MP_B_dropAboveQ"],
            a_seg=a_seg,
            b_seg=b_seg,
        )
    finally:
        BSplineSolver._solve_with_kcl = orig_kcl
    I = sol_stash["I"]
    print(f"B+none solution: I[{NB}] = {I[NB]:.6f}   I[{NA}] = {I[NA]:.6f}")
    print(
        f"  (v[{NB}] = {sol_stash['v'][NB]:.2e}, v[{NA}] = {sol_stash['v'][NA]:.2e} "
        "— both must be 0 for the hook-only merge)\n"
    )

    for cname, t_ab in cross.items():
        for mname, hook in (("split", None), ("merged", merge_hook)):
            st = capture(
                seeded(crossing_deck(1)),
                t_ab=t_ab,
                a_seg=a_seg,
                b_seg=b_seg,
                z_hook=hook,
            )
            z = st["z_in"]
            d = z - z_mono
            print(
                f"  {cname:>16} + {mname:<6}: Z_in = {z:9.4f}   "
                f"Delta = {d:8.4f}   dist = {abs(d - ENGINE_DELTA_X1):8.3f}",
                flush=True,
            )
        print()


if __name__ == "__main__":
    main()
