"""AK#1130: at what neighbour-length RATIO does nec2++'s error cross 1 %?

The isolation showed a ~5:1 step at the source costs -8.75 % and a ~1.2:1 step
costs +0.02 %. This walks the ratio to bracket the crossing, which is what a
future advisory would need a threshold from.

The ratio is (adjacent mast segment length) / (source segment length). The mast
is 5.1745 m in 21 segments = 0.2464 m per segment, held fixed; only the gap
length moves, fed as ONE segment.
"""

import warnings

warnings.filterwarnings("ignore")

from antennaknobs.builder import AntennaBuilder  # noqa: E402
from antennaknobs.engines.momwire import MomwireEngine  # noqa: E402
from antennaknobs.engines.pynec import PyNECEngine  # noqa: E402
from antennaknobs.wire_catalog import Wire  # noqa: E402

MAST_TOP, BASE, MAST_SEGS = 8.2245, 3.0, 21
RAD = (3.3135, 3.3135, 1.2944)


class Variant(AntennaBuilder):
    default_params = {"freq": 14.27, "design_freq": 14.27, "gap": 0.05}

    def build_wires(self):
        top = BASE + self.gap
        tups = [
            Wire((0.0, 0.0, BASE), (0.0, 0.0, top), 1, 1 + 0j),
            Wire((0.0, 0.0, top), (0.0, 0.0, MAST_TOP), MAST_SEGS),
        ]
        for s in ((1, -1), (1, 1)):
            tups.append(
                Wire((0.0, 0.0, BASE), (RAD[0] * s[0], RAD[1] * s[1], RAD[2]), 20)
            )
        return tups


print(f"{'gap m':>8s} {'ratio':>7s} {'momwire R':>10s} {'nec2++ R':>10s} {'err %':>8s}")
for gap in (0.05, 0.07, 0.09, 0.11, 0.13, 0.16, 0.20, 0.25):
    b = Variant()
    b.gap = gap
    mast_seg = (MAST_TOP - BASE - gap) / MAST_SEGS
    zm = complex(MomwireEngine(b, ground="pec").impedance()[0])
    zp = complex(PyNECEngine(b, ground="pec").impedance()[0])
    err = 100 * (zp.real / zm.real - 1)
    print(
        f"{gap:8.3f} {mast_seg / gap:7.2f} {zm.real:10.3f} {zp.real:10.3f} {err:+8.2f}"
    )
