"""Corner-fed full-wave delta loop; corner coordinates from a closed-form expression for the top corner."""

import math
from types import MappingProxyType

from antennaknobs import AntennaBuilder
from antennaknobs.network import Wire


class Builder(AntennaBuilder):
    default_params = MappingProxyType(
        {
            "design_freq": 28.47,
            "freq": 28.47,
            "base": 7.0,
            "length_factor": 1.0800,
            "angle_deg": 62.3894,
        }
    )

    # Feed-point variants overlay default_params (only the tuning that differs).
    # z100 (100 Ω feed) is the design default; z200 (200 Ω feed) lowers the apex
    # angle and shortens the loop.
    z100_params = default_params
    z200_params = MappingProxyType({"length_factor": 1.0650, "angle_deg": 43.9516})

    def build_wires(self):
        eps = 0.05
        b = self.base

        wavelength = 299.792458 / self.design_freq

        driver = wavelength * self.length_factor

        angle = math.radians(self.angle_deg)
        cos_theta = math.cos(angle)
        tan_theta = math.tan(angle)

        def ry(p):
            return p[0], -p[1], p[2]

        d = driver
        # y of the top corner (half the top-edge width), in closed form from the
        # total wire length d -- no numerical solve, unlike the drone builds.
        y = (cos_theta * (d - 2 * eps) + 2 * eps) / (2 * (cos_theta + 1))

        r"""
         B-----------------A
          \         theta /
           \             /
            \           /
             \         /
              \       /
               \     /
                T---S
    """

        S = (0, eps, b - (y - eps) * tan_theta)
        A = (0, y, b)

        B, T = ry(A), ry(S)

        return [
            Wire(S, A),
            Wire(A, B),
            Wire(B, T),
            Wire(T, S, ex=1 + 0j),
        ]
