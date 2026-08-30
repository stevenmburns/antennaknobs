"""A-2 session 4, item 6: the AGARD junction as Lagrange rows on the
graded MP-B fill — the last untested (spelling x mesh x constraint) cell.

probe19: B+split converges under interface grading to Delta ~ 0 (stub
invisible — no continuity), B+merged blows up (coincident-tent node
pricing). probe2 tried constraint rows only on the BROKEN naive fill at
the COARSE mesh, where the tents cannot bend to satisfy them. On the
graded mesh the interface tents are 1-5 cm; the AGARD conditions

    V:  I(0+) - I(0-) = 0                (continuity)
    S:  I'(0+) - (eps+/eps-) I'(0-) = 0  (slope / charge jump)

imposed as rows on the SANE cross spelling are exactly NEC-4's junction
treatment. Scored in Delta vs the engine limit, levels 1 and 2.

Run: prlimit --as=$((8*1024*1024*1024)) .venv/bin/python \
     scratch/524-phase2/proto/probe20_graded_rows.py [level ...]
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

from momwire.bspline import BSplineSolver  # noqa: E402
from probe1_baseline import seeded  # noqa: E402
from probe2_crossing import node_rows  # noqa: E402
from probe9_sense import capture  # noqa: E402
from probe18_graded import mono_graded  # noqa: E402
from probe19_graded_mpb import ENGINE_LIMIT, crossing_graded, pieces_graded  # noqa: E402

EPS_RATIO = 1.0 / (13.0 - 12.841855j)  # eps+/eps- at soil A, 7 MHz


def solve_rows(lv, t_ab, rows):
    s = seeded(crossing_graded(lv))
    geom = s._build_geometry()
    below = s._below_segments(geom)
    b_seg = np.sort(np.nonzero(below)[0])
    a_seg = np.sort(np.nonzero(~below)[0])

    orig_kcl = BSplineSolver._solve_with_kcl

    def wrap_kcl(self, Z, v, kcl_A, overwrite=False):
        if rows:
            add = np.stack(rows)
            kcl_A = np.vstack([kcl_A.astype(add.dtype), add])
        return orig_kcl(self, Z, v, kcl_A, overwrite=False)

    BSplineSolver._solve_with_kcl = wrap_kcl
    try:
        st = capture(s, t_ab=t_ab, a_seg=a_seg, b_seg=b_seg)
    finally:
        BSplineSolver._solve_with_kcl = orig_kcl
    return st["z_in"]


def main():
    levels = [int(x) for x in sys.argv[1:]] or [1, 2]
    out = {}
    for lv in levels:
        pieces = pieces_graded(lv)
        t_ab = pieces["M"] + pieces["SW"] + pieces["SQ"]  # B_dropAboveQ

        s = seeded(crossing_graded(lv))
        geom = s._build_geometry()
        row_v, der_a, der_b = node_rows(s, geom)
        row_s = der_a - EPS_RATIO * der_b

        z_mono = capture(BSplineSolver(**mono_graded(lv)))["z_in"]
        print(
            f"g{lv}: mono = {z_mono:.4f}   engine limit = {ENGINE_LIMIT:.4f}",
            flush=True,
        )

        for rname, rows in (("V", [row_v]), ("S", [row_s]), ("V+S", [row_v, row_s])):
            t0 = time.time()
            z = solve_rows(lv, t_ab, rows)
            d = z - z_mono
            dist = abs(d - ENGINE_LIMIT)
            out[f"g{lv}+B+{rname}"] = dict(
                z=f"{z:.4f}", delta=f"{d:.4f}", dist_ohm=round(float(dist), 3)
            )
            print(
                f"  g{lv} B+{rname:>4}: Z = {z:9.4f}   Delta = {d:9.4f}   "
                f"dist = {dist:7.3f}   ({time.time() - t0:.0f}s)",
                flush=True,
            )

    fp = HERE.parent / "results" / "probe20-graded-rows.json"
    old = json.loads(fp.read_text()) if fp.exists() else {}
    old.update(out)
    fp.write_text(json.dumps(old, indent=1))
    print(f"saved {fp}")


if __name__ == "__main__":
    main()
