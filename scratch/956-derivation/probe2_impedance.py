"""momwire#956 derivation, probe 2: what the two departures probe1 named do to Z.

probe1 established, exactly (3.6e-14), on the vertical x vertical cross block:

    shipped - field_form = (s_w1 + s_w2 + SW)  +  (CORNER_inplane - CORNER_all)

  (W)  the W cross terms, spelled with the full arclength charge Fd where the
       transmitted dyad's G_zx / G_zy carry only the TRANSVERSE divergence
       (1 - tz^2) Fd -- zero on a vertical wire;
  (C)  the by-parts corner -sigma sigma' c1 V(E,E') restricted to end pairs
       both in the plane, where the section-4 identity has it on EVERY end
       pair with nonzero basis values (here: the above node tent x the five
       hub wings, |dC| = 1.43e+02 on 228x220 against a field form of 3.7).

This probe patches each departure out, separately and together, and reads Z:

  E1  the #956 deck (4 radials, hub 0.15 m, soil A, shipped mesh) against NEC-5
      run locally on the same exported deck;
  E2  the crossing ROD ladder of scratch/931-study (rise + radiator, no screen,
      so no hub and departure (C) is absent by construction), L = 0.15 / 0.30 /
      0.60 / 1.20 m, momwire shipped and fixed against NEC-5 on the same decks.
      The recorded residual there is +1.24 / 2.25 / 4.60 / 9.99 ohm, through
      the origin -- if (W) is the term, the fixed column closes it.

Patching is by module attribute on `_crossing_fill` (dense path forced); nothing
in src/momwire is edited. NEC-5 via NEC5_EXE (set in the environment).
"""

import os
import sys

os.environ.setdefault("MOMWIRE_CROSSING_FORCE_DENSE", "1")
for _v in ("OMP_NUM_THREADS", "OPENBLAS_NUM_THREADS", "MKL_NUM_THREADS"):
    os.environ.setdefault(_v, "4")
os.environ.setdefault(
    "NEC5_EXE", os.path.expanduser("~/antennas/NEC5-downloads/nec5-linux/nec5cl")
)

import argparse  # noqa: E402
import warnings  # noqa: E402
from pathlib import Path  # noqa: E402

import numpy as np  # noqa: E402

warnings.filterwarnings("ignore")
HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent / "956-oracle"))
sys.path.insert(0, str(HERE.parent / "931-study"))
sys.path.insert(0, str(HERE))

from momwire import _crossing_fill as CF  # noqa: E402
from momwire import _near_interface as NI  # noqa: E402
from momwire._crossing_fill import _on_plane_side  # noqa: E402
from momwire._crossing_fill import _rank1_add  # noqa: E402
from momwire._crossing_fill import _rank1_add_cols  # noqa: E402
from momwire._crossing_fill import _real_matvec_c  # noqa: E402
from momwire._crossing_fill import _Rank1Buffer  # noqa: E402

from antennaknobs.engines.momwire import MomwireEngine  # noqa: E402
from antennaknobs.engines.nec5 import NEC5Engine  # noqa: E402

from probe1_wterms import end_tz  # noqa: E402
from probe3_cross_block import build as build_brv  # noqa: E402
import probe_rod_ladder as ROD  # noqa: E402

SOIL_A = (13.0, 0.005)
FIX = {"W": False, "C": False}
_ORIG_MAIN = CF._main_sandwich
_ORIG_ENDS = CF._ends_and_corner


