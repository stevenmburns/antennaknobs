"""#956 Phase B gate 1, resolved by population.

The on-axis sub-block does not converge in q at all — worst-vs-momwire runs
1.72e-01 -> 3.27 -> 17.7 at q = 6 / 12 / 24, with rung-to-rung self-convergence
of 4.15 and 3.38. A quantity that GROWS with quadrature order is a divergent
integral being resolved, not an integral being resolved. That is the touching
collinear pairs at the node, and it is expected: on-axis zero-radius field form
over two segments that share an endpoint has no finite value.

The question gate 1 actually has to answer is narrower: do the FAR on-axis
entries — the ones probe8 priced at +0.46 ohm — converge, or do they drift with
the near ones? Same saved rungs, split by separation.
"""

import sys
import warnings
from pathlib import Path

import numpy as np

warnings.filterwarnings("ignore")
sys.path.insert(0, str(Path(__file__).resolve().parent))

from probe3_cross_block import (  # noqa: E402
    build,
    momwire_block,
    parts,
    solve_with,
    solver_of,
)
from probe5_partition import basis_support  # noqa: E402
from probe9_qladder import axis_segments  # noqa: E402


def main():
    b = build()
    s = solver_of(b)
    geom, supp_seg, polys, a_idx, b_idx = parts(s)
    aa = axis_segments(geom, a_idx)
    bb = axis_segments(geom, b_idx)
    mw = momwire_block(s, geom, supp_seg, polys, a_idx, b_idx)
    here = Path(__file__).resolve().parent / "blocks"

    sup_a = basis_support(geom, supp_seg, aa, polys)
    sup_b = basis_support(geom, supp_seg, bb, polys)
    D = np.full(mw.shape, np.inf)
    for m in range(len(sup_a)):
        if not len(sup_a[m]):
            continue
        for n in range(len(sup_b)):
            if not len(sup_b[n]):
                continue
            D[m, n] = np.linalg.norm(
                sup_a[m][:, None, :] - sup_b[n][None, :, :], axis=-1
            ).min()

    rungs = {}
    for qf in (1, 2, 4):
        p = here / f"axis_q{qf}.npy"
        if p.exists():
            rungs[qf] = np.load(p)
    z0, _ = solve_with(solver_of(b))
    print(f"momwire Z = {z0.real:.4f}{z0.imag:+.4f}j")
    print(
        f"\n{'threshold':>12} {'entries':>8} "
        + " ".join(f"{'q=' + str(6 * q):>13}" for q in rungs)
        + f" {'max drift':>11} {'dR(finest)':>11}"
    )
    for thr in (0.0, 0.05, 0.1, 0.25, 0.5, 1.0):
        msk = np.isfinite(D) & (D >= thr)
        if not msk.any():
            continue
        sums = []
        for qf in rungs:
            sums.append(float(np.abs(rungs[qf][msk]).max()))
        # rung-to-rung drift on THIS population only, relative to the last rung
        keys = sorted(rungs)
        drift = 0.0
        for i in range(1, len(keys)):
            a, c = rungs[keys[i - 1]], rungs[keys[i]]
            sc = max(float(np.abs(c[msk]).max()), 1e-300)
            drift = max(drift, float(np.abs(c[msk] - a[msk]).max() / sc))
        blk = mw.copy()
        blk[msk] = rungs[keys[-1]][msk]
        z, ncall = solve_with(solver_of(b), block=blk)
        assert ncall == 1
        print(
            f"{thr:12.3f} {int(msk.sum()):8d} "
            + " ".join(f"{v:13.4e}" for v in sums)
            + f" {drift:11.4e} {z.real - z0.real:+11.4f}"
        )
        sys.stdout.flush()

    # and the same substitution at EVERY rung on the population that matters,
    # because a stable dR across q is the only thing that licenses quoting it
    print(
        f"\n{'threshold':>12} "
        + " ".join(f"{'dR q=' + str(6 * q):>12}" for q in sorted(rungs))
    )
    for thr in (0.25, 0.5, 1.0):
        msk = np.isfinite(D) & (D >= thr)
        cells = []
        for qf in sorted(rungs):
            blk = mw.copy()
            blk[msk] = rungs[qf][msk]
            z, _ = solve_with(solver_of(b), block=blk)
            cells.append(z.real - z0.real)
        print(f"{thr:12.3f} " + " ".join(f"{v:+12.4f}" for v in cells))
        sys.stdout.flush()


if __name__ == "__main__":
    main()
