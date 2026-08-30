"""momwire#567 phase 0 — the mixed-potential cross-medium block, standalone.

Implements FORMULATION.md §5: the transmitted cross block written in mixed-
potential form from the scalar tables {U_T, V_T, W_T, dzW_T}, with the
integration-by-parts boundary terms carried EXPLICITLY (§6). Nothing here
touches production code paths; the shipped field-form block is the identity
target, not an input.

Scope guard: the by-parts that moves horizontal derivatives of W onto basis
polynomials uses t̂⊥·∇⊥ = d/dl, which is exact only for segments that are
purely horizontal or purely vertical. The phase-0 decks are exactly that; a
tilted wire needs the extra t_z·∂z(′)W piece (one more table, same contour)
and refuses here rather than silently mis-assembling.
"""

from __future__ import annotations

import numpy as np
from numpy.polynomial.legendre import leggauss

from momwire import _medium_spec
from momwire._sommerfeld_transmitted import (
    _ADAPT_DEPTH,
    _DETOUR,
    _GW,
    _GX,
    _MAX_TAIL_PANELS_T,
    _bessel_j0_j1x,
    _c1_moment,
    _gamma,
    _run_contour,
    k_medium,
)

_TILT_TOL = 1e-12


def mp_kernel_integrand(lam, rho, z, zp, k_p, k_m):
    """The four MP λ-integrands at one (ρ, z, z′), stacked (4, n):

      0: U_T            = 2∫ Ẽ/(γ₊+γ₋) J₀ λ dλ            (7g, = family index 5)
      1: V_T            = 2∫ Ẽ/(k₋²γ₊+k₊²γ₋) J₀ λ dλ      (7f, scalar — the NEW one)
      2: W_T            = 2∫ (γ₊−γ₋)·Ṽ J₀ λ dλ            (FORMULATION §3)
      3: ∂z W_T         = −γ₊·W̃ under the integral         (FORMULATION §4)

    Same Ẽ, same contour, same conventions as `_integrand_six_transmitted`;
    index 1 of the shipped family (λ²V) is NOT re-derived from component 1
    here — #568's conditioning rule.
    """
    lam = np.asarray(lam, dtype=np.complex128)
    g_p = _gamma(lam, k_p)
    g_m = _gamma(lam, k_m)
    e = 2.0 * np.exp(-g_m * abs(zp) - g_p * z) * lam
    a = e / (k_m * k_m * g_p + k_p * k_p * g_m)
    u = e / (g_m + g_p)
    b0, _b1x = _bessel_j0_j1x(lam * rho)
    w = (g_p - g_m) * a
    return np.stack([u * b0, a * b0, w * b0, -g_p * w * b0])


def mp_tables(eps_t, k2, rho, z, zp, rtol=1e-10):
    """Direct (no-grid) evaluation of the four MP scalars at broadcast
    (ρ, z, z′). Returns dict of complex arrays. O(ms)/point, python contour."""
    k_p = float(k2)
    k_m = k_medium(complex(eps_t), k_p)
    rho_b, z_b, zp_b = np.broadcast_arrays(
        np.asarray(rho, float), np.asarray(z, float), np.asarray(zp, float)
    )
    out = np.empty((4,) + rho_b.shape, dtype=np.complex128)
    it = np.nditer(rho_b, flags=["multi_index"])
    for _ in it:
        ix = it.multi_index
        r_i, z_i, p_i = float(rho_b[ix]), float(z_b[ix]), float(zp_b[ix])
        if not (p_i < 0.0 and z_i >= 0.0):
            raise ValueError(f"need source below, observer at-or-above: {z_i}, {p_i}")

        def f(lam):
            return mp_kernel_integrand(lam, r_i, z_i, p_i, k_p, k_m)

        vals, _hp, _tp, conv, _acc = _run_contour(
            f,
            k_p,
            k_m,
            r_i,
            abs(p_i) + abs(z_i),
            rtol,
            _ADAPT_DEPTH,
            _DETOUR,
            _GX,
            _GW,
            max_panels=_MAX_TAIL_PANELS_T,
        )
        if not conv:
            raise RuntimeError(f"contour did not converge at {(r_i, z_i, p_i)}")
        out[(slice(None),) + ix] = vals
    return {"U": out[0], "V": out[1], "W": out[2], "dzW": out[3]}


# ---------------------------------------------------------------------------
# Geometry / basis helpers
# ---------------------------------------------------------------------------


