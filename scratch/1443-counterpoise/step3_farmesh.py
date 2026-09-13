"""AK#1443 step 3: the far mesh at a fixed, matched-size source.

The source is held at F = 4 (`step2_source.SourceCounterpoise`): NEC-5's fed wire
8 x 6.25 mm with EX at the knot, momwire on antennaknobs' own odd port, 9 x
5.56 mm with the gap mid-segment (P2.5: B within 0.18 % there). nominal_nsegs
21 / 42 / 84 then refines the radiator and the buried radials together, on the
design's own radiator (`stock`) and on step 2's explicitly graded one
(`graded`). Read in Z and Y = 1/Z.

The harness asserts that momwire's feed is off-knot, with a segment count one
away from NEC-5's.

Run from the antennaknobs repo root:
  NEC5_EXE=<nec5cl> .venv/bin/python scratch/1443-counterpoise/step3_farmesh.py RADIATOR [--out F]
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import time
from pathlib import Path

from step2_source import SourceCounterpoise, port_check

from antennaknobs.engines.momwire import MomwireEngine
from antennaknobs.engines.nec5 import NEC5Engine

SOURCE_F = 4


def fr(a, b):
    return 100.0 * (a - b) / max(abs(a), abs(b))


def row(nn, graded):
    b = SourceCounterpoise()
    b.nominal_nsegs = nn
    b.source_f = SOURCE_F
    b.grade_radiator = graded
    g = ("finite", b.design_eps_r, b.design_sigma)
    deck = NEC5Engine(b, ground=g).deck([b.freq])
    n5_segs = sum(
        int(ln.split()[2]) for ln in deck.splitlines() if ln.startswith("GW ")
    )
    t0 = time.time()
    zn = complex(NEC5Engine(b, ground=g).impedance()[0])
    t_n5 = time.time() - t0
    eng = MomwireEngine(b, ground=g)
    segs, on_knot = port_check(eng)
    if on_knot or abs(segs - n5_segs) != 1:
        raise RuntimeError(
            f"not the odd port: momwire {segs} segs vs NEC-5 {n5_segs}, on knot {on_knot}"
        )
    t0 = time.time()
    zm = complex(eng.impedance()[0])
    t_mw = time.time() - t0
    ym, yn = 1 / zm, 1 / zn
    rec = dict(
        nn=nn,
        graded=graded,
        source_f=SOURCE_F,
        momwire_segs=segs,
        nec5_segs=n5_segs,
        deck_sha=hashlib.sha256(deck.encode()).hexdigest()[:16],
        momwire=str(zm),
        nec5=str(zn),
        dR_pct=fr(zn.real, zm.real),
        dZ_pct=100.0 * abs(zn - zm) / max(abs(zn), abs(zm)),
        dG_pct=fr(yn.real, ym.real),
        dB_pct=fr(yn.imag, ym.imag),
        secs_momwire=round(t_mw, 1),
        secs_nec5=round(t_n5, 1),
    )
    print(
        f"nn={nn} graded={graded} segs mw/n5 {segs}/{n5_segs}  momwire {zm:.6g}  "
        f"NEC-5 {zn:.6g}  dR {rec['dR_pct']:+.2f} %  dG {rec['dG_pct']:+.2f} %  "
        f"dB {rec['dB_pct']:+.2f} %  |dZ| {rec['dZ_pct']:.2f} %  "
        f"({t_mw:.0f} s / {t_n5:.0f} s)",
        flush=True,
    )
    return rec


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("radiator", choices=["stock", "graded"])
    ap.add_argument("--out", type=Path, default=None)
    args = ap.parse_args()
    exe = os.environ["NEC5_EXE"]
    meta = dict(
        nec5_exe=exe, nec5_sha256=hashlib.sha256(Path(exe).read_bytes()).hexdigest()
    )
    print(meta, flush=True)
    graded = args.radiator == "graded"
    out = [row(nn, graded) for nn in (21, 42, 84)]
    if args.out is not None:
        args.out.write_text(
            json.dumps(dict(meta=meta, radiator=args.radiator, rows=out), indent=1)
        )
        print(f"saved {args.out}")


if __name__ == "__main__":
    main()
