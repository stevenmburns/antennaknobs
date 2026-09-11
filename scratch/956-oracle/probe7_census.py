"""#956 Phase B: the full disagreement census, geometry attached.

The projectors agree (probe6): 1.6e-06 to 1.1e-04 at every off-axis offset, and
the only rel = 1.0 row is rho = 0 exactly, where BOTH read zero (momwire
6.3e-14, prototype 0.0) — E_z of a horizontal dipole on its own vertical axis.
So a surviving block disagreement is not the kernel. This lists every entry
that disagrees and says what geometry it stands for.
"""

import sys
import warnings
from pathlib import Path

import numpy as np

warnings.filterwarnings("ignore")
sys.path.insert(0, str(Path(__file__).resolve().parent))

from probe3_cross_block import build, parts, solver_of  # noqa: E402
from probe5_partition import basis_support  # noqa: E402


def describe(supp_seg, polys, seg_l, seg_r, m):
    live = ~np.all(np.abs(polys[m]) == 0.0, axis=1)
    out = []
    for a in range(supp_seg.shape[1]):
        if not live[a]:
            continue
        sg = int(supp_seg[m, a])
        out.append(
            f"{sg}:[{seg_l[sg][0]:.3f},{seg_l[sg][1]:.3f},{seg_l[sg][2]:.3f}]"
            f"->[{seg_r[sg][0]:.3f},{seg_r[sg][1]:.3f},{seg_r[sg][2]:.3f}]"
        )
    return " ".join(out)


def main():
    b = build()
    s = solver_of(b)
    geom, supp_seg, polys, a_idx, b_idx = parts(s)
    seg_l = np.asarray(geom["seg_l"])
    seg_r = np.asarray(geom["seg_r"])
    here = Path(__file__).resolve().parent / "blocks"
    tag = f"r{b.n_radials}_d{b.depth}"
    mw = np.load(here / f"mw_{tag}.npy")
    ob = np.load(here / f"oracle_{tag}_q1.npy")

    sup_a = basis_support(geom, supp_seg, a_idx, polys)
    sup_b = basis_support(geom, supp_seg, b_idx, polys)
    rows = [m for m in range(len(sup_a)) if len(sup_a[m])]
    cols = [n for n in range(len(sup_b)) if len(sup_b[n])]

    scale = float(np.abs(mw[np.ix_(rows, cols)]).max())
    recs = []
    for m in rows:
        for n in cols:
            a, o = mw[m, n], ob[m, n]
            if abs(a) < 1e-6 * scale and abs(o) < 1e-6 * scale:
                continue
            rel = abs(o - a) / max(abs(a), 1e-300)
            if rel < 1e-2:
                continue
            d = np.linalg.norm(
                sup_a[m][:, None, :] - sup_b[n][None, :, :], axis=-1
            ).min()
            recs.append((rel, d, m, n, a, o))
    recs.sort(reverse=True)
    live_pairs = sum(
        1
        for m in rows
        for n in cols
        if abs(mw[m, n]) >= 1e-6 * scale or abs(ob[m, n]) >= 1e-6 * scale
    )
    print(f"live entries (|.| >= 1e-6 of block max): {live_pairs}")
    print(f"entries disagreeing by >= 1 %: {len(recs)}\n")
    for rel, d, m, n, a, o in recs[:20]:
        print(f"rel {rel:9.4e}  sep {d:9.4e} m   basis {m:3d} x {n:3d}")
        print(
            f"   momwire {a.real:12.5e}{a.imag:+12.5e}j   "
            f"oracle {o.real:12.5e}{o.imag:+12.5e}j   |o|/|m| {abs(o) / abs(a):.4e}"
        )
        print(f"   above  {describe(supp_seg, polys, seg_l, seg_r, m)}")
        print(f"   below  {describe(supp_seg, polys, seg_l, seg_r, n)}")


if __name__ == "__main__":
    main()
