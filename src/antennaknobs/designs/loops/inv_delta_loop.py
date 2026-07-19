"""Inverted delta loop — the triangle flipped so the feed edge sits at the top."""

from antennaknobs import AntennaBuilder
import math

from types import MappingProxyType


class Builder(AntennaBuilder):
    default_params = MappingProxyType(
        {
            "design_freq": 28.47,
            "freq": 28.47,
            "base": 7.0,
            "length_factor": 1.0828,
            "angle_deg": 64.6526,
        }
    )

    # Feed-point variants overlay default_params (only the tuning that differs).
    # z100 (100 Ω feed) is the design default; z200 (200 Ω feed) lowers the apex
    # angle and shortens the loop.
    z100_params = default_params
    z200_params = MappingProxyType({"length_factor": 1.0787, "angle_deg": 47.2805})

    def build_wires(self):
        eps = 0.05
        b = self.base

        wavelength = 299.792458 / self.design_freq

        driver = wavelength * self.length_factor

        angle = math.radians(self.angle_deg)
        cos_theta = math.cos(angle)
        tan_theta = math.tan(angle)

        def build_path(lst, ns, ex):
            return ((a, b, ns, ex) for a, b in zip(lst[:-1], lst[1:]))

        def ry(p):
            return p[0], -p[1], p[2]

        n_seg0 = self.nominal_nsegs

        d = driver
        h = (cos_theta * (d - 2 * eps) + 2 * eps) / (2 * (cos_theta + 1))

        """
                T---S
               /     \
              /       \
             /         \
            /           \
           /             \
          /         theta \
         B-----------------A

    """

        S = (0, eps, b)
        A = (0, h, b - (h - eps) * tan_theta)

        B, T = ry(A), ry(S)

        n_seg1 = self.segs_for(math.dist(T, S), math.dist(S, A))

        tups = []

        tups.extend(build_path([S, A, B, T], n_seg0, None))
        tups.extend(build_path([T, S], n_seg1, 1 + 0j))

        return tups
