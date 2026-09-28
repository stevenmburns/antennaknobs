"""Off-Center-Fed dipole (Windom): a half-wave fed away from the middle
(L. B. Cebik, W4RNL).

A resonant half-wave wire fed at the centre shows ~70 ohm. As the feedpoint
slides toward one end the resistive impedance climbs smoothly -- ~100 ohm part
way out, ~200 ohm near the one-third point, ~300 ohm and up further still --
while staying essentially resistive at resonance. The OCF (the modern,
two-wire-feed descendant of the 1929 single-wire Windom) exploits that: feeding
about a THIRD of the way from one end lands near 200-300 ohm, a 4:1 or 6:1
balun step from coax, and -- because the same off-centre point is also near a
current loop on several harmonics -- gives a multiband doublet.

This fills the "off-centre feed" gap: every other dipole in the catalog
(invvee, fan, trap, folded) is centre-fed. The defining, testable physics here
is the feedpoint impedance's dependence on feed POSITION, not the (ordinary
dipole) pattern.

Geometry, in the framework's (x, y, z) convention:
  - y : the wire axis; total length ~half-wave, the feed offset toward -y
  - x, z : the wire sits at x = 0, z = base
  - HORIZONTALLY POLARISED, ordinary dipole figure-8 broadside off +/- x.

    o------------F=================================o      z = base
    |<-- ~1/3 -->|<------------- ~2/3 ------------->|
"""

from antennaknobs import AntennaBuilder
from antennaknobs.network import Driven, Network, PortOnWire, Wire
from types import MappingProxyType


class Builder(AntennaBuilder):
    default_params = MappingProxyType(
        {
            "design_freq": 28.57,
            "freq": 28.57,
            "base": 7.0,
            # Total wire length as a fraction of a wavelength (~resonant
            # half-wave; slightly short for end effects).
            "length_frac": 0.485,
            # Feed position as a fraction of the total length measured from the
            # near (-y) end. ~0.18 (just under a fifth of the way in) lands near
            # the classic ~200 ohm Windom point on a thin free-space wire; the
            # textbook "one-third from the end" is nearer 100 ohm here.
            "feed_frac": 0.18,
            "ui_params": MappingProxyType(
                {
                    # OCF feed is high-ish; reference SWR to a 4:1-balun 200 ohm.
                    "target_z0": 200.0,
                    "default_view": "xy",
                    "length_frac": {
                        "min": 0.44,
                        "max": 0.52,
                    },
                    "feed_frac": {
                        "min": 0.1,
                        "max": 0.5,
                    },
                }
            ),
        }
    )

    def build_wires(self):
        wavelength = self.design_wavelength

        length = self.length_frac * wavelength
        z = self.base

        # One continuous wire, y = -length/2 .. +length/2. The feed is not a
        # wire of its own: `build_network` places it `feed_frac` of the way
        # along from the -y end (AK#1767), so no short gap wire changes its
        # segment count as the mesh refines.
        return [Wire((0.0, -length / 2, z), (0.0, length / 2, z), name="feed")]

    def build_network(self):
        return Network(
            ports={"feed": PortOnWire("feed", at=self.feed_frac)},
            sources=[Driven(port="feed", voltage=1 + 0j)],
        )
