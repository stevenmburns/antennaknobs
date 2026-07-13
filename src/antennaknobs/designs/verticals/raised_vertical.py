"""Elevated quarter-wave vertical, fed above ground."""

from antennaknobs import AntennaBuilder

import math
from types import MappingProxyType


class Builder(AntennaBuilder):
    default_params = MappingProxyType(
        {
            "freq": 14.27,
            "length": 5.2245,
            "radial_factor": 0.9545,
            "theta": 110.0,
            "base": 3.0,
        }
    )

    def build_wires(self):
        eps = 0.05

        z = self.length

        n_seg0 = self.nominal_nsegs
        n_seg1 = 1

        tups = []
        tups.extend([((0, 0, 0), (0, 0, eps), n_seg1, 1 + 0j)])
        tups.extend([((0, 0, eps), (0, 0, z), n_seg0, None)])

        # ±45° spread of the two sloping radials
        radial_angle = math.pi / 4

        theta = math.pi / 180 * self.theta

        for phi in [-radial_angle, radial_angle]:
            r = self.length * self.radial_factor

            x = r * math.cos(phi) * math.sin(theta)
            y = r * math.sin(phi) * math.sin(theta)
            rz = r * math.cos(theta)

            tups.extend([((0, 0, 0), (x, y, rz), n_seg0, None)])

        base = self.base
        new_tups = []
        for (x0, y0, z0), (x1, y1, z1), n_seg, ev in tups:
            new_tups.append(((x0, y0, z0 + base), (x1, y1, z1 + base), n_seg, ev))

        return new_tups
