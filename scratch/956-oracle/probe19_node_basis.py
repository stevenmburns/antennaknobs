"""#956: is entry (228, 220) a KERNEL question or a BASIS question?

Phase 1's whole failure is one entry: the crossing-node above basis against the
hub-end rise basis, 0.1 m apart on the axis, where momwire's assembled Z reads
1.4649e+02 and my field form reads 2.53 % of it.

This removes the kernel from the comparison. The same `_field_galerkin_block`
contraction over the same `supp_seg`/`polys` basis, driven by MOMWIRE'S OWN
transmitted projector instead of the prototype's:

  (a) momwire kernel + supp_seg/polys basis   <- if this equals my 3.7, the
                                                 kernel is not the difference
  (b) prototype kernel + supp_seg/polys basis <- my instrument
  (c) momwire's ASSEMBLED Z entry             <- what the fill actually puts there

If (a) == (b) != (c), the disagreement is not in the Green's function at all: it
is the basis representation or the crossing fill's spelling. If (a) == (c) != (b),
it is the kernel, and my gates said that is right on non-node pairs.

A well-separated control entry runs beside it, so "the three agree" is shown to
be reachable by this harness at all.
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

from momwire import _sommerfeld_transmitted as trans  # noqa: E402

from probe3_cross_block import build, parts, solver_of  # noqa: E402
from probe16_phase1 import axis_segs  # noqa: E402

C0 = 299792458.0
FREQ = 7.1e6
SOIL_A = (13.0, 0.005)
EPS0 = 8.8541878128e-12
MU0 = 4.0e-7 * np.pi
GZ = 0.0


def medium():
    w = 2.0 * np.pi * FREQ
    eps_t = complex(SOIL_A[0]) - 1j * SOIL_A[1] / (w * EPS0)
    k_p = w / C0
    k_m = k_p * np.sqrt(eps_t)
    if k_m.imag > 0:
        k_m = np.conj(k_m)
    return eps_t, k_p, complex(k_m), w


def main():
    eps_t, k_p, k_m, w = medium()
    b = build()
    s = solver_of(b)
    geom, supp_seg, polys, a_idx, b_idx = parts(s)
    Z = s._compute_Z_operator(geom, supp_seg, polys)
    ia = axis_segs(geom, a_idx)
    ib = axis_segs(geom, b_idx)
    oa, ta, Wa = s._buried_nodes(geom, ia)
    ob, tb, Wb = s._buried_nodes(geom, ib)

    zp = GZ - ob[:, 2]
    cd = np.hypot(
        oa[:, 0][:, None] - ob[:, 0][None, :], oa[:, 1][:, None] - ob[:, 1][None, :]
    )
    r_obs = np.hypot(cd, (oa[:, 2] - GZ)[:, None])
    grid = trans.get_grid_below_above(
        eps_t,
        k_p,
        float(r_obs.max()) * 1.05,
        float(zp.min()),
        float(zp.max()),
        w,
        mu=MU0,
        r_min=float(r_obs.min()) * 0.95,
    )

    def mw_proj(o, to, sr, ts):
        return trans.transmitted_field_proj_below_to_above(
            o, to, sr, ts, GZ, k_p, k_m, grid
        )

    Q_mw = s._field_galerkin_block(
        supp_seg, polys, mw_proj, ia, ib, oa, ta, Wa, ob, tb, Wb
    )
    Q_proto = np.load(
        Path(__file__).resolve().parent / "blocks" / "phase1_Q_a0.0005_q1.npy"
    )

    print(
        f"{'entry':>12} {'(a) mw kernel':>26} {'(b) proto kernel':>26} "
        f"{'(c) assembled Z':>26}"
    )
    for m, n, label in ((228, 220, "the failure"), (239, 222, "control, far")):
        a_, b_, c_ = -Q_mw[m, n], -Q_proto[m, n], Z[m, n]
        print(
            f"{f'{m}x{n}':>12} {a_.real:12.5e}{a_.imag:+12.5e}j "
            f"{b_.real:12.5e}{b_.imag:+12.5e}j "
            f"{c_.real:12.5e}{c_.imag:+12.5e}j   ({label})"
        )
        print(
            f"{'':>12} |a-b|/|c| {abs(a_ - b_) / abs(c_):.4e}   "
            f"|a-c|/|c| {abs(a_ - c_) / abs(c_):.4e}   "
            f"|b-c|/|c| {abs(b_ - c_) / abs(c_):.4e}"
        )
        sys.stdout.flush()


if __name__ == "__main__":
    main()
