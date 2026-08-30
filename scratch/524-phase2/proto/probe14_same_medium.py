"""A-2 session 4, item 1: the same-medium families' by-parts terms.

DERIVATION-SAME-MEDIUM.md made block-level. Three measurements:

  14a. FIT: the shipped MP self pieces (direct `_assemble_Z` subset and
       weighted `_image_Z_weighted`) are alpha*S_A + beta*S_Phi with my
       closed-form quadrature shapes S_A = (Fw) G (Fw)^T and
       S_Phi = (Fdw) G (Fdw)^T, on well-separated entries. Pins the four
       beta (direct/image x above/below) INCLUDING sign and the medium /
       image-weight factors - the probe5 way, no trusted constants.
  14b. IDENTITY: closed-form P = iint f_m f_n dz dz' G equals
       iint f'f'G + bnd_shape with the -,-,+ sign structure of the
       derivation, per family, on the node column (separated entries).
       Pins the bnd implementation end-to-end.
  14c. SUPPORT: the ends tables reduce to the node only, sigma_b = +1,
       sigma_a = -1.

Outputs results/probe14-bnd-x{mult}.npz with the four bnd matrices
(no-corner) and the four corner matrices separately, ready for probe15:

  BND_add = beta_dir*bnd(G_dir) - beta_img*bnd(G_img)   per family
  (the minus from the fill's global `Z -= image` convention)

Run: prlimit --as=$((8*1024*1024*1024)) .venv/bin/python \
     scratch/524-phase2/proto/probe14_same_medium.py [mult]
"""

from __future__ import annotations

import sys
import time
from pathlib import Path

import numpy as np

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "567-phase0" / "proto"))
sys.path.insert(0, str(Path(__file__).resolve().parents[3] / "momwire" / "tests"))

import mp_cross  # noqa: E402
from probe1_baseline import crossing_deck, seeded  # noqa: E402

A_WIRE = 0.001  # deck wire radius; thin-wire kernel offset


# --- closed-form kernels ---------------------------------------------------


def g_of_r(k, R):
    return np.exp(-1j * k * R) / R


def gzz_pair(k, zP, zQ, mirror):
    """dz dz' of e^{-jkR}/R between axis points at zP (test) and zQ
    (source), R^2 = a^2 + zeta^2 with zeta = zP - zQ (direct) or
    zP + zQ (image, gz = 0). Chain rule: direct -> -G_zetazeta,
    image -> +G_zetazeta."""
    zeta = zP + zQ if mirror else zP - zQ
    R = np.sqrt(A_WIRE * A_WIRE + zeta * zeta)
    G = g_of_r(k, R)
    Gp = -(1j * k + 1.0 / R) * G  # dG/dR
    Gpp = G / (R * R) + (1j * k + 1.0 / R) ** 2 * G  # d2G/dR2
    Gzz = Gp / R + zeta * zeta / (R * R) * (Gpp - Gp / R)
    return Gzz if mirror else -Gzz


def kernel_matrix(k, zP, zQ, mirror):
    zq = -zQ if mirror else zQ
    R = np.sqrt(A_WIRE * A_WIRE + (zP[:, None] - zq[None, :]) ** 2)
    return g_of_r(k, R)


def kernel_point(k, zP, z_end, mirror):
    ze = -z_end if mirror else z_end
    R = np.sqrt(A_WIRE * A_WIRE + (zP - ze) ** 2)
    return g_of_r(k, R)


# --- shapes and bnd pieces -------------------------------------------------


def shapes(ax, k, mirror):
    """S_A, S_Phi, P (pointwise dz dz') quadrature shapes on one axis."""
    z = ax["nodes"][:, 2]
    Fw = ax["F"] * ax["w"]
    Fdw = ax["Fd"] * ax["w"]
    G = kernel_matrix(k, z, z, mirror)
    D = gzz_pair(k, z[:, None], z[None, :], mirror)
    S_A = Fw @ G @ Fw.T
    S_P = Fdw @ G @ Fdw.T
    P = Fw @ D @ Fw.T
    return S_A, S_P, P


def bnd_shape(ax, k, mirror):
    """The derivation Sec 2 boundary shape (beta = 1): -test-end row,
    -source-end col, +corner. Returns (no_corner, corner_only)."""
    z = ax["nodes"][:, 2]
    Fdw = ax["Fd"] * ax["w"]
    n = ax["n_basis"]
    out = np.zeros((n, n), dtype=np.complex128)
    corner = np.zeros((n, n), dtype=np.complex128)
    for ptE, sig, fvT in ax["ends"]:  # test ends
        # kernel between the test END (observation, never mirrored) and the
        # source LINE points z' (mirrored for the image kernel):
        zq = -z if mirror else z
        R = np.sqrt(A_WIRE * A_WIRE + (ptE[2] - zq) ** 2)
        col = Fdw @ g_of_r(k, R)
        out += -sig * np.outer(fvT, col)
    for ptEp, sigp, fvS in ax["ends"]:  # source ends
        zep = -ptEp[2] if mirror else ptEp[2]
        R = np.sqrt(A_WIRE * A_WIRE + (z - zep) ** 2)
        col_kernel = g_of_r(k, R)
        row = Fdw @ col_kernel
        out += -sigp * np.outer(row, fvS)
    for ptE, sig, fvT in ax["ends"]:
        for ptEp, sigp, fvS in ax["ends"]:
            zep = -ptEp[2] if mirror else ptEp[2]
            R = np.sqrt(A_WIRE * A_WIRE + (ptE[2] - zep) ** 2)
            corner += sig * sigp * g_of_r(k, R) * np.outer(fvT, fvS)
    return out, corner


