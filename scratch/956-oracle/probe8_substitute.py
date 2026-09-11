"""#956 Phase B: substitute the oracle's entries by POPULATION and read R.

probe7's census: the block's disagreement is not spread over the block. It is

  * four TOUCHING collinear pairs at the node — where the field-form oracle is
    the zero-radius limit of a divergent integral and is NOT an instrument; and
  * the on-axis RISE x RADIATOR pairs at 0.6-0.9 m, where the oracle runs 9-21 %
    ABOVE momwire and nothing else does (off-axis pairs beyond 0.25 m agree to
    a median of 1.05e-08).

The second population has every signature #956's residual has: it exists only
because a conductor runs up the axis to the plane, its count grows with the
rise, it is flat in radial count and radial length, and it vanishes with the
rise rather than leaving an intercept. So the number that matters is what
substituting JUST that population does to R — not what substituting the whole
block does, which is dominated by the touching pairs the oracle cannot serve.
"""

import sys
import warnings
from pathlib import Path

import numpy as np

warnings.filterwarnings("ignore")
sys.path.insert(0, str(Path(__file__).resolve().parent))

from probe3_cross_block import build, parts, solve_with, solver_of  # noqa: E402
from probe5_partition import basis_support  # noqa: E402


def on_axis(pts, tol=1e-9):
    return bool(len(pts)) and bool(np.all(np.abs(pts[:, :2]) < tol))


def main():
    b = build()
    s = solver_of(b)
    geom, supp_seg, polys, a_idx, b_idx = parts(s)
    here = Path(__file__).resolve().parent / "blocks"
    tag = f"r{b.n_radials}_d{b.depth}"
    mw = np.load(here / f"mw_{tag}.npy")
    ob = np.load(here / f"oracle_{tag}_q1.npy")

    sup_a = basis_support(geom, supp_seg, a_idx, polys)
    sup_b = basis_support(geom, supp_seg, b_idx, polys)
    rows = [m for m in range(len(sup_a)) if len(sup_a[m])]
    cols = [n for n in range(len(sup_b)) if len(sup_b[n])]

    D = np.full(mw.shape, np.inf)
    AX = np.zeros(mw.shape, bool)
    for m in rows:
        for n in cols:
            D[m, n] = np.linalg.norm(
                sup_a[m][:, None, :] - sup_b[n][None, :, :], axis=-1
            ).min()
            AX[m, n] = on_axis(sup_a[m]) and on_axis(sup_b[n])

    z0, _ = solve_with(solver_of(b))
    print(f"momwire            Z = {z0.real:10.4f}{z0.imag:+10.4f}j")
    print(f"{'population':>34} {'entries':>8} {'R':>10} {'X':>10} {'dR':>9}")

    def run(name, mask):
        blk = mw.copy()
        blk[mask] = ob[mask]
        z, ncall = solve_with(solver_of(b), block=blk)
        assert ncall == 1, ncall
        print(
            f"{name:>34} {int(mask.sum()):8d} {z.real:10.4f} {z.imag:+10.4f} "
            f"{z.real - z0.real:+9.4f}"
        )
        sys.stdout.flush()
        return z

    finite = np.isfinite(D)
    for thr in (0.25, 0.1):
        run(f"all pairs >= {thr} m", finite & (D >= thr))
        run(f"ON-AXIS pairs >= {thr} m", finite & (D >= thr) & AX)
        run(f"off-axis pairs >= {thr} m", finite & (D >= thr) & ~AX)
    run("touching pairs only (sep = 0)", finite & (D <= 1e-12))
    run("everything except touching", finite & (D > 1e-12))


if __name__ == "__main__":
    main()
