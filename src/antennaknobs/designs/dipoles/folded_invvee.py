"""Folded inverted-vee — the folded dipole's impedance step-up, with drooped arms."""

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

        def ry(p):
            return p[0], -p[1], p[2]

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

        # Auto-mesh gives every wire the same segment length, which is
        # exactly what this geometry needs: the two parallel conductors
        # (S-A / B-s and t-C / D-T) stay density-matched, and the short
        # facing link s-t and feed T-S get a proportionally small count
        # instead of the full nominal one. The latter matters — a full
        # nominal count on the 0.1 m link drives its segment length below
        # the wire RADIUS at fine meshes (N=321: 0.31 mm segs on a
        # 0.5 mm-radius wire, Δ/a = 0.62), the classic reduced-kernel
        # ill-posedness, which the folded element's stub antiresonance
        # amplifies into a wildly wrong sin/pynec impedance (issue #484:
        # 280−1188j at N=321; proportional density holds the ladder flat
        # at 223−30j through N=641).
        return [
            Wire(S, A),
            Wire(A, B),
            Wire(B, s),
            Wire(s, t),
            Wire(t, C),
            Wire(C, D),
            Wire(D, T),
            Wire(T, S, ex=1 + 0j),
        ]
