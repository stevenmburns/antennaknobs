"""AK#1816: buried_radial_vertical's 5 cm feed-gap wire at 1..k segments.
momwire Z (bs2 at its density, razor-2p at its), and the NEC-5 / NEC-4.2
decks the wrappers write for the same builder, for a black-box run."""

import json
import sys
import time
from pathlib import Path
from antennaknobs.designs.verticals.buried_radial_vertical import Builder as B
from antennaknobs.network import as_wire
from antennaknobs.engines.momwire import MomwireEngine
from antennaknobs.engines.nec5 import NEC5Engine
from antennaknobs.nec_export import export_nec
from antennaknobs import momwire_bases

G = ("finite", 13.0, 0.005)
OUT = Path(sys.argv[1])
OUT.mkdir(parents=True, exist_ok=True)
GAPS = [None, 1, 2, 3, 4, 5, 7]


def make(gap, n):
    class Gap(B):
        def build_wires(self):
            ws = [as_wire(t) for t in super().build_wires()]
            if gap is None:
                return ws
            return [w._replace(n_seg=gap) if w.ex is not None else w for w in ws]

    b = Gap()
    b.nominal_nsegs = n
    return b


_, rcls, rkw = momwire_bases.resolve("razor-2p")
res = {}
for gap in GAPS:
    tag = "auto" if gap is None else str(gap)
    row = {}
    for n in (15, 30):
        t = time.time()
        e = MomwireEngine(make(gap, n), ground=G)
        row[f"bs2@{n}"] = complex(e.impedance()[0])
        print(tag, n, row[f"bs2@{n}"], f"{time.time() - t:.1f}s", flush=True)
    for n in (40,):
        e = MomwireEngine(make(gap, n), solver=rcls, solver_kwargs=dict(rkw), ground=G)
        row[f"razor@{n}"] = complex(e.impedance()[0])
        print(tag, "razor", n, row[f"razor@{n}"], flush=True)
    for n in (40, 80):
        b = make(gap, n)
        (OUT / f"nec5_gap{tag}_n{n}.nec").write_text(
            NEC5Engine(b, ground=G).deck([float(b.freq)])
        )
    for n in (21, 42):
        b = make(gap, n)
        (OUT / f"nec42_gap{tag}_n{n}.nec").write_text(
            export_nec(b, ground=G, include_rp=False, dialect="nec42")
        )
    res[tag] = {k: (str(v) if isinstance(v, complex) else v) for k, v in row.items()}
(OUT / "momwire.json").write_text(json.dumps(res, indent=1))
