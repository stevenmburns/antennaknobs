"""A-2 session 5, probe 28 — the MATCHED-SPELLING Delta.

probe27's +67-54j "miss" compared a completed crossing column against a
SHIPPED mono column — but the mono deck's contact basis carries the same
missing bnd+corner content (the house rule: difference-of-columns only
cancels what is spelled identically in both). This probe completes BOTH
columns with the same machinery and scores

    Delta = Z_crossing(complete) - Z_mono(complete)

vs the engine ladder limit -2.82 - 1.69j, at g1 and g2.

Run: prlimit --as=$((8*1024*1024*1024)) .venv/bin/python \
       scratch/524-phase2/proto/probe28_matched_delta.py [level ...]
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
from probe1_baseline import seeded  # noqa: E402
from probe2_crossing import node_rows  # noqa: E402,F401
from probe9_sense import capture  # noqa: E402
from probe13_x3 import node_indices  # noqa: E402
from probe18_graded import mono_graded  # noqa: E402
from probe19_graded_mpb import ENGINE_LIMIT, crossing_graded  # noqa: E402
from probe20_graded_rows import EPS_RATIO  # noqa: E402,F401
from probe25_node_cell import graded_axis_data  # noqa: E402
from probe27_complete import cross_complete  # noqa: E402

A_WIRE = 0.001
ct.install(wire_radius=A_WIRE)


def self_complete(s, geom, families):
    """beta_dir (bnd+cor)(G_dir) - beta_img (bnd+cor)(G_img), graded axes,
    summed over the given families [(idx, k, img_weight, eps), ...]."""
    total = None
    for idx, k, wgt, eps in families:
        if idx.size == 0:
            continue
        axG = graded_axis_data(s, geom, idx)
        bnd_dir, cor_dir = p14.bnd_shape(axG, k, False)
        bnd_img, cor_img = p14.bnd_shape(axG, k, True)
        beta_dir = 1.0 / (1j * s.omega * eps * 4 * np.pi)
        beta_img = wgt / (1j * s.omega * eps * 4 * np.pi)
        piece = beta_dir * (bnd_dir + cor_dir) - beta_img * (bnd_img + cor_img)
        total = piece if total is None else total + piece
    return total


def crossing_families(s):
    geom = s._build_geometry()
    below = s._below_segments(geom)
    b_idx = np.nonzero(below)[0]
    a_idx = np.nonzero(~below)[0]
    eps_t, eps_m, k_p, k_m, c2, a_m = s._buried_medium()
    return geom, [(b_idx, k_m, a_m, eps_m), (a_idx, k_p, c2, s.eps)]


def mono_families(s):
    geom = s._build_geometry()
    a_idx = np.arange(geom["n_segs_total"])
    _eps_t, _eps_m, k_p, _k_m, c2, _a_m = s._buried_medium()
    return geom, [(a_idx, k_p, c2, s.eps)]


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

        t_A, _corner = cross_complete(s, lv)
        gx, fams_x = crossing_families(s)
        d_cross = self_complete(s, gx, fams_x)

        sm = BSplineSolver(**mono_graded(lv))
        gm, fams_m = mono_families(sm)
        d_mono = self_complete(sm, gm, fams_m)

        def hook_x(Zp, add=d_cross):
            return Zp + add

        def hook_m(Zp, add=d_mono):
            return Zp + add

        t0 = time.time()
        z_mono = capture(BSplineSolver(**mono_graded(lv)), z_hook=hook_m)["z_in"]
        z_mono_ship = capture(BSplineSolver(**mono_graded(lv)))["z_in"]
        print(
            f"g{lv}: mono complete = {z_mono:.4f} (shipped "
            f"{z_mono_ship:.4f})  ({time.time() - t0:.0f}s)",
            flush=True,
        )

        def merge_hook(Zp, nb=nb, na=na):
            Zp = hook_x(Zp)
            Zp[:, nb] += Zp[:, na]
            Zp[nb, :] += Zp[na, :]
            Zp[na, :] = 0.0
            Zp[:, na] = 0.0
            Zp[na, na] = 1.0
            return Zp

        for cname, hook in (("split", hook_x), ("merged", merge_hook)):
            t0 = time.time()
            st = capture(
                seeded(crossing_graded(lv)),
                t_ab=t_A,
                a_seg=a_seg,
                b_seg=b_seg,
                z_hook=hook,
            )
            z = st["z_in"]
            d = z - z_mono
            dist = abs(d - ENGINE_LIMIT)
            out[f"g{lv}+matched+{cname}"] = dict(
                z=f"{z:.4f}",
                mono=f"{z_mono:.4f}",
                delta=f"{d:.4f}",
                dist_ohm=round(float(dist), 3),
            )
            print(
                f"  g{lv} matched+{cname:>6}: Z = {z:9.4f}   Delta = "
                f"{d:9.4f}   engine limit {ENGINE_LIMIT:.4f}   dist = "
                f"{dist:7.3f}   ({time.time() - t0:.0f}s)",
                flush=True,
            )

    fp = HERE.parent / "results" / "probe28-matched-delta.json"
    old = json.loads(fp.read_text()) if fp.exists() else {}
    old.update(out)
    fp.write_text(json.dumps(old, indent=1))
    print(f"saved {fp}")


if __name__ == "__main__":
    main()