def axis_data(s, geom, seg_idx):
    """Everything one axis of the block needs: nodes, per-node tangents and
    weights, per-basis value/derivative matrices at the nodes, and the
    signed wire-end table for the boundary terms."""
    d = s.degree
    q = s._n_qp_buried_field()
    xg, wg = leggauss(q)
    tq = 0.5 * (xg + 1.0)
    seg_l = geom["seg_l"][seg_idx]
    seg_r = geom["seg_r"][seg_idx]
    h = geom["h_per_seg"][seg_idx]
    tang = geom["tangents"][seg_idx]
    n_seg = len(seg_idx)

    nodes = (
        seg_l[:, None, :] + tq[None, :, None] * (seg_r - seg_l)[:, None, :]
    ).reshape(n_seg * q, 3)
    t_node = np.repeat(tang, q, axis=0)
    if np.any(
        (np.abs(t_node[:, 2]) > _TILT_TOL)
        & (np.hypot(t_node[:, 0], t_node[:, 1]) > _TILT_TOL)
    ):
        raise NotImplementedError(
            "tilted segments need the tilt tables (see docstring)"
        )
    w_node = (0.5 * h[:, None] * wg[None, :]).reshape(n_seg * q)
    u_phys = (h[:, None] * tq[None, :]).reshape(n_seg * q)

    supp_seg, polys, *_ = s._build_basis_polynomials(geom)
    n_basis = polys.shape[0]
    pos = np.full(geom["n_segs_total"], -1, dtype=np.int64)
    pos[seg_idx] = np.arange(n_seg)

    F = np.zeros((n_basis, n_seg * q))
    Fd = np.zeros((n_basis, n_seg * q))
    for m in range(n_basis):
        for a in range(d + 1):
            i = pos[supp_seg[m, a]]
            if i < 0:
                continue
            sl = slice(i * q, (i + 1) * q)
            u = u_phys[sl]
            for p in range(d + 1):
                c = polys[m, a, p]
                if c == 0.0:
                    continue
                F[m, sl] += c * u**p
                if p >= 1:
                    Fd[m, sl] += p * c * u ** (p - 1)

    # Signed wire-end table: (point, sign, per-basis value there). Interior
    # junction points cancel per basis by KCL when these are summed; free
    # ends carry no basis; only a kept contact basis survives.
    seg_off = geom["seg_offsets"]
    ends = []
    on_axis = set(int(g) for g in seg_idx)
    for w in range(len(seg_off) - 1):
        first, last = seg_off[w], seg_off[w + 1] - 1
        if first not in on_axis:
            continue
        for gseg, sign, u_end in ((first, -1.0, 0.0), (last, +1.0, None)):
            hh = geom["h_per_seg"][gseg]
            u = hh if u_end is None else 0.0
            pt = geom["seg_l"][gseg] + (u / hh) * (
                geom["seg_r"][gseg] - geom["seg_l"][gseg]
            )
            fv = np.zeros(n_basis)
            for m in range(n_basis):
                for a in range(d + 1):
                    if supp_seg[m, a] == gseg:
                        fv[m] += sum(polys[m, a, p] * u**p for p in range(d + 1))
            if np.any(fv != 0.0):
                ends.append((pt, sign, fv))
    return dict(nodes=nodes, t=t_node, w=w_node, F=F, Fd=Fd, ends=ends, n_basis=n_basis)


def _pair_geometry(above_nodes, below_nodes):
    """(ρ, z, z′, dhx, dhy) tables, above × below; dh is the unit horizontal
    from the BELOW point to the ABOVE point (the transposed-combine rule)."""
    dx = above_nodes[:, 0][:, None] - below_nodes[:, 0][None, :]
    dy = above_nodes[:, 1][:, None] - below_nodes[:, 1][None, :]
    rho = np.hypot(dx, dy)
    safe = np.where(rho > 0.0, rho, 1.0)
    dhx = np.where(rho > 0.0, dx / safe, 1.0)
    dhy = np.where(rho > 0.0, dy / safe, 0.0)
    z = np.broadcast_to(above_nodes[:, 2][:, None], rho.shape)
    zp = np.broadcast_to(below_nodes[:, 2][None, :], rho.shape)
    return rho, z, zp, dhx, dhy


