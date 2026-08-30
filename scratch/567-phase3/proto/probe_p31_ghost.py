"""#567 phase 3, probes P3.0 + P3.1 — the ghost continuation on the lone
anchor deck.

The spelling under test (DECISION.md section 4): keep the #151 contact
serve and the continuation-consistent M-only cross block, and add the one
missing SOURCE — a prescribed (non-dof) continuation of the contact
current below the node, I_g(z) = I(0) * e^{-j k_m |z|} on the monopole
axis, amplitude 1 by charge conservation (contact-over-finite-ground.md
section 2.2), coupled to the DETACHED radial bases only (below/below
family; the fiction's above-side account already lives in #151 — adding
ghost-above coupling would double-count it).

Implementation: the ghost is realized as a seeded auxiliary all-below
deck [radial, ghost-wire], whose assembled Z supplies Galerkin
ghost-basis x radial-basis entries in the production below/below spelling
(MP direct + A_m image + field-form remainder). Contracting the ghost
rows with the least-squares tent representation of e^{-j k_m |z|}
(value-1 "gnd" tent at the in-plane top makes g(0)=1 representable)
gives the coupling correction row added at [m0, radials] and its
transpose in the primary M-only solve.

Cells:
  P3.0  M-only regression   -> must reproduce probe35's 103.8272-75.5958j
  P3.1  M-only + ghost      -> vs anchor 92.130-70.141j  (the GO number)
  (record) + ghost self     -> doctrine says omit; measured for the record

Ladders: ghost truncation L in {4.2, 8.4} m (1 and 2 soil decay lengths).

Run: prlimit --as=$((8*1024*1024*1024)) .venv/bin/python \
       scratch/567-phase3/proto/probe_p31_ghost.py
"""

from __future__ import annotations

import json
import sys
import time
from pathlib import Path

import numpy as np

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]
sys.path.insert(0, str(ROOT / "scratch" / "524-phase2" / "proto"))
sys.path.insert(0, str(ROOT / "momwire" / "tests"))

from momwire import _crossing_fill, _medium_spec  # noqa: E402
from momwire import _sommerfeld_below as sb  # noqa: E402
from momwire.bspline import BSplineSolver  # noqa: E402
from probe9_sense import capture  # noqa: E402
from test_buried_serve_553 import contact_deck  # noqa: E402

ANCHOR = 92.130 - 70.141j
M_ONLY_BANK = 103.8272 - 75.5958j  # probe35, 2026-08-27

LAM0 = 42.827494
RADIAL = [[0.0, 0.0, -0.15], [5.0, 0.0, -0.15]]


def k_soil():
    w = 2 * np.pi * 299792458.0 / LAM0
    eps0 = 8.8541878128e-12
    eps_t = 13.0 - 1j * 0.005 / (w * eps0)
    return sb.k_medium(eps_t, 2 * np.pi / LAM0)


def seeded(build, media):
    s = BSplineSolver(**build)
    s._cached_wire_media = media
    # momwire#698's exemption audit fires on seeded junction-carrying
    # contact decks (production refuses earlier, at wire_media, which the
    # seeding bypasses on purpose): stub the crossing-junction reading.
    s._crossing_junctions = lambda: ()
    return s


