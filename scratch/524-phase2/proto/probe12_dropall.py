"""A-2: the consistent crossing spelling — drop ALL node-charge terms, merge.

Physics: with the merged (value-1 both arms) crossing dof, the node's
by-parts point charges cancel in pairs (above-arm sign -1, below-arm +1)
PROVIDED every block tests them with the interface-consistent kernel — a
kernel with one point ON the interface is one object seen from either
side. So dropping them all consistently is exact (up to O(ka) and the
dynamic W-type node corrections), and numerically kind: no 1.5 kOhm
cancellations left to quadrature.

What that means per block (t-convention, mp_cross signs):
  cross (above x below):  t_ab = M + SW      (SQ, BT, corner all dropped —
                          the corner was MEASURED off probe5's residual:
                          r[5,4] = 1512.6-1658.5j, single-entry)
  below/below self:       subtract T_bb, S_bb, C_bb (node-charge terms,
                          kernel = V_T with the observer leg at z = 0)
  above/above self:       subtract T_aa, S_aa, C_aa (kernel = V_T with the
                          source leg at z' = 0-)

Then merge the node dofs (probe10) and score in Delta vs engine x1.

Step 0 validates the machinery: corner_pred = c1 * V_T(a, 0, 0-) must
reproduce the measured residual in sign and magnitude.

Run: .venv/bin/python scratch/524-phase2/proto/probe12_dropall.py
"""

from __future__ import annotations

import sys
from pathlib import Path

import numpy as np

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "567-phase0" / "proto"))
sys.path.insert(0, str(Path(__file__).resolve().parents[3] / "momwire" / "tests"))

import mp_cross  # noqa: E402
from momwire.bspline import BSplineSolver  # noqa: E402
from momwire._sommerfeld_transmitted import _c1_moment  # noqa: E402
from probe1_baseline import crossing_deck, seeded  # noqa: E402
from probe8_split import build_pieces, mono_deck  # noqa: E402
from probe9_sense import capture  # noqa: E402
from probe10_merge import NB, NA, merge_hook  # noqa: E402

ENGINE_DELTA_X1 = -2.3260 - 0.7130j
CORNER_MEASURED = 1512.61 - 1658.55j  # probe5 residual [5,4]
A_WIRE = 0.001

_orig_mp_tables = mp_cross.mp_tables


def _clamped(eps_t, k_p, rho, z, zp, rtol=1e-10):
    zp = np.minimum(np.asarray(zp, dtype=np.float64), -1e-9)
    return _orig_mp_tables(eps_t, k_p, rho, z, zp, rtol=rtol)


mp_cross.mp_tables = _clamped


