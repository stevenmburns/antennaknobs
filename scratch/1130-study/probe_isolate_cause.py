"""AK#1130 step 6: WHICH feature of the deck does nec2++ mis-solve?

The issue's deck differs from a clean dipole in two ways at once: the source
sits on a ONE-SEGMENT 5 cm gap (lambda/420), and that gap's lower end is a
4-way junction (two radials, the mast, the gap). Vary each separately.
"""

import warnings


warnings.filterwarnings("ignore")

from antennaknobs.builder import AntennaBuilder  # noqa: E402
from antennaknobs.engines.momwire import MomwireEngine  # noqa: E402
from antennaknobs.engines.pynec import PyNECEngine  # noqa: E402
from antennaknobs.wire_catalog import Wire  # noqa: E402

MAST_TOP, BASE = 8.2245, 3.0
RAD = (3.3135, 3.3135, 1.2944)


class Variant(AntennaBuilder):
    default_params = {
        "freq": 14.27,
        "design_freq": 14.27,
        "gap": 0.05,
        "gap_segs": 1,
        "radials": 2,
    }

    def build_wires(self):
        top = BASE + self.gap
        tups = [
            Wire((0.0, 0.0, BASE), (0.0, 0.0, top), int(self.gap_segs), 1 + 0j),
            Wire((0.0, 0.0, top), (0.0, 0.0, MAST_TOP), 21),
        ]
        for s in ((1, -1), (1, 1))[: int(self.radials)]:
            tups.append(
                Wire((0.0, 0.0, BASE), (RAD[0] * s[0], RAD[1] * s[1], RAD[2]), 20)
            )
        return tups


def row(label, **over):
    b = Variant()
    for k, v in over.items():
        setattr(b, k, v)
    zs = {}
    for name, cls in (("momwire", MomwireEngine), ("nec2++", PyNECEngine)):
        zs[name] = complex(cls(b, ground="pec").impedance()[0])
    d = 100 * (zs["nec2++"].real / zs["momwire"].real - 1)
    print(
        f"  {label:34s} momwire R {zs['momwire'].real:7.3f}   "
        f"nec2++ R {zs['nec2++'].real:7.3f}   {d:+6.2f} %"
    )


print("baseline (the issue's deck): gap 5 cm, 1 segment, 2 radials")
row("gap 0.05 m, 1 seg, 2 radials", gap=0.05, gap_segs=1, radials=2)
print("\nvary the GAP SEGMENTATION (geometry fixed):")
for n in (1, 3, 5, 9):
    row(f"gap 0.05 m, {n} seg, 2 radials", gap=0.05, gap_segs=n, radials=2)
print("\nvary the GAP LENGTH (1 segment):")
for g in (0.05, 0.2, 0.5, 1.0):
    row(f"gap {g} m, 1 seg, 2 radials", gap=g, gap_segs=1, radials=2)
print("\nremove the JUNCTION (no radials), keep the 1-segment 5 cm gap:")
row("gap 0.05 m, 1 seg, 0 radials", gap=0.05, gap_segs=1, radials=0)
