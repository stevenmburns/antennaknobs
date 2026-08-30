"""A-2 next-experiments #1: split bnd_src_W's charge from its W piece.

mp_cross_block now returns the source-side boundary term in two pieces:
  SW = bnd_src_Wp  (the W by-parts term at the below arm's z'=0 end)
  SQ = bnd_src_q   (the below-end CHARGE (V) by-parts term)
  BT = bnd_test    (the above-end (contact) charge term)
  M  = main_raw    (the no-boundary MP block)

Spelling grid (x {none, V continuity row}):
  B_dropAboveQ = M + SW + SQ      (probe6/7's "B_dropq" — regression check)
  dropBothQ    = M + SW
  dropBelowQ   = M + SW + BT

Scored in the DELTA instrument: momwire Delta = Z(crossing, MP-swapped)
- Z(mono-alone, shipped serve, matched mesh), vs the engine's banked Delta
ladder. The mono column is re-solved here (last session's scratchpad died
with its mono_ladder.py; the banked numbers below are the cross-check).

Banked (PLAN.md): momwire mono x1 = 71.5556 - 49.4339j, x3 = 71.4922 -
49.0045j; engine Delta x1 = -2.3260 - 0.7130j, x3 = -2.6840 - 1.4260j,
x5 = -2.8200 - 1.6940j.

Run: .venv/bin/python scratch/524-phase2/proto/probe8_split.py [mult]
(mult odd; block pieces cached per mult in results/probe8-blocks-x{mult}.npz)
"""

from __future__ import annotations

import json
import sys
import time
from pathlib import Path

import numpy as np

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "567-phase0" / "proto"))
sys.path.insert(0, str(Path(__file__).resolve().parents[3] / "momwire" / "tests"))

import mp_cross  # noqa: E402
from momwire.bspline import BSplineSolver  # noqa: E402
from probe1_baseline import crossing_deck, seeded  # noqa: E402
from probe2_crossing import node_rows  # noqa: E402
from test_buried_serve_553 import SOIL_A, WL7  # noqa: E402

ENGINE_DELTA = {1: -2.3260 - 0.7130j, 3: -2.6840 - 1.4260j, 5: -2.8200 - 1.6940j}
ENGINE_X = {1: 74.761 - 57.730j, 3: 70.858 - 51.678j, 5: 70.038 - 50.717j}

# z' = 0 clamp: the below arm ENDS at the interface; the z' -> 0- limit is
# continuous, the tables just refuse exactly 0 (phase-0 scope edge).
_orig_mp_tables = mp_cross.mp_tables


def _mp_tables_clamped(eps_t, k_p, rho, z, zp, rtol=1e-10):
    zp = np.minimum(np.asarray(zp, dtype=np.float64), -1e-9)
    return _orig_mp_tables(eps_t, k_p, rho, z, zp, rtol=rtol)


mp_cross.mp_tables = _mp_tables_clamped


def mono_deck(mult=1):
    """The contact monopole ALONE (shipped serve): engine EX 4,2,7 =
    arclength 4.3333 m; odd mult keeps the fed segment centred."""
    return dict(
        wires=[np.array([(0.0, 0.0, 0.0), (0.0, 0.0, 10.0)])],
        n_per_edge_per_wire=[[15 * mult]],
        feeds=[(0, 4.3333333333, 1 + 0j)],
        wavelength=WL7,
        wire_radius=0.001,
        ground_z=0.0,
        ground_eps=SOIL_A,
        ground_model="sommerfeld",
    )


def build_pieces(mult):
    fp = HERE.parent / "results" / f"probe8-blocks-x{mult}.npz"
    if fp.exists():
        d = np.load(fp)
        return {k: d[k] for k in ("M", "SW", "SQ", "BT")}
    s = seeded(crossing_deck(mult))
    t0 = time.time()
    mp = mp_cross.mp_cross_block(s, rtol=1e-10, boundary="drop")
    print(f"x{mult}: MP block pieces built in {time.time() - t0:.0f}s", flush=True)
    pieces = dict(
        M=mp["main_raw"], SW=mp["bnd_src_Wp"], SQ=mp["bnd_src_q"], BT=mp["bnd_test"]
    )
    np.savez(fp, **pieces)
    return pieces


def solve_swapped(mult, t_ab, rows):
    s = seeded(crossing_deck(mult))
    geom = s._build_geometry()
    below = s._below_segments(geom)
    b_seg = np.sort(np.nonzero(below)[0])
    a_seg = np.sort(np.nonzero(~below)[0])
    t_ba = t_ab.T

    orig_blk = BSplineSolver._field_galerkin_block

    def wrap_blk(self, supp_seg, polys, proj_fn, obs_idx, src_idx, *rest):
        o = np.sort(np.asarray(obs_idx))
        sr = np.sort(np.asarray(src_idx))
        if np.array_equal(o, a_seg) and np.array_equal(sr, b_seg):
            return t_ab.copy()
        if np.array_equal(o, b_seg) and np.array_equal(sr, a_seg):
            return t_ba.copy()
        return orig_blk(self, supp_seg, polys, proj_fn, obs_idx, src_idx, *rest)

    orig_kcl = BSplineSolver._solve_with_kcl

    def wrap_kcl(self, Z, v, kcl_A, overwrite=False):
        if rows:
            add = np.stack(rows)
            kcl_A = np.vstack([kcl_A.astype(add.dtype), add])
        return orig_kcl(self, Z, v, kcl_A, overwrite=False)

    BSplineSolver._field_galerkin_block = wrap_blk
    BSplineSolver._solve_with_kcl = wrap_kcl
    try:
        z, _ = s.compute_impedance()
    finally:
        BSplineSolver._field_galerkin_block = orig_blk
        BSplineSolver._solve_with_kcl = orig_kcl
    return z


def main():
    mult = int(sys.argv[1]) if len(sys.argv) > 1 else 1
    pieces = build_pieces(mult)
    M, SW, SQ, BT = (pieces[k] for k in ("M", "SW", "SQ", "BT"))

    t0 = time.time()
    z_mono, _ = BSplineSolver(**mono_deck(mult)).compute_impedance()
    print(
        f"x{mult}: mono (shipped) = {z_mono:.4f}  ({time.time() - t0:.0f}s)", flush=True
    )

    s = seeded(crossing_deck(mult))
    geom = s._build_geometry()
    row_v, _der_a, _der_b = node_rows(s, geom)

    spellings = {
        "B_dropAboveQ": M + SW + SQ,
        "dropBothQ": M + SW,
        "dropBelowQ": M + SW + BT,
    }
    rowsets = {"none": [], "V": [row_v]}
    d_eng = ENGINE_DELTA[mult]

    out = {"mono": f"{z_mono:.4f}", "engine_delta": f"{d_eng:.4f}"}
    for bname, t_ab in spellings.items():
        for rname, rows in rowsets.items():
            t0 = time.time()
            z = solve_swapped(mult, t_ab, rows)
            delta = z - z_mono
            dist = abs(delta - d_eng)
            key = f"{bname}+{rname}"
            out[key] = dict(
                z=f"{z:.4f}", delta=f"{delta:.4f}", dist_ohm=round(float(dist), 3)
            )
            print(
                f"  {key:>18}: Z = {z:9.4f}   Delta = {delta:8.4f}   "
                f"engine Delta = {d_eng:.4f}   dist = {dist:6.3f} ohm   "
                f"({time.time() - t0:.0f}s)",
                flush=True,
            )

    fp = HERE.parent / "results" / f"probe8-split-x{mult}.json"
    fp.write_text(json.dumps(out, indent=1))


if __name__ == "__main__":
    main()
