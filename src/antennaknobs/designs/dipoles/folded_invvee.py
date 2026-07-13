"""Folded inverted-vee — the folded dipole's impedance step-up, with drooped arms."""

from antennaknobs import AntennaBuilder
import math

from types import MappingProxyType


class Builder(AntennaBuilder):
    default_params = MappingProxyType(
        {
            "design_freq": 28.47,
            "freq": 28.47,
            "base": 7.0,
            "length_factor": 0.955,
            "angle_deg": 31.0772,
            "space": 0.05,
        }
    )

    def build_wires(self):
        eps = 0.05
        b = self.base

        wavelength = 299.792458 / self.design_freq

        driver_y = 0.25 * wavelength * self.length_factor

        angle = math.radians(self.angle_deg)
        z_sin = math.sin(angle)
        y_cos = math.cos(angle)

        def build_path(lst, ns, ex):
            return ((a, b, ns, ex) for a, b in zip(lst[:-1], lst[1:]))

        def ry(p):
            return p[0], -p[1], p[2]

        n_seg0 = self.nominal_nsegs
        n_seg1 = max(3, self.nominal_nsegs // 7)

        """
                    
                B---A
                |   |
                |   |
                |   |
                |   |
                |   |
                |   |
                |   |
                s   S
                |   |
                t   T
                |   |
                |   |
                |   |
                |   |
                |   |
                |   |
                |   |
                C---D

    """

        S = (0, eps, b)
        s = (self.space, eps, b)
        A = (0, eps + (driver_y - eps) * y_cos, b - (driver_y - eps) * z_sin)
        B = (self.space, eps + (driver_y - eps) * y_cos, b - (driver_y - eps) * z_sin)

        D, T, C, t = ry(A), ry(S), ry(B), ry(s)

        tups = []

        tups.extend(build_path([S, A], n_seg0, None))
        tups.extend(build_path([A, B], n_seg1, None))
        tups.extend(build_path([B, s], n_seg0, None))
        tups.extend(build_path([s, t], n_seg0, None))
        tups.extend(build_path([t, C], n_seg0, None))
        tups.extend(build_path([C, D], n_seg1, None))
        tups.extend(build_path([D, T], n_seg0, None))
        tups.extend(build_path([T, S], n_seg1, 1 + 0j))

        return tups
