"""momwire#760 unit 4 — where the cross-edge quadrature error actually lives.

#760 owes a singularity-aware rule for the near-touching pair class. Before
building one there is a cheaper question to settle: is the q=8 error carried by
a handful of pairs, or spread thinly over all of them? The first answer says
build an adaptive-order rule (refine the few pairs that matter); the second says
adaptive order buys little and the money is in singularity subtraction, which
fixes the whole class at once.

First-order sensitivity answers it without a second solve. The fill error is a
pure perturbation of Z at fixed dimension (unlike a mesh change, which moves the
trial space), so with `Z c = v` and the driving-point current read back as
`I = v^T c`,

    dZ_in = u^T dZ u,        u = c / I

is exact to first order — a rank-1 weight `u_m u_n` on every entry, and NO
adjoint solve, because momwire's Galerkin fill is complex-symmetric (the
symmetry gate of momwire#249 §4.1 keeps it so) and `compute_impedance` reads the
port current with the SAME Galerkin vector that drives the RHS
(`bspline.py:5148`). The KCL block, when a deck has one, is unperturbed and
keeps the augmented matrix symmetric, so the identity survives it.

Taking dZ = Z(q_hi) - Z(q_lo) on a FIXED mesh turns that into a per-entry
attribution of the measured q_lo -> q_hi move. `--validate` checks the identity
against the real move before any of the ranking is believed.

The attribution is then pushed down to the granularity a rule would act at.
Basis supports straddle segments and edges, so each basis is split across them
by a partition of unity weighted by support length (rows of `W` sum to 1), and

    C = W^T (u u^T * dZ) W

aggregates the SIGNED contribution per segment pair (the granularity of the
quadrature loop) and per edge pair (the granularity of the fill's pair classes).
Because W is row-stochastic the total is preserved: sum(C) == dZ_in.

Signed is the operative word. The L1 mass of `u_m u_n dZ_mn` overstates the move
by ~3 orders of magnitude on the fan, so a trigger built on |.| would demand
accuracy everywhere. What matters is whether the cancellation is INSIDE the
blocks a rule refines as a unit (harmless) or BETWEEN the top blocks and the
tail (fatal for localizing).

Run: prlimit --as=$((8*1024*1024*1024)) \
       .venv/bin/python scratch/674-study/probe4_sensitivity_ranking.py \
       [--deck fan|brv] [--case base|n1|n2|n3] [--lo 8] [--hi 32]
"""

from __future__ import annotations

import argparse
import json
import sys
import time
import warnings
from pathlib import Path

import numpy as np

# Inlined rather than via a `HERE =` local on purpose: ruff's E402 exemption
# for the sys.path idiom only survives if the mutation is the ONLY statement
# before the import, so a bare assignment here would cost a suppression comment
# that the repo's convention exists to avoid. (Spelling the directive out in
# prose here would also make ruff try to PARSE it -- hence the paraphrase.)
sys.path.insert(0, str(Path(__file__).resolve().parent))
sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "momwire" / "tests"))

from momwire.bspline import BSplineSolver

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]

# ----------------------------------------------------------------- decks


def fan_build(case, n_qp_pair):
    from probe3_soil_ladder import CASES, _graded_soil_build

    return dict(_graded_soil_build(**CASES[case]), n_qp_pair=n_qp_pair)


def brv_build(case, n_qp_pair):
    sys.path.insert(0, str(ROOT / "scratch" / "buried-quality-post"))
    from probe1_ladders import harvested_kwargs, mw_engine

    nsegs = {"base": 21, "n1": 31, "n2": 42}.get(case, 21)
    engine, b = mw_engine(nsegs)
    return dict(harvested_kwargs(engine, b), n_qp_pair=n_qp_pair)


DECKS = {"fan": fan_build, "brv": brv_build}

# ------------------------------------------------------- fill and solve


