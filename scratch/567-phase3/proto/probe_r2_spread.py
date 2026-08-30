"""#567 phase 3, round 2 — the DERIVED spreading ghost (hemispherical
Born electrode).

Derivation, fixed before any anchor is scored (no anchor-informed knob):

- Current I(0) injected at the interface point spreads UNIFORMLY IN
  SOLID ANGLE over the soil hemisphere — the classical grounding
  electrode, exact at DC for a homogeneous half-space.
- Each ray carries the charge-field (Born) profile
      I(s) = (1 + j k_m s) e^{-j k_m s},
  the total (conduction + displacement) current through radius s of a
  retarded point charge's field in the soil medium; reduces to the DC
  limit I(s) = I as k -> 0. Born character noted: the profile is not
  self-consistent (the rigorous electrode current solves an integral
  equation); propagation from ray to radial is the house Green's
  function's job and carries the interface corrections.
- The soil takes the derived static partition tau_soil = eps/(eps+1)
  of the injected current (the air side's 1/(eps+1) returns as
  displacement and belongs to #151's above-side account — coupling-only
  doctrine unchanged).
- tau = 1 overall by charge conservation (doctrine); coupling-only; the
  vertical line of round 1 is REPLACED by the hemisphere (alpha = 0 is
  just one quadrature region).

Discretization (validated by CONVERGENCE + rotation invariance, never by
anchor distance): Gauss-Legendre in mu = cos(alpha) over (0,1) (uniform
solid angle <=> uniform in mu), n_phi equal azimuths with optional
half-step rotation, graded leg meshes, truncation ladder in L. Legs are
harvested in GROUPS through seeded all-below aux decks (pairwise Z
entries are deck-independent; grouping only amortizes grid builds), each
group sharing one grounded K=n junction at the origin so every leg keeps
its value-1 top tent (the round-1 trap).

GO adjudicator: after ladders converge, score BOTH anchors once, then
the beta instrument — beta*(lone) == beta*(fan) == 1 within envelope.

Run: prlimit --as=$((8*1024*1024*1024)) .venv/bin/python \
       scratch/567-phase3/proto/probe_r2_spread.py [lone|fan|beta ...]
"""

from __future__ import annotations

import json
import sys
import time
from pathlib import Path

import numpy as np
from numpy.polynomial.legendre import leggauss

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]
sys.path.insert(0, str(HERE))
sys.path.insert(0, str(ROOT / "scratch" / "524-phase2" / "proto"))
sys.path.insert(0, str(ROOT / "momwire" / "tests"))

from momwire import _crossing_fill, _medium_spec  # noqa: E402
from momwire.bspline import BSplineSolver  # noqa: E402,F401
from probe9_sense import capture  # noqa: E402
from probe_p31_ghost import LAM0, RADIAL, k_soil, seeded, wire_bases  # noqa: E402
from test_buried_serve_553 import contact_deck, fan_deck  # noqa: E402

ANCHORS = {"lone": 92.130 - 70.141j, "fan": 90.051 - 70.731j}
M_ONLY_BANK = {"lone": 103.8272 - 75.5958j, "fan": 105.2020 - 78.7769j}

GROUP = 8  # legs per aux harvest deck


def eps_t():
    w = 2 * np.pi * 299792458.0 / LAM0
    return 13.0 - 1j * 0.005 / (w * 8.8541878128e-12)


def tau_soil():
    et = eps_t()
    return et / (et + 1.0)


def profile(s, km):
    return (1.0 + 1j * km * s) * np.exp(-1j * km * s)


def leg_dirs(n_alpha, n_phi, offset=0.0):
    """[(w_geom, direction)] — w_geom = solid-angle fraction of the soil
    hemisphere (sums to 1). Gauss in mu = cos(alpha) on (0,1)."""
    xg, wg = leggauss(n_alpha)
    mu = 0.5 * (xg + 1.0)
    wmu = 0.5 * wg
    out = []
    for m_i, w_i in zip(mu, wmu):
        sa = float(np.sqrt(1.0 - m_i * m_i))
        for j in range(n_phi):
            ph = 2.0 * np.pi * (j + offset) / n_phi
            d = np.array([sa * np.cos(ph), sa * np.sin(ph), -float(m_i)])
            out.append((float(w_i) / n_phi, d))
    return out