def ghost_deck(L, dens=1):
    """Aux all-below deck: wire 0 = the canonical radial (mesh-matched to
    the primary deck's [10]), wire 1 = the ghost, knot at the radial's
    depth (-0.15, the pass-through point) and graded coarser downward.
    `dens` scales the ghost's per-edge segment counts (fit refinement)."""
    if L == 4.2:
        breaks = [0.15, 0.5, 1.2, 2.4, 4.2]
        n_per = [3, 4, 4, 4, 6]
    elif L == 8.4:
        breaks = [0.15, 0.5, 1.2, 2.4, 4.2, 8.4]
        n_per = [3, 4, 4, 4, 6, 8]
    else:
        raise ValueError(L)
    n_per = [dens * n for n in n_per]
    ghost = [[0.0, 0.0, 0.0]] + [[0.0, 0.0, -b] for b in breaks]
    # The one-member junction at the ghost's in-plane top is what keeps
    # its value-1 "dir" tent: _wire_endpoint_status skips BELOW wires
    # entirely (no ground tagging), and a free end drops the end basis —
    # measured in this probe's first run (g0 = 0, fit_rel 8.7e-2). The
    # junction is grounded (shared point at gz) so no KCL row appears.
    return dict(
        wires=[RADIAL, ghost],
        n_per_edge_per_wire=[[10], n_per],
        junctions=[[(1, "start")]],
        feeds=[(0, 2.5, 1 + 0j)],
        wavelength=LAM0,
        wire_radius=0.001,
        ground_z=0.0,
        ground_eps=(13.0, 0.005),
        ground_model="sommerfeld",
    )


def wire_bases(s, geom, wire_idx):
    """Basis indices whose live support lies wholly on wire wire_idx,
    in construction order (supp_seg rows are zero-padded — a slot is
    live only if its polynomial is nonzero)."""
    supp_seg, polys, *_ = s._build_basis_polynomials(geom)
    off = geom["seg_offsets"]
    segs = set(range(int(off[wire_idx]), int(off[wire_idx + 1])))
    out = []
    for m in range(polys.shape[0]):
        live = [
            int(supp_seg[m, a])
            for a in range(supp_seg.shape[1])
            if np.any(polys[m, a] != 0.0)
        ]
        if live and all(g in segs for g in live):
            out.append(m)
    return out


def ghost_row(L, km, dens=1):
    """Harvest the assembled aux Z and contract the ghost rows with the
    tent representation of e^{-j k_m |z|}. Returns (row over aux radial
    bases, ghost self scalar, fit diagnostics)."""
    s = seeded(ghost_deck(L, dens), (_medium_spec.BELOW, _medium_spec.BELOW))
    geom = s._build_geometry()
    g_rad = wire_bases(s, geom, 0)
    g_gho = wire_bases(s, geom, 1)
    off = geom["seg_offsets"]
    gho_segs = np.arange(int(off[1]), int(off[2]))

    ax = _crossing_fill.axis_data(s, geom, gho_segs)
    z = ax["nodes"][:, 2]
    target = np.exp(-1j * km * np.abs(z))
    sqw = np.sqrt(ax["w"])
    A = (ax["F"][g_gho] * sqw).T
    b = target * sqw
    w_fit, *_ = np.linalg.lstsq(A, b, rcond=None)
    fit_rel = float(np.linalg.norm(A @ w_fit - b) / np.linalg.norm(b))
    # g(0) must be 1: evaluate via the in-plane end's basis values.
    g0 = complex(
        sum(
            w_fit[i] * fv[g_gho[i]]
            for pt, sign, fv in ax["ends"]
            if abs(pt[2]) < 1e-9
            for i in range(len(g_gho))
        )
    )

    st = capture(s)
    Z = st["Z"]
    row = w_fit @ Z[np.ix_(g_gho, g_rad)]
    self_term = complex(w_fit @ Z[np.ix_(g_gho, g_gho)] @ w_fit)
    return (
        row,
        self_term,
        dict(
            fit_rel=fit_rel,
            g0=f"{g0:.6f}",
            n_ghost_bases=len(g_gho),
            n_rad_bases=len(g_rad),
            aux_z=f"{st['z_in']:.4f}",
        ),
    )