def main_sandwich_fixed(ctx, A, B, eps_t, k_p, c1, gz, memo=None):
    if not FIX["W"]:
        return _ORIG_MAIN(ctx, A, B, eps_t, k_p, c1, gz, memo=memo)
    k2sq = k_p * k_p
    dx = A["nodes"][:, 0][:, None] - B["nodes"][:, 0][None, :]
    dy = A["nodes"][:, 1][:, None] - B["nodes"][:, 1][None, :]
    rho = np.hypot(dx, dy)
    z = np.broadcast_to((A["nodes"][:, 2] - gz)[:, None], rho.shape)
    zp = np.broadcast_to((B["nodes"][:, 2] - gz)[None, :], rho.shape)
    tables = CF._tables(ctx, eps_t, k_p, rho, z, zp, CF._CROSS_RTOL, memo=memo)
    U, V, W, dzW = tables["U"], tables["V"], tables["W"], tables["dzW"]
    wA, wB = A["w"], B["w"]
    txA, tyA, tzA = A["t"].T
    txB, tyB, tzB = B["t"].T
    hA, hB = 1.0 - tzA * tzA, 1.0 - tzB * tzB
    FA_w, FB_w = A["F"] * wA, B["F"] * wB
    FdA_w, FdB_w = A["Fd"] * wA, B["Fd"] * wB
    s_u = (FA_w * txA) @ U @ (FB_w * txB).T + (FA_w * tyA) @ U @ (FB_w * tyB).T
    s_zz = (FA_w * tzA) @ (k2sq * V - dzW) @ (FB_w * tzB).T
    s_w1 = (FA_w * tzA) @ W @ (FdB_w * hB).T
    s_w2 = (FdA_w * hA) @ W @ (FB_w * tzB).T
    s_phi = -FdA_w @ V @ FdB_w.T
    return c1 * (s_u + s_zz + s_w1 + s_w2 + s_phi)


def ends_and_corner_fixed(ctx, A, B, eps_t, k_p, c1, gz, memo=None, *, corner=True):
    if not (FIX["W"] or FIX["C"]):
        return _ORIG_ENDS(ctx, A, B, eps_t, k_p, c1, gz, memo=memo, corner=corner)
    t_ab = np.zeros((A["n_basis"], B["n_basis"]), dtype=np.complex128)
    _txA, _tyA, tzA = A["t"].T
    wA, wB = A["w"], B["w"]
    wA_tz = wA * tzA
    buf, bufT = _Rank1Buffer(), _Rank1Buffer()
    tzB_end = end_tz(ctx, B) if FIX["W"] else np.zeros(len(B["ends"]))
    for pt, sign, fv in A["ends"]:
        rho_e = np.hypot(pt[0] - B["nodes"][:, 0], pt[1] - B["nodes"][:, 1])
        te = CF._tables(
            ctx,
            eps_t,
            k_p,
            rho_e,
            _on_plane_side(np.full_like(rho_e, pt[2] - gz), "above", "end point"),
            _on_plane_side(B["nodes"][:, 2] - gz, "below", "quadrature node"),
            CF._CROSS_RTOL,
            memo=memo,
        )
        nz = np.flatnonzero(fv)
        _rank1_add(
            t_ab, nz, fv[nz], _real_matvec_c(B["Fd"], wB * te["V"]), c1 * sign, buf
        )
    for (pt, sign, fv), tze in zip(B["ends"], tzB_end, strict=True):
        rho_e = np.hypot(A["nodes"][:, 0] - pt[0], A["nodes"][:, 1] - pt[1])
        te = CF._tables(
            ctx,
            eps_t,
            k_p,
            rho_e,
            _on_plane_side(A["nodes"][:, 2] - gz, "above", "quadrature node"),
            _on_plane_side(np.full_like(rho_e, pt[2] - gz), "below", "end point"),
            CF._CROSS_RTOL,
            memo=memo,
        )
        nz = np.flatnonzero(fv)
        sw_scale = (1.0 - tze * tze) if FIX["W"] else 1.0
        if sw_scale != 0.0:
            _rank1_add_cols(
                t_ab,
                nz,
                _real_matvec_c(A["F"], wA_tz * te["W"]),
                fv[nz],
                -c1 * sign * sw_scale,
                bufT,
            )
        _rank1_add_cols(
            t_ab, nz, _real_matvec_c(A["Fd"], wA * te["V"]), fv[nz], c1 * sign, bufT
        )
    if not corner:
        return t_ab
    a_wire = float(ctx.a_wire)
    v_corner = None
    for pt_a, sig_a, fv_a in A["ends"]:
        for pt_b, sig_b, fv_b in B["ends"]:
            in_plane = abs(pt_a[2] - gz) <= 1e-12 and abs(pt_b[2] - gz) <= 1e-12
            if not in_plane and not FIX["C"]:
                continue
            if in_plane:
                if v_corner is None:
                    v_corner = complex(
                        NI.six_point(
                            eps_t, k_p, a_wire, 0.0, 0.0, rtol=CF._CORNER_RTOL
                        )[1]
                    )
                v = v_corner
            else:
                rho = np.hypot(pt_a[0] - pt_b[0], pt_a[1] - pt_b[1])
                v = complex(
                    NI.six_point(
                        eps_t,
                        k_p,
                        np.hypot(rho, a_wire),
                        max(pt_a[2] - gz, 0.0),
                        min(pt_b[2] - gz, 0.0),
                        rtol=CF._CORNER_RTOL,
                    )[1]
                )
            nza, nzb = np.flatnonzero(fv_a), np.flatnonzero(fv_b)
            t_ab[np.ix_(nza, nzb)] += (-sig_a * sig_b * c1 * v) * np.outer(
                fv_a[nza], fv_b[nzb]
            )
    return t_ab


