"""#567 phase 3, probe P3.5 — the beta instrument: is the ghost row's
SHAPE right?

Scale the transferred ghost coupling row by a complex beta and minimize
|Z(beta) - anchor| per deck (Nelder-Mead on (Re, Im), seeded from a
coarse grid). If beta*(lone) == beta*(fan), the coupling mechanism
transfers and beta* is a measured spelling constant to identify against
the interface-coefficient family {1, 2/(1+eps), (eps-1)/(eps+1), 1/eps};
if they differ, the prescribed-line-ghost family dies the same death as
phase 0's scalar endpoint weight — measured, on the record.

Run: prlimit --as=$((8*1024*1024*1024)) .venv/bin/python \
       scratch/567-phase3/proto/probe_p35_beta.py
"""

from __future__ import annotations

import json
import sys
import time
from pathlib import Path

import numpy as np
from scipy.optimize import minimize

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]
sys.path.insert(0, str(HERE))
sys.path.insert(0, str(ROOT / "scratch" / "524-phase2" / "proto"))
sys.path.insert(0, str(ROOT / "momwire" / "tests"))

from momwire import _crossing_fill, _medium_spec  # noqa: E402
from probe9_sense import capture  # noqa: E402
from probe_p31_ghost import ghost_deck, k_soil, seeded, wire_bases  # noqa: E402
from probe_p33_fan import aux_deck as fan_aux_deck  # noqa: E402
from probe_p34_decomp import harvest  # noqa: E402
from test_buried_serve_553 import contact_deck, fan_deck  # noqa: E402

ANCHORS = {"lone": 92.130 - 70.141j, "fan": 90.051 - 70.731j}


def eps_t():
    w = 2 * np.pi * 299792458.0 / 42.827494
    return 13.0 - 1j * 0.005 / (w * 8.8541878128e-12)


def main():
    km = k_soil()
    et = eps_t()
    out = {}
    decks = {
        "lone": (
            contact_deck(),
            (_medium_spec.ABOVE, _medium_spec.BELOW),
            ghost_deck(8.4, 2),
            (_medium_spec.BELOW, _medium_spec.BELOW),
            1,
        ),
        "fan": (
            fan_deck(),
            (_medium_spec.ABOVE,) + (_medium_spec.BELOW,) * 4,
            fan_aux_deck(),
            (_medium_spec.BELOW,) * 5,
            4,
        ),
    }
    for name, (build, media, aux, aux_media, n_bw) in decks.items():
        row, aux_below = harvest(aux, aux_media, n_bw, km)

        s = seeded(dict(build), media)
        geom = s._build_geometry()
        below = s._below_segments(geom)
        b_seg = np.sort(np.nonzero(below)[0])
        a_seg = np.sort(np.nonzero(~below)[0])
        ax_a = _crossing_fill.axis_data(s, geom, a_seg)
        ax_b = _crossing_fill.axis_data(s, geom, b_seg)
        t_ab = _crossing_fill.cross_complete_block(
            s, geom, dict(ax_a, ends=[]), dict(ax_b, ends=[])
        )
        m0 = None
        for pt, _sg, fv in ax_a["ends"]:
            if abs(pt[2]) < 1e-9:
                m0 = int(np.argmax(np.abs(fv)))
        n_wires = len(build["wires"])
        prim_below = sorted(
            m for w in range(1, n_wires) for m in wire_bases(s, geom, w)
        )

        def z_of(beta):
            def hook(Z):
                rr = beta * row
                Z[m0, prim_below] += rr
                Z[prim_below, m0] += rr
                return Z

            st = capture(
                seeded(dict(build), media),
                t_ab=t_ab,
                a_seg=a_seg,
                b_seg=b_seg,
                z_hook=hook,
            )
            return st["z_in"]

        def miss(v):
            return abs(z_of(v[0] + 1j * v[1]) - ANCHORS[name])

        t0 = time.time()
        # Coarse grid seed, then simplex.
        grid = [
            (re, im)
            for re in (0.0, 0.5, 1.0, 1.5, 2.0)
            for im in (-1.0, -0.5, 0.0, 0.5, 1.0)
        ]
        seed = min(grid, key=miss)
        res = minimize(
            miss,
            np.array(seed),
            method="Nelder-Mead",
            options=dict(xatol=1e-3, fatol=1e-3),
        )
        bstar = res.x[0] + 1j * res.x[1]
        zb = z_of(bstar)
        print(
            f"{name}: beta* = {bstar:.4f}  Z = {zb:9.4f}  "
            f"residual miss = {res.fun:7.3f} ohm  "
            f"(beta=1 miss was {miss([1.0, 0.0]):.3f}; {time.time() - t0:.0f}s)",
            flush=True,
        )
        out[name] = dict(
            beta=f"{bstar:.4f}",
            z=f"{zb:.4f}",
            residual_miss_ohm=round(float(res.fun), 3),
        )

    fam = {
        "1": 1.0 + 0j,
        "2/(1+eps)": 2.0 / (1.0 + et),
        "(eps-1)/(eps+1)": (et - 1.0) / (et + 1.0),
        "1/eps": 1.0 / et,
        "2*eps/(1+eps)": 2.0 * et / (1.0 + et),
    }
    print("family constants at soil A:", flush=True)
    for k, v in fam.items():
        print(f"  {k:>15} = {v:.4f}", flush=True)
    out["family"] = {k: f"{v:.4f}" for k, v in fam.items()}

    fp = HERE.parent / "results" / "probe-p35-beta.json"
    fp.parent.mkdir(exist_ok=True)
    old = json.loads(fp.read_text()) if fp.exists() else {}
    old.update(out)
    fp.write_text(json.dumps(old, indent=1))
    print(f"saved {fp}")


if __name__ == "__main__":
    main()
