"""momwire#865 probe 3: does the buried-side refusal band scale with LENGTH?

The below/below refusal names a pair elevation theta against a 0.1 deg grazing
floor. If theta ~ atan(2h/L) then the band is h >= L*tan(0.1deg)/2, i.e.
proportional to the wire's length -- and the surface-radial class #865 exists
for uses LONG radials, so the buried side would be refused centimetres down,
not micrometres. That would be a scoping fact, not a detail.

Prediction to falsify: h_min = L * tan(0.1 deg) / 2 = L * 8.727e-4.
"""

import math

from antennaknobs import AntennaBuilder
from antennaknobs.engines.momwire import MomwireEngine
from antennaknobs.wire_catalog import Wire

RAD, FREQ = 5.0e-4, 7.1
SOIL = ("finite", 13.0, 0.005)


class Dip(AntennaBuilder):
    default_params = {
        "freq": FREQ,
        "design_freq": FREQ,
        "z": -0.01,
        "half": 2.9557,
        "wire_radius": RAD,
    }

    def build_wires(self):
        z, h, g = self.z, self.half, 0.025
        return [
            Wire((-h, 0.0, z), (-g, 0.0, z), 25),
            Wire((-g, 0.0, z), (g, 0.0, z), 2, ex=1 + 0j),
            Wire((g, 0.0, z), (h, 0.0, z), 25),
        ]


def deepest_refused(half):
    """Bisect for the shallowest depth momwire will serve."""
    lo, hi = 1e-5, 1.0  # lo refused, hi served
    for _ in range(28):
        mid = math.sqrt(lo * hi)
        b = Dip()
        b.half, b.z = half, -mid
        try:
            MomwireEngine(b, ground=SOIL).impedance()
            hi = mid
        except Exception:  # noqa: BLE001
            lo = mid
    return hi


print(
    f"{'half (m)':>9s} {'L=2*half':>9s} {'h_min meas':>12s} {'predicted':>11s} {'ratio':>7s}"
)
for half in (1.0, 2.9557, 6.0, 12.0):
    L = 2 * half
    meas = deepest_refused(half)
    pred = L * math.tan(math.radians(0.1)) / 2
    print(
        f"{half:9.3f} {L:9.3f} {meas * 1000:9.3f} mm {pred * 1000:8.3f} mm {meas / pred:7.3f}"
    )