def main():
    km = k_soil()
    print(f"k_m = {km:.6f}  (decay length {-1 / km.imag:.3f} m)", flush=True)
    out = {}

    # ---- primary deck: M-only machinery (probe35's cell, re-run) ----
    build = contact_deck()
    s = seeded(build, (_medium_spec.ABOVE, _medium_spec.BELOW))
    geom = s._build_geometry()
    below = s._below_segments(geom)
    b_seg = np.sort(np.nonzero(below)[0])
    a_seg = np.sort(np.nonzero(~below)[0])
    ax_a = _crossing_fill.axis_data(s, geom, a_seg)
    ax_b = _crossing_fill.axis_data(s, geom, b_seg)
    t0 = time.time()
    t_ab = _crossing_fill.cross_complete_block(
        s, geom, dict(ax_a, ends=[]), dict(ax_b, ends=[])
    )
    print(f"M-only cross block built ({time.time() - t0:.0f}s)", flush=True)

    # contact basis m0 = the value-1 basis at the in-plane above end
    m0 = None
    for pt, sign, fv in ax_a["ends"]:
        if abs(pt[2]) < 1e-9:
            m0 = int(np.argmax(np.abs(fv)))
            assert abs(fv[m0] - 1.0) < 1e-9, fv[m0]
    assert m0 is not None
    prim_rad = wire_bases(s, geom, 1)
    print(f"m0 = {m0}, primary radial bases = {prim_rad}", flush=True)

    def solve(cell, hook=None):
        t0 = time.time()
        st = capture(
            seeded(contact_deck(), (_medium_spec.ABOVE, _medium_spec.BELOW)),
            t_ab=t_ab,
            a_seg=a_seg,
            b_seg=b_seg,
            z_hook=hook,
        )
        z = st["z_in"]
        miss = abs(z - ANCHOR)
        print(
            f"  {cell:>16}: Z = {z:9.4f}   miss = {miss:7.3f} ohm"
            f"   ({time.time() - t0:.0f}s)",
            flush=True,
        )
        out[cell] = dict(z=f"{z:.4f}", miss_ohm=round(miss, 3))
        return z

    z_m = solve("P3.0 M-only")
    drift = abs(z_m - M_ONLY_BANK)
    print(f"  P3.0 drift vs probe35 bank: {drift:.4f} ohm", flush=True)
    out["P3.0 drift_vs_bank_ohm"] = round(drift, 4)
    need = ANCHOR - z_m
    print(f"  needed move: {need:.4f}", flush=True)

    # ---- ghost ladders: truncation, mesh (fit), decay sensitivity ----
    cells = [
        ("P3.1 M+ghost L=4.2", 4.2, km, 1, True),
        ("P3.1 M+ghost L=8.4", 8.4, km, 1, True),
        ("P3.1 M+ghost L=4.2 d2", 4.2, km, 2, False),
        ("P3.1 M+ghost L=4.2 d3", 4.2, km, 3, False),
        ("P3.2 decay x0.5", 8.4, 0.5 * km, 2, False),
        ("P3.2 decay x2", 4.2, 2.0 * km, 2, False),
    ]
    for cell, L, k_eff, dens, with_self in cells:
        t0 = time.time()
        row, self_term, diag = ghost_row(L, k_eff, dens)
        print(
            f"{cell}: fit_rel={diag['fit_rel']:.2e} g0={diag['g0']} "
            f"self={self_term:.4f} ({time.time() - t0:.0f}s)",
            flush=True,
        )
        out[f"{cell} diag"] = dict(diag, self=f"{self_term:.4f}")

        def hook_coupling(Z, row=row):
            Z[m0, prim_rad] += row
            Z[prim_rad, m0] += row
            return Z

        solve(cell, hook_coupling)
        if with_self:

            def hook_with_self(Z, row=row, st_=self_term):
                Z[m0, prim_rad] += row
                Z[prim_rad, m0] += row
                Z[m0, m0] += st_
                return Z

            solve(f"rec  {cell}+self", hook_with_self)

    fp = HERE.parent / "results" / "probe-p31-ghost.json"
    fp.parent.mkdir(exist_ok=True)
    old = json.loads(fp.read_text()) if fp.exists() else {}
    old.update(out)
    fp.write_text(json.dumps(old, indent=1))
    print(f"saved {fp}")


if __name__ == "__main__":
    main()
