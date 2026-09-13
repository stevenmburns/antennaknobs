"""AK#1443 step 3, P3.4: the G residual along the source axis, on the clean mesh.

The graded radiator (`step2_source.SourceCounterpoise`, grade_radiator=True) at
nominal_nsegs 42, where step 3 found both engines converged in the far mesh,
with the source at F = 4 / 6 / 8 / 12. NEC-5's fed wire has 2F segments with EX
at the knot; momwire runs on antennaknobs' own odd port, 2F + 1 segments with the
gap mid-segment. The harness asserts off-knot and a one-segment difference, as
step 3 did. Read in Z and Y = 1/Z.

Run from the antennaknobs repo root:
  NEC5_EXE=<nec5cl> .venv/bin/python scratch/1443-counterpoise/step3_source_graded.py [--out F]
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path

from step2_source import SourceCounterpoise, port_check

from antennaknobs.engines.momwire import MomwireEngine
from antennaknobs.engines.nec5 import NEC5Engine

NN = 42


def fr(a, b):
    return 100.0 * (a - b) / max(abs(a), abs(b))


def row(f):
    b = SourceCounterpoise()
    b.nominal_nsegs = NN
    b.source_f = f
    b.grade_radiator = True
    g = ("finite", b.design_eps_r, b.design_sigma)
    deck = NEC5Engine(b, ground=g).deck([b.freq])
    n5_segs = sum(
        int(ln.split()[2]) for ln in deck.splitlines() if ln.startswith("GW ")
    )
    zn = complex(NEC5Engine(b, ground=g).impedance()[0])
    eng = MomwireEngine(b, ground=g)
    segs, on_knot = port_check(eng)
    if on_knot or abs(segs - n5_segs) != 1:
        raise RuntimeError(
            f"not the odd port: momwire {segs} segs vs NEC-5 {n5_segs}, on knot {on_knot}"
        )
    zm = complex(eng.impedance()[0])
    ym, yn = 1 / zm, 1 / zn
    rec = dict(
        nn=NN,
        F=f,
        momwire_segs=segs,
        nec5_segs=n5_segs,
        fed_seg_mm_nec5=50.0 / (2 * f),
        fed_seg_mm_momwire=50.0 / (2 * f + 1),
        momwire=str(zm),
        nec5=str(zn),
        dR_pct=fr(zn.real, zm.real),
        dZ_pct=100.0 * abs(zn - zm) / max(abs(zn), abs(zm)),
        dG_pct=fr(yn.real, ym.real),
        dB_pct=fr(yn.imag, ym.imag),
    )
    print(
        f"F={f} segs mw/n5 {segs}/{n5_segs}  momwire {zm:.6g}  NEC-5 {zn:.6g}  "
        f"dR {rec['dR_pct']:+.2f} %  dG {rec['dG_pct']:+.2f} %  dB {rec['dB_pct']:+.2f} %",
        flush=True,
    )
    return rec


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", type=Path, default=None)
    args = ap.parse_args()
    exe = os.environ["NEC5_EXE"]
    meta = dict(
        nec5_exe=exe, nec5_sha256=hashlib.sha256(Path(exe).read_bytes()).hexdigest()
    )
    print(meta, flush=True)
    out = [row(f) for f in (4, 6, 8, 12)]
    if args.out is not None:
        args.out.write_text(json.dumps(dict(meta=meta, rows=out), indent=1))
        print(f"saved {args.out}")


if __name__ == "__main__":
    main()
