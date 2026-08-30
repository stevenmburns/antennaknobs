"""A-2 session 5, probe 24: the Delta ladder on DESIGNED kernels.

probe8's instrument (uniform x1/x3 crossing deck, MP spelling grid x
{none, V row}) with mp_cross.mp_tables swapped for the designed
radius-folded evaluation (corner_tables). Scored in Delta = Z(crossing)
- Z(mono-alone) vs the engine ladder:

  x1 -2.3260 - 0.7130j    x3 -2.6840 - 1.4260j    x5/limit -2.82 - 1.69j

Run: prlimit --as=$((8*1024*1024*1024)) .venv/bin/python \
       scratch/524-phase2/proto/probe24_designed_ladder.py [mult]
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
from probe1_baseline import crossing_deck, seeded  # noqa: E402
from probe2_crossing import node_rows  # noqa: E402
from probe8_split import ENGINE_DELTA, mono_deck, solve_swapped  # noqa: E402

A_WIRE = 0.001
ct.install(wire_radius=A_WIRE)  # AFTER probe8_split's clamp install


def pieces_designed(mult):
    fp = HERE.parent / "results" / f"probe24-blocks-x{mult}.npz"
    if fp.exists():
        d = np.load(fp)
        return {k: d[k] for k in ("M", "SW", "SQ", "BT")}
    s = seeded(crossing_deck(mult))
    t0 = time.time()
    mp = mp_cross.mp_cross_block(s, rtol=1e-10, boundary="drop")
    print(f"x{mult}: DESIGNED MP pieces built in {time.time() - t0:.0f}s", flush=True)
    pieces = dict(
        M=mp["main_raw"],
        SW=mp["bnd_src_Wp"],
        SQ=mp["bnd_src_q"],
        BT=mp["bnd_test"],
    )
    np.savez(fp, **pieces)
    return pieces


def main():
    mult = int(sys.argv[1]) if len(sys.argv) > 1 else 1
    pieces = pieces_designed(mult)
    M, SW, SQ, BT = (pieces[k] for k in ("M", "SW", "SQ", "BT"))

    t0 = time.time()
    z_mono, _ = BSplineSolver(**mono_deck(mult)).compute_impedance()
    print(
        f"x{mult}: mono (shipped) = {z_mono:.4f}  ({time.time() - t0:.0f}s)", flush=True
    )

    s = seeded(crossing_deck(mult))
    geom = s._build_geometry()
    row_v, _da, _db = node_rows(s, geom)

    spellings = {
        "B_dropAboveQ": M + SW + SQ,
        "dropBothQ": M + SW,
        "A_keep": M + SW + SQ + BT,
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
                f"  {key:>18}: Z = {z:9.4f}   Delta = {delta:9.4f}   "
                f"engine Delta = {d_eng:.4f}   dist = {dist:6.3f} ohm   "
                f"({time.time() - t0:.0f}s)",
                flush=True,
            )

    fp = HERE.parent / "results" / f"probe24-designed-x{mult}.json"
    fp.write_text(json.dumps(out, indent=1))
    print(f"saved {fp}")


if __name__ == "__main__":
    main()
