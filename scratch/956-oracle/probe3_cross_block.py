"""#956 Phase B: price the rise deck's below<->above cross block against the
phase-0 prototype, and substitute it back into the solve.

On a CROSSING deck the cross pair does not go through the transmitted grid at
all — `compute_Z_operator_buried` routes it to `_crossing_fill`'s designed
complete mixed-potential spelling (`cross_complete_block_split`), by-parts
ends and corner included. So the quantity under test is that block, and the
independent comparison is the honest FIELD form of the same interaction:

    t_ab_oracle = _field_galerkin_block(..., proj_oracle, ...)

assembled by momwire's OWN basis contraction with only the Green's function
replaced (see `proj_oracle`). The two forms differ by an integration-by-parts
boundary term that the crossing fill supplies deliberately; agreement is
therefore a statement that its bookkeeping is right, and a disagreement of the
size of #956's ~2 ohm is the term.

Modes:
  gate2   the substitution plumbing is neutral: feed momwire's OWN block back
          through the patch and require the solved Z bit-for-bit.
  ladder  the oracle block at a quadrature ladder, with the block difference
          against momwire's reported per rung (the peer's gate 1).
  price   substitute the oracle block and read R.
"""

import argparse
import sys
import time
import warnings
from pathlib import Path

import numpy as np

warnings.filterwarnings("ignore")
sys.path.insert(0, str(Path(__file__).resolve().parent))

from antennaknobs.designs.verticals.buried_radial_vertical import (  # noqa: E402
    Builder,
)
from antennaknobs.engines.momwire import MomwireEngine  # noqa: E402
from momwire import _crossing_fill  # noqa: E402

import proj_oracle as PO  # noqa: E402


C0 = 299792458.0
SOIL_A = (13.0, 0.005)
FREQ = 7.1e6


def build(n_radials=4, depth=None, nominal_nsegs=None):
    b = Builder()
    b.n_radials = n_radials
    b.design_eps_r, b.design_sigma = SOIL_A
    if depth is not None:
        b.depth = depth
    if nominal_nsegs is not None:
        b.nominal_nsegs = nominal_nsegs
    return b


def solver_of(b):
    eng = MomwireEngine(b, ground=("finite", *SOIL_A))
    return eng._make_solver(wavelength=C0 / (b.freq * 1e6))


def parts(s):
    """Everything the cross block is assembled from, once."""
    geom = s._build_geometry()
    supp_seg, polys, *_ = s._build_basis_polynomials(geom)
    below = s._below_segments(geom)
    a_idx = np.nonzero(~below)[0]
    b_idx = np.nonzero(below)[0]
    return geom, supp_seg, polys, a_idx, b_idx


def momwire_block(s, geom, supp_seg, polys, a_idx, b_idx):
    ctx = s._crossing_context(geom, supp_seg, polys)
    ax_a = _crossing_fill.axis_data(ctx, a_idx)
    ax_b = _crossing_fill.axis_data(ctx, b_idx)
    return _crossing_fill.cross_complete_block_split(ctx, a_idx, b_idx, ax_a, ax_b)


def solve_with(s, block=None):
    """Z with `cross_complete_block_split` replaced by a constant block."""
    real = _crossing_fill.cross_complete_block_split
    calls = []
    if block is not None:

        def patched(ctx, a_idx, b_idx, ax_a, ax_b):
            calls.append(1)
            return block

        _crossing_fill.cross_complete_block_split = patched
    try:
        z, _ = s.compute_impedance()
    finally:
        _crossing_fill.cross_complete_block_split = real
    return complex(z), len(calls)


