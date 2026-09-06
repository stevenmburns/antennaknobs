"""AK#1130 step 4: the two engines disagree on R by 9.6 % -- who is right?

Step 3 showed the patterns are the same SHAPE, one scalar apart, and that the
scalar IS the R ratio: each engine normalises its own field by its own input
power. So the fraction above unity is not a pattern bug; it is that nec2++'s R
is too small for the field it reports.

9.6 % is large for a raised vertical over PEC. Before blaming either solver's
physics, check they are solving the same antenna: same wires, same segment
counts, same feed. Then ask NEC-5 for a third reading.
"""

import warnings

import numpy as np

warnings.filterwarnings("ignore")

from antennaknobs.designs.verticals.raised_vertical import Builder  # noqa: E402
from antennaknobs.engines.momwire import MomwireEngine  # noqa: E402
from antennaknobs.engines.nec5 import NEC5Engine  # noqa: E402
from antennaknobs.engines.pynec import PyNECEngine  # noqa: E402

b = Builder()
tups = b.build_wires()
print("deck as the builder emits it:")
for i, t in enumerate(tups):
    n = t[2]
    print(
        f"  wire {i}: {np.round(np.asarray(t[0]), 4)} -> "
        f"{np.round(np.asarray(t[1]), 4)}  n_seg={n}  ex={t[3]}"
    )
print(f"  freq {b.freq} MHz")

print("\nimpedance by engine, ground = pec:")
for name, cls in (
    ("momwire", MomwireEngine),
    ("nec2++", PyNECEngine),
    ("NEC-5", NEC5Engine),
):
    try:
        z = complex(cls(b, ground="pec").impedance()[0])
        print(f"  {name:8s} {z.real:9.4f}{z.imag:+9.4f}j")
    except Exception as e:  # noqa: BLE001 - a probe; the reason is printed
        print(f"  {name:8s} {type(e).__name__}: {str(e)[:70]}")