def main():
    pieces = build_pieces(1)
    M, SW = pieces["M"], pieces["SW"]
    t_ab = M + SW  # cross spelling: everything node-charge dropped

    s = seeded(crossing_deck(1))
    geom = s._build_geometry()
    below = s._below_segments(geom)
    b_seg = np.sort(np.nonzero(below)[0])
    a_seg = np.sort(np.nonzero(~below)[0])
    eps_t, _eps_m, k_p, _k_m, _c2, _a_m = s._buried_medium()
    c1 = _c1_moment(s.omega, s.mu)

    A = mp_cross.axis_data(s, geom, a_seg)
    B = mp_cross.axis_data(s, geom, b_seg)
    n_basis = A["n_basis"]

    # --- the corner value: MEASURED, not integrated -------------------------
    # The contour cannot converge with both legs on the interface at rho = a,
    # but the cross corner is already measured (probe5 residual [5,4]) and
    # sign bookkeeping fixes the self corners with no new unknowns:
    #   cross corner (t-conv) = s_c*c1*sA*sB*v = -s_c*c1*v = CORNER_MEASURED
    #   self  corner (t-conv) = s_c*c1*(+1)*v  = -CORNER_MEASURED
    # (same interface kernel value for all four blocks, up to O(k*a)).
    self_corner = -CORNER_MEASURED
    print(f"  self corner (from measured cross corner) = {self_corner:.2f}")
    print(f"  implied c1*v_corner magnitude = {abs(CORNER_MEASURED):.1f}\n")

    # --- node-charge columns via the interface-consistent kernel ------------
    # On-axis rho = 0, the same spelling as the shipped end-table calls;
    # convergence comes from the e^{-gamma|z|} decay of the off-node leg.
    an = A["nodes"]
    rho_a = np.hypot(an[:, 0], an[:, 1])
    ta = _clamped(eps_t, k_p, rho_a, an[:, 2], np.full(len(an), -1e-9))
    v_above_col = ta["V"]  # V(node -> above points)

    bn = B["nodes"]
    rho_b = np.hypot(bn[:, 0], bn[:, 1])
    tb = _clamped(eps_t, k_p, rho_b, np.zeros(len(bn)), bn[:, 2])
    v_below_col = tb["V"]  # V(node -> below points), obs leg on interface

    FdA_w = A["Fd"] * A["w"]
    FdB_w = B["Fd"] * B["w"]
    e_na = np.zeros(n_basis)
    e_na[NA] = 1.0
    e_nb = np.zeros(n_basis)
    e_nb[NB] = 1.0

    s_above, s_below = -1.0, +1.0  # node is the above wire's START, below's END
    col_a = FdA_w @ v_above_col
    col_b = FdB_w @ v_below_col

    T_aa = c1 * s_above * np.outer(e_na, col_a)
    S_aa = c1 * s_above * np.outer(col_a, e_na)
    T_bb = c1 * s_below * np.outer(e_nb, col_b)
    S_bb = c1 * s_below * np.outer(col_b, e_nb)

    def corners(sign):
        # sign=+1 uses the bookkeeping value; -1 is the contrast spelling.
        C_aa = sign * self_corner * np.outer(e_na, e_na)
        C_bb = sign * self_corner * np.outer(e_nb, e_nb)
        return C_aa, C_bb

    # --- assembly sign: compare the naive captured Z with the shipped t -----
    d5 = np.load(HERE.parent / "results" / "probe5-blocks.npz")
    st_naive = capture(seeded(crossing_deck(1)))
    alpha = st_naive["Z"][NA, NB] / d5["shipped_ab"][NA, NB]
    print(f"  assembly sign alpha = {alpha:.4f}  (expect ~ -1 or +1)\n")

    z_mono = capture(BSplineSolver(**mono_deck(1)))["z_in"]
    target = z_mono + ENGINE_DELTA_X1
    print(f"  mono = {z_mono:.4f}   target Z_in = {target:.4f}\n")

    def run(name, corr_t, merged, cross_t):
        def hook(Zp):
            if corr_t is not None:
                Zp -= alpha * corr_t
            if merged:
                Zp = merge_hook(Zp)
            return Zp

        st = capture(
            seeded(crossing_deck(1)),
            t_ab=cross_t,
            a_seg=a_seg,
            b_seg=b_seg,
            z_hook=hook,
        )
        z = st["z_in"]
        d = z - z_mono
        print(
            f"  {name:>38}: Z_in = {z:9.4f}   Delta = {d:9.4f}   "
            f"dist = {abs(d - ENGINE_DELTA_X1):8.3f}",
            flush=True,
        )

    TS = T_aa + S_aa + T_bb + S_bb
    for s_c in (+1.0, -1.0):
        C_aa, C_bb = corners(s_c)
        run(f"dropall (s_c={s_c:+.0f}) + merged", TS + C_aa + C_bb, True, t_ab)
    run("drop T/S only (no corners) + merged", TS, True, t_ab)
    run("dropall (s_c=+1) split", TS + sum(corners(+1.0)), False, t_ab)
    run(
        "self-drops only, cross=B, merged",
        TS + sum(corners(+1.0)),
        True,
        pieces["M"] + pieces["SW"] + pieces["SQ"],
    )
    run("no self-drops (=probe10 dropBoth+merged)", None, True, t_ab)


if __name__ == "__main__":
    main()
