"""A-2 session 5, probe 29 — the eps = 1 ADJUDICATOR for the complete
node cell.

probe27/28 left a stable, spelling-independent crossing answer (138.77
-102.99j) that disagrees with the engine's junction answer (~70) — and
the mono lesson (completing the contact column wrecks a validated serve)
says the columns cannot adjudicate each other. At eps = 1 the interface
vanishes: the crossing deck IS a 12 m free-space wire, whose exact answer
the shipped free-space fill gives independently. All four families
collapse (c2 = a_m = 0 kills the images, remainders vanish, transmitted
-> G), and the COMPLETE node-cell arithmetic must reproduce the single
wire to the identity floor. Pass => the complete composition is right
where truth is known, and the real-soil gap is a physics/convention
question about the ENGINE's junction. Fail => our composition is wrong
and the failure localizes it.

Run: prlimit --as=$((8*1024*1024*1024)) .venv/bin/python \
       scratch/524-phase2/proto/probe29_eps1.py [level]
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

import corner_tables as ct  # noqa: E402
import mp_cross  # noqa: E402,F401
import probe14_same_medium as p14  # noqa: E402
from momwire import _sommerfeld_transmitted  # noqa: E402
from momwire.bspline import BSplineSolver  # noqa: E402
from probe1_baseline import seeded  # noqa: E402
from probe9_sense import capture  # noqa: E402
from probe13_x3 import node_indices  # noqa: E402
from probe18_graded import GRADES  # noqa: E402
from probe19_graded_mpb import crossing_graded  # noqa: E402
from probe25_node_cell import cross_pieces_on_axes, graded_axis_data  # noqa: E402
from probe27_complete import SHIPPED_CORNER_X1  # noqa: E402
from momwire._sommerfeld_transmitted import _c1_moment  # noqa: E402

A_WIRE = 0.001
ct.install(wire_radius=A_WIRE)

# the transmitted grid is never consumed (capture swaps the cross blocks);
# skip its eps=1 pathological fill
_sommerfeld_transmitted.get_grid_below_above = lambda *a, **k: None


def free_space_truth(level):
    g = GRADES[level]
    pts = [(0.0, 0.0, z) for z in g["below"][0] + [0.0] + g["above"][0]]
    kw = dict(
        wires=[np.array(pts)],
        n_per_edge_per_wire=[g["below"][1] + g["above"][1]],
        feeds=[(0, 2.0 + 4.3333333333, 1 + 0j)],
        wavelength=crossing_graded(level)["wavelength"],
        wire_radius=A_WIRE,
    )
    z, _ = BSplineSolver(**kw).compute_impedance()
    return z


def main():
    lv = int(sys.argv[1]) if len(sys.argv) > 1 else 1
    t0 = time.time()
    z_truth = free_space_truth(lv)
    print(
        f"g{lv}: free-space single-wire truth = {z_truth:.4f} "
        f"({time.time() - t0:.0f}s)",
        flush=True,
    )

    build = crossing_graded(lv)
    build["ground_eps"] = (1.0, 0.0)
    s = seeded(build)
    geom = s._build_geometry()
    below = s._below_segments(geom)
    b_idx = np.nonzero(below)[0]
    a_idx = np.nonzero(~below)[0]
    b_seg = np.sort(b_idx)
    a_seg = np.sort(a_idx)
    nb, na = node_indices(s, geom)
    eps_t, eps_m, k_p, k_m, c2, a_m = s._buried_medium()
    print(f"g{lv}: eps_t = {eps_t}, c2 = {c2}, a_m = {a_m}", flush=True)

    axA = graded_axis_data(s, geom, a_idx)
    axB = graded_axis_data(s, geom, b_idx)
    t0 = time.time()
    M, SW, SQ, BT = cross_pieces_on_axes(s, axA, axB)
    print(
        f"g{lv}: designed graded cross pieces (eps=1) {time.time() - t0:.0f}s",
        flush=True,
    )

    c1 = _c1_moment(s.omega, s.mu)
    v_corner = complex(ct.six_point(1.0, k_p, A_WIRE, 0.0, 0.0, rtol=1e-10)[1])
    cand = c1 * v_corner
    pick = cand if abs(np.angle(cand / SHIPPED_CORNER_X1)) < np.pi / 2 else -cand
    CORNER = np.zeros_like(M)
    CORNER[na, nb] = pick
    t_A = M + SW + SQ + BT + CORNER
    print(f"g{lv}: corner (eps=1) = {pick:.4f}", flush=True)

    total = None
    for idx, k, wgt, eps in ((b_idx, k_m, a_m, eps_m), (a_idx, k_p, c2, s.eps)):
        axG = graded_axis_data(s, geom, idx)
        bnd_dir, cor_dir = p14.bnd_shape(axG, k, False)
        bnd_img, cor_img = p14.bnd_shape(axG, k, True)
        beta_dir = 1.0 / (1j * s.omega * eps * 4 * np.pi)
        beta_img = wgt / (1j * s.omega * eps * 4 * np.pi)
        piece = beta_dir * (bnd_dir + cor_dir) - beta_img * (bnd_img + cor_img)
        total = piece if total is None else total + piece

    def merge_hook(Zp, nb=nb, na=na, add=total):
        Zp = Zp + add
        Zp[:, nb] += Zp[:, na]
        Zp[nb, :] += Zp[na, :]
        Zp[na, :] = 0.0
        Zp[:, na] = 0.0
        Zp[na, na] = 1.0
        return Zp

    t0 = time.time()
    st = capture(s, t_ab=t_A, a_seg=a_seg, b_seg=b_seg, z_hook=merge_hook)
    z = st["z_in"]
    print(f"g{lv}: complete+merged (eps=1) = {z:.4f}  ({time.time() - t0:.0f}s)")
    print(
        f"g{lv}: VERDICT |Z - truth| = {abs(z - z_truth):.4f} ohm "
        f"({abs(z - z_truth) / abs(z_truth) * 100:.3f} %)"
    )


if __name__ == "__main__":
    main()
