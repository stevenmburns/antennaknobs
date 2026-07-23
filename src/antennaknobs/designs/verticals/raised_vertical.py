"""Elevated quarter-wave vertical, fed above ground."""

from antennaknobs import AntennaBuilder
from antennaknobs.network import Wire

import math
from types import MappingProxyType


class Builder(AntennaBuilder):
    default_params = MappingProxyType(
        {
            "freq": 14.27,
            # Geometry is hand-tuned in absolute metres; design_freq only
            # anchors auto_mesh's density scale (nominal_nsegs per
            # quarter-wave), so it is hidden from the UI.
            "design_freq": 14.27,
            "length": 5.2245,
            "radial_factor": 0.9545,
            "theta": 110.0,
            "base": 3.0,
            "ui_params": MappingProxyType({"design_freq": {"hidden": True}}),
        }
    )

    def build_wires(self):
        eps = 0.05

        z = self.length
        base = self.base

        tups = []
        # Driven gap at the riser foot; the riser stacks on top of it.
        tups.append(Wire((0, 0, base), (0, 0, base + eps), ex=1 + 0j))
        tups.append(Wire((0, 0, base + eps), (0, 0, base + z)))

        # ±45° spread of the two sloping radials
        radial_angle = math.pi / 4

        theta = math.pi / 180 * self.theta

        for phi in [-radial_angle, radial_angle]:
            r = self.length * self.radial_factor

            x = r * math.cos(phi) * math.sin(theta)
            y = r * math.sin(phi) * math.sin(theta)
            rz = r * math.cos(theta)

            tups.append(Wire((0, 0, base), (x, y, rz + base)))

        return tups
