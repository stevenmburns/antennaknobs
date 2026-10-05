"""AK#1767: specialty.buried_dipole, the 5 cm gap wire (old) vs one wire fed
at its middle (new). momwire ladders; NEC-5 / NEC-4.2 decks for a black box."""

import json
import sys
from pathlib import Path
from antennaknobs.designs.specialty.buried_dipole import Builder as B
from antennaknobs.network import Wire
from antennaknobs.engines.momwire import MomwireEngine
from antennaknobs.engines.nec5 import NEC5Engine
from antennaknobs.nec_export import export_nec
from antennaknobs import momwire_bases

G = ("finite", 13.0, 0.005)
OUT = Path(sys.argv[1])
OUT.mkdir(parents=True, exist_ok=True)


class Merged(B):
    def build_wires(self):
        half = 0.25 * self.design_wavelength * self.velocity_factor * self.length_factor
        z = -self.depth
        return [Wire((-half, 0.0, z), (half, 0.0, z), ex=1 + 0j)]


def make(cls, n, depth=0.15):
    b = cls()
    b.nominal_nsegs = n
    b.depth = depth
    return b


_, rcls, rkw = momwire_bases.resolve("razor-2p")
_, scls, skw = momwire_bases.resolve("sinusoidal-galerkin")
res = {}
for name, cls in (("old", B), ("new", Merged)):
    for depth in (0.15, 1.0):
        for n in (15, 30, 60, 120):
            e = MomwireEngine(make(cls, n, depth), ground=G)
            z = complex(e.impedance()[0])
            fs = e.fed_segments()[0]
            res[f"{name} d{depth} bs2@{n}"] = (
                str(z),
                fs["segments"],
                round(fs["length_m"], 4),
            )
            print(name, depth, "bs2", n, z, fs["segments"], fs["length_m"], flush=True)
        for n in (40, 80, 160):
            e = MomwireEngine(
                make(cls, n, depth), solver=rcls, solver_kwargs=dict(rkw), ground=G
            )
            z = complex(e.impedance()[0])
            res[f"{name} d{depth} razor@{n}"] = str(z)
            print(name, depth, "razor", n, z, flush=True)
        for n in (20, 40):
            e = MomwireEngine(
                make(cls, n, depth), solver=scls, solver_kwargs=dict(skw), ground=G
            )
            z = complex(e.impedance()[0])
            res[f"{name} d{depth} sg@{n}"] = str(z)
            print(name, depth, "sg", n, z, flush=True)
        for n in (40, 80, 160):
            b = make(cls, n, depth)
            (OUT / f"nec5_{name}_d{depth}_n{n}.nec").write_text(
                NEC5Engine(b, ground=G).deck([float(b.freq)])
            )
        for n in (21, 42, 84):
            b = make(cls, n, depth)
            (OUT / f"nec42_{name}_d{depth}_n{n}.nec").write_text(
                export_nec(b, ground=G, include_rp=False, dialect="nec42")
            )
(OUT / "momwire.json").write_text(json.dumps(res, indent=1))
