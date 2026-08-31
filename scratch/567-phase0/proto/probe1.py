"""Probe 1+2+3 of FORMULATION.md §8: the MP block is the field-form block.

Reference-free identities, blind to the anchors:
  I1  t_ab_MP(keep) == t_ab_field       (direct surfaces, no grid) at REAL soil
  I2  same at ε̃ = 1.0 and ε̃ = 4−1j     (the collapse is W-blind; 4−1j is not)
  I3  t_ba_field == t_ab_MP(keep)ᵀ      (reciprocity of the whole construction)
  I4  at ε̃ = 1: field − MP(drop) is localized on the contact basis and its
      size reproduces G-U5-3's banked 2.3–2.5  (the 2.484, explained)

Run:  .venv/bin/python scratch/567-phase0/proto/probe1.py [--deck fan]
"""

from __future__ import annotations

import json
import sys
import time
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent))
sys.path.insert(0, str(Path(__file__).resolve().parents[3] / "momwire" / "tests"))

from mp_cross import axis_data, mp_cross_block, mp_tables, seeded, _pair_geometry  # noqa: F401 — kept: imported for its import-time effect / to document the probe's inputs
from momwire._sommerfeld_transmitted import divide_out_transmitted, t_surfaces_direct

from test_buried_serve_553 import contact_deck, fan_deck


def field_block_direct(s, A, B, swap_roles=False, rtol=1e-10):
    """The field-form Galerkin block from DIRECT surface evaluation (no
    grid, no interpolation): the shipped dyad combination at node pairs,
    contracted with the same basis values/weights the MP block uses.

    swap_roles=False → t_ab (test above, source below), the (7a)–(7e) dyad.
    swap_roles=True  → t_ba (test below, source above), the transposed dyad
    per `_combine_transmitted_transposed`'s docstring, same surface values.
    """
    eps_t, _eps_m, k_p, k_m, _c2, _a_m = s._buried_medium()
    rho, z, zp, dhx, dhy = _pair_geometry(A["nodes"], B["nodes"])
    surf = t_surfaces_direct(eps_t, k_p, rho, z, zp, rtol=rtol, omega=s.omega, mu=s.mu)
    # `t_surfaces_direct` returns the surfaces AS TABULATED — the field with
    # `divide_out_transmitted` divided out; the combine step multiplies it
    # back. Restore it here: true field = g · surface.
    g = divide_out_transmitted(k_p, k_m, rho, z, zp)
    surf = {k: g * v for k, v in surf.items()}

    txA, tyA, tzA = A["t"].T
    txB, tyB, tzB = B["t"].T
    if not swap_roles:
        # source below (B), moment p = t̂_B; observer above (A)
        cph = txB[None, :] * dhx + tyB[None, :] * dhy
        sph = txB[None, :] * dhy - tyB[None, :] * dhx
        pz = tzB[None, :]
        e_rho = pz * surf["TrhoV"] + cph * surf["TrhoH"]
        e_phi = sph * surf["TphiH"]
        e_z = pz * surf["TzV"] + cph * surf["TzH"]
        proj = (
            txA[:, None] * (dhx * e_rho - dhy * e_phi)
            + tyA[:, None] * (dhy * e_rho + dhx * e_phi)
            + tzA[:, None] * e_z
        )
        FA_w = A["F"] * A["w"]
        FB_w = B["F"] * B["w"]
        return FA_w @ proj @ FB_w.T
    # source above (A), moment p = t̂_A; observer below (B). dh stays
    # below→above; the dyad swaps TrhoV ↔ TzH (the fifth surface).
    cph = txA[:, None] * dhx + tyA[:, None] * dhy  # (nA, nB) with A varying
    sph = txA[:, None] * dhy - tyA[:, None] * dhx
    pz = tzA[:, None]
    e_rho = pz * surf["TzH"] + cph * surf["TrhoH"]
    e_phi = sph * surf["TphiH"]
    e_z = pz * surf["TzV"] + cph * surf["TrhoV"]
    proj = (
        txB[None, :] * (dhx * e_rho - dhy * e_phi)
        + tyB[None, :] * (dhy * e_rho + dhx * e_phi)
        + tzB[None, :] * e_z
    )  # (nA, nB): t̂_obs(below)·E at below node from above source
    FA_w = A["F"] * A["w"]
    FB_w = B["F"] * B["w"]
    return FB_w @ proj.T @ FA_w.T  # rows = below tests, cols = above sources


def contact_basis_index(s, geom):
    supp_seg, _polys, *_ = s._build_basis_polynomials(geom)
    n_above = int(np.count_nonzero(~s._below_segments(geom)))
    return int(np.max(np.nonzero(supp_seg[:, 0] < n_above)[0]))


def run(deck_name, eps, rtol=1e-10):
    build = {"contact": contact_deck, "fan": fan_deck}[deck_name]()
    s = seeded(build, eps=eps)
    geom = s._build_geometry()
    below = s._below_segments(geom)
    b_idx = np.nonzero(below)[0]
    a_idx = np.nonzero(~below)[0]
    A = axis_data(s, geom, a_idx)
    B = axis_data(s, geom, b_idx)

    t0 = time.time()
    mp = mp_cross_block(s, rtol=rtol)
    t_mp = time.time() - t0
    t0 = time.time()
    f_ab = field_block_direct(s, A, B, swap_roles=False, rtol=rtol)
    f_ba = field_block_direct(s, A, B, swap_roles=True, rtol=rtol)
    t_field = time.time() - t0

    scale = float(np.max(np.abs(f_ab)))
    keep = mp["t_ab"]
    drop = mp["main"]
    ci = contact_basis_index(s, geom)

    def worst(x):
        return float(np.max(np.abs(x)) / scale)

    d_keep = keep - f_ab
    d_drop = drop - f_ab
    others_keep = d_keep.copy()
    others_keep[ci, :] = 0.0
    others_keep[:, ci] = 0.0
    others_drop = d_drop.copy()
    others_drop[ci, :] = 0.0
    others_drop[:, ci] = 0.0

    rep = dict(
        deck=deck_name,
        eps=str(eps),
        n_pairs=int(A["nodes"].shape[0] * B["nodes"].shape[0]),
        secs_mp=round(t_mp, 1),
        secs_field=round(t_field, 1),
        scale=scale,
        I1_keep_vs_field=worst(d_keep),
        I1_keep_vs_field_offcontact=worst(others_keep),
        I3_reciprocity=float(np.max(np.abs(keep.T - f_ba)) / scale),
        I4_drop_vs_field=worst(d_drop),
        I4_drop_offcontact=worst(others_drop),
        W_norm_rel=float(
            np.max(np.abs(mp["tables"]["W"]))
            / max(np.max(np.abs(mp["tables"]["V"])), 1e-300)
        ),
        bnd_test_rel=worst(mp["bnd_test"]),
        contact_basis=ci,
    )
    return rep


if __name__ == "__main__":
    deck = "fan" if "--deck" in sys.argv and "fan" in sys.argv else "contact"
    out = []
    for eps in [(13.0, 0.005), (1.0, 0.0), (4.0, 0.000389)]:
        rep = run(deck, eps)
        print(json.dumps(rep, indent=1))
        out.append(rep)
    res = Path(__file__).resolve().parents[1] / "results"
    res.mkdir(exist_ok=True)
    (res / f"probe1-{deck}.json").write_text(json.dumps(out, indent=1))