CF._FORCE_DENSE = True
CF._main_sandwich = main_sandwich_fixed
CF._ends_and_corner = ends_and_corner_fixed


def z_momwire(b, g, w=False, c=False):
    FIX["W"], FIX["C"] = w, c
    try:
        return complex(MomwireEngine(b, ground=g).impedance()[0])
    finally:
        FIX["W"], FIX["C"] = False, False


def fmt(z):
    return f"{z.real:9.4f}{z.imag:+9.4f}j"


def e1(args):
    g = ("finite", *SOIL_A)
    b = build_brv(n_radials=args.n_radials, depth=args.depth)
    print(
        f"E1 buried_radial_vertical connected, {args.n_radials} radials, hub {args.depth} m, soil A, shipped mesh"
    )
    zn = complex(NEC5Engine(b, ground=g).impedance()[0])
    print(f"  NEC-5 (local)       {fmt(zn)}")
    for label, w, c in (
        ("shipped", False, False),
        ("fix W", True, False),
        ("fix C", False, True),
        ("fix W+C", True, True),
    ):
        zm = z_momwire(b, g, w, c)
        print(
            f"  momwire {label:8s}  {fmt(zm)}   dR {zn.real - zm.real:+8.4f}  dX {zn.imag - zm.imag:+8.4f}"
        )
        sys.stdout.flush()


def e2(args):
    g = ("finite", *SOIL_A)
    print(
        f"E2 crossing rod ladder (931-study RodBuilder, nn={args.nn}, rest_h {ROD.REST_H})"
    )
    print(
        f"  {'L':>5} {'segs':>5} {'NEC-5':>20} {'mw shipped':>20} {'dR':>8} {'dX':>8} {'mw fix W':>20} {'dR':>8} {'dX':>8}"
    )
    for L in args.lengths:
        b = ROD.build("A", L, args.nn)
        text = NEC5Engine(b, ground=g).deck([b.freq])
        segs = sum(
            int(ln.split()[2]) for ln in text.splitlines() if ln.startswith("GW ")
        )
        zn = complex(NEC5Engine(b, ground=g).impedance()[0])
        z0 = z_momwire(b, g)
        z1 = z_momwire(b, g, w=True)
        print(
            f"  {L:5.2f} {segs:5d} {fmt(zn):>20} {fmt(z0):>20} {zn.real - z0.real:+8.3f} {zn.imag - z0.imag:+8.3f} "
            f"{fmt(z1):>20} {zn.real - z1.real:+8.3f} {zn.imag - z1.imag:+8.3f}"
        )
        sys.stdout.flush()


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("mode", choices=["e1", "e2"])
    ap.add_argument("--n-radials", type=int, default=4)
    ap.add_argument("--depth", type=float, default=0.15)
    ap.add_argument("--nn", type=int, default=42)
    ap.add_argument(
        "--lengths", type=float, nargs="+", default=[0.15, 0.30, 0.60, 1.20]
    )
    a = ap.parse_args()
    {"e1": e1, "e2": e2}[a.mode](a)