def fill(deck, case, q):
    """Z, coeffs, port current and Z_in on a mesh that does not depend on q."""
    s = BSplineSolver(**DECKS[deck](case, q))
    geom = s._build_geometry()
    supp_seg, polys, kcl_A, wire_knots, wire_basis_global = s._build_basis_polynomials(
        geom
    )
    t0 = time.time()
    Z = s._compute_Z_operator(geom, supp_seg, polys)
    v, port_vectors, _vpf_T, all_voltages, kcl_con = s._feed_drive_and_readout(
        geom, wire_knots, wire_basis_global, supp_seg.shape[0], kcl_A
    )
    if len(port_vectors) != 1:
        raise SystemExit(f"probe4 assumes a single feed; deck has {len(port_vectors)}")
    c = s._solve_with_kcl(Z, v, kcl_con)
    i_port = port_vectors[0] @ c[: port_vectors[0].shape[0]]
    z_in = all_voltages[0] / i_port
    secs = time.time() - t0
    print(f"  q={q:<3d} Z_in = {z_in:.4f}   ({secs:.1f}s)", flush=True)
    return dict(
        solver=s,
        geom=geom,
        supp_seg=supp_seg,
        polys=np.asarray(polys),
        Z=Z,
        c=c,
        i_port=i_port,
        z_in=z_in,
        secs=secs,
    )


# ------------------------------------------------- support partition of unity


def support_weights(geom, supp_seg, polys):
    """Row-stochastic (n_basis, n_seg) split of each basis over its support.

    Unused wings are padded with segment index 0 (`_build_basis_polynomials`
    zero-fills), which is a LEGAL index — so the padding is identified by its
    all-zero polynomial block, not by the segment id.
    """
    h = np.asarray(geom["h_per_seg"], dtype=float)
    n_basis, n_wings = supp_seg.shape
    W = np.zeros((n_basis, h.size))
    live = np.abs(polys).sum(axis=2) > 0.0  # (n_basis, n_wings)
    for m in range(n_basis):
        for a in range(n_wings):
            if live[m, a]:
                W[m, supp_seg[m, a]] += h[supp_seg[m, a]]
        tot = W[m].sum()
        if tot > 0:
            W[m] /= tot
        else:  # a basis with no live wing cannot carry current; leave it at 0
            warnings.warn(f"basis {m} has empty support", stacklevel=2)
    return W


def segment_edges(geom):
    """(n_seg,) global edge id, plus per-edge (wire, edge_in_wire) labels."""
    seg_off = np.asarray(geom["seg_offsets"])
    owner = np.zeros(int(seg_off[-1]), dtype=int)
    labels = []
    for w, per in enumerate(geom["per_wire"]):
        eo = list(per["edge_offsets"])
        for e in range(len(eo) - 1):
            owner[seg_off[w] + eo[e] : seg_off[w] + eo[e + 1]] = len(labels)
            labels.append((w, e))
    return owner, labels


# --------------------------------------------------------------- geometry


def _seg_seg_distance(p0, p1, q0, q1):
    """Shortest distance between two 3-D closed segments (Ericson)."""
    d1, d2, r = p1 - p0, q1 - q0, p0 - q0
    a, e, f = d1 @ d1, d2 @ d2, d2 @ r
    eps = 1e-15
    if a <= eps and e <= eps:
        return float(np.linalg.norm(r))
    if a <= eps:
        s, t = 0.0, np.clip(f / e, 0.0, 1.0)
    else:
        c = d1 @ r
        if e <= eps:
            t, s = 0.0, np.clip(-c / a, 0.0, 1.0)
        else:
            b = d1 @ d2
            denom = a * e - b * b
            s = np.clip((b * f - c * e) / denom, 0.0, 1.0) if denom > eps else 0.0
            t = (b * s + f) / e
            if t < 0.0:
                t, s = 0.0, np.clip(-c / a, 0.0, 1.0)
            elif t > 1.0:
                t, s = 1.0, np.clip((b - c) / a, 0.0, 1.0)
    return float(np.linalg.norm((p0 + s * d1) - (q0 + t * d2)))


def pair_geometry(geom):
    """(n_seg, n_seg) shortest distance, and the #760 key R_min / min(h, h)."""
    sl = np.asarray(geom["seg_l"], dtype=float)
    sr = np.asarray(geom["seg_r"], dtype=float)
    h = np.asarray(geom["h_per_seg"], dtype=float)
    n = h.size
    dist = np.zeros((n, n))
    for p in range(n):
        for q in range(p + 1, n):
            d = _seg_seg_distance(sl[p], sr[p], sl[q], sr[q])
            dist[p, q] = dist[q, p] = d
    ratio = dist / np.minimum.outer(h, h)
    return dist, ratio


# ---------------------------------------------------------------- reporting


def _concentration(mag, total, fracs=(0.5, 0.9, 0.99)):
    order = np.argsort(mag.ravel())[::-1]
    csum = np.cumsum(mag.ravel()[order]) / total
    return {
        f"{f:.0%}": int(np.searchsorted(csum, f)) + 1 for f in fracs if total > 0
    }, order


