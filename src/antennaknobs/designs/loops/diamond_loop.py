"""Full-wave diamond (square) loop fed at the bottom corner."""

from antennaknobs import AntennaBuilder
from antennaknobs.network import Wire
import math

from types import MappingProxyType


class Builder(AntennaBuilder):
    default_params = MappingProxyType(
        {
            "design_freq": 28.47,
            "freq": 28.47,
            "base": 7.0,
            "length_factor": 1.0703,
            "angle_deg": 30.8767,
            # Cover both feed variants: the z100 apex angle (51.5°) sits
            # above the auto ±50% window around the z200 default (≤46.3°).
            "ui_params": MappingProxyType({"angle_deg": {"min": 15.0, "max": 60.0}}),
        }
    )

    # Feed-point variants overlay default_params (only the tuning that differs).
    # z200 (200 Ω feed) is the design default; z100 (100 Ω feed) raises the apex
    # angle.
    z100_params = MappingProxyType({"length_factor": 1.0724, "angle_deg": 51.4573})
    z200_params = default_params

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
        # Apex height, solved from the constraint that the total wire perimeter
        # equals the driver length d.
        h = d * cos_theta / 4 - eps * cos_theta / 2 + eps / 2

        r"""
                  B 
                 / \
                /   \
               /     \
              /       \
             /         \
            /           \
           /             \
          /         theta \
         C           ------A
          \         theta /
           \             /
            \           /
             \         /
              \       /
               \     /
                T---S
    """

        B = (0, 0, b)
        A = (0, h, b - tan_theta * h)
        S = (0, eps, b - (2 * h - eps) * tan_theta)

        C, T = ry(A), ry(S)

        return [
            Wire(S, A),
            Wire(A, B),
            Wire(B, C),
            Wire(C, T),
            Wire(T, S, ex=1 + 0j),
        ]
