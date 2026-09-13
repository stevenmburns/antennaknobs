"""AK#1443 step 2: is the source region the 31 %?

The census deck feeds a 50 mm wire at the radiator's foot and then jumps to a
radiator segment of 500 mm (nominal_nsegs 21) or 250 mm (42), a 10:1-20:1 step
at the source. nominal_nsegs refines the radiator and radials, never the fed
wire. momwire#1048 found #1027's rod carried its whole disagreement on exactly
that axis, so it is measured first here.

Two ladders, both with the ports matched (momwire's feed parity patched to even,
so it shares NEC-5's knot source) and both asserted segment for segment:

  feed     the fed wire at 2F segments (25 mm / F), the radiator as the census
           meshes it -- how far the fed segment alone moves each engine
  graded   the fed wire at 2F segments and the radiator graded away from it by
           an explicit schedule: panels double in length from 2 * (25 mm / F),
           each panel's segment is min(census radiator segment,
           max(25 mm / F, panel start / 2)). Adjacent segments differ by at most
           2x and none exceeds the census's own radiator segment.
           `graded_wire`'s growth-4 recipe is not used: on this radiator it
           makes 2.4 m segments in the middle (momwire#1048's P2b.3 confound).

F = 1 on the `feed` ladder is the census deck, checked by sha256.

Run from the antennaknobs repo root:
  NEC5_EXE=<nec5cl> .venv/bin/python scratch/1443-counterpoise/step2_source.py LADDER [--nn N] [--out F]
"""

from __future__ import annotations

import argparse
import hashlib
import itertools
import json
import math
import os
from contextlib import contextmanager
from pathlib import Path
from types import MappingProxyType

import numpy as np

import antennaknobs.engines.momwire as mwe
from antennaknobs.designs.verticals.elevated_buried_counterpoise import Builder
from antennaknobs.engines.momwire import MomwireEngine
from antennaknobs.engines.nec5 import NEC5Engine
from antennaknobs.network import Wire
from antennaknobs.wire_catalog import GradedSegments

CENSUS_SHA = {21: "14239f58d8073ceb", 42: "5c08c0eee924e8fe"}
EPS = 0.05  # the design's fed-wire length


def graded_schedule(length, h0, rest):
    """(fracs, counts) grading from p0: panels doubling from 2 * h0, adjacent
    segments within 2x, no segment above `rest`."""
    bounds = []
    b = 2.0 * h0
    while b < length * (1 - 1e-9):
        bounds.append(b)
        b *= 2.0
    edges = [0.0, *bounds, length]
    counts = []
    for lo, hi in itertools.pairwise(edges):
        s = min(rest, max(h0, lo / 2.0))
        counts.append(max(2, math.ceil((hi - lo) / s - 1e-9)))
    fracs = tuple(x / length for x in bounds)
    return fracs, tuple(counts)


class SourceCounterpoise(Builder):
    default_params = MappingProxyType(
        {**Builder.default_params, "source_f": 1, "grade_radiator": False}
    )

    def build_wires(self):
        stock = super().build_wires()
        f = int(self.source_f)
        base = self.base
        height = 0.25 * self.design_wavelength * self.length_factor
        feed = Wire(
            (0.0, 0.0, base),
            (0.0, 0.0, base + EPS),
            n_seg=None if f == 1 else 2 * f,
            ex=1 + 0j,
        )
        if self.grade_radiator:
            length = height - EPS
            rest = length / int(self.nominal_nsegs)
            fracs, counts = graded_schedule(length, (EPS / 2.0) / f, rest)
            radiator = Wire(
                (0.0, 0.0, base + EPS),
                (0.0, 0.0, base + height),
                n_seg=GradedSegments(fracs=fracs, counts=counts),
            )
        else:
            radiator = stock[1]
        return [feed, radiator, *stock[2:]]


@contextmanager
def momwire_even_parity():
    orig = mwe._parity_for_solver
    mwe._parity_for_solver = lambda solver, solver_kwargs: "even"
    try:
        yield
    finally:
        mwe._parity_for_solver = orig


def port_check(eng):
    w, s_f, _v = eng._feeds[0]
    poly = np.asarray(eng._polylines[w], dtype=float)
    knots = mwe._polyline_knots(poly, eng._edge_segments[w])
    arcs = np.concatenate(
        [[0.0], np.cumsum(np.linalg.norm(np.diff(knots, axis=0), axis=1))]
    )
    segs = sum(sum(e) for e in eng._edge_segments)
    return segs, bool(np.min(np.abs(arcs - s_f)) < 1e-12)


def row(nn, f, graded):
    b = SourceCounterpoise()
    b.nominal_nsegs = nn
    b.source_f = f
    b.grade_radiator = graded
    g = ("finite", b.design_eps_r, b.design_sigma)
    deck = NEC5Engine(b, ground=g).deck([b.freq])
    sha = hashlib.sha256(deck.encode()).hexdigest()[:16]
    if f == 1 and not graded and sha != CENSUS_SHA[nn]:
        raise RuntimeError(f"F = 1 is not the census deck: {sha} vs {CENSUS_SHA[nn]}")
    gw = [ln.split() for ln in deck.splitlines() if ln.startswith("GW ")]
    n5_segs = sum(int(t[2]) for t in gw)
    feed_h = math.dist([float(x) for x in gw[0][3:6]], [float(x) for x in gw[0][6:9]])
    feed_h /= int(gw[0][2])
    zn = complex(NEC5Engine(b, ground=g).impedance()[0])
    with momwire_even_parity():
        eng = MomwireEngine(b, ground=g)
        segs, on_knot = port_check(eng)
        if segs != n5_segs or not on_knot:
            raise RuntimeError(
                f"port not matched: momwire {segs} segs vs NEC-5 {n5_segs}, knot {on_knot}"
            )
        zm = complex(eng.impedance()[0])
    rec = dict(
        nn=nn,
        F=f,
        graded=graded,
        deck_sha=sha,
        segs=segs,
        feed_seg_mm=1000 * feed_h,
        momwire=str(zm),
        nec5=str(zn),
        dR_over_maxR_pct=100 * (zn.real - zm.real) / max(abs(zm.real), abs(zn.real)),
        dZ_over_maxZ_pct=100 * abs(zn - zm) / max(abs(zm), abs(zn)),
    )
    print(
        f"nn={nn} F={f} graded={graded} segs={segs} feed seg {rec['feed_seg_mm']:.3f} mm  "
        f"momwire {zm:.6g}  NEC-5 {zn:.6g}  dR/max|R| {rec['dR_over_maxR_pct']:+.2f} %  "
        f"|dZ|/max|Z| {rec['dZ_over_maxZ_pct']:.2f} %",
        flush=True,
    )
    return rec


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("ladder", choices=["feed", "graded"])
    ap.add_argument("--nn", type=int, default=21)
    ap.add_argument("--out", type=Path, default=None)
    args = ap.parse_args()
    exe = os.environ["NEC5_EXE"]
    meta = dict(
        nec5_exe=exe, nec5_sha256=hashlib.sha256(Path(exe).read_bytes()).hexdigest()
    )
    print(meta, flush=True)
    graded = args.ladder == "graded"
    out = [row(args.nn, f, graded) for f in (1, 2, 4, 8)]
    if args.out is not None:
        args.out.write_text(
            json.dumps(dict(meta=meta, ladder=args.ladder, rows=out), indent=1)
        )
        print(f"saved {args.out}")


if __name__ == "__main__":
    main()
