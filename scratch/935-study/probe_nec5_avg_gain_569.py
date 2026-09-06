"""momwire#569, for Skylake-builder: is NEC-5's radiated fraction converged?

#569 pairs NEC-5's 15.3 % against momwire's 16.7 % and calls the comparison
"suggestive only" because the two come from different quadratures. The momwire
side has since been made quadrature-independent (16.99 %, stable to ~0.02 pp),
so the remaining question is whether NEC-5's own number moves with ITS
integration density. If it does not, the gap is physics rather than quadrature.

Same deck as `tests/fixtures/nec5/brv_connected_minus1.nec` -- the connected
buried-radial screen -- rebuilt through the engine because that fixture is
impedance-only and this needs an RP block.
"""

import math

from antennaknobs.designs.verticals.buried_radial_vertical import (
    Builder as BuriedRadialVertical,
)
from antennaknobs.engines.nec5 import NEC5Engine

SOIL = ("finite", 13.0, 0.005)

b = BuriedRadialVertical()
eng = NEC5Engine(b, ground=SOIL)

z = eng.impedance()
print(f"deck control: Z = {z}")
print(f"freq = {b.freq}, soil = {SOIL}\n")

print(f"{'grid':>12s}  {'avg power gain':>16s}  {'Omega/pi':>10s}  {'radiated':>10s}")
for nt, np_ in ((18, 36), (45, 90), (90, 360), (180, 720)):
    avg, omega = eng.average_power_gain(n_theta=nt, n_phi=np_)
    frac = avg * omega / (4.0 * math.pi)
    print(
        f"{nt:5d} x {np_:4d}  {avg:16.6f}  {omega / math.pi:10.4f}  {100 * frac:9.3f} %"
    )

# Measured 2026-09-06, NEC-5 (LLNL-CODE-746721) on this box. Quoted in
# stevenmburns/momwire#569 (Skylake-builder's comment 5557735738):
#
#   deck control: Z = 77.805 + 44.468j   (momwire reads 75.8482 + 40.4523j)
#
#          grid    avg power gain    Omega/pi    radiated
#     18 x   36          0.328991      1.8578    15.280 %
#     45 x   90          0.321617      1.9430    15.623 %
#     90 x  360          0.318878      1.9770    15.761 %
#    180 x  720          0.317490      1.9885    15.783 %
#
# The fourth rung is why the conclusion is what it is: steps of +0.343,
# +0.138, +0.022 put the limit at ~15.79 %, so NEC-5's published 15.3 % was
# its own coarse rung and the like-for-like gap NARROWS to ~1.2 pp rather
# than widening to 1.7. momwire's 16.7 % turned out to be the coarse end of
# ITS ladder too (16.7025 % at 18x36), independently, in both codes.
#
# Omega/pi converges to 1.9885 rather than 2 -- the RP block samples cell
# CENTRES from del_theta/2, so it never quite covers the hemisphere. I
# flagged that as a possible common-solid-angle correction; Skylake measured
# it and it does not survive: over lossy 13/0.005 the pattern peaks at 26 deg
# elevation and collapses toward grazing, so the missing wedge carries
# 0.025 % of the radiated total = 0.0042 pp against a 1.2 pp gap. The
# instinct would have been right over PEC ground, where the horizon IS the
# peak. Recorded because the wrong half is the instructive half.