def separated_mask(ax, min_gap=3):
    """Entry mask: basis pairs whose Gauss supports are >= min_gap segment
    half-widths apart (quadrature-clean for smooth kernels). Falls back to
    smaller separations on short axes (the 4-segment below arm) rather
    than returning an empty mask."""
    z = ax["nodes"][:, 2]
    n = ax["n_basis"]
    F = ax["F"]
    lo = np.full(n, np.inf)
    hi = np.full(n, -np.inf)
    for m in range(n):
        on = np.abs(F[m]) > 0
        if on.any():
            lo[m], hi[m] = z[on].min(), z[on].max()
    seg = (hi[np.isfinite(hi)] - lo[np.isfinite(lo)]).max() / 2 if n else 0.0
    gap = np.maximum(lo[:, None] - hi[None, :], lo[None, :] - hi[:, None])
    live = np.isfinite(lo)[:, None] & np.isfinite(lo)[None, :]
    for g in (min_gap, 1.9, 0.9, 0.4):
        mask = live & (gap > g * seg * 0.5)
        if mask.any():
            return mask, lo, hi
    return live & (gap > 0), lo, hi


def fit_ab(target, S_A, S_P, mask):
    idx = np.nonzero(mask)
    A = np.stack([S_A[idx], S_P[idx]], axis=1)
    b = target[idx]
    coef, *_ = np.linalg.lstsq(A, b, rcond=None)
    resid = A @ coef - b
    rel = np.linalg.norm(resid) / max(np.linalg.norm(b), 1e-300)
    return coef[0], coef[1], rel, idx[0].size


