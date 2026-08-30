"""A-2 session 6, probe 34 — adjudicator 3: the consistent-omission
spelling zoo at resolved quadrature (soil A, graded meshes, cached
designed blocks). Question: can ANY omission spelling (the #151
end-charge omission extended to the crossing node — shipped self blocks
+ designed cross MINUS boundary/corner pieces, no constraints) reproduce
the engine's Delta ~ -2.82-1.69j while staying mesh-stable g1 -> g2?

probe23 already measured designed-B (M+SW+SQ) + split: Delta stable ~ 0.
This fills in the rest of the omission axis: M-only, M+SW, and
A = M+SW+SQ+BT, split each, plus one corner-only-no-self-completion
control cell for the telescoping record.

Run: prlimit --as=$((8*1024*1024*1024)) .venv/bin/python \
       scratch/524-phase2/proto/probe34_omission_zoo.py [level ...]
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
from momwire.bspline import BSplineSolver  # noqa: E402
from momwire._sommerfeld_transmitted import _c1_moment  # noqa: E402
from probe1_baseline import seeded  # noqa: E402
from probe9_sense import capture  # noqa: E402
from probe13_x3 import node_indices  # noqa: E402
from probe18_graded import mono_graded  # noqa: E402
from probe19_graded_mpb import ENGINE_LIMIT, crossing_graded  # noqa: E402

A_WIRE = 0.001
ct.install(wire_radius=A_WIRE)


def cfmt(z):
    return f"{z.real:+.4f}{z.imag:+.4f}j"


def main():
    levels = [int(x) for x in sys.argv[1:]] or [1, 2]
    out = {}
    for lv in levels:
        d = np.load(HERE.parent / "results" / f"probe23-blocks-g{lv}.npz")
        M, SW, SQ, BT = d["M"], d["SW"], d["SQ"], d["BT"]
        s = seeded(crossing_graded(lv))
        geom = s._build_geometry()
        below = s._below_segments(geom)
        b_seg = np.sort(np.nonzero(below)[0])
        a_seg = np.sort(np.nonzero(~below)[0])
        nb, na = node_indices(s, geom)
        eps_t, _em, k_p, _km, _c2, _am = s._buried_medium()
        c1 = _c1_moment(s.omega, s.mu)
        corner = c1 * complex(ct.six_point(eps_t, k_p, A_WIRE, 0.0, 0.0, rtol=1e-10)[1])
        CORNER = np.zeros_like(M)
        CORNER[na, nb] = corner

        z_mono = capture(BSplineSolver(**mono_graded(lv)))["z_in"]
        print(f"\n== g{lv}: mono = {cfmt(z_mono)}", flush=True)

        cells = {
            "M-only": M,
            "M+SW": M + SW,
            "B(M+SW+SQ)": M + SW + SQ,
            "A(M+SW+SQ+BT)": M + SW + SQ + BT,
            "A+corner-no-selfcomp": M + SW + SQ + BT + CORNER,
        }
        for name, t_A in cells.items():
            t0 = time.time()
            st = capture(
                seeded(crossing_graded(lv)), t_ab=t_A, a_seg=a_seg, b_seg=b_seg
            )
            z = st["z_in"]
            dd = z - z_mono
            dist = abs(dd - ENGINE_LIMIT)
            print(
                f"  g{lv} {name:>22} +split: Z = {cfmt(z)}  Delta = "
                f"{cfmt(dd)}  dist = {dist:7.3f}  ({time.time() - t0:.0f}s)",
                flush=True,
            )
            out[f"g{lv}+{name}+split"] = dict(
                z=f"{z:.4f}", delta=f"{dd:.4f}", dist_ohm=round(float(dist), 3)
            )

    fp = HERE.parent / "results" / "probe34-omission-zoo.json"
    old = json.loads(fp.read_text()) if fp.exists() else {}
    old.update(out)
    fp.write_text(json.dumps(old, indent=1))
    print(f"\nsaved {fp}")


if __name__ == "__main__":
    main()
