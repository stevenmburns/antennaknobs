"""A-2 session 5, probe 23 — GATE 2: probe19/probe20's grid on DESIGNED
near-interface kernels (corner_tables, radius-folded at a = 1e-3).

Everything identical to probe19 (B x split/merged) + probe20 (B x V/S/V+S
rows) except mp_cross.mp_tables is the designed evaluation: rotated-tail
contour, z' = 0 exact (no clamp), rho_eff = hypot(rho, a) (the §3 radius
rule — the shipped cross fill's rho = 0 node entries are truncated
divergences). Spelling B drops the test-end charge, so it carries no
corner term (consistent-by-omission).

GATE: the continuity mechanisms (merged == V row) must STOP diverging
g1 -> g2. Then Delta vs the engine limit -2.82 - 1.69j.

Run: prlimit --as=$((8*1024*1024*1024)) .venv/bin/python \
       scratch/524-phase2/proto/probe23_designed_gate2.py [level ...]
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
import mp_cross  # noqa: E402
from momwire.bspline import BSplineSolver  # noqa: E402
from probe1_baseline import seeded  # noqa: E402
from probe2_crossing import node_rows  # noqa: E402
from probe9_sense import capture  # noqa: E402
from probe13_x3 import node_indices  # noqa: E402
from probe18_graded import mono_graded  # noqa: E402
from probe19_graded_mpb import ENGINE_LIMIT, crossing_graded  # noqa: E402
from probe20_graded_rows import EPS_RATIO, solve_rows  # noqa: E402

A_WIRE = 0.001

# AFTER all probe imports (probe19 pulls probe8_split, which installs the
# clamped tables) — the designed radius-folded tables take over here.
ct.install(wire_radius=A_WIRE)


def pieces_designed(level):
    fp = HERE.parent / "results" / f"probe23-blocks-g{level}.npz"
    if fp.exists():
        d = np.load(fp)
        return {k: d[k] for k in ("M", "SW", "SQ", "BT")}
    s = seeded(crossing_graded(level))
    t0 = time.time()
    mp = mp_cross.mp_cross_block(s, rtol=1e-10, boundary="drop")
    print(f"g{level}: DESIGNED MP pieces built in {time.time() - t0:.0f}s", flush=True)
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
        pieces = pieces_designed(lv)
        t_ab = pieces["M"] + pieces["SW"] + pieces["SQ"]  # B_dropAboveQ

        s = seeded(crossing_graded(lv))
        geom = s._build_geometry()
        below = s._below_segments(geom)
        b_seg = np.sort(np.nonzero(below)[0])
        a_seg = np.sort(np.nonzero(~below)[0])
        nb, na = node_indices(s, geom)
        row_v, der_a, der_b = node_rows(s, geom)
        row_s = der_a - EPS_RATIO * der_b
        h_min = float(geom["h_per_seg"].min())

        z_mono = capture(BSplineSolver(**mono_graded(lv)))["z_in"]
        print(
            f"g{lv}: mono = {z_mono:.4f}  h_node = {h_min:.4f}  engine "
            f"limit = {ENGINE_LIMIT:.4f}",
            flush=True,
        )

        def merge_hook(Zp, nb=nb, na=na):
            Zp[:, nb] += Zp[:, na]
            Zp[nb, :] += Zp[na, :]
            Zp[na, :] = 0.0
            Zp[:, na] = 0.0
            Zp[na, na] = 1.0
            return Zp

        cells = [
            ("split", "hook", None),
            ("merged", "hook", merge_hook),
            ("V", "rows", [row_v]),
            ("S", "rows", [row_s]),
            ("V+S", "rows", [row_v, row_s]),
        ]
        for cname, kind, arg in cells:
            t0 = time.time()
            if kind == "hook":
                st = capture(
                    seeded(crossing_graded(lv)),
                    t_ab=t_ab,
                    a_seg=a_seg,
                    b_seg=b_seg,
                    z_hook=arg,
                )
                z = st["z_in"]
            else:
                z = solve_rows(lv, t_ab, arg)
            d = z - z_mono
            dist = abs(d - ENGINE_LIMIT)
            out[f"g{lv}+B+{cname}"] = dict(
                z=f"{z:.4f}",
                delta=f"{d:.4f}",
                dist_ohm=round(float(dist), 3),
                h_node=h_min,
            )
            print(
                f"  g{lv} B+{cname:>6}: Z = {z:9.4f}   Delta = {d:9.4f}"
                f"   dist = {dist:7.3f}   ({time.time() - t0:.0f}s)",
                flush=True,
            )

    fp = HERE.parent / "results" / "probe23-designed-gate2.json"
    old = json.loads(fp.read_text()) if fp.exists() else {}
    old.update(out)
    fp.write_text(json.dumps(old, indent=1))
    print(f"saved {fp}")


if __name__ == "__main__":
    main()
