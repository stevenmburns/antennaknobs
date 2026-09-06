"""AK#1130 step 3: is the excess a CONSTANT factor or a shape difference?

If nec2++'s gain differs from momwire's by one factor everywhere, the excess is
a normalisation constant -- and then the only question is which P_in it came
from. If the two patterns differ in SHAPE, the engines disagree about physics
and no normalisation fix is available.
"""

import warnings

import numpy as np

warnings.filterwarnings("ignore")

from antennaknobs.designs.verticals.raised_vertical import Builder  # noqa: E402
from antennaknobs.engines.momwire import MomwireEngine  # noqa: E402
from antennaknobs.engines.pynec import PyNECEngine  # noqa: E402

pats = {}
for name, cls in (("momwire", MomwireEngine), ("nec2++", PyNECEngine)):
    eng = cls(Builder(), ground="pec")
    z = complex(eng.impedance()[0])
    ff = eng.far_field()
    pats[name] = (np.asarray(ff.rings, dtype=float), z)

gm, zm = pats["momwire"]
gp, zp = pats["nec2++"]
print(f"grid shapes: momwire {gm.shape}  nec2++ {gp.shape}")

# gains are dBi; compare in LINEAR terms
lm, lp = 10 ** (gm / 10.0), 10 ** (gp / 10.0)
ratio = lp / np.maximum(lm, 1e-300)
print(
    f"linear gain ratio nec2++/momwire: min {ratio.min():.5f}  "
    f"max {ratio.max():.5f}  mean {ratio.mean():.5f}  sd {ratio.std():.2e}"
)
print(f"R ratio momwire/nec2++ = {zm.real / zp.real:.5f}")
print()
print("ratio by theta ring (theta = row index, degrees from zenith):")
for i in (0, 15, 30, 45, 60, 75, 85, 88, 89):
    print(
        f"  theta {i:3d}  ratio {ratio[i].mean():.5f}   "
        f"momwire {gm[i].mean():8.3f} dBi   nec2++ {gp[i].mean():8.3f} dBi"
    )