def signed_capture(C, delta, fracs=(0.5, 0.9, 0.99)):
    """Ranking blocks by |C|, how many must be corrected to capture `delta`.

    Reports the SIGNED partial sum, i.e. the residual a rule would leave if it
    refined only the top-k blocks and left the rest at the coarse order.
    """
    flat = C.ravel()
    order = np.argsort(np.abs(flat))[::-1]
    partial = np.cumsum(flat[order])
    remaining = np.abs(delta - partial) / abs(delta)
    out = {}
    for f in fracs:
        hit = np.nonzero(remaining <= 1.0 - f)[0]
        out[f"{f:.0%}"] = int(hit[0]) + 1 if hit.size else None
    return out, order, remaining


def geometric_rule_sweep(C, key, delta, thresholds):
    """Would a geometry key find these blocks?

    Include every segment pair with `key <= threshold` — i.e. refine those and
    leave the rest at the coarse order — and report the signed contribution
    captured, plus the residual such a rule would leave and what it costs.
    """
    rows = []
    for t in thresholds:
        mask = key <= t
        got = C[mask].sum()
        rows.append(
            dict(
                threshold=t,
                pairs=int(mask.sum()),
                pair_frac=round(float(mask.mean()), 5),
                captured=f"{got:.4f}",
                captured_frac=round(float(abs(got) / abs(delta)), 4),
                residual=round(float(abs(delta - got)), 4),
            )
        )
    return rows


def entry_distance(supp_seg, polys, dist):
    """(n_basis, n_basis) shortest distance between two bases' supports."""
    live = np.abs(polys).sum(axis=2) > 0.0
    n_basis = supp_seg.shape[0]
    segs = [supp_seg[m][live[m]] for m in range(n_basis)]
    R = np.zeros((n_basis, n_basis))
    for m in range(n_basis):
        sm = segs[m]
        for n in range(m, n_basis):
            d = dist[np.ix_(sm, segs[n])].min()
            R[m, n] = R[n, m] = d
    return R


