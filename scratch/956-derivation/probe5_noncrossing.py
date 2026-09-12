"""momwire#956 derivation, probe 5: the corrected spelling against momwire's OWN
transmitted-grid field form on a deck that shares no by-parts machinery.

probe20 (Haswell) showed that on a NON-crossing mixed deck the assembled cross
entry IS `_field_galerkin_block` over the transmitted grid, to 3.5e-10. That
deck never routes through `_crossing_fill`, so here the crossing fill's dense
spelling is evaluated on the same deck's axes -- shipped and with the W terms
transverse-masked -- and both are compared, entry by entry, with the grid field
form the solver actually assembles. Nothing in this comparison shares a by-parts
identity with probe1: the grid route is AGARD (7a-7e) interpolated, the fill is
the mixed-potential sandwich on designed tables.

Expected if the derivation is right: the masked spelling agrees with the field
form to the grid's own accuracy on the on-axis (vertical x vertical) block; the
shipped spelling departs there by the W terms; both agree on the off-axis wire.
"""

import os
import sys

os.environ.setdefault("MOMWIRE_CROSSING_FORCE_DENSE", "1")
for _v in ("OMP_NUM_THREADS", "OPENBLAS_NUM_THREADS", "MKL_NUM_THREADS"):
    os.environ.setdefault(_v, "4")

import warnings  # noqa: E402
from pathlib import Path  # noqa: E402

import numpy as np  # noqa: E402

warnings.filterwarnings("ignore")
HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent / "956-oracle"))
sys.path.insert(0, str(HERE))

import probe2_impedance as P2  # noqa: E402  (installs the patches)
from momwire import _crossing_fill as CF  # noqa: E402
from probe20_contraction import noncrossing_deck  # noqa: E402


def rel(x, y):
    return float(np.abs(x - y).max() / max(np.abs(y).max(), 1e-300))


def main():
    s = noncrossing_deck()
    geom = s._build_geometry()
    supp_seg, polys, *_ = s._build_basis_polynomials(geom)
    below = s._below_segments(geom)
    a_idx = np.nonzero(~below)[0]
    b_idx = np.nonzero(below)[0]
    Z = s._compute_Z_operator(geom, supp_seg, polys)  # the grid route (no crossing)
    ctx = s._crossing_context(geom, supp_seg, polys)
    A = CF.axis_data(ctx, a_idx)
    B = CF.axis_data(ctx, b_idx)
    print(
        f"non-crossing deck: {a_idx.size} above / {b_idx.size} below segments, n_basis {A['n_basis']}, ends above {len(A['ends'])} below {len(B['ends'])}"
    )

    P2.FIX["W"] = False
    shipped = CF.cross_complete_block(ctx, A, B, corner=True)
    P2.FIX["W"] = True
    fixed = CF.cross_complete_block(ctx, A, B, corner=True)
    P2.FIX["W"] = False

    # rows/cols with support: the assembled cross quadrant is Z[m, n] = -t_ab[m, n]
    live_a = np.flatnonzero(np.abs(A["F"]).sum(axis=1) > 0)
    live_b = np.flatnonzero(np.abs(B["F"]).sum(axis=1) > 0)
    ff = -Z[np.ix_(live_a, live_b)]
    on_axis_b = np.array(
        [
            bool(
                np.all(
                    np.hypot(B["nodes"][:, 0], B["nodes"][:, 1])[np.abs(B["F"][n]) > 0]
                    < 1e-9
                )
            )
            for n in live_b
        ]
    )
    sh = shipped[np.ix_(live_a, live_b)]
    fx = fixed[np.ix_(live_a, live_b)]
    for label, mask in (
        ("on-axis (vertical x vertical)", on_axis_b),
        ("off-axis wire", ~on_axis_b),
    ):
        cols = np.flatnonzero(mask)
        if cols.size == 0:
            continue
        print(f"\n{label}: {cols.size} below bases")
        print(f"   shipped vs grid field form : {rel(sh[:, cols], ff[:, cols]):.3e}")
        print(f"   fixed   vs grid field form : {rel(fx[:, cols], ff[:, cols]):.3e}")
        print(
            f"   |shipped - fixed| max      : {np.abs(sh[:, cols] - fx[:, cols]).max():.3e}   (|ff| max {np.abs(ff[:, cols]).max():.3e})"
        )
    # a few on-axis entries
    cols = np.flatnonzero(on_axis_b)
    print(
        f"\n{'entry':>9} {'|ff grid|':>11} {'|shipped|':>11} {'ship/ff-1':>10} {'|fixed|':>11} {'fix/ff-1':>10}"
    )
    idx = np.argsort(-np.abs(ff[:, cols]).ravel())[:10]
    for k in idx:
        i, j = np.unravel_index(k, ff[:, cols].shape)
        f0, s0, x0 = ff[i, cols[j]], sh[i, cols[j]], fx[i, cols[j]]
        print(
            f"{live_a[i]:>4}x{live_b[cols[j]]:<4} {abs(f0):11.4e} {abs(s0):11.4e} {abs(s0 / f0 - 1):10.2e} {abs(x0):11.4e} {abs(x0 / f0 - 1):10.2e}"
        )


if __name__ == "__main__":
    main()
