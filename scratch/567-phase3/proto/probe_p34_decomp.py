"""#567 phase 3, probe P3.4 — WHERE does the ghost row act?

Masks the transferred ghost coupling row by below-basis group (hub-local
vs along-radial rings) on both anchor decks. If the fan's overshoot is
hub-local over-coupling (the line ghost passing point-blank through the
hub), the masked cells will show it, and the respelling axis is the
ghost's ANGULAR distribution, not its amplitude or decay.

Run: prlimit --as=$((8*1024*1024*1024)) .venv/bin/python \
       scratch/567-phase3/proto/probe_p34_decomp.py
"""

from __future__ import annotations

import json
import sys
import time
from pathlib import Path

import numpy as np

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]
sys.path.insert(0, str(HERE))
sys.path.insert(0, str(ROOT / "scratch" / "524-phase2" / "proto"))
sys.path.insert(0, str(ROOT / "momwire" / "tests"))

from momwire import _crossing_fill, _medium_spec  # noqa: E402
from momwire.bspline import BSplineSolver  # noqa: E402,F401
from probe9_sense import capture  # noqa: E402
from probe_p31_ghost import k_soil, seeded, wire_bases  # noqa: E402
from probe_p31_ghost import ghost_deck  # noqa: E402
from probe_p33_fan import aux_deck as fan_aux_deck  # noqa: E402
from test_buried_serve_553 import contact_deck, fan_deck  # noqa: E402

ANCHORS = {"lone": 92.130 - 70.141j, "fan": 90.051 - 70.731j}


def basis_reach(s, geom, bases):
    """Per-basis max horizontal distance from the monopole axis over its
    live support (0 for hub/dir bases standing at the origin)."""
    supp_seg, polys, *_ = s._build_basis_polynomials(geom)
    reach = {}
    for m in bases:
        r = 0.0
        for a in range(supp_seg.shape[1]):
            if not np.any(polys[m, a] != 0.0):
                continue
            g = int(supp_seg[m, a])
            for p in (geom["seg_l"][g], geom["seg_r"][g]):
                r = max(r, float(np.hypot(p[0], p[1])))
        reach[m] = r
    return reach


def harvest(aux_build, media, n_below_wires, km):
    s = seeded(aux_build, media)
    geom = s._build_geometry()
    below = sorted(m for w in range(n_below_wires) for m in wire_bases(s, geom, w))
    g_gho = wire_bases(s, geom, n_below_wires)
    off = geom["seg_offsets"]
    gho_segs = np.arange(int(off[n_below_wires]), int(off[n_below_wires + 1]))
    ax = _crossing_fill.axis_data(s, geom, gho_segs)
    sqw = np.sqrt(ax["w"])
    A = (ax["F"][g_gho] * sqw).T
    b = np.exp(-1j * km * np.abs(ax["nodes"][:, 2])) * sqw
    w_fit, *_ = np.linalg.lstsq(A, b, rcond=None)
    st = capture(s)
    return w_fit @ st["Z"][np.ix_(g_gho, below)], below


def main():
    km = k_soil()
    out = {}
    decks = {
        "lone": (
            contact_deck(),
            (_medium_spec.ABOVE, _medium_spec.BELOW),
            ghost_deck(8.4, 2) | dict(),
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
        assert len(prim_below) == len(aux_below)
        reach = basis_reach(s, geom, prim_below)

        cuts = [0.35, 0.85, 1.85, 99.0]
        for cut in cuts:
            mask = np.array([reach[m] <= cut for m in prim_below])
            rr = row * mask

            def hook(Z, rr=rr):
                Z[m0, prim_below] += rr
                Z[prim_below, m0] += rr
                return Z

            t0 = time.time()
            st = capture(
                seeded(dict(build), media),
                t_ab=t_ab,
                a_seg=a_seg,
                b_seg=b_seg,
                z_hook=hook,
            )
            z = st["z_in"]
            miss = abs(z - ANCHORS[name])
            print(
                f"{name} reach<={cut:>5}: n={int(mask.sum()):3d}  "
                f"Z = {z:9.4f}  miss = {miss:7.3f}  "
                f"({time.time() - t0:.0f}s)",
                flush=True,
            )
            out[f"{name} reach<={cut}"] = dict(
                n=int(mask.sum()), z=f"{z:.4f}", miss_ohm=round(miss, 3)
            )

    fp = HERE.parent / "results" / "probe-p34-decomp.json"
    fp.parent.mkdir(exist_ok=True)
    old = json.loads(fp.read_text()) if fp.exists() else {}
    old.update(out)
    fp.write_text(json.dumps(old, indent=1))
    print(f"saved {fp}")


if __name__ == "__main__":
    main()
