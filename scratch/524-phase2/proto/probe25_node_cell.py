"""A-2 session 5, probe 25 — the CONSISTENT NODE CELL (exit beta, built on
designed kernels).

Gate 2 first pass (probe23) measured: designed cross tables alone do not
stop the merge/V blow-up. Diagnosis: the merged node diagonal is
Zbb[nb,nb] + Zaa[na,na] + 2 Zx[nb,na]; the corner-class (1/a-scale)
content telescopes ONLY under one convention, and the shipped SELF blocks'
node entries still carry quadrature-truncated content in two places:

  * the IMAGE pieces (off-edge n_qp_pair Gauss on pairs ~a apart — the
    "mirror is 2 depth away" premise dies at the interface node);
  * the outer Galerkin quadrature of every node-touching entry (segment
    Gauss cannot resolve variation at scale a on a >= 1 cm segment).

With the radius folded in, ALL node kernels are bounded (R >= a), so
log-graded quadrature to the a-scale genuinely converges (probe22: the
identities close to 5.7e-11 on exactly this quadrature). This probe:

  1. rebuilds axis quadrature with graded panels on node-touching
     segments (a-scale doubling), standard Gauss elsewhere;
  2. recomputes the designed cross pieces on that quadrature and patches
     the node-touching entries into probe23's t_ab (spelling B);
  3. recomputes the self IMAGE pieces' node-touching entries (closed-form
     kernels, alpha fitted on separated entries + analytic beta, probe14's
     shapes) at graded vs shipped quadrature, and applies the difference
     as a z-hook (Z carries -IMG, so Z += -(IMG_graded - IMG_gauss));
  4. checks the DIRECT self blocks against graded shapes (analytic
     moments are exact -> validates graded convergence, no correction);
  5. re-runs gate 2's cells (split / merged / V / S / V+S) at g1, g2.

Run: prlimit --as=$((8*1024*1024*1024)) .venv/bin/python \
       scratch/524-phase2/proto/probe25_node_cell.py [level ...]
"""

from __future__ import annotations

import json
import sys
import time
from pathlib import Path

import numpy as np
from numpy.polynomial.legendre import leggauss

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "567-phase0" / "proto"))
sys.path.insert(0, str(Path(__file__).resolve().parents[3] / "momwire" / "tests"))

import corner_tables as ct  # noqa: E402
import mp_cross  # noqa: E402
import probe14_same_medium as p14  # noqa: E402
from momwire.bspline import BSplineSolver  # noqa: E402
from probe1_baseline import seeded  # noqa: E402
from probe2_crossing import node_rows  # noqa: E402
from probe9_sense import capture  # noqa: E402
from probe13_x3 import node_indices  # noqa: E402
from probe18_graded import mono_graded  # noqa: E402
from probe19_graded_mpb import ENGINE_LIMIT, crossing_graded  # noqa: E402
from probe20_graded_rows import EPS_RATIO, solve_rows  # noqa: E402,F401
from probe23_designed_gate2 import pieces_designed  # noqa: E402

A_WIRE = 0.001
GX8, GW8 = leggauss(8)
ct.install(wire_radius=A_WIRE)


def graded_u(h, toward_end, a=A_WIRE):
    """Quadrature (u, w) on [0, h], log-graded (a-scale, doubling) toward
    u = h (toward_end='hi') or u = 0 ('lo'); Gauss-8 per panel."""
    edges = [0.0]
    step = a
    while edges[-1] + step < h:
        edges.append(edges[-1] + step)
        step *= 2.0
    edges.append(h)
    e = np.array(edges)
    if toward_end == "hi":
        e = h - e[::-1]
    mid = 0.5 * (e[:-1] + e[1:])
    half = 0.5 * (e[1:] - e[:-1])
    u = (mid[:, None] + half[:, None] * GX8[None, :]).ravel()
    w = (half[:, None] * GW8[None, :]).ravel()
    return u, w