def leg_mesh(L):
    if L == 4.2:
        return [0.15, 0.5, 1.2, 2.4, 4.2], [3, 4, 4, 4, 6]
    if L == 8.4:
        return [0.15, 0.5, 1.2, 2.4, 4.2, 8.4], [3, 4, 4, 4, 6, 8]
    raise ValueError(L)


def below_system(name):
    """(wires, n_per_edge, junctions) of the primary deck's below system,
    re-indexed from 0 — mesh-matched to the primary."""
    if name == "lone":
        return [np.asarray(RADIAL, float)], [[10]], []
    b = fan_deck()
    return (
        [np.asarray(w, float) for w in b["wires"][1:]],
        [[10]] * 4,
        [[(0, "start"), (1, "start"), (2, "start"), (3, "start")]],
    )


def aux_group_deck(name, dirs, L):
    """All-below deck: the below system + one leg wire per direction,
    all leg tops joined in ONE grounded junction at the origin."""
    wires, npe, juncs = below_system(name)
    n0 = len(wires)
    breaks, n_per = leg_mesh(L)
    leg_group = []
    for _w, d in dirs:
        pts = [np.zeros(3)] + [b * d for b in breaks]
        wires = wires + [np.asarray(pts, float)]
        npe = npe + [list(n_per)]
        leg_group.append((len(wires) - 1, "start"))
    return dict(
        wires=wires,
        n_per_edge_per_wire=npe,
        junctions=[list(j) for j in juncs] + [leg_group],
        feeds=[(0, 2.5, 1 + 0j)],
        wavelength=LAM0,
        wire_radius=0.001,
        ground_z=0.0,
        ground_eps=(13.0, 0.005),
        ground_model="sommerfeld",
    ), n0


def leg_fit(s, geom, leg_bases, leg_segs, km):
    """Tilt-agnostic per-leg fit of profile(s) onto the leg's bases —
    axis_data refuses tilted segments, so sample the polynomials
    directly (plain Gauss per segment; s = distance from the origin)."""
    supp_seg, polys, *_ = s._build_basis_polynomials(geom)
    d = s.degree
    xg, wg = leggauss(6)
    tq = 0.5 * (xg + 1.0)
    rows_A, rows_b, rows_w = [], [], []
    for g in leg_segs:
        sl, sr = geom["seg_l"][g], geom["seg_r"][g]
        h = float(geom["h_per_seg"][g])
        u = h * tq
        nodes = sl[None, :] + (u / h)[:, None] * (sr - sl)[None, :]
        F = np.zeros((len(leg_bases), len(u)))
        for i, m in enumerate(leg_bases):
            for a_ in range(supp_seg.shape[1]):
                if supp_seg[m, a_] != g or not np.any(polys[m, a_] != 0.0):
                    continue
                for p in range(d + 1):
                    c = polys[m, a_, p]
                    if c != 0.0:
                        F[i] += c * u**p
        rows_A.append(F.T)
        rows_b.append(profile(np.linalg.norm(nodes, axis=1), km))
        rows_w.append(np.full(len(u), 0.5 * h * 1.0) * wg)
    A = np.vstack(rows_A)
    b = np.concatenate(rows_b)
    w = np.sqrt(np.concatenate(rows_w))
    coef, *_ = np.linalg.lstsq(A * w[:, None], b * w, rcond=None)
    fit_rel = float(np.linalg.norm((A @ coef - b) * w) / np.linalg.norm(b * w))
    return coef, fit_rel


