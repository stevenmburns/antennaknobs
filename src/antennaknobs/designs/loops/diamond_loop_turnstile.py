"""Two diamond loops crossed and fed in phase quadrature (turnstile)."""

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
            "length_factor": 1.0724,
            "angle_deg": 51.4402,
        }
    )

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

        def rx(p):
            return -p[0], p[1], p[2]

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

        tups = [
            Wire(S, A),
            Wire(A, B),
            Wire(B, C),
            Wire(C, T),
            Wire(T, S, ex=1 + 0j),
        ]

        B = (0, 0, eps + b)
        A = (h, 0, eps + b - tan_theta * h)
        S = (eps, 0, eps + b - (2 * h - eps) * tan_theta)
        C, T = rx(A), rx(S)

        tups += [
            Wire(S, A),
            Wire(A, B),
            Wire(B, C),
            Wire(C, T),
            Wire(T, S, ex=1 + 0j),
        ]

        return tups