def graded_axis_data(s, geom, seg_idx):
    """mp_cross.axis_data with graded quadrature on segments touching
    z = 0; same return contract (nodes, t, w, F, Fd, ends, n_basis)."""
    d = s.degree
    q = s._n_qp_buried_field()
    xg, wg = leggauss(q)
    tq = 0.5 * (xg + 1.0)

    supp_seg, polys, *_ = s._build_basis_polynomials(geom)
    n_basis = polys.shape[0]

    nodes_l, t_l, w_l, u_l, segpos = [], [], [], [], []
    for g in seg_idx:
        sl, sr = geom["seg_l"][g], geom["seg_r"][g]
        h = geom["h_per_seg"][g]
        tang = geom["tangents"][g]
        touch_lo = abs(sl[2]) < 1e-12
        touch_hi = abs(sr[2]) < 1e-12
        if touch_lo or touch_hi:
            u, w = graded_u(h, "lo" if touch_lo else "hi")
        else:
            u = h * tq
            w = 0.5 * h * wg
        nodes_l.append(sl[None, :] + (u / h)[:, None] * (sr - sl)[None, :])
        t_l.append(np.repeat(tang[None, :], len(u), axis=0))
        w_l.append(w)
        u_l.append(u)
        segpos.append(np.full(len(u), g, dtype=np.int64))
    nodes = np.concatenate(nodes_l)
    t_node = np.concatenate(t_l)
    w_node = np.concatenate(w_l)
    u_phys = np.concatenate(u_l)
    segof = np.concatenate(segpos)

    F = np.zeros((n_basis, len(u_phys)))
    Fd = np.zeros((n_basis, len(u_phys)))
    for m in range(n_basis):
        for a_ in range(d + 1):
            gseg = supp_seg[m, a_]
            sel = np.nonzero(segof == gseg)[0]
            if sel.size == 0:
                continue
            u = u_phys[sel]
            for p in range(d + 1):
                c = polys[m, a_, p]
                if c == 0.0:
                    continue
                F[m, sel] += c * u**p
                if p >= 1:
                    Fd[m, sel] += p * c * u ** (p - 1)

    base = mp_cross.axis_data(s, geom, seg_idx)  # ends table reused
    return dict(
        nodes=nodes, t=t_node, w=w_node, F=F, Fd=Fd, ends=base["ends"], n_basis=n_basis
    )


def cross_pieces_on_axes(s, A, B, rtol=1e-9):
    """mp_cross_block's arithmetic on custom axes (designed tables are
    installed as mp_cross.mp_tables). Returns M, SW, SQ, BT."""
    from momwire._sommerfeld_transmitted import _c1_moment

    eps_t, _eps_m, k_p, _k_m, _c2, _a_m = s._buried_medium()
    rho, z, zp, _x, _y = mp_cross._pair_geometry(A["nodes"], B["nodes"])
    tables = mp_cross.mp_tables(eps_t, k_p, rho, z, zp, rtol=rtol)
    U, V, W, dzW = tables["U"], tables["V"], tables["W"], tables["dzW"]

    c1 = _c1_moment(s.omega, s.mu)
    k2sq = k_p * k_p
    wA, wB = A["w"], B["w"]
    txA, tyA, tzA = A["t"].T
    txB, tyB, tzB = B["t"].T
    FA_w, FB_w = A["F"] * wA, B["F"] * wB
    FdA_w, FdB_w = A["Fd"] * wA, B["Fd"] * wB

    s_u = (FA_w * txA) @ U @ (FB_w * txB).T + (FA_w * tyA) @ U @ (FB_w * tyB).T
    s_zz = (FA_w * tzA) @ (k2sq * V - dzW) @ (FB_w * tzB).T
    s_w1 = (FA_w * tzA) @ W @ FdB_w.T
    s_w2 = FdA_w @ W @ (FB_w * tzB).T
    s_phi = -FdA_w @ V @ FdB_w.T
    M = c1 * (s_u + s_zz + s_w1 + s_w2 + s_phi)

    n_basis = A["n_basis"]
    BT = np.zeros((n_basis, n_basis), dtype=np.complex128)
    SW = np.zeros((n_basis, n_basis), dtype=np.complex128)
    SQ = np.zeros((n_basis, n_basis), dtype=np.complex128)
    for pt, sign, fv in A["ends"]:
        rho_e = np.hypot(pt[0] - B["nodes"][:, 0], pt[1] - B["nodes"][:, 1])
        te = mp_cross.mp_tables(
            eps_t,
            k_p,
            rho_e,
            np.full_like(rho_e, max(pt[2], 0.0)),
            B["nodes"][:, 2],
            rtol=rtol,
        )
        BT += c1 * sign * np.outer(fv, FdB_w @ te["V"])
    for pt, sign, fv in B["ends"]:
        rho_e = np.hypot(A["nodes"][:, 0] - pt[0], A["nodes"][:, 1] - pt[1])
        te = mp_cross.mp_tables(
            eps_t,
            k_p,
            rho_e,
            A["nodes"][:, 2],
            np.full_like(rho_e, pt[2]),
            rtol=rtol,
        )
        SW += -c1 * sign * np.outer((FA_w * tzA) @ te["W"], fv)
        SQ += c1 * sign * np.outer(FdA_w @ te["V"], fv)
    return M, SW, SQ, BT


