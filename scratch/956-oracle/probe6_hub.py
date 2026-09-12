"""#956 Phase B step 1: the hub four.

Four basis pairs at exactly 0.15 m separation read |o-m|/|m| = 1.0102 — the
oracle essentially ZERO where momwire reads 141.4. A ratio pinned at 1.0 is
"one side is zero", which is a projector question before it is a physics one.

Three instruments, cheapest first:

  who      WHICH pairs they are, and what geometry they stand for.
  proj     the two projectors entry for entry at exactly that configuration,
           plus an off-axis perturbation ladder: if the oracle's value comes up
           continuously toward momwire's as the observer leaves the axis, a
           rho -> 0 branch is the explanation and the hole is MINE. If both
           projectors read near zero there, the 141.4 is `_crossing_fill`'s own
           extra content and that is a different finding.
  block    the same field-form assembly driven by MOMWIRE's transmitted
           projector instead of the prototype's — the direct separation of
           "the kernel" from "the crossing fill's spelling", because it differs
           from the oracle block only in the Green's function and from
           momwire's block only in the form.
"""

import argparse
import sys
import warnings
from pathlib import Path

import numpy as np

warnings.filterwarnings("ignore")
sys.path.insert(0, str(Path(__file__).resolve().parent))

from momwire import _sommerfeld_transmitted as trans  # noqa: E402

import proj_oracle as PO  # noqa: E402
from probe3_cross_block import FREQ, SOIL_A, build, parts, solver_of  # noqa: E402
from probe5_partition import basis_support  # noqa: E402

EPS0 = 8.8541878128e-12
MU0 = 4.0e-7 * np.pi
GZ = 0.0


def medium():
    w = 2.0 * np.pi * FREQ
    eps_t = complex(SOIL_A[0]) - 1j * SOIL_A[1] / (w * EPS0)
    k_p = w / 299792458.0
    k_m = k_p * np.sqrt(eps_t)
    if k_m.imag > 0:
        k_m = np.conj(k_m)
    return eps_t, k_p, complex(k_m), w


def setup():
    b = build()
    s = solver_of(b)
    geom, supp_seg, polys, a_idx, b_idx = parts(s)
    here = Path(__file__).resolve().parent / "blocks"
    tag = f"r{b.n_radials}_d{b.depth}"
    mw = np.load(here / f"mw_{tag}.npy")
    ob = np.load(here / f"oracle_{tag}_q1.npy")
    return b, s, geom, supp_seg, polys, a_idx, b_idx, mw, ob


def who(args):
    b, s, geom, supp_seg, polys, a_idx, b_idx, mw, ob = setup()
    sup_a = basis_support(geom, supp_seg, a_idx, polys)
    sup_b = basis_support(geom, supp_seg, b_idx, polys)
    rows = [m for m in range(len(sup_a)) if len(sup_a[m])]
    cols = [n for n in range(len(sup_b)) if len(sup_b[n])]
    seg_l = np.asarray(geom["seg_l"])
    seg_r = np.asarray(geom["seg_r"])
    hits = []
    for i, m in enumerate(rows):
        for j, n in enumerate(cols):
            d = np.linalg.norm(
                sup_a[m][:, None, :] - sup_b[n][None, :, :], axis=-1
            ).min()
            if abs(d - 0.15) < 1e-9:
                hits.append((m, n, d))
    print(f"pairs at exactly 0.15 m: {len(hits)}")
    for m, n, d in hits:
        print(f"\n  above basis {m}  x  below basis {n}   sep {d:.6f}")
        print(f"    above wings (segments): {supp_seg[m]}")
        for a in supp_seg[m]:
            print(f"       seg {a:3d}  {seg_l[a]} -> {seg_r[a]}")
        print(f"    below wings (segments): {supp_seg[n]}")
        for a in supp_seg[n]:
            print(f"       seg {a:3d}  {seg_l[a]} -> {seg_r[a]}")
        print(f"    momwire {mw[m, n]!r}")
        print(f"    oracle  {ob[m, n]!r}")
        print(
            f"    |o-m|/|m| {abs(ob[m, n] - mw[m, n]) / abs(mw[m, n]):.6f}   "
            f"|o|/|m| {abs(ob[m, n]) / abs(mw[m, n]):.6e}"
        )


def proj(args):
    """The two projectors at the hub configuration, then off the axis."""
    eps_t, k_p, k_m, w = medium()
    PO.set_medium(FREQ, *SOIL_A)
    # source: a horizontal dipole at the hub depth, just off the hub.
    # observer: on the rise/radiator axis, just above the plane.
    zsrc = -0.15
    t_src = np.array([[1.0, 0.0, 0.0]])
    t_obs = np.array([[0.0, 0.0, 1.0]])
    print(
        f"{'x_src':>10} {'rho':>10} {'z_obs':>8} {'momwire':>26} "
        f"{'prototype':>26} {'rel':>10}"
    )
    for zobs in (0.02, 0.2):
        print(
            f"--- observer on the axis at z = {zobs} m, "
            f"HED source at depth {abs(zsrc)} m, walking OFF the hub"
        )
        for xs in (0.0, 5e-4, 2.5e-3, 1e-2, 5e-2, 0.25, 1.0):
            src = np.array([[xs, 0.0, zsrc]])
            obs = np.array([[0.0, 0.0, zobs]])
            rho = abs(xs)
            p_o = PO.make_proj(FREQ, *SOIL_A, workers=1)(obs, t_obs, src, t_src)[0, 0]
            r_hi = float(np.hypot(rho, zobs))
            grid = trans.get_grid_below_above(
                eps_t,
                k_p,
                max(r_hi * 1.2, 1e-3),
                abs(zsrc),
                abs(zsrc),
                w,
                mu=MU0,
                r_min=max(r_hi * 0.8, 1e-6),
            )
            p_m = trans.transmitted_field_proj_below_to_above(
                obs, t_obs, src, t_src, GZ, k_p, k_m, grid
            )[0, 0]
            rel = abs(p_o - p_m) / max(abs(p_m), 1e-300)
            print(
                f"{xs:10.4e} {rho:10.4e} {zobs:8.3f} "
                f"{p_m.real:12.5e}{p_m.imag:+12.5e}j "
                f"{p_o.real:12.5e}{p_o.imag:+12.5e}j {rel:10.3e}"
            )
            sys.stdout.flush()


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("mode", choices=["who", "proj"])
    args = ap.parse_args()
    {"who": who, "proj": proj}[args.mode](args)


if __name__ == "__main__":
    main()
