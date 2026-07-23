"""Resonant V-beam: two long wires splayed into a V (L. B. Cebik, W4RNL).

A single long wire (1 wavelength or more) is not broadside like a dipole -- its
main lobes swing toward the wire's own axis, making a shallow cone a fixed
angle off the wire. Put two such long wires together at an apex, opening them by
twice that angle, and the forward lobes of the two legs line up along the
bisector and ADD: a bidirectional beam off both ends of the V's centreline,
HORIZONTALLY POLARISED, with more gain than a dipole for the wire used. It is
the standing-wave (resonant, un-terminated) sibling of the terminated rhombic
-- which is just two V-beams placed nose to nose with a load.

This fills the "resonant long-wire array" gap directly alongside the existing
terminated `rhombic`: same wire family, but bidirectional (no termination, no
DC path to burn the back lobe).

Cebik / long-wire theory: for ~1 wl legs the lobe sits ~36 degrees off each
wire, so the included apex angle is ~2 * 36 = ~72 degrees (each leg ~36 degrees
off the bisector). Longer legs want a narrower apex and give more gain.

Geometry, in the framework's (x, y, z) convention:
  - x : the bisector / firing axis; the apex sits at -x, the legs open toward
        +x, and the beam fires bidirectionally off +/- x
  - y : the two legs splay symmetrically to +/- y
  - z : constant height `base` (the V lies in a horizontal plane)

              o  (leg end, +y)
             /
        F===<            apex feed at -x, opening toward +x
             \\
              o  (leg end, -y)        beam <--> +/- x (along the bisector)
"""

from antennaknobs import AntennaBuilder
from antennaknobs.network import Wire
from types import MappingProxyType
import math


class Builder(AntennaBuilder):
    default_params = MappingProxyType(
        {
            "design_freq": 28.57,
            "freq": 28.57,
            "base": 7.0,
            # Leg length as a fraction of a wavelength (each wire). Longer ->
            # more gain, narrower apex.
            "leg_frac": 1.0,
            # Half the included apex angle, in degrees: each leg sits this far
            # off the bisector. ~36 deg suits ~1 wl legs.
            "half_apex_deg": 36.0,
            "ui_params": MappingProxyType(
                {
                    # Long-wire apex feed is high and reactive; open-wire fed.
                    "target_z0": 300.0,
                    # Legs splay in x/y -> the xy view is face-on.
                    "default_view": "xy",
                    "leg_frac": {
                        "min": 0.75,
                        "max": 2.0,
                    },
                    "half_apex_deg": {
                        "min": 20.0,
                        "max": 55.0,
                        "step": 0.1,
                        "precision": 2,
                    },
                }
            ),
        }
    )

    def build_wires(self):
        eps = 0.05
        wavelength = 299.792458 / self.design_freq

        leg = self.leg_frac * wavelength
        theta = math.radians(self.half_apex_deg)
        dx = math.cos(theta)
        dy = math.sin(theta)
        z = self.base

        # Apex near the origin, legs opening toward +x at +/- theta off the
        # bisector. A driven gap bridges the two inner ends.
        inner_p = (eps * dx, eps * dy, z)  # toward +y leg
        inner_m = (eps * dx, -eps * dy, z)  # toward -y leg
        end_p = (leg * dx, leg * dy, z)
        end_m = (leg * dx, -leg * dy, z)

        return [
            # Driven gap across the apex between the two legs' inner ends.
            Wire(inner_m, inner_p, ex=1 + 0j),
            Wire(inner_p, end_p),  # +y leg
            Wire(inner_m, end_m),  # -y leg
        ]