def masked_refine(Z_lo, dZ, S, ks, s_lo, v, kcl_con, port_vec, volts, z_hi, z_lo):
    """EXACT test of PARTIAL refinement, the question adaptive order lives on.

    `dZ` is nonzero only on pairs whose supports touch, so refining that whole
    class trivially reproduces the fine answer. What a rule actually proposes is
    to refine a SUBSET of it. So: rank entries by the first-order weight
    |u_m u_n dZ_mn|, correct the top k (symmetrized, so a pair is corrected with
    its transpose), SOLVE, and compare.

    `vs_coarse` < 1 means the partial rule beat leaving everything coarse; > 1
    means refining those pairs made the answer WORSE than not refining at all.
    """
    tri = np.triu(np.abs(S) + np.abs(S).T)
    order = np.argsort(tri.ravel())[::-1]
    rows = []
    for k in ks:
        mask = np.zeros(S.shape, dtype=bool)
        idx = order[:k]
        mask.ravel()[idx] = True
        mask |= mask.T
        Z_mix = Z_lo + np.where(mask, dZ, 0.0)
        c = s_lo._solve_with_kcl(Z_mix, v, kcl_con)
        z = volts[0] / (port_vec @ c[: port_vec.shape[0]])
        rows.append(
            dict(
                k=int(k),
                entries=int(mask.sum()),
                z=f"{z:.4f}",
                err_vs_hi=round(float(abs(z - z_hi)), 4),
                vs_coarse=round(float(abs(z - z_hi) / abs(z_lo - z_hi)), 3),
            )
        )
    return rows


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--deck", default="fan", choices=sorted(DECKS))
    ap.add_argument("--case", default="base")
    ap.add_argument("--lo", type=int, default=8)
    ap.add_argument("--hi", type=int, default=32)
    ap.add_argument("--top", type=int, default=12)
    args = ap.parse_args()

    print(f"[{args.deck}/{args.case}] fills at q={args.lo} and q={args.hi}", flush=True)
    lo = fill(args.deck, args.case, args.lo)
    hi = fill(args.deck, args.case, args.hi)

    Z_lo, Z_hi = lo["Z"], hi["Z"]
    if Z_lo.shape != Z_hi.shape:
        raise SystemExit("mesh changed between orders — the perturbation is not pure")
    dZ = Z_hi - Z_lo
    u = lo["c"] / lo["i_port"]
    n_p = Z_lo.shape[0]
    u = u[:n_p]

    delta_pred = complex(u @ dZ @ u)
    delta_act = complex(hi["z_in"] - lo["z_in"])
    resid = abs(delta_act - delta_pred)
    asym = float(np.abs(Z_lo - Z_lo.T).max() / np.abs(Z_lo).max())

    print()
    print("=== first-order identity (the thing everything below rests on) ===")
    print(f"  measured  z(q{args.hi}) - z(q{args.lo}) = {delta_act:.5f}")
    print(f"  predicted u^T dZ u              = {delta_pred:.5f}")
    print(
        f"  residual (second order)         = {resid:.5f}"
        f"  ({100 * resid / abs(delta_act):.2f}% of the move)"
    )
    print(f"  corrected z(q{args.lo}) + pred        = {lo['z_in'] + delta_pred:.4f}")
    print(f"  reference z(q{args.hi})                = {hi['z_in']:.4f}")
    print(f"  relative asymmetry of Z         = {asym:.2e}")

    S = np.outer(u, u) * dZ
    l1 = float(np.abs(S).sum())
    entry_conc, _ = _concentration(np.abs(S), l1)

    print()
    print("=== entry level ===")
    print(
        f"  sum|u_m u_n dZ_mn| = {l1:.4f}   vs |dZ_in| = {abs(delta_pred):.4f}"
        f"   (cancellation {l1 / abs(delta_pred):.0f}x)"
    )
    for k, n in entry_conc.items():
        print(
            f"  {k:>4} of the L1 mass in {n} of {S.size} entries"
            f" ({100 * n / S.size:.2f}%)"
        )

    W = support_weights(lo["geom"], lo["supp_seg"], lo["polys"])
    C_seg = W.T @ S @ W
    owner, labels = segment_edges(lo["geom"])
    n_edge = len(labels)
    E = np.zeros((W.shape[1], n_edge))
    E[np.arange(W.shape[1]), owner] = 1.0
    C_edge = E.T @ C_seg @ E

    for name, C in (("segment pair", C_seg), ("edge pair", C_edge)):
        got = complex(C.sum())
        print()
        print(f"=== {name} blocks ({C.shape[0]}^2 = {C.size}) ===")
        print(
            f"  partition check: sum(C) = {got:.5f}  (vs {delta_pred:.5f},"
            f" err {abs(got - delta_pred):.2e})"
        )
        cap, order, remaining = signed_capture(C, delta_pred)
        for k, n in cap.items():
            if n is not None:
                print(
                    f"  {k:>4} of the SIGNED move captured by the top {n} blocks"
                    f" ({100 * n / C.size:.2f}%)"
                )
            else:
                print(f"  {k:>4} of the SIGNED move never captured by |C| ranking")
        print(
            f"  L1/|signed| within this grouping ="
            f" {float(np.abs(C).sum()) / abs(got):.1f}x"
        )

    dist, ratio = pair_geometry(lo["geom"])
    print()
    print(f"=== top {args.top} segment-pair blocks ===")
    print(
        f"  {'p':>4} {'q':>4} {'wire/edge':>13} {'R_min(mm)':>10}"
        f" {'R/h':>7} {'contribution':>22} {'|C|':>9}"
    )
    flat_order = np.argsort(np.abs(C_seg).ravel())[::-1]
    for idx in flat_order[: args.top]:
        p, q = divmod(int(idx), C_seg.shape[1])
        wp, ep = labels[owner[p]]
        wq, eq = labels[owner[q]]
        print(
            f"  {p:>4} {q:>4} {f'{wp}.{ep}-{wq}.{eq}':>13}"
            f" {1000 * dist[p, q]:>10.3f} {ratio[p, q]:>7.3f}"
            f" {C_seg[p, q]:>22.5f} {abs(C_seg[p, q]):>9.5f}"
        )

    sweeps = {
        "R_min/min(h,h)": (ratio, (0.0, 0.5, 1.0, 2.0, 4.0, 8.0, 16.0)),
        "R_min (mm)": (1000.0 * dist, (0.0, 1.0, 10.0, 50.0, 150.0, 600.0, 5000.0)),
    }
    sweep_out = {}
    for label, (key, thresholds) in sweeps.items():
        rows = geometric_rule_sweep(C_seg, key, delta_pred, thresholds)
        sweep_out[label] = rows
        print()
        print(f"=== refine every pair with {label} <= t, leave the rest coarse ===")
        print(
            f"  {'t':>8} {'pairs':>7} {'% pairs':>8} {'captured':>22}"
            f" {'% of move':>10} {'residual':>9}"
        )
        for r in rows:
            print(
                f"  {r['threshold']:>8.1f} {r['pairs']:>7d}"
                f" {100 * r['pair_frac']:>7.2f}%"
                f" {complex(r['captured']):>22.5f}"
                f" {100 * r['captured_frac']:>9.1f}% {r['residual']:>9.4f}"
            )

    s_lo = lo["solver"]
    geom_lo = lo["geom"]
    supp_lo, polys_lo, kcl_A_lo, wk_lo, wbg_lo = s_lo._build_basis_polynomials(geom_lo)
    v_lo, pv_lo, _t, volts_lo, kcl_con_lo = s_lo._feed_drive_and_readout(
        geom_lo, wk_lo, wbg_lo, supp_lo.shape[0], kcl_A_lo
    )
    R_entry = entry_distance(lo["supp_seg"], lo["polys"], dist)
    touching = int((R_entry == 0).sum())
    far_l1 = float(np.abs(S[R_entry > 0]).sum())
    print()
    print("=== where dZ actually lives ===")
    print(
        f"  entries whose supports touch: {touching} of {S.size}"
        f" ({100 * touching / S.size:.1f}%)"
    )
    print(
        f"  L1 of u_m u_n dZ_mn on touching = {np.abs(S[R_entry == 0]).sum():.4f}"
        f" ; on the rest = {far_l1:.3e}"
    )

    n_touch = max(touching // 2, 1)
    ks = sorted({1, 2, 4, 8, 16, 32, 64, 128, 256, n_touch // 2, n_touch})
    mrows = masked_refine(
        Z_lo,
        dZ,
        S,
        [k for k in ks if k <= n_touch],
        s_lo,
        v_lo,
        kcl_con_lo,
        pv_lo[0],
        volts_lo,
        hi["z_in"],
        lo["z_in"],
    )
    print()
    print("=== EXACT partial refinement, ranked by first-order weight ===")
    print(
        f"  coarse q={args.lo} sits {abs(delta_act):.4f} ohm from q={args.hi}."
        f"  vs_coarse > 1 means refining that subset made it WORSE."
    )
    print(
        f"  {'top k':>7} {'entries':>8} {'Z_in':>22} {'err vs hi':>10}"
        f" {'vs coarse':>10}"
    )
    for r in mrows:
        print(
            f"  {r['k']:>7d} {r['entries']:>8d} {complex(r['z']):>22.4f}"
            f" {r['err_vs_hi']:>10.4f} {r['vs_coarse']:>10.3f}"
        )

    out = dict(
        deck=args.deck,
        case=args.case,
        q_lo=args.lo,
        q_hi=args.hi,
        n_basis=int(n_p),
        n_seg=int(W.shape[1]),
        n_edge=n_edge,
        z_lo=f"{lo['z_in']:.4f}",
        z_hi=f"{hi['z_in']:.4f}",
        secs=dict(lo=round(lo["secs"], 1), hi=round(hi["secs"], 1)),
        identity=dict(
            measured=f"{delta_act:.5f}",
            predicted=f"{delta_pred:.5f}",
            residual=round(resid, 5),
            residual_pct=round(100 * resid / abs(delta_act), 3),
            z_asymmetry=f"{asym:.2e}",
        ),
        entry=dict(
            l1=round(l1, 4),
            cancellation=round(l1 / abs(delta_pred), 1),
            concentration=entry_conc,
        ),
        segment_pair=dict(
            capture=signed_capture(C_seg, delta_pred)[0],
            l1_ratio=round(float(np.abs(C_seg).sum()) / abs(delta_pred), 1),
        ),
        edge_pair=dict(
            capture=signed_capture(C_edge, delta_pred)[0],
            l1_ratio=round(float(np.abs(C_edge).sum()) / abs(delta_pred), 1),
        ),
        geometric_rule=sweep_out,
        dz_support=dict(touching=touching, far_l1=f"{far_l1:.3e}"),
        masked_refine=mrows,
    )
    path = (
        HERE
        / "results"
        / f"probe4-sensitivity-{args.deck}-{args.case}-q{args.lo}-{args.hi}.json"
    )
    path.parent.mkdir(exist_ok=True)
    path.write_text(json.dumps(out, indent=2))
    print(f"\nsaved {path}", flush=True)


if __name__ == "__main__":
    main()