def touching_bases(s, geom, seg_idx):
    """Basis indices with support on a segment touching z = 0, on the
    given axis."""
    supp_seg, polys, *_ = s._build_basis_polynomials(geom)
    touch = set()
    for g in seg_idx:
        if abs(geom["seg_l"][g][2]) < 1e-12 or abs(geom["seg_r"][g][2]) < 1e-12:
            touch.add(int(g))
    out = []
    for m in range(polys.shape[0]):
        # supp_seg rows are zero-padded; test polys per slot (probe0's trap)
        for a_ in range(supp_seg.shape[1]):
            if np.any(polys[m, a_] != 0.0) and int(supp_seg[m, a_]) in touch:
                out.append(m)
                break
    return sorted(set(out))


def self_image_correction(s, geom, seg_idx, k, weight_dot, weight_phi, mirror=True):
    """(graded - standard) of the image shapes alpha*S_A + beta*S_Phi over
    all entries, alpha fitted on separated standard entries against the
    shipped image block, beta analytic. Returns (delta, check_dir)."""
    axS = mp_cross.axis_data(s, geom, seg_idx)
    axG = graded_axis_data(s, geom, seg_idx)
    p14_axS = dict(axS)
    p14_axG = dict(axG)
    S_A_s, S_P_s, _ = p14.shapes(p14_axS, k, mirror)
    S_A_g, S_P_g, _ = p14.shapes(p14_axG, k, mirror)
    return (S_A_s, S_P_s, S_A_g, S_P_g)


