"""A-2 session 4, item 2: the EXACT spelling — all four blocks' node terms
consistent — scored in Delta.

Spelling logic (DERIVATION-SAME-MEDIUM.md Secs 2-4):
  * self blocks: shipped + BND (probe14's closed-form by-parts node terms,
    analytic betas, no corners) — this makes them the exact field form of
    the value-1 node tents, minus the corner;
  * cross blocks: MP A-no-corner (probe8's M+SW+SQ+BT) — everything
    except the corner;
  * merged crossing dof (probe10's Z-hook; v[node] = 0 both).
  Corners then cancel CONSISTENTLY (all four dropped; their static parts
  are equal and would telescope to ~0 under merge anyway — probe14
  measured c_bb = c_aa = 14534-15859j while the shipped cross block's
  implicit corner is quadrature-truncated 9.6x below that, so any
  spelling that KEEPS corners mixes conventions and must blow up; two
  such controls are scored to confirm).

Run: prlimit --as=$((8*1024*1024*1024)) .venv/bin/python \
     scratch/524-phase2/proto/probe15_exact_merge.py [mult]
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
from probe1_baseline import crossing_deck, seeded  # noqa: E402
from probe8_split import ENGINE_DELTA, build_pieces, mono_deck  # noqa: E402
from probe9_sense import capture  # noqa: E402
from probe13_x3 import node_indices  # noqa: E402


def main():
    mult = int(sys.argv[1]) if len(sys.argv) > 1 else 1
    d_eng = ENGINE_DELTA[mult]

    bnd = np.load(HERE.parent / "results" / f"probe14-bnd-x{mult}.npz")
    BND = bnd["BND_bb"] + bnd["BND_aa"]
    COR = bnd["COR_bb"] + bnd["COR_aa"]

    pieces = build_pieces(mult)
    t_ab_A = pieces["M"] + pieces["SW"] + pieces["SQ"] + pieces["BT"]

    s = seeded(crossing_deck(mult))
    geom = s._build_geometry()
    below = s._below_segments(geom)
    b_seg = np.sort(np.nonzero(below)[0])
    a_seg = np.sort(np.nonzero(~below)[0])
    nb, na = node_indices(s, geom)
    assert int(bnd["nb"]) == nb and int(bnd["na"]) == na

    def merge(Zp):
        Zp[:, nb] += Zp[:, na]
        Zp[nb, :] += Zp[na, :]
        Zp[na, :] = 0.0
        Zp[:, na] = 0.0
        Zp[na, na] = 1.0
        return Zp

    def hook(add=None, merged=False):
        def h(Zp):
            if add is not None:
                Zp = Zp + add
            return merge(Zp) if merged else Zp

        return h

    t0 = time.time()
    z_mono = capture(BSplineSolver(**mono_deck(mult)))["z_in"]
    print(
        f"x{mult}: mono = {z_mono:.4f}   engine Delta = {d_eng:.4f}   "
        f"({time.time() - t0:.0f}s)",
        flush=True,
    )

    grid = [
        ("naive+none+split", None, None, False),  # regression
        ("MPcrossA+none+merged", t_ab_A, None, True),  # probe10 repro
        ("MPcrossA+BND+split", t_ab_A, BND, False),
        ("MPcrossA+BND+merged", t_ab_A, BND, True),  # THE spelling
        ("shipped+BND+merged", None, BND, True),  # corner-mix control
        ("MPcrossA+BND+COR+merged", t_ab_A, BND + COR, True),  # control
    ]

    out = {"mono": f"{z_mono:.4f}", "engine_delta": f"{d_eng:.4f}"}
    for name, t_ab, add, merged in grid:
        t0 = time.time()
        st = capture(
            seeded(crossing_deck(mult)),
            t_ab=t_ab,
            a_seg=a_seg,
            b_seg=b_seg,
            z_hook=hook(add, merged),
        )
        z = st["z_in"]
        d = z - z_mono
        dist = abs(d - d_eng)
        out[name] = dict(z=f"{z:.4f}", delta=f"{d:.4f}", dist_ohm=round(float(dist), 3))
        print(
            f"  {name:>26}: Z_in = {z:10.4f}   Delta = {d:9.4f}   "
            f"dist = {dist:8.3f}   ({time.time() - t0:.0f}s)",
            flush=True,
        )

    fp = HERE.parent / "results" / f"probe15-exact-x{mult}.json"
    fp.write_text(json.dumps(out, indent=1))
    print(f"saved {fp}")


if __name__ == "__main__":
    main()