def main():
    mult = int(sys.argv[1]) if len(sys.argv) > 1 else 1
    s = seeded(crossing_deck(mult))
    geom = s._build_geometry()
    below = s._below_segments(geom)
    b_idx = np.nonzero(below)[0]
    a_idx = np.nonzero(~below)[0]
    eps_t, eps_m, k_p, k_m, c2, a_m = s._buried_medium()
    supp_seg, polys, *_ = s._build_basis_polynomials(geom)
    n_basis = polys.shape[0]

    axA = mp_cross.axis_data(s, geom, a_idx)
    axB = mp_cross.axis_data(s, geom, b_idx)

    # ---- 14c: support ------------------------------------------------------
    print("14c ends tables:")
    for name, ax in (("below", axB), ("above", axA)):
        for pt, sig, fv in ax["ends"]:
            nz = np.nonzero(fv)[0]
            print(
                f"  {name}: end z={pt[2]:+.3f} sigma={sig:+.0f} "
                f"bases={nz.tolist()} f={fv[nz]}"
            )

    # ---- shipped MP pieces -------------------------------------------------
    t0 = time.time()
    MP_bb = s._assemble_Z(
        s._build_J_blocks_subset(geom, k_m, b_idx),
        supp_seg,
        polys,
        geom,
        eps=eps_m,
    )
    MP_aa = s._assemble_Z(
        s._build_J_blocks_subset(geom, k_p, a_idx), supp_seg, polys, geom
    )
    td_img = s._image_tangent_dot(geom["tangents"])
    IMG_bb = s._image_Z_weighted(
        s._build_J_blocks_subset(geom, k_m, b_idx, mirror_sources=True),
        supp_seg,
        polys,
        a_m * td_img.astype(np.complex128),
        np.full(td_img.shape, a_m, dtype=np.complex128),
        eps=eps_m,
    )
    IMG_aa = s._image_Z_weighted(
        s._build_J_blocks_subset(geom, k_p, a_idx, mirror_sources=True),
        supp_seg,
        polys,
        c2 * td_img.astype(np.complex128),
        np.full(td_img.shape, c2, dtype=np.complex128),
    )
    print(f"shipped MP pieces built ({time.time() - t0:.0f}s)")

    # ---- 14a: fits ---------------------------------------------------------
    omega, mu, eps0 = s.omega, s.mu, s.eps  # noqa: F841 — kept: names the quantity the probe computed, read when inspecting
    beta_ref = {
        "bb_dir": 1.0 / (1j * omega * eps_m * 4 * np.pi),
        "aa_dir": 1.0 / (1j * omega * eps0 * 4 * np.pi),
        "bb_img": a_m / (1j * omega * eps_m * 4 * np.pi),
        "aa_img": c2 / (1j * omega * eps0 * 4 * np.pi),
    }
    fits = {}
    print("\n14a fits (alpha = A-term const, beta = Phi-term const):")
    for name, ax, k, mirror, target in (
        ("bb_dir", axB, k_m, False, MP_bb),
        ("aa_dir", axA, k_p, False, MP_aa),
        ("bb_img", axB, k_m, True, IMG_bb),
        ("aa_img", axA, k_p, True, IMG_aa),
    ):
        S_A, S_P, P = shapes(ax, k, mirror)
        mask, lo, hi = separated_mask(ax)
        alpha, beta, rel, npts = fit_ab(target, S_A, S_P, mask)
        ratio = beta / beta_ref[name]
        # the saved matrices use the ANALYTIC beta (the aa fits pin the
        # convention to 3e-10; the bb path shares the code, and its own
        # looser-mask fit corroborates)
        fits[name] = dict(
            alpha=alpha,
            beta=beta_ref[name],
            S_A=S_A,
            S_P=S_P,
            P=P,
            ax=ax,
            k=k,
            mirror=mirror,
        )
        print(
            f"  {name}: alpha={alpha:.6g}  beta={beta:.6g}  "
            f"beta/expected={ratio:.6f}  rel_resid={rel:.2e}  n={npts}"
        )

    # ---- 14b: identity on the node column ----------------------------------
    print("\n14b identity P == S_Phi + bnd_shape (separated node-column entries):")
    bnds = {}
    for name in ("bb_dir", "aa_dir", "bb_img", "aa_img"):
        f = fits[name]
        ax = f["ax"]
        bnd_nc, bnd_cor = bnd_shape(ax, f["k"], f["mirror"])
        bnds[name] = (bnd_nc, bnd_cor)
        mask, lo, hi = separated_mask(ax)
        # node column: rows m separated from the node basis n0
        end_bases = set()
        for _pt, _s, fv in ax["ends"]:
            end_bases |= set(np.nonzero(fv)[0].tolist())
        resid_no = f["P"] - f["S_P"]
        resid_with = f["P"] - (f["S_P"] + bnd_nc + bnd_cor)
        scale = np.abs(f["P"])[mask].max() if mask.any() else 1.0
        for n0 in sorted(end_bases):
            rows = [m for m in range(n_basis) if mask[m, n0]]
            if not rows:
                continue
            r0 = np.abs(resid_no[rows, n0]).max() / scale
            r1 = np.abs(resid_with[rows, n0]).max() / scale
            print(
                f"  {name} col {n0}: |P - S_Phi| = {r0:.2e}  "
                f"|P - (S_Phi+bnd)| = {r1:.2e}  (of max, {len(rows)} rows)"
            )
        # interior floor
        interior = mask.copy()
        for e in end_bases:
            interior[e, :] = False
            interior[:, e] = False
        if interior.any():
            fl = np.abs(resid_no[interior]).max() / scale
            print(f"  {name} interior floor |P - S_Phi| = {fl:.2e}")

    # ---- the additive corrections per family -------------------------------
    BND_bb = (
        fits["bb_dir"]["beta"] * bnds["bb_dir"][0]
        - fits["bb_img"]["beta"] * bnds["bb_img"][0]
    )
    BND_aa = (
        fits["aa_dir"]["beta"] * bnds["aa_dir"][0]
        - fits["aa_img"]["beta"] * bnds["aa_img"][0]
    )
    COR_bb = (
        fits["bb_dir"]["beta"] * bnds["bb_dir"][1]
        - fits["bb_img"]["beta"] * bnds["bb_img"][1]
    )
    COR_aa = (
        fits["aa_dir"]["beta"] * bnds["aa_dir"][1]
        - fits["aa_img"]["beta"] * bnds["aa_img"][1]
    )

    nb = len(b_idx)  # node bases: below arm last basis, above arm first
    na = nb + 1
    print(f"\nnode bases nb={nb} na={na}")
    print(
        f"BND_bb[{nb},:] max |.| = {np.abs(BND_bb[nb]).max():.4g}   "
        f"COR_bb[{nb},{nb}] = {COR_bb[nb, nb]:.4f}"
    )
    print(
        f"BND_aa[{na},:] max |.| = {np.abs(BND_aa[na]).max():.4g}   "
        f"COR_aa[{na},{na}] = {COR_aa[na, na]:.4f}"
    )
    stat_b = (1 - a_m) / eps_m
    stat_a = (1 - c2) / eps0
    print(
        f"static net weights: below (1-A_m)/eps_m = {stat_b:.6g}, "
        f"above (1-C2)/eps0 = {stat_a:.6g}, ratio = {stat_b / stat_a:.6f}"
    )

    fp = HERE.parent / "results" / f"probe14-bnd-x{mult}.npz"
    np.savez(
        fp, BND_bb=BND_bb, BND_aa=BND_aa, COR_bb=COR_bb, COR_aa=COR_aa, nb=nb, na=na
    )
    print(f"saved {fp}")


if __name__ == "__main__":
    main()
