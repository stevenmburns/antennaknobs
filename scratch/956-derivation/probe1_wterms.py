"""momwire#956 derivation, probe 1: the W cross terms on vertical x vertical pairs.

THE DERIVATION (spectral bookkeeping the fill itself documents: dz <-> -g+,
dz' <-> +g-, W~ = (g+ - g-) V~, every kernel of the family riding the SAME
V~ J0(lam rho) lam dlam, so per-lambda algebra is exact at fixed rho):

  field form, vertical source x vertical test (AGARD 7b):
      (dz^2 + k^2) V  <->  (g+^2 + k^2) V~ = lam^2 V~
  and  k^2 V - dzW - dz dz' V  <->  k^2 + g+(g+ - g-) + g+ g-  =  lam^2   (same thing)

  so  FF = INT f_m f_n (k^2 V - dzW)  -  INT f_m f_n dz dz' V
         = s_zz + [ -INT f'_m f'_n V + BT + SQ - CORNER_all ]      (the section-4 identity)
         = s_zz + s_phi + BT + SQ + CORNER_all                      EXACTLY.

  The shipped spelling is  s_u + s_zz + s_w1 + s_w2 + s_phi + BT + SW + SQ + CORNER_inplane,
  so on a vertical x vertical pair

      shipped - FF = s_w1 + s_w2 + SW  +  (CORNER_inplane - CORNER_all).

  Bulk of the excess, per lambda: (g+ - g-)^2 V~ = (g+ - g-) W~  <->  -(dzW + dz'W);
  end residue (g+ - g-) E_m b_n <-> sum_E sigma f_m(E) INT f_n W(E, .).  Both vanish
  identically at eps~ = 1 (W == 0), which is why every eps~ = 1 gate passed.

  Where the W terms DO belong: G_zx / G_zy of the transmitted dyad, i.e. the
  z-directed potential driven by the TRANSVERSE divergence of the source,
  d/dx' J_x + d/dy' J_y = (1 - tz^2) dI/dl on a straight wire. The fill spells
  that divergence as the full arclength derivative Fd, which is right for a
  horizontal wire and wrong for a vertical one (checked: horizontal source x
  vertical test closes exactly with s_w1 + s_phi + BT + SW + SQ + CORNER_all).

WHAT THIS PROBE MEASURES, on the #956 deck (buried_radial_vertical, 4 radials,
hub 0.15 m, soil A, 7.1 MHz, shipped mesh):

  G1  my term-by-term rebuild of _main_sandwich equals the module's (bit class);
  G2  my rebuild of _ends_and_corner equals the module's;
  G3  Haswell's two entries reproduce (228x220 |Z| 1.4649e+02, 239x222 1.1629e-01);
  D1  on every pure vertical x vertical pair:  FF_direct (= s_zz + s_phi + BT + SQ
      + CORNER_all, and independently INT f f (k^2 V - dzW - dz dz'V)) against the
      shipped entry, the W-term excess, and the corrected spelling;
  D2  Haswell's field-form values on 228x220 / 239x222 against FF_direct here.

Scratch only; nothing in src/momwire is touched.
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

from momwire import _crossing_fill as CF  # noqa: E402
from momwire import _near_interface as NI  # noqa: E402
from momwire._sommerfeld_transmitted import _c1_moment  # noqa: E402

from probe3_cross_block import build, parts, solver_of  # noqa: E402


def tables6(ctx, eps_t, k_p, rho, z, zp, memo):
    return NI.radius_tables(
        eps_t, k_p, rho, z, zp, float(ctx.a_wire), rtol=CF._CROSS_RTOL, memo=memo
    )


def sandwich_terms(ctx, A, B, eps_t, k_p, c1, gz, memo):
    """The five terms of `_main_sandwich`, separately, plus the direct field
    form for the vertical x vertical class and the transverse-masked W terms."""
    k2sq = k_p * k_p
    dx = A["nodes"][:, 0][:, None] - B["nodes"][:, 0][None, :]
    dy = A["nodes"][:, 1][:, None] - B["nodes"][:, 1][None, :]
    rho = np.hypot(dx, dy)
    z = np.broadcast_to((A["nodes"][:, 2] - gz)[:, None], rho.shape)
    zp = np.broadcast_to((B["nodes"][:, 2] - gz)[None, :], rho.shape)
    T = tables6(ctx, eps_t, k_p, rho, z, zp, memo)
    U, V, W, dzW, dzpV = T["U"], T["V"], T["W"], T["dzW"], T["dzpV"]

    wA, wB = A["w"], B["w"]
    txA, tyA, tzA = A["t"].T
    txB, tyB, tzB = B["t"].T
    FA_w, FB_w = A["F"] * wA, B["F"] * wB
    FdA_w, FdB_w = A["Fd"] * wA, B["Fd"] * wB
    hA, hB = 1.0 - tzA * tzA, 1.0 - tzB * tzB  # transverse fraction per node

    out = {}
    out["s_u"] = (FA_w * txA) @ U @ (FB_w * txB).T + (FA_w * tyA) @ U @ (FB_w * tyB).T
    out["s_zz"] = (FA_w * tzA) @ (k2sq * V - dzW) @ (FB_w * tzB).T
    out["s_w1"] = (FA_w * tzA) @ W @ FdB_w.T
    out["s_w2"] = FdA_w @ W @ (FB_w * tzB).T
    out["s_phi"] = -FdA_w @ V @ FdB_w.T
    out["s_w1_fix"] = (FA_w * tzA) @ W @ (FdB_w * hB).T
    out["s_w2_fix"] = (FdA_w * hA) @ W @ (FB_w * tzB).T
    # the direct field form, vertical x vertical only (tz tz weights)
    out["ff_vv"] = (FA_w * tzA) @ (k2sq * V - dzW - dzpV) @ (FB_w * tzB).T
    return {k: c1 * v for k, v in out.items()}


def end_tz(ctx, ax, seg_idx=None):
    """tz of the wire owning each entry of ax['ends'], in the ends' own order.

    Replicates `axis_data`'s end loop (wire order, first/last segment) so each
    end is paired with ITS wire. Matching by endpoint alone is wrong: five
    wires share the hub point, and a point match hands every hub end the tz
    of whichever wire matched last (the first version of this probe did that,
    stripped the radials' legitimate SW terms with the rise's, and read a
    +36 ohm move that was the bug and not the physics)."""
    geom = ctx.geom
    seg_off = geom.seg_offsets
    if seg_idx is None:
        seg_idx = np.unique(ax["segof"])
    on_axis = set(int(g) for g in seg_idx)
    out = []
    k = 0
    for w in range(len(seg_off) - 1):
        first, last = seg_off[w], seg_off[w + 1] - 1
        if first not in on_axis:
            continue
        for gseg, u_end in ((first, 0.0), (last, None)):
            hh = geom.h[gseg]
            u = hh if u_end is None else 0.0
            pt = geom.seg_l[gseg] + (u / hh) * (geom.seg_r[gseg] - geom.seg_l[gseg])
            fv = ctx.basis.end_values(gseg, u)
            if np.any(fv != 0.0):
                assert np.allclose(pt, ax["ends"][k][0], atol=1e-12), (
                    k,
                    pt,
                    ax["ends"][k][0],
                )
                out.append(float(geom.tangents[gseg][2]))
                k += 1
    assert k == len(ax["ends"]), (k, len(ax["ends"]))
    return np.asarray(out)


def end_terms(ctx, A, B, eps_t, k_p, c1, gz, memo):
    """BT, SW, SQ, the code's in-plane corner, the all-pairs corner, and the
    transverse-masked SW."""
    n = (A["n_basis"], B["n_basis"])
    BT = np.zeros(n, complex)
    SW = np.zeros(n, complex)
    SW_fix = np.zeros(n, complex)
    SQ = np.zeros(n, complex)
    C_in = np.zeros(n, complex)
    C_all = np.zeros(n, complex)
    _txA, _tyA, tzA = A["t"].T
    wA, wB = A["w"], B["w"]
    tzB_end = end_tz(ctx, B)

    for pt, sign, fv in A["ends"]:
        rho_e = np.hypot(pt[0] - B["nodes"][:, 0], pt[1] - B["nodes"][:, 1])
        te = tables6(
            ctx,
            eps_t,
            k_p,
            rho_e,
            np.full_like(rho_e, max(pt[2] - gz, 0.0)),
            B["nodes"][:, 2] - gz,
            memo,
        )
        BT += c1 * sign * np.outer(fv, B["Fd"] @ (wB * te["V"]))
    for (pt, sign, fv), tze in zip(B["ends"], tzB_end, strict=True):
        rho_e = np.hypot(A["nodes"][:, 0] - pt[0], A["nodes"][:, 1] - pt[1])
        te = tables6(
            ctx,
            eps_t,
            k_p,
            rho_e,
            A["nodes"][:, 2] - gz,
            np.full_like(rho_e, min(pt[2] - gz, 0.0)),
            memo,
        )
        sw = -c1 * sign * np.outer(A["F"] @ (wA * tzA * te["W"]), fv)
        SW += sw
        SW_fix += (1.0 - tze * tze) * sw
        SQ += c1 * sign * np.outer(A["Fd"] @ (wA * te["V"]), fv)

    a_wire = float(ctx.a_wire)
    for pt_a, sig_a, fv_a in A["ends"]:
        for pt_b, sig_b, fv_b in B["ends"]:
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
            term = (-sig_a * sig_b * c1 * v) * np.outer(fv_a, fv_b)
            C_all += term
            if abs(pt_a[2] - gz) < 1e-12 and abs(pt_b[2] - gz) < 1e-12:
                C_in += term
    return dict(BT=BT, SW=SW, SW_fix=SW_fix, SQ=SQ, C_in=C_in, C_all=C_all)


def rel(x, y):
    return float(np.abs(x - y).max() / max(np.abs(y).max(), 1e-300))


def main():
    b = build()
    s = solver_of(b)
    geom, supp_seg, polys, a_idx, b_idx = parts(s)
    ctx = s._crossing_context(geom, supp_seg, polys)
    A = CF.axis_data(ctx, a_idx)
    B = CF.axis_data(ctx, b_idx)
    eps_t, _eps_m, k_p, _k_m, _c2, _a_m = ctx.medium
    gz = float(ctx.ground_z)
    c1 = _c1_moment(ctx.omega, ctx.mu)
    print(
        f"deck: {len(a_idx)} above / {len(b_idx)} below segments, n_basis {A['n_basis']}"
    )
    print(
        f"eps~ = {eps_t:.4f}, k_p = {k_p:.6f}, c1 = {c1:.4f}, a = {float(ctx.a_wire)}"
    )

    memo = {}
    S = sandwich_terms(ctx, A, B, eps_t, k_p, c1, gz, memo)
    E = end_terms(ctx, A, B, eps_t, k_p, c1, gz, memo)
    main_mine = S["s_u"] + S["s_zz"] + S["s_w1"] + S["s_w2"] + S["s_phi"]
    ends_mine = E["BT"] + E["SW"] + E["SQ"] + E["C_in"]
    main_mod = CF._main_sandwich(ctx, A, B, eps_t, k_p, c1, gz, memo={})
    ends_mod = CF._ends_and_corner(ctx, A, B, eps_t, k_p, c1, gz, memo={}, corner=True)
    full_mod = CF.cross_complete_block(ctx, A, B, corner=True)
    print(f"G1 main rebuild vs module : {rel(main_mine, main_mod):.3e}")
    print(f"G2 ends rebuild vs module : {rel(ends_mine, ends_mod):.3e}")
    print(f"G3 full vs main+ends      : {rel(main_mine + ends_mine, full_mod):.3e}")
    shipped = main_mine + ends_mine

    # ---- classify bases: pure vertical (all live nodes have tz = +-1) ------
    def pure_vertical(ax):
        live = np.abs(ax["F"]) > 0
        tz2 = ax["t"][:, 2] ** 2
        return np.array(
            [
                bool(live[i].any()) and bool(np.all(tz2[live[i]] > 1 - 1e-12))
                for i in range(ax["n_basis"])
            ]
        )

    va = pure_vertical(A)
    vb = pure_vertical(B)
    on_axis_b = np.array(
        [
            bool((np.abs(B["F"][i]) > 0).any())
            and bool(
                np.all(
                    np.hypot(B["nodes"][:, 0], B["nodes"][:, 1])[np.abs(B["F"][i]) > 0]
                    < 1e-9
                )
            )
            for i in range(B["n_basis"])
        ]
    )
    rows = np.flatnonzero(va)
    cols = np.flatnonzero(vb & on_axis_b)
    print(
        f"pure-vertical above bases: {rows.size}; pure-vertical on-axis below bases: {cols.size} -> {list(cols)}"
    )
    # the wing structure at the hub and the node, for the record
    tzB_end = end_tz(ctx, B)
    print("below ends (point, sign, tz of owning wire, bases with nonzero value):")
    for (pt, sign, fv), tze in zip(B["ends"], tzB_end, strict=True):
        print(
            f"   {np.round(pt, 4)} {sign:+.0f} tz={tze:+.0f} bases {list(np.flatnonzero(fv))}"
        )
    print("above ends:")
    for pt, sign, fv in A["ends"]:
        print(f"   {np.round(pt, 4)} {sign:+.0f} bases {list(np.flatnonzero(fv))}")
    for i in (0, 55, 110, 165, 220, 227):
        live = np.abs(B["F"][i]) > 0
        segs = np.unique(B["segof"][live])
        tzs = np.unique(np.round(B["t"][live, 2], 6))
        print(
            f"   below basis {i}: live segs {segs.min()}..{segs.max()} (n={segs.size}), tz values {tzs}"
        )

    ff_direct = S["s_zz"] + S["s_phi"] + E["BT"] + E["SQ"] + E["C_all"]
    ff_kernel = S["ff_vv"]
    fixed = (
        S["s_u"]
        + S["s_zz"]
        + S["s_w1_fix"]
        + S["s_w2_fix"]
        + S["s_phi"]
        + E["BT"]
        + E["SW_fix"]
        + E["SQ"]
        + E["C_all"]
    )
    wterms = S["s_w1"] + S["s_w2"] + E["SW"]
    sub = np.ix_(rows, cols)
    print("\nD1 on the pure vertical x vertical block (rows x cols above):")
    print(f"   |shipped| max {np.abs(shipped[sub]).max():.4e}")
    print(
        f"   ff_direct (s_zz+s_phi+BT+SQ+C_all) vs ff_kernel (f f (k2V - dzW - dzdz'V)): {rel(ff_direct[sub], ff_kernel[sub]):.3e}"
    )
    print(f"   fixed spelling vs ff_direct : {rel(fixed[sub], ff_direct[sub]):.3e}")
    print(
        f"   shipped - ff_direct == wterms + (C_in - C_all) : {rel(shipped[sub] - ff_direct[sub], wterms[sub] + E['C_in'][sub] - E['C_all'][sub]):.3e}"
    )
    print(
        f"   |shipped - ff_direct| max {np.abs(shipped[sub] - ff_direct[sub]).max():.4e}  (|wterms| max {np.abs(wterms[sub]).max():.4e})"
    )

    # per-entry table for the entries with any weight, sorted by |shipped|
    print(
        f"\n{'entry':>9} {'sep':>7} {'|shipped|':>11} {'|ff_direct|':>11} {'|ff_kernel|':>11} {'ff_d/ff_k-1':>12} {'ship/ff-1':>10} {'|wterms|':>10} {'|dC|':>10}"
    )
    from probe5_partition import basis_support

    sup_a = basis_support(geom, supp_seg, a_idx, polys)
    sup_b = basis_support(geom, supp_seg, b_idx, polys)

    def sep(m, n):
        if len(sup_a[m]) == 0 or len(sup_b[n]) == 0:
            return np.nan
        return float(
            np.linalg.norm(sup_a[m][:, None, :] - sup_b[n][None, :, :], axis=-1).min()
        )

    picks = []
    for m in rows:
        for n in cols:
            if abs(shipped[m, n]) > 1e-12 * np.abs(shipped[sub]).max():
                picks.append((m, n))
    picks.sort(key=lambda mn: -abs(shipped[mn]))
    for m, n in picks[:40]:
        fd, fk, sh = ff_direct[m, n], ff_kernel[m, n], shipped[m, n]
        dC = E["C_in"][m, n] - E["C_all"][m, n]
        print(
            f"{m:>4}x{n:<4} {sep(m, n):7.4f} {abs(sh):11.4e} {abs(fd):11.4e} {abs(fk):11.4e} "
            f"{abs(fd / fk - 1) if fk != 0 else np.nan:12.2e} {abs(sh / fd - 1) if fd != 0 else np.nan:10.3f} "
            f"{abs(wterms[m, n]):10.3e} {abs(dC):10.3e}"
        )

    # ---- D2: Haswell's two entries -------------------------------------------
    hz = {(228, 220): 1.4649e02, (239, 222): 1.1629e-01}
    hff = {
        (228, 220): -2.48301e00 + 2.75406e00j,
        (239, 222): -9.02580e-02 + 1.08228e-01j,
    }
    print("\nD2 Haswell's entries (probe21 |Z|, probe19 field form (a)):")
    for mn in hz:
        m, n = mn
        print(
            f"  {m}x{n}: |shipped| here {abs(shipped[m, n]):.4e} (Haswell {hz[mn]:.4e}); "
            f"ff_direct here {ff_direct[m, n]:.5e} vs Haswell (a) {hff[mn]:.5e} -> rel {abs(ff_direct[m, n] - hff[mn]) / abs(hff[mn]):.3e}; "
            f"ff_kernel here {ff_kernel[m, n]:.5e}; wterms {wterms[m, n]:.5e}; dC {E['C_in'][m, n] - E['C_all'][m, n]:.5e}"
        )
        print(
            f"           row m vertical? {va[m]}  col n vertical on-axis? {vb[n] and on_axis_b[n]}"
        )

    np.savez(
        HERE / "probe1_blocks.npz",
        shipped=shipped,
        ff_direct=ff_direct,
        ff_kernel=ff_kernel,
        fixed=fixed,
        wterms=wterms,
        rows=rows,
        cols=cols,
        **S,
        **E,
    )


if __name__ == "__main__":
    main()