def mp_cross_block(s, rtol=1e-10, tables=None, boundary="keep"):
    """t_ab in MP form (FORMULATION §5) over the (above × below) pairs,
    returned as a full (n_basis, n_basis) matrix plus the pieces:

    returns dict:
      t_ab       — main MP block + boundary per `boundary`
      main       — the no-boundary MP block (spelling B of §7)
      bnd_test   — the test-side (contact) Φ boundary block
      bnd_src_W  — source-side W boundary (0 for KCL-clean decks)
      tables     — the kernel tables (reused across calls)

    `boundary`: 'keep' (spelling A ≡ field form) or 'drop' (spelling B).
    t_ba is the transpose by reciprocity (asserted separately in probe 1).
    """
    geom = s._build_geometry()
    below = s._below_segments(geom)
    b_idx = np.nonzero(below)[0]
    a_idx = np.nonzero(~below)[0]
    eps_t, _eps_m, k_p, k_m, _c2, _a_m = s._buried_medium()

    A = axis_data(s, geom, a_idx)
    B = axis_data(s, geom, b_idx)
    rho, z, zp, _dhx, _dhy = _pair_geometry(A["nodes"], B["nodes"])
    if tables is None:
        tables = mp_tables(eps_t, k_p, rho, z, zp, rtol=rtol)
    U, V, W, dzW = tables["U"], tables["V"], tables["W"], tables["dzW"]

    c1 = _c1_moment(s.omega, s.mu)
    k2sq = k_p * k_p

    wA, wB = A["w"], B["w"]
    txA, tyA, tzA = A["t"].T
    txB, tyB, tzB = B["t"].T

    # Horizontal tangent dot needs the pair azimuth only through t⊥·t⊥′,
    # which is coordinate-frame invariant — no dh needed in MP form.
    FA_w = A["F"] * wA
    FB_w = B["F"] * wB
    FdA_w = A["Fd"] * wA
    FdB_w = B["Fd"] * wB

    s_u = (FA_w * txA) @ U @ (FB_w * txB).T + (FA_w * tyA) @ U @ (FB_w * tyB).T
    s_zz = (FA_w * tzA) @ (k2sq * V - dzW) @ (FB_w * tzB).T
    s_w1 = (FA_w * tzA) @ W @ FdB_w.T
    s_w2 = FdA_w @ W @ (FB_w * tzB).T
    s_phi = -FdA_w @ V @ FdB_w.T
    main = c1 * (s_u + s_zz + s_w1 + s_w2 + s_phi)

    # --- boundary terms -----------------------------------------------------
    n_basis = A["n_basis"]
    bnd_test = np.zeros((n_basis, n_basis), dtype=np.complex128)
    bnd_src_Wp = np.zeros((n_basis, n_basis), dtype=np.complex128)
    bnd_src_q = np.zeros((n_basis, n_basis), dtype=np.complex128)
    for pt, sign, fv in A["ends"]:
        # test-side Φ by-parts: +σ f_m(E) Σ_j f_n′ w_j V(E, j)
        rho_e = np.hypot(pt[0] - B["nodes"][:, 0], pt[1] - B["nodes"][:, 1])
        te = mp_tables(
            eps_t,
            k_p,
            rho_e,
            np.full_like(rho_e, max(pt[2], 0.0)),
            B["nodes"][:, 2],
            rtol=rtol,
        )
        col = FdB_w @ te["V"]
        bnd_test += c1 * sign * np.outer(fv, col)
    for pt, sign, fv in B["ends"]:
        # source-side W by-parts: −σ f_n(E) Σ_i f_m t_z w_i W(i, E)
        rho_e = np.hypot(A["nodes"][:, 0] - pt[0], A["nodes"][:, 1] - pt[1])
        te = mp_tables(
            eps_t,
            k_p,
            rho_e,
            A["nodes"][:, 2],
            np.full_like(rho_e, pt[2]),
            rtol=rtol,
        )
        row = (FA_w * tzA) @ te["W"]
        bnd_src_Wp += -c1 * sign * np.outer(row, fv)
        # source-side Φ by-parts (+σ f_n(E) Σ_i f_m' w_i V(i,E)) and the
        # corner term belong here too for a general deck; on these decks
        # every below end is KCL-clean or free, so they cancel identically
        # inside the same loop — carried for the fan-junction proof:
        rowp = FdA_w @ te["V"]
        bnd_src_q += c1 * sign * np.outer(rowp, fv)

    bnd_src_W = bnd_src_Wp + bnd_src_q
    t_ab = main + bnd_src_W + (bnd_test if boundary == "keep" else 0.0)
    return dict(
        t_ab=t_ab,
        main=main + bnd_src_W,
        main_raw=main,
        bnd_test=bnd_test,
        bnd_src_W=bnd_src_W,
        bnd_src_Wp=bnd_src_Wp,
        bnd_src_q=bnd_src_q,
        tables=tables,
    )


def seeded(build, eps=None):
    """A refused deck reached past the refusal, the G-U5-3 way."""
    from momwire import BSplineSolver

    kw = dict(build)
    if eps is not None:
        kw["ground_eps"] = eps
    s = BSplineSolver(**kw)
    n_wires = len(kw["wires"])
    s._cached_wire_media = (_medium_spec.ABOVE,) + (_medium_spec.BELOW,) * (n_wires - 1)
    return s
