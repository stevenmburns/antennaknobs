"""AK#1455's gate: `elevated_buried_counterpoise`'s driving-point impedance on
NEC-5 and momwire across nominal_nsegs 21 / 42 / 84, on the graded default and
on the stock radiator.

  NEC5_EXE=<nec5cl> PYTHONPATH=<momwire src>:src \\
      python scratch/1455-ebc-graded/ladder.py RADIATOR --out F.json

RADIATOR is `graded` (the design's default after AK#1455) or `stock` (the
radiator as one uniform auto-meshed wire, the design before it). Both engines
use the stock ports, i.e. the design as the catalog serves it. Each rung
records the radiator's segment lengths, the NEC-5 deck's GW segment total and
sha256, Z, Y = 1/Z and the wall time per engine.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import time
from pathlib import Path

import numpy as np

from antennaknobs.designs.verticals.elevated_buried_counterpoise import Builder
from antennaknobs.engines.momwire import MomwireEngine
from antennaknobs.engines.nec5 import NEC5Engine
from antennaknobs.network import GradedSegments, Wire, as_wire


class StockRadiator(Builder):
    """The design as it was before AK#1455: one uniform radiator wire at the
    design density."""

    def build_wires(self):
        ws = [as_wire(w) for w in super().build_wires()]
        return [ws[0], Wire(ws[1].p0, ws[1].p1), *ws[2:]]


def radiator_segments(b):
    """The radiator's segment lengths, feed end first, as the builder meshes it."""
    w = [as_wire(t) for t in b.auto_mesh(b.build_wires())][1]
    length = float(np.linalg.norm(np.subtract(w.p1, w.p0)))
    if isinstance(w.n_seg, GradedSegments):
        edges = [0.0, *w.n_seg.fracs, 1.0]
        out = []
        for k, n in enumerate(w.n_seg.counts):
            out += [(edges[k + 1] - edges[k]) * length / n] * int(n)
        return out
    return [length / int(w.n_seg)] * int(w.n_seg)


def fr(a, b):
    return 100.0 * (a - b) / max(abs(a), abs(b))


def row(nn, radiator):
    cls = StockRadiator if radiator == "stock" else Builder
    b = cls()
    b.nominal_nsegs = nn
    ground = ("finite", b.design_eps_r, b.design_sigma)
    deck = NEC5Engine(b, ground=ground).deck([b.freq])
    n5_segs = sum(
        int(ln.replace(",", " ").split()[2])
        for ln in deck.splitlines()
        if ln.startswith("GW")
    )
    t0 = time.perf_counter()
    zn = complex(NEC5Engine(b, ground=ground).impedance()[0])
    t_n5 = time.perf_counter() - t0
    t0 = time.perf_counter()
    zm = complex(MomwireEngine(b, ground=ground).impedance()[0])
    t_mw = time.perf_counter() - t0
    segs = radiator_segments(b)
    ym, yn = 1 / zm, 1 / zn
    rec = dict(
        nn=nn,
        radiator=radiator,
        radiator_segments=len(segs),
        radiator_seg_first_mm=1000 * segs[0],
        radiator_seg_max_mm=1000 * max(segs),
        nec5_gw_segments=n5_segs,
        nec5_deck_sha256=hashlib.sha256(deck.encode()).hexdigest(),
        momwire=[zm.real, zm.imag],
        nec5=[zn.real, zn.imag],
        dR_pct=fr(zn.real, zm.real),
        dG_pct=fr(yn.real, ym.real),
        dB_pct=fr(yn.imag, ym.imag),
        secs_momwire=round(t_mw, 2),
        secs_nec5=round(t_n5, 2),
    )
    print(
        f"nn={nn} {radiator}: radiator {len(segs)} segs (first {1000 * segs[0]:.2f} mm, "
        f"max {1000 * max(segs):.2f} mm)  NEC-5 GW {n5_segs}  momwire {zm:.6g}  "
        f"NEC-5 {zn:.6g}  dR {rec['dR_pct']:+.2f} %  ({t_mw:.0f} s / {t_n5:.0f} s)",
        flush=True,
    )
    return rec


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("radiator", choices=["graded", "stock"])
    ap.add_argument("--out", type=Path, required=True)
    args = ap.parse_args()
    exe = os.environ.get("NEC5_EXE", "")
    import momwire

    meta = dict(
        nec5_exe=exe,
        nec5_sha256=hashlib.sha256(Path(exe).read_bytes()).hexdigest(),
        momwire=str(Path(momwire.__file__).resolve().parent),
    )
    rows = [row(nn, args.radiator) for nn in (21, 42, 84)]
    r = [x["nec5"][0] for x in rows]
    m = [x["momwire"][0] for x in rows]
    summary = dict(
        nec5_R_spread_pct=100.0 * (max(r) - min(r)) / rows[-1]["nec5"][0],
        momwire_R_spread_pct=100.0 * (max(m) - min(m)) / rows[-1]["momwire"][0],
    )
    print(json.dumps(summary))
    args.out.write_text(
        json.dumps(
            dict(meta=meta, radiator=args.radiator, rows=rows, summary=summary),
            indent=1,
        )
    )


if __name__ == "__main__":
    main()
