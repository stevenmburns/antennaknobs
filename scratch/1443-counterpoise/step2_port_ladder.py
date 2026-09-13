"""AK#1443 step 2, P2.5: do momwire's two port spellings converge to the same Y?

`step2_source.SourceCounterpoise`'s `feed` ladder with momwire on antennaknobs'
own odd-parity port and no patch: the builder asks for 2F fed segments, the odd
coercion makes them 2F + 1 (F = 1 auto-meshes to one), so the delta gap sits
mid-segment as the census has it. NEC-5 is unchanged. The harness asserts that
momwire's feed is NOT on a knot and that its segment count differs from NEC-5's
by exactly one, then reads Z and Y = 1/Z.

Run from the antennaknobs repo root:
  NEC5_EXE=<nec5cl> .venv/bin/python scratch/1443-counterpoise/step2_port_ladder.py [--out F]
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


def row(nn, f):
    b = SourceCounterpoise()
    b.nominal_nsegs = nn
    b.source_f = f
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
        nn=nn,
        F=f,
        momwire_segs=segs,
        nec5_segs=n5_segs,
        momwire=str(zm),
        nec5=str(zn),
        G_momwire=ym.real,
        B_momwire=ym.imag,
        G_nec5=yn.real,
        B_nec5=yn.imag,
    )
    print(
        f"nn={nn} F={f} momwire segs {segs} (odd port) NEC-5 segs {n5_segs}  "
        f"momwire {zm:.6g}  NEC-5 {zn:.6g}  G {ym.real:.5e}/{yn.real:.5e}  "
        f"B {ym.imag:.5e}/{yn.imag:.5e}",
        flush=True,
    )
    return rec


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--nn", type=int, default=21)
    ap.add_argument("--out", type=Path, default=None)
    args = ap.parse_args()
    exe = os.environ["NEC5_EXE"]
    meta = dict(
        nec5_exe=exe, nec5_sha256=hashlib.sha256(Path(exe).read_bytes()).hexdigest()
    )
    print(meta, flush=True)
    out = [row(args.nn, f) for f in (1, 2, 4, 8)]
    if args.out is not None:
        args.out.write_text(json.dumps(dict(meta=meta, rows=out), indent=1))
        print(f"saved {args.out}")


if __name__ == "__main__":
    main()