def harvest(name, n_alpha, n_phi, offset, L, km):
    """Sum of w_geom-weighted per-leg coupling rows over the below
    system's bases, harvested GROUP legs at a time."""
    dirs = leg_dirs(n_alpha, n_phi, offset)
    wires0, _npe0, _j0 = below_system(name)
    n0 = len(wires0)
    total = None
    worst_fit = 0.0
    for k0 in range(0, len(dirs), GROUP):
        chunk = dirs[k0 : k0 + GROUP]
        build, _ = aux_group_deck(name, chunk, L)
        s = seeded(build, (_medium_spec.BELOW,) * len(build["wires"]))
        geom = s._build_geometry()
        below_b = sorted(m for w in range(n0) for m in wire_bases(s, geom, w))
        st = capture(s)
        Z = st["Z"]
        off = geom["seg_offsets"]
        for i, (w_geom, _d) in enumerate(chunk):
            wi = n0 + i
            lb = wire_bases(s, geom, wi)
            segs = range(int(off[wi]), int(off[wi + 1]))
            coef, fit_rel = leg_fit(s, geom, lb, segs, km)
            worst_fit = max(worst_fit, fit_rel)
            r = w_geom * (coef @ Z[np.ix_(lb, below_b)])
            total = r if total is None else total + r
    return tau_soil() * total, worst_fit


def primary(name):
    """(build, media, t_ab, a_seg, b_seg, m0, prim_below) — the M-only
    primary machinery, identical to rounds 1's."""
    build = contact_deck() if name == "lone" else fan_deck()
    n_wires = len(build["wires"])
    media = (_medium_spec.ABOVE,) + (_medium_spec.BELOW,) * (n_wires - 1)
    s = seeded(dict(build), media)
    geom = s._build_geometry()
    below = s._below_segments(geom)
    b_seg = np.sort(np.nonzero(below)[0])
    a_seg = np.sort(np.nonzero(~below)[0])
    ax_a = _crossing_fill.axis_data(s, geom, a_seg)
    ax_b = _crossing_fill.axis_data(s, geom, b_seg)
    t_ab = _crossing_fill.cross_complete_block(
        s, geom, dict(ax_a, ends=[]), dict(ax_b, ends=[])
    )
    m0 = None
    for pt, _sg, fv in ax_a["ends"]:
        if abs(pt[2]) < 1e-9:
            m0 = int(np.argmax(np.abs(fv)))
    prim_below = sorted(m for w in range(1, n_wires) for m in wire_bases(s, geom, w))
    return build, media, t_ab, a_seg, b_seg, m0, prim_below


def scored(name, row, prim, beta=1.0):
    build, media, t_ab, a_seg, b_seg, m0, prim_below = prim

    def hook(Z):
        rr = beta * row
        Z[m0, prim_below] += rr
        Z[prim_below, m0] += rr
        return Z

    st = capture(
        seeded(dict(build), media),
        t_ab=t_ab,
        a_seg=a_seg,
        b_seg=b_seg,
        z_hook=hook,
    )
    return st["z_in"]


