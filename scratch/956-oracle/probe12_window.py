"""#956: the validity window was a PROXY, and the proxy broke.

The rise ladder read +0.2124 / +0.4562 / +77.5334 ohm on rises of 0.075 / 0.15 /
0.30 m. The third is not physics. The off-axis control — which had held at
-0.00024 and -0.00013 ohm — broke at the same rung, reading -88.26. A control
that breaks when the measurement does says the INSTRUMENT failed, not that the
term changed.

Root cause: "separation >= 0.25 m" was never the real criterion. The pathology
is the CROSSING-NODE bases, which do not vanish at z = 0 and whose free-end
charges cancel only across pair classes. On the 0.15 m deck those bases happened
to sit inside 0.25 m of everything, so an absolute threshold excluded them. The
hub depth sets the radial depth too, so at 0.30 m the radials move OUTSIDE the
threshold while still pairing with the node bases — and the excluded population
walked back in.

So the window must name what it means: exclude every pair in which EITHER basis
touches the interface. The blocks are saved, so this is re-analysis and not a
re-run.
"""

import sys
import warnings
from pathlib import Path

import numpy as np

warnings.filterwarnings("ignore")
sys.path.insert(0, str(Path(__file__).resolve().parent))

from probe3_cross_block import build, parts, solve_with, solver_of  # noqa: E402
from probe5_partition import basis_support  # noqa: E402
from probe8_substitute import on_axis  # noqa: E402

Z_TOL = 1e-9


def touches_plane(pts):
    return bool(len(pts)) and bool(np.any(np.abs(pts[:, 2]) < Z_TOL))


def analyse(depth, floor):
    b = build(depth=depth)
    s = solver_of(b)
    geom, supp_seg, polys, a_idx, b_idx = parts(s)
    here = Path(__file__).resolve().parent / "blocks"
    mw = np.load(here / f"mw_rise_{depth}.npy")
    ob = np.load(here / f"oracle_rise_{depth}.npy")
    z0, _ = solve_with(solver_of(b))

    sup_a = basis_support(geom, supp_seg, a_idx, polys)
    sup_b = basis_support(geom, supp_seg, b_idx, polys)
    node_a = np.array([touches_plane(p) for p in sup_a])
    node_b = np.array([touches_plane(p) for p in sup_b])

    D = np.full(mw.shape, np.inf)
    AX = np.zeros(mw.shape, bool)
    for m in range(len(sup_a)):
        if not len(sup_a[m]):
            continue
        for n in range(len(sup_b)):
            if not len(sup_b[n]):
                continue
            D[m, n] = np.linalg.norm(
                sup_a[m][:, None, :] - sup_b[n][None, :, :], axis=-1
            ).min()
            AX[m, n] = on_axis(sup_a[m]) and on_axis(sup_b[n])

    clean = np.isfinite(D) & (D >= floor) & ~node_a[:, None] & ~node_b[None, :]

    def sub(mask):
        blk = mw.copy()
        blk[mask] = ob[mask]
        z, ncall = solve_with(solver_of(b), block=blk)
        assert ncall == 1
        return z.real - z0.real, int(mask.sum())

    d_on, n_on = sub(clean & AX)
    d_off, n_off = sub(clean & ~AX)
    print(
        f"  rise {depth:6.3f}  node-touching bases {int(node_a.sum())} above / "
        f"{int(node_b.sum())} below   ON-AXIS {d_on:+10.4f} ({n_on:4d})   "
        f"off-axis {d_off:+10.5f} ({n_off:5d})"
    )
    sys.stdout.flush()
    return depth, d_on, d_off


def main():
    floor = float(sys.argv[1]) if len(sys.argv) > 1 else 0.25
    print(f"window: no basis touching z = 0, AND separation >= {floor} m")
    rows = [analyse(d, floor) for d in (0.075, 0.15, 0.30)]
    print("\nrise-length scaling, on the NAMED window:")
    for i in range(1, len(rows)):
        d0, a0, _ = rows[i - 1]
        d1, a1, _ = rows[i]
        if a0:
            p = np.log(abs(a1 / a0)) / np.log(d1 / d0)
            print(
                f"  {d0:.3f} -> {d1:.3f} m : {a0:+.4f} -> {a1:+.4f}   "
                f"ratio {a1 / a0:8.3f}   exponent {p:+.2f}"
            )
    print("  (the residual itself: ~d^1.1)")


if __name__ == "__main__":
    main()