def main():
    levels = [int(x) for x in sys.argv[1:]] or [1, 2]
    out = {}
    for lv in levels:
        s = seeded(crossing_graded(lv))
        geom = s._build_geometry()
        below = s._below_segments(geom)
        b_idx = np.nonzero(below)[0]
        a_idx = np.nonzero(~below)[0]
        b_seg = np.sort(b_idx)
        a_seg = np.sort(a_idx)
        nb, na = node_indices(s, geom)
        eps_t, eps_m, k_p, k_m, c2, a_m = s._buried_medium()
        supp_seg, polys, *_ = s._build_basis_polynomials(geom)

        # ---- 1+2: resolved cross pieces, patch node-touching entries ----
        t0 = time.time()
        axA_g = graded_axis_data(s, geom, a_idx)
        axB_g = graded_axis_data(s, geom, b_idx)
        Mg, SWg, SQg, BTg = cross_pieces_on_axes(s, axA_g, axB_g)
        print(f"g{lv}: resolved cross pieces {time.time() - t0:.0f}s", flush=True)

        pieces = pieces_designed(lv)
        t_ab = (pieces["M"] + pieces["SW"] + pieces["SQ"]).astype(complex)
        t_ab_res = Mg + SWg + SQg

        tb_a = touching_bases(s, geom, a_idx)
        tb_b = touching_bases(s, geom, b_idx)
        patch = np.zeros_like(t_ab, dtype=bool)
        for m in tb_a:
            patch[m, :] = True
        for n in tb_b:
            patch[:, n] = True
        moved = np.abs(t_ab_res - t_ab)[patch].max()
        t_ab_new = np.where(patch, t_ab_res, t_ab)
        print(
            f"g{lv}: touching above {tb_a} below {tb_b}; max cross move "
            f"{moved:.4g}; [na,nb] {t_ab[na, nb]:.4g} -> "
            f"{t_ab_res[na, nb]:.4g}",
            flush=True,
        )

        # ---- 3+4: self image corrections + direct check -----------------
        d_hooks = []
        for name, idx, k, wgt, eps in (
            ("bb", b_idx, k_m, a_m, eps_m),
            ("aa", a_idx, k_p, c2, None),
        ):
            S_A_s, S_P_s, S_A_g, S_P_g = self_image_correction(
                s, geom, idx, k, wgt, wgt
            )
            # shipped image block for the alpha fit
            td_img = s._image_tangent_dot(geom["tangents"])
            kw = {} if eps is None else {"eps": eps}
            IMG = s._image_Z_weighted(
                s._build_J_blocks_subset(geom, k, idx, mirror_sources=True),
                supp_seg,
                polys,
                wgt * td_img.astype(np.complex128),
                np.full(td_img.shape, wgt, dtype=np.complex128),
                **kw,
            )
            axS = mp_cross.axis_data(s, geom, idx)
            mask, _lo, _hi = p14.separated_mask(axS)
            alpha, beta_fit, relr, npts = p14.fit_ab(IMG, S_A_s, S_P_s, mask)
            omega, mu, eps0 = s.omega, s.mu, s.eps  # noqa: F841 — kept: names the quantity the probe computed, read when inspecting
            beta = wgt / (1j * omega * (eps if eps is not None else eps0) * 4 * np.pi)
            dimg = alpha * (S_A_g - S_A_s) + beta * (S_P_g - S_P_s)
            # direct check: graded shapes vs shipped analytic direct
            kwd = {} if eps is None else {"eps": eps}
            MPd = s._assemble_Z(
                s._build_J_blocks_subset(geom, k, idx),
                supp_seg,
                polys,
                geom,
                **kwd,
            )
            S_A_sd, S_P_sd, _ = p14.shapes(axS, k, False)
            axG = graded_axis_data(s, geom, idx)
            S_A_gd, S_P_gd, _ = p14.shapes(axG, k, False)
            a_d, b_d, rel_d, _ = p14.fit_ab(MPd, S_A_sd, S_P_sd, mask)
            beta_dir = 1.0 / (
                1j * omega * (eps if eps is not None else eps0) * 4 * np.pi
            )
            tb = tb_b if name == "bb" else tb_a
            node_i = nb if name == "bb" else na
            dir_res = np.abs((a_d * S_A_gd + beta_dir * S_P_gd) - MPd)[node_i, node_i]
            print(
                f"g{lv} {name}: alpha fit rel {relr:.1e} (n={npts}); "
                f"img corr [{node_i},{node_i}] = {dimg[node_i, node_i]:.4g}"
                f"; direct graded-vs-analytic node resid {dir_res:.4g} "
                f"(|MPd| {abs(MPd[node_i, node_i]):.4g})",
                flush=True,
            )
            mask_self = np.zeros_like(dimg, dtype=bool)
            for m in tb:
                mask_self[m, :] = True
                mask_self[:, m] = True
            d_hooks.append(np.where(mask_self, dimg, 0.0))

        d_img_total = -(d_hooks[0] + d_hooks[1])  # Z carries -IMG

        def corr_hook(Zp, add=d_img_total):
            return Zp + add

        # ---- 5: gate-2 cells --------------------------------------------
        row_v, der_a, der_b = node_rows(s, geom)
        row_s = der_a - EPS_RATIO * der_b
        z_mono = capture(BSplineSolver(**mono_graded(lv)))["z_in"]
        h_min = float(geom["h_per_seg"].min())
        print(f"g{lv}: mono = {z_mono:.4f}  h_node = {h_min:.4f}", flush=True)

        def merge_hook(Zp, nb=nb, na=na):
            Zp = corr_hook(Zp)
            Zp[:, nb] += Zp[:, na]
            Zp[nb, :] += Zp[na, :]
            Zp[na, :] = 0.0
            Zp[:, na] = 0.0
            Zp[na, na] = 1.0
            return Zp

        cells = [
            ("split", "hook", corr_hook),
            ("merged", "hook", merge_hook),
            ("V", "rows", [row_v]),
            ("S", "rows", [row_s]),
            ("V+S", "rows", [row_v, row_s]),
        ]
        for cname, kind, arg in cells:
            t0 = time.time()
            if kind == "hook":
                st = capture(
                    seeded(crossing_graded(lv)),
                    t_ab=t_ab_new,
                    a_seg=a_seg,
                    b_seg=b_seg,
                    z_hook=arg,
                )
                z = st["z_in"]
            else:
                orig_kcl = BSplineSolver._solve_with_kcl

                def wrap_kcl(self, Z, v, kcl_A, overwrite=False, rows=arg):
                    Z = corr_hook(Z.copy())
                    if rows:
                        add = np.stack(rows)
                        kcl_A = np.vstack([kcl_A.astype(add.dtype), add])
                    return orig_kcl(self, Z, v, kcl_A, overwrite=False)

                BSplineSolver._solve_with_kcl = wrap_kcl
                try:
                    st = capture(
                        seeded(crossing_graded(lv)),
                        t_ab=t_ab_new,
                        a_seg=a_seg,
                        b_seg=b_seg,
                    )
                finally:
                    BSplineSolver._solve_with_kcl = orig_kcl
                z = st["z_in"]
            d = z - z_mono
            dist = abs(d - ENGINE_LIMIT)
            out[f"g{lv}+cell+{cname}"] = dict(
                z=f"{z:.4f}",
                delta=f"{d:.4f}",
                dist_ohm=round(float(dist), 3),
            )
            print(
                f"  g{lv} cell+{cname:>6}: Z = {z:9.4f}   Delta = "
                f"{d:9.4f}   dist = {dist:7.3f}   ({time.time() - t0:.0f}s)",
                flush=True,
            )

    fp = HERE.parent / "results" / "probe25-node-cell.json"
    old = json.loads(fp.read_text()) if fp.exists() else {}
    old.update(out)
    fp.write_text(json.dumps(old, indent=1))
    print(f"saved {fp}")


if __name__ == "__main__":
    main()
