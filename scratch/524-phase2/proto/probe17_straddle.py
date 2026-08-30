"""A-2 session 4, item 3: the STRADDLING basis — the construction sketch
solved with the shipped fill, no node terms at all.

probe15 measured that the two-value-1-tents node is quadrature-unstable by
construction: every by-parts spelling (now derived and pinned, probe14)
swings Z_in by O(100) ohm through coincident-end levers that no practical
quadrature resolves to the 3-ohm physics signal. The construction sketch's
claim was always that the crossing basis DISSOLVES the boundary-term
problem: a basis that straddles z = 0 vanishes at its support ends, so
field form == MP identically and there are no node terms.

The shipped per-segment-class buried fill can already assemble exactly
that: model the crossing deck as ONE polyline wire (-2 -> 0 -> 10, knot
edge at z = 0 by design), label it BELOW to route into
`_compute_Z_operator_buried`, and patch `_below_segments` to the
per-segment z-truth. Then:

  * no junction, no contact bases, no value-1 ends — interior tents
    straddle the interface;
  * `_wire_endpoint_status` skips BELOW wires -> both real ends free (they
    are); the z=0 vertex is an interior knot, not an endpoint;
  * every block class fills exactly as shipped (aa direct+image+remainder,
    bb likewise, cross transmitted field form).

Scored in the Delta instrument vs the engine ladder; the slope condition
(AGARD charge jump) is NOT imposed — it is left to mesh convergence,
which the x1 -> x3 tracking measures honestly.

Run: prlimit --as=$((8*1024*1024*1024)) .venv/bin/python \
     scratch/524-phase2/proto/probe17_straddle.py [mult ...]
"""

from __future__ import annotations

import json
import sys
import time
import types
from pathlib import Path

import numpy as np

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
sys.path.insert(0, str(Path(__file__).resolve().parents[3] / "momwire" / "tests"))

from momwire import _medium_spec  # noqa: E402
from momwire import bspline as _bs  # noqa: E402
from momwire.bspline import BSplineSolver  # noqa: E402
from probe8_split import ENGINE_DELTA, mono_deck  # noqa: E402
from test_buried_serve_553 import SOIL_A, WL7  # noqa: E402


def _subset_per_edge(self, geom, k, seg_idx, mirror_sources=False):
    """`_build_J_blocks_subset` with the same-edge overwrite guarded per
    EDGE instead of per wire. The shipped guard assumes a subset is a union
    of whole WIRES (media are per-wire); the straddling deck's subsets are
    unions of whole EDGES (the knot at z = 0 keeps each edge single-medium),
    which the shipped loop mis-slices (below call: crash on the above edge;
    above call: silently keeps off-edge quadrature on the above edge). The
    analytic static+regularized split lands exactly where `_build_J_blocks`
    puts it, edge by member edge."""
    d = self.degree
    n_total = geom["n_segs_total"]
    if seg_idx.size == 0:
        return np.zeros((d + 1, d + 1, n_total, n_total), dtype=np.complex128)
    seg_l = geom["seg_l"]
    seg_r = geom["seg_r"]
    a_row = self._seg_radius(geom)[seg_idx]
    src_l = seg_l[seg_idx]
    src_r = seg_r[seg_idx]
    if mirror_sources:
        src_l = self._image_positions(src_l)
        src_r = self._image_positions(src_r)
    block = _bs._seg_seg_full_moments_offedge(
        seg_l[seg_idx],
        seg_r[seg_idx],
        src_l,
        src_r,
        a_row,
        k,
        d,
        self.n_qp_pair,
    )
    if not mirror_sources:
        per_wire = geom["per_wire"]
        seg_off = geom["seg_offsets"]
        local_of = np.full(n_total, -1, dtype=np.int64)
        local_of[seg_idx] = np.arange(len(seg_idx))
        for w in range(len(per_wire)):
            pw = per_wire[w]
            ed_off = pw["edge_offsets"]
            ed_arc = pw["edge_arc_edges"]
            base = seg_off[w]
            a_w = float(self._radius_per_wire[w])
            for i_e in range(len(ed_off) - 1):
                lo = int(local_of[base + ed_off[i_e]])
                if lo < 0:
                    continue  # edge not in this subset
                hi = lo + (ed_off[i_e + 1] - ed_off[i_e])
                sl = slice(lo, hi)
                A_st = _bs._seg_seg_static_moments(ed_arc[i_e], a_w, max_d=d)
                A_reg = _bs._seg_seg_reg_moments(
                    ed_arc[i_e], a_w, k, max_d=d, n_qp=self.n_qp_pair
                )
                block[:, :, sl, sl] = A_st + A_reg
    J = np.zeros((d + 1, d + 1, n_total, n_total), dtype=np.complex128)
    J[:, :, seg_idx[:, None], seg_idx[None, :]] = block
    return J


def straddle_deck(mult=1):
    """The crossing deck as ONE polyline: knot edge at z = 0 by design.
    Same mesh as the two-wire deck (4*mult below, 15*mult above); feed at
    arclength 2 + 4.3333 m from the buried tip (engine EX 4,2,7)."""
    return dict(
        wires=[np.array([(0.0, 0.0, -2.0), (0.0, 0.0, 0.0), (0.0, 0.0, 10.0)])],
        n_per_edge_per_wire=[[4 * mult, 15 * mult]],
        feeds=[(0, 6.3333333333, 1 + 0j)],
        wavelength=WL7,
        wire_radius=0.001,
        ground_z=0.0,
        ground_eps=SOIL_A,
        ground_model="sommerfeld",
    )


def seeded_straddle(kw):
    s = BSplineSolver(**kw)
    s._cached_wire_media = (_medium_spec.BELOW,)  # route into the buried fill

    def z_below(self, geom):
        mid = 0.5 * (geom["seg_l"][:, 2] + geom["seg_r"][:, 2])
        return mid < 0.0

    s._below_segments = types.MethodType(z_below, s)
    s._build_J_blocks_subset = types.MethodType(_subset_per_edge, s)
    return s


def main():
    mults = [int(m) for m in sys.argv[1:]] or [1]
    out = {}
    for m in mults:
        s = seeded_straddle(straddle_deck(m))
        geom = s._build_geometry()
        below = s._below_segments(geom)
        print(
            f"x{m}: {int(np.count_nonzero(below))} below / "
            f"{int(np.count_nonzero(~below))} above segments",
            flush=True,
        )

        t0 = time.time()
        z, _ = s.compute_impedance()
        secs = time.time() - t0
        z_mono, _ = BSplineSolver(**mono_deck(m)).compute_impedance()
        d = z - z_mono
        d_eng = ENGINE_DELTA[m]
        dist = abs(d - d_eng)
        out[f"x{m}"] = dict(
            z=f"{z:.4f}",
            mono=f"{z_mono:.4f}",
            delta=f"{d:.4f}",
            engine=f"{d_eng:.4f}",
            dist_ohm=round(float(dist), 3),
            secs=round(secs, 1),
        )
        print(
            f"x{m}: Z = {z:9.4f}   mono = {z_mono:9.4f}   "
            f"Delta = {d:8.4f}   engine = {d_eng:.4f}   "
            f"dist = {dist:6.3f} ohm   ({secs:.0f}s)",
            flush=True,
        )

    fp = HERE.parent / "results" / "probe17-straddle.json"
    old = json.loads(fp.read_text()) if fp.exists() else {}
    old.update(out)
    fp.write_text(json.dumps(old, indent=1))
    print(f"saved {fp}")


if __name__ == "__main__":
    main()