def gate2(args):
    """The substitution plumbing is neutral."""
    b = build(n_radials=args.n_radials, depth=args.depth)
    s = solver_of(b)
    geom, supp_seg, polys, a_idx, b_idx = parts(s)
    blk = momwire_block(s, geom, supp_seg, polys, a_idx, b_idx)
    print(f"cross block {blk.shape}, |max| {np.abs(blk).max():.6e}")

    z_plain, n0 = solve_with(solver_of(b))
    z_patched, n1 = solve_with(solver_of(b), block=blk)
    print(f"unpatched  Z = {z_plain!r}   (patch calls {n0})")
    print(f"patched    Z = {z_patched!r}   (patch calls {n1})")
    if n1 == 0:
        raise SystemExit("GATE 2 FAIL: the patch was never called — inert harness")
    same = z_plain == z_patched
    print(f"\nGATE 2 {'PASS' if same else 'FAIL'}: bit-identical = {same}")
    if not same:
        print(
            f"  difference {abs(z_plain - z_patched):.6e} "
            f"({abs(z_plain - z_patched) / abs(z_plain):.3e} relative)"
        )
    # and the negative half: a block that is NOT momwire's must MOVE Z, or the
    # patch is being ignored for a reason the equality above cannot see.
    z_zero, _ = solve_with(solver_of(b), block=np.zeros_like(blk))
    moved = abs(z_zero - z_plain) / abs(z_plain)
    print(f"zeroed block Z = {z_zero!r}  -> moved {moved:.3e} relative")
    if moved < 1e-9:
        raise SystemExit("GATE 2 FAIL: zeroing the block did not move Z")
    return same


def oracle_block(s, geom, supp_seg, polys, a_idx, b_idx, q_factor, workers):
    """momwire's OWN basis contraction over the prototype's kernel.

    `_field_galerkin_block` supplies the moment weights, the wing sums and the
    chunking; `proj_oracle` supplies the Green's function. Nothing else
    differs, which is what makes a block difference attributable.
    """
    obs_a, t_a, W_a = s._buried_nodes(geom, a_idx, q_factor=q_factor)
    obs_b, t_b, W_b = s._buried_nodes(geom, b_idx, q_factor=q_factor)
    proj = PO.make_proj(FREQ, *SOIL_A, workers=workers)
    return s._field_galerkin_block(
        supp_seg, polys, proj, a_idx, b_idx, obs_a, t_a, W_a, obs_b, t_b, W_b
    )


def _rel(a, b):
    """Graded against b's OWN magnitude, both signs reported — a ratio pinned
    at 2.0 is a sign convention, not an error (momwire#1004's lesson)."""
    sc = max(float(np.abs(b).max()), 1e-300)
    return (
        float(np.abs(a - b).max() / sc),
        float(np.abs(a + b).max() / sc),
        sc,
    )


def ladder(args):
    b = build(n_radials=args.n_radials, depth=args.depth)
    s = solver_of(b)
    geom, supp_seg, polys, a_idx, b_idx = parts(s)
    mw = momwire_block(s, geom, supp_seg, polys, a_idx, b_idx)
    z_plain, _ = solve_with(solver_of(b))
    print(
        f"deck: n_radials {b.n_radials}  depth {b.depth} m  "
        f"segs above {len(a_idx)} below {len(b_idx)}"
    )
    print(f"momwire block |max| {np.abs(mw).max():.6e}   Z = {z_plain!r}")
    out = Path(__file__).resolve().parent / "blocks"
    out.mkdir(exist_ok=True)
    tag = f"r{args.n_radials}_d{b.depth}"
    np.save(out / f"mw_{tag}.npy", mw)
    for qf in args.q_factors:
        t0 = time.time()
        ob = oracle_block(s, geom, supp_seg, polys, a_idx, b_idx, qf, args.workers)
        dt = time.time() - t0
        np.save(out / f"oracle_{tag}_q{qf}.npy", ob)
        minus, plus, sc = _rel(ob, mw)
        z_sub, ncall = solve_with(solver_of(b), block=ob)
        dR = z_sub.real - z_plain.real
        print(
            f"  q_factor {qf:2d} (q={qf * s._n_qp_buried_field():3d})  "
            f"{dt / 60:6.1f} min   |o-m|/|m| {minus:.4e}  |o+m|/|m| {plus:.4e}   "
            f"Z_sub {z_sub.real:9.4f}{z_sub.imag:+9.4f}j   dR {dR:+8.4f} ohm"
            f"   [calls {ncall}]"
        )
        sys.stdout.flush()


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("mode", choices=["gate2", "ladder"])
    ap.add_argument("--n-radials", type=int, default=4)
    ap.add_argument("--depth", type=float, default=None)
    ap.add_argument("--q-factors", type=int, nargs="+", default=[1])
    ap.add_argument("--workers", type=int, default=7)
    args = ap.parse_args()
    if args.mode == "gate2":
        gate2(args)
    else:
        ladder(args)


if __name__ == "__main__":
    main()
