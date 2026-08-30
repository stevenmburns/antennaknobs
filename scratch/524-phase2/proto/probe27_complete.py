"""A-2 session 5, probe 27 — the COMPLETE spelling on designed kernels:
the only quadrature-convergent node treatment.

probe26 + the sign audit named the final defect class: every "drop"
spelling is truncation-regularized — at RESOLVED quadrature the retained
integral's ln(a)-class content diverges with its balancing end/corner
terms deleted (designed-B t_ab[na,nb] flips sign class vs shipped).
The complete field-form-equivalent spelling is the only convergent one:

  cross: t_A = M + SW + SQ + BT + CORNER        (designed, graded)
  self:  Z_fam + beta_dir (bnd+cor)(G_dir) - beta_img (bnd+cor)(G_img)
         (probe14 machinery, graded axes so the end integrals resolve)

Predictions checked inline:
  P1  designed cross corner ~ c_bb ~ c_aa ~ 14534-15859j (the 9.58x
      truncation of probe14d recovered) — Sec 3 static equality;
  P2  under merge the corner-class content telescopes: the merged solves
      STOP diverging g1 -> g2;
  P3  Delta lands near the engine limit -2.82 - 1.69j.

Run: prlimit --as=$((8*1024*1024*1024)) .venv/bin/python \
       scratch/524-phase2/proto/probe27_complete.py [level ...]
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

import corner_tables as ct  # noqa: E402
import mp_cross  # noqa: E402,F401
import probe14_same_medium as p14  # noqa: E402
from momwire.bspline import BSplineSolver  # noqa: E402
from momwire._sommerfeld_transmitted import _c1_moment  # noqa: E402
from probe1_baseline import seeded  # noqa: E402
from probe2_crossing import node_rows  # noqa: E402
from probe9_sense import capture  # noqa: E402
from probe13_x3 import node_indices  # noqa: E402
from probe18_graded import mono_graded  # noqa: E402
from probe19_graded_mpb import ENGINE_LIMIT, crossing_graded  # noqa: E402
from probe20_graded_rows import EPS_RATIO  # noqa: E402
from probe25_node_cell import cross_pieces_on_axes, graded_axis_data  # noqa: E402

A_WIRE = 0.001
ct.install(wire_radius=A_WIRE)

SHIPPED_CORNER_X1 = 1512.61 - 1658.55j  # probe5/probe11's measured residual


def cross_complete(s, lv):
    fp = HERE.parent / "results" / f"probe27-blocks-g{lv}.npz"
    geom = s._build_geometry()
    below = s._below_segments(geom)
    b_idx = np.nonzero(below)[0]
    a_idx = np.nonzero(~below)[0]
    if fp.exists():
        d = np.load(fp)
        pieces = {k: d[k] for k in ("M", "SW", "SQ", "BT")}
    else:
        axA = graded_axis_data(s, geom, a_idx)
        axB = graded_axis_data(s, geom, b_idx)
        t0 = time.time()
        M, SW, SQ, BT = cross_pieces_on_axes(s, axA, axB)
        print(
            f"g{lv}: designed graded cross pieces {time.time() - t0:.0f}s", flush=True
        )
        pieces = dict(M=M, SW=SW, SQ=SQ, BT=BT)
        np.savez(fp, **pieces)

    # the corner term: sigma_a sigma_b f_m(0) f_n(0) x designed V at R = a,
    # sign calibrated against the measured shipped-field corner phase
    eps_t, _em, k_p, _km, _c2, _am = s._buried_medium()
    nb, na = node_indices(s, geom)
    c1 = _c1_moment(s.omega, s.mu)
    v_corner = complex(ct.six_point(eps_t, k_p, A_WIRE, 0.0, 0.0, rtol=1e-10)[1])
    cand = c1 * v_corner
    pick = (
        cand
        if abs(cand - SHIPPED_CORNER_X1) < abs(-cand - SHIPPED_CORNER_X1)
        else -cand
    )
    ratio = abs(pick) / abs(SHIPPED_CORNER_X1)
    print(
        f"g{lv}: P1 corner: c1*V(a) = {cand:.4f}; picked {pick:.4f}; "
        f"|designed|/|shipped-truncated| = {ratio:.3f} (probe14d says "
        f"~9.58); c_bb ref 14534-15859j",
        flush=True,
    )
    CORNER = np.zeros_like(pieces["M"])
    CORNER[na, nb] = pick
    t_A = pieces["M"] + pieces["SW"] + pieces["SQ"] + pieces["BT"] + CORNER
    return t_A, pick


def self_complete_hook(s, geom):
    """BND + corner corrections for both self families on graded axes."""
    below = s._below_segments(geom)
    b_idx = np.nonzero(below)[0]
    a_idx = np.nonzero(~below)[0]
    eps_t, eps_m, k_p, k_m, c2, a_m = s._buried_medium()
    omega, eps0 = s.omega, s.eps
    add = np.zeros((0,))  # noqa: F841 — kept: names the quantity the probe computed, read when inspecting
    total = None
    for name, idx, k, wgt, eps in (
        ("bb", b_idx, k_m, a_m, eps_m),
        ("aa", a_idx, k_p, c2, eps0),
    ):
        axG = graded_axis_data(s, geom, idx)
        bnd_dir, cor_dir = p14.bnd_shape(axG, k, False)
        bnd_img, cor_img = p14.bnd_shape(axG, k, True)
        beta_dir = 1.0 / (1j * omega * eps * 4 * np.pi)
        beta_img = wgt / (1j * omega * eps * 4 * np.pi)
        piece = beta_dir * (bnd_dir + cor_dir) - beta_img * (bnd_img + cor_img)
        total = piece if total is None else total + piece
        nn = np.abs(piece).max()
        print(
            f"  self-complete {name}: max |bnd+cor| = {nn:.4f}; corner "
            f"dir[max] = {np.abs(cor_dir).max():.4f}",
            flush=True,
        )
    return total


def main():
    levels = [int(x) for x in sys.argv[1:]] or [1, 2]
    out = {}
    for lv in levels:
        s = seeded(crossing_graded(lv))
        geom = s._build_geometry()
        below = s._below_segments(geom)
        b_seg = np.sort(np.nonzero(below)[0])
        a_seg = np.sort(np.nonzero(~below)[0])
        nb, na = node_indices(s, geom)
        h_min = float(geom["h_per_seg"].min())

        t_A, corner = cross_complete(s, lv)
        d_self = self_complete_hook(s, geom)

        def corr_hook(Zp, add=d_self):
            return Zp + add

        row_v, der_a, der_b = node_rows(s, geom)
        row_s = der_a - EPS_RATIO * der_b
        z_mono = capture(BSplineSolver(**mono_graded(lv)))["z_in"]
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
            ("split", None, corr_hook),
            ("merged", None, merge_hook),
            ("V", [row_v], None),
            ("V+S", [row_v, row_s], None),
        ]
        for cname, rows, hook in cells:
            t0 = time.time()
            if rows is None:
                st = capture(
                    seeded(crossing_graded(lv)),
                    t_ab=t_A,
                    a_seg=a_seg,
                    b_seg=b_seg,
                    z_hook=hook,
                )
                z = st["z_in"]
            else:
                orig_kcl = BSplineSolver._solve_with_kcl

                def wrap_kcl(self, Z, v, kcl_A, overwrite=False, rows=rows):
                    Z = corr_hook(Z.copy())
                    add = np.stack(rows)
                    kcl_A = np.vstack([kcl_A.astype(add.dtype), add])
                    return orig_kcl(self, Z, v, kcl_A, overwrite=False)

                BSplineSolver._solve_with_kcl = wrap_kcl
                try:
                    st = capture(
                        seeded(crossing_graded(lv)), t_ab=t_A, a_seg=a_seg, b_seg=b_seg
                    )
                finally:
                    BSplineSolver._solve_with_kcl = orig_kcl
                z = st["z_in"]
            d = z - z_mono
            dist = abs(d - ENGINE_LIMIT)
            out[f"g{lv}+complete+{cname}"] = dict(
                z=f"{z:.4f}",
                delta=f"{d:.4f}",
                dist_ohm=round(float(dist), 3),
            )
            print(
                f"  g{lv} complete+{cname:>6}: Z = {z:9.4f}   Delta = "
                f"{d:9.4f}   dist = {dist:7.3f}   ({time.time() - t0:.0f}s)",
                flush=True,
            )

    fp = HERE.parent / "results" / "probe27-complete.json"
    old = json.loads(fp.read_text()) if fp.exists() else {}
    old.update(out)
    fp.write_text(json.dumps(old, indent=1))
    print(f"saved {fp}")


if __name__ == "__main__":
    main()
