"""AK#1767 option (b): `specialty.buried_dipole` with its 5 cm feed-gap wire
pinned at 1 / 3 / 5 segments (`None` = the design's own count). momwire bs2
ladder; the NEC-5 and NEC-4.2 decks the engines write at the catalog rungs
(nominal 21 default, 42 refined) for a black-box run on the laptop.

    NEC5_EXE=/bin/true NEC42_EXE=/bin/true \\
        python scratch/1767-buried-dipole/gap_pin.py <outdir>
"""

import json
import sys
import warnings
from pathlib import Path

from antennaknobs.designs.specialty.buried_dipole import Builder
from antennaknobs.engines.momwire import MomwireEngine
from antennaknobs.engines.nec5 import NEC5Engine
from antennaknobs.engines.nec42 import NEC42Engine
from antennaknobs.network import as_wire

warnings.simplefilter("ignore")
G = ("finite", 13.0, 0.005)
OUT = Path(sys.argv[1])
OUT.mkdir(parents=True, exist_ok=True)


def make(gap, n):
    class Gap(Builder):
        def build_wires(self):
            ws = [as_wire(t) for t in super().build_wires()]
            if gap is None:
                return ws
            return [w._replace(n_seg=gap) if w.ex is not None else w for w in ws]

    b = Gap()
    b.nominal_nsegs = n
    return b


res = {}
for gap in (None, 1, 3, 5):
    tag = "auto" if gap is None else str(gap)
    for n in (15, 21, 30, 60, 120, 240):
        eng = MomwireEngine(make(gap, n), ground=G)
        z = complex(eng.impedance()[0])
        (fed,) = eng.fed_segments()
        res[f"{tag} bs2@{n}"] = [z.real, z.imag, fed["segments"], fed["length_m"]]
        print(tag, n, f"{z:.4f}", fed["segments"], flush=True)
    for n in (21, 42):
        b = make(gap, n)
        (OUT / f"nec42_gap{tag}_n{n}.nec").write_text(
            NEC42Engine(b, ground=G).deck(7.1)
        )
        (OUT / f"nec5_gap{tag}_n{n}.nec").write_text(
            NEC5Engine(b, ground=G, require_exe=False).deck([7.1])
        )
(OUT / "momwire.json").write_text(json.dumps(res, indent=1))