def main():
    km = k_soil()
    names = sys.argv[1:] or ["lone"]
    out = {}
    print(
        f"tau_soil = {tau_soil():.4f}   k_m = {km:.4f}",
        flush=True,
    )

    if "lone" in names:
        prim = primary("lone")
        z0 = scored("lone", np.zeros(len(prim[6]), complex), prim)
        assert abs(z0 - M_ONLY_BANK["lone"]) < 0.001, z0
        print(f"lone M-only regression ok: {z0:.4f}", flush=True)
        # Ladders around the baseline (n_alpha=4, n_phi=8, off=0, L=8.4).
        cells = [
            ("base a4 p8 L8.4", 4, 8, 0.0, 8.4),
            ("a3", 3, 8, 0.0, 8.4),
            ("p16", 4, 16, 0.0, 8.4),
            ("rot", 4, 8, 0.5, 8.4),
            ("L4.2", 4, 8, 0.0, 4.2),
        ]
        for cell, na, np_, offs, L in cells:
            t0 = time.time()
            row, worst_fit = harvest("lone", na, np_, offs, L, km)
            z = scored("lone", row, prim)
            miss = abs(z - ANCHORS["lone"])
            print(
                f"  lone {cell:>16}: Z = {z:9.4f}  miss = {miss:7.3f}  "
                f"fit<={worst_fit:.1e}  ({time.time() - t0:.0f}s)",
                flush=True,
            )
            out[f"lone {cell}"] = dict(
                z=f"{z:.4f}",
                miss_ohm=round(miss, 3),
                worst_fit=f"{worst_fit:.2e}",
            )

    if "control" in names:
        # Machinery certification: the ROUND-1 spelling (vertical leg,
        # e^{-jk s}, tau = 1) pushed through the round-2 harvester must
        # reproduce round 1's 96.0971-76.9498j (small fit-sampler
        # differences only). Certifies that round 2's null is physics,
        # not a harvest bug.
        prof_saved = globals()["profile"]
        try:
            globals()["profile"] = lambda s, km: np.exp(-1j * km * s)
            prim = primary("lone")
            vert = [(1.0, np.array([0.0, 0.0, -1.0]))]
            build, n0 = aux_group_deck("lone", vert, 8.4)
            s = seeded(build, (_medium_spec.BELOW,) * len(build["wires"]))
            geom = s._build_geometry()
            below_b = sorted(m for m in wire_bases(s, geom, 0))
            st = capture(s)
            off = geom["seg_offsets"]
            lb = wire_bases(s, geom, 1)
            coef, fit_rel = leg_fit(s, geom, lb, range(int(off[1]), int(off[2])), km)
            row_v = coef @ st["Z"][np.ix_(lb, below_b)]
            z = scored("lone", row_v, prim)
            print(
                f"  CONTROL round-1 spelling via round-2 harvest: "
                f"Z = {z:9.4f}  (round-1 bank 96.0971-76.9498j, "
                f"delta {abs(z - (96.0971 - 76.9498j)):.4f} ohm)  "
                f"fit={fit_rel:.1e}",
                flush=True,
            )
            out["control r1-via-r2"] = dict(
                z=f"{z:.4f}",
                delta_vs_r1=round(abs(z - (96.0971 - 76.9498j)), 4),
            )
        finally:
            globals()["profile"] = prof_saved

    if "diag" in names:
        # Control 1: ONE VERTICAL leg through the round-2 machinery
        # (w_geom = 1). Must land near round 1's 96.10-76.95j (up to
        # tau_soil and the (1+jk s) profile factor) or the harvest is
        # broken. Control 2: per-leg ||row|| vs polar angle — if the
        # grazing legs' coupling really collapses (image cancellation),
        # the alpha-dependence shows it directly.
        prim = primary("lone")
        vert = [(1.0, np.array([0.0, 0.0, -1.0]))]
        build, n0 = aux_group_deck("lone", vert, 8.4)
        s = seeded(build, (_medium_spec.BELOW,) * len(build["wires"]))
        geom = s._build_geometry()
        below_b = sorted(m for m in wire_bases(s, geom, 0))
        st = capture(s)
        off = geom["seg_offsets"]
        lb = wire_bases(s, geom, 1)
        coef, fit_rel = leg_fit(s, geom, lb, range(int(off[1]), int(off[2])), km)
        g0 = (  # noqa: F841 — kept: names the quantity the probe computed, read when inspecting
            float(
                np.abs(
                    coef @ np.array([1.0 if i == 0 else 0.0 for i in range(len(lb))])
                )
            )
            if False
            else None
        )
        row_v = tau_soil() * (coef @ st["Z"][np.ix_(lb, below_b)])
        z = scored("lone", row_v, prim)
        print(
            f"  diag vertical-leg control: Z = {z:9.4f}  miss = "
            f"{abs(z - ANCHORS['lone']):7.3f}  fit={fit_rel:.1e}  "
            f"||row|| = {np.linalg.norm(row_v):.4f}",
            flush=True,
        )
        out["diag vertical control"] = dict(
            z=f"{z:.4f}", miss_ohm=round(abs(z - ANCHORS["lone"]), 3)
        )
        # Per-leg norms at n_phi=8 baseline, azimuth 0 (toward the
        # radial) and 180 (away), per polar node.
        dirs = leg_dirs(4, 8, 0.0)
        build, n0 = aux_group_deck("lone", dirs[:GROUP], 8.4)
        for k0 in range(0, len(dirs), GROUP):
            chunk = dirs[k0 : k0 + GROUP]
            build, n0 = aux_group_deck("lone", chunk, 8.4)
            s = seeded(build, (_medium_spec.BELOW,) * len(build["wires"]))
            geom = s._build_geometry()
            below_b = sorted(m for m in wire_bases(s, geom, 0))
            st = capture(s)
            off = geom["seg_offsets"]
            for i, (w_geom, d) in enumerate(chunk):
                wi = n0 + i
                lb = wire_bases(s, geom, wi)
                coef, fit_rel = leg_fit(
                    s, geom, lb, range(int(off[wi]), int(off[wi + 1])), km
                )
                r = coef @ st["Z"][np.ix_(lb, below_b)]
                alpha = float(np.degrees(np.arccos(-d[2])))
                phi = float(np.degrees(np.arctan2(d[1], d[0]))) % 360
                print(
                    f"    leg alpha={alpha:5.1f} phi={phi:5.1f}: "
                    f"||row||(unweighted) = {np.linalg.norm(r):9.4f}  "
                    f"w_geom = {w_geom:.4f}  fit={fit_rel:.1e}",
                    flush=True,
                )

    if "fan" in names:
        prim = primary("fan")
        z0 = scored("fan", np.zeros(len(prim[6]), complex), prim)
        assert abs(z0 - M_ONLY_BANK["fan"]) < 0.001, z0
        print(f"fan M-only regression ok: {z0:.4f}", flush=True)
        for cell, offs in (("base a4 p8 L8.4", 0.0), ("rot", 0.5)):
            t0 = time.time()
            row, worst_fit = harvest("fan", 4, 8, offs, 8.4, km)
            z = scored("fan", row, prim)
            miss = abs(z - ANCHORS["fan"])
            print(
                f"  fan {cell:>16}: Z = {z:9.4f}  miss = {miss:7.3f}  "
                f"fit<={worst_fit:.1e}  ({time.time() - t0:.0f}s)",
                flush=True,
            )
            out[f"fan {cell}"] = dict(
                z=f"{z:.4f}",
                miss_ohm=round(miss, 3),
                worst_fit=f"{worst_fit:.2e}",
            )

    if "beta" in names:
        from scipy.optimize import minimize

        for name in ("lone", "fan"):
            prim = primary(name)
            row, _ = harvest(name, 4, 8, 0.0, 8.4, km)

            def miss(v):
                return abs(
                    scored(name, row, prim, beta=v[0] + 1j * v[1]) - ANCHORS[name]
                )

            grid = [
                (re, im)
                for re in (0.0, 0.5, 1.0, 1.5, 2.0)
                for im in (-1.0, -0.5, 0.0, 0.5, 1.0)
            ]
            seed = min(grid, key=miss)
            res = minimize(
                miss,
                np.array(seed),
                method="Nelder-Mead",
                options=dict(xatol=1e-3, fatol=1e-3),
            )
            bstar = res.x[0] + 1j * res.x[1]
            print(
                f"  {name}: beta* = {bstar:.4f}  residual = "
                f"{res.fun:.3f} ohm  (beta=1 miss {miss([1.0, 0.0]):.3f})",
                flush=True,
            )
            out[f"beta {name}"] = dict(
                beta=f"{bstar:.4f}", residual=round(float(res.fun), 3)
            )

    fp = HERE.parent / "results" / "probe-r2-spread.json"
    fp.parent.mkdir(exist_ok=True)
    old = json.loads(fp.read_text()) if fp.exists() else {}
    old.update(out)
    fp.write_text(json.dumps(old, indent=1))
    print(f"saved {fp}")


if __name__ == "__main__":
    main()
