"""A-2 session 4, item 5: the SANE cross spelling under interface grading.

probe18 measured that grading cannot fix the field-form cross blocks (the
near-interface garbage is self-similar under refinement). The remaining
convergence question is about the sane spelling: MP-B cross blocks
(drop-above-q, the only spelling whose Delta is O(1) ohm) diverged under
UNIFORM refinement (+0.73 -> +2.25 while the engine descends to -2.7);
NEC-4's own prescription is junction segments SMALL at the interface.
This probe grades the two-wire crossing deck toward z = 0 (probe18's
GRADES), rebuilds the MP cross pieces at that mesh, and scores
B_dropAboveQ x {split, merged} in Delta vs the engine LIMIT.

Converges toward -2.8-1.7j => production = MP cross fill + graded
interface knots. Stands still or diverges => the missing physics is not
reachable by any (spelling x mesh) combination of the existing families,
and the designed near-interface cell / new kernel work is load-bearing.

Run: prlimit --as=$((8*1024*1024*1024)) .venv/bin/python \
     scratch/524-phase2/proto/probe19_graded_mpb.py [level ...]
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
import probe8_split  # noqa: E402,F401  (installs the z'=0 clamp on mp_tables)
from momwire.bspline import BSplineSolver  # noqa: E402
from probe1_baseline import seeded  # noqa: E402
from probe9_sense import capture  # noqa: E402
from probe13_x3 import node_indices  # noqa: E402
from probe18_graded import GRADES, mono_graded  # noqa: E402
from test_buried_serve_553 import SOIL_A, WL7  # noqa: E402

ENGINE_LIMIT = -2.8200 - 1.6940j


def crossing_graded(level):
    g = GRADES[level]
    below_pts = np.array([(0.0, 0.0, z) for z in g["below"][0] + [0.0]])
    above_pts = np.array([(0.0, 0.0, z) for z in [0.0] + g["above"][0]])
    return dict(
        wires=[below_pts, above_pts],
        n_per_edge_per_wire=[g["below"][1], g["above"][1]],
        junctions=[[(0, "end"), (1, "start")]],
        feeds=[(1, 4.3333333333, 1 + 0j)],
        wavelength=WL7,
        wire_radius=0.001,
        ground_z=0.0,
        ground_eps=SOIL_A,
        ground_model="sommerfeld",
    )


def pieces_graded(level):
    fp = HERE.parent / "results" / f"probe19-blocks-g{level}.npz"
    if fp.exists():
        d = np.load(fp)
        return {k: d[k] for k in ("M", "SW", "SQ", "BT")}
    s = seeded(crossing_graded(level))
    t0 = time.time()
    mp = mp_cross.mp_cross_block(s, rtol=1e-10, boundary="drop")
    print(f"g{level}: MP pieces built in {time.time() - t0:.0f}s", flush=True)
    pieces = dict(
        M=mp["main_raw"],
        SW=mp["bnd_src_Wp"],
        SQ=mp["bnd_src_q"],
        BT=mp["bnd_test"],
    )
    np.savez(fp, **pieces)
    return pieces


def main():
    levels = [int(x) for x in sys.argv[1:]] or [1, 2]
    out = {}
    for lv in levels:
        pieces = pieces_graded(lv)
        t_ab = pieces["M"] + pieces["SW"] + pieces["SQ"]  # B_dropAboveQ

        s = seeded(crossing_graded(lv))
        geom = s._build_geometry()
        below = s._below_segments(geom)
        b_seg = np.sort(np.nonzero(below)[0])
        a_seg = np.sort(np.nonzero(~below)[0])
        nb, na = node_indices(s, geom)
        h_min = float(geom["h_per_seg"].min())
        print(
            f"g{lv}: nb={nb} na={na} n_basis={t_ab.shape[0]} h_node={h_min:.4f}",
            flush=True,
        )

        z_mono = capture(BSplineSolver(**mono_graded(lv)))["z_in"]

        def merge_hook(Zp, nb=nb, na=na):
            Zp[:, nb] += Zp[:, na]
            Zp[nb, :] += Zp[na, :]
            Zp[na, :] = 0.0
            Zp[:, na] = 0.0
            Zp[na, na] = 1.0
            return Zp

        for mname, hook in (("split", None), ("merged", merge_hook)):
            t0 = time.time()
            st = capture(
                seeded(crossing_graded(lv)),
                t_ab=t_ab,
                a_seg=a_seg,
                b_seg=b_seg,
                z_hook=hook,
            )
            z = st["z_in"]
            d = z - z_mono
            dist = abs(d - ENGINE_LIMIT)
            out[f"g{lv}+{mname}"] = dict(
                z=f"{z:.4f}",
                mono=f"{z_mono:.4f}",
                delta=f"{d:.4f}",
                dist_ohm=round(float(dist), 3),
                h_node=h_min,
            )
            print(
                f"  g{lv} B+{mname:>6}: Z = {z:9.4f}   Delta = {d:9.4f}   "
                f"engine limit = {ENGINE_LIMIT:.4f}   dist = {dist:7.3f}"
                f"   ({time.time() - t0:.0f}s)",
                flush=True,
            )

    fp = HERE.parent / "results" / "probe19-graded-mpb.json"
    old = json.loads(fp.read_text()) if fp.exists() else {}
    old.update(out)
    fp.write_text(json.dumps(old, indent=1))
    print(f"saved {fp}")


if __name__ == "__main__":
    main()
