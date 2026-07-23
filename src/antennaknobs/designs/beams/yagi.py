"""Yagi-Uda parasitic beam (driven element + reflector + directors)."""

from antennaknobs import AntennaBuilder
from antennaknobs.network import Wire
import math

from types import MappingProxyType


class Builder(AntennaBuilder):
    default_params = MappingProxyType(
        {
            "freq": 28.47,
            "design_freq": 28.47,
            "base": 7.0,
            "length_factor": 0.93,
            "director_factor": 0.95,
            "reflector_factor": 1.05,
            "boom_factor": 0.2,
            "angle_deg": 0.0,
            "n_directors": 2,
        }
    )

    def build_wires(self):
        eps = 0.05
        b = self.base

        wavelength = 299.792458 / self.design_freq

        driver_y = 0.25 * wavelength * self.length_factor
        reflector_y = driver_y * self.reflector_factor
        director_y = driver_y * self.director_factor
        boom_x = wavelength * self.boom_factor

        angle = math.radians(self.angle_deg)
        z_sin = math.sin(angle)
        y_cos = math.cos(angle)

        def ry(p):
            return p[0], -p[1], p[2]

        """
    B                    
    |                    A
    |                    |
    |                    |
    |                    |
    |                    |
    |                    |
    |                    |
    |                    S
    U                    |
    |                    T
    |                    |
    |                    |
    |                    |
    |                    |
    |                    |
    |                    D
    C
    """

        S = (0, eps, b)
        A = (0, eps + (driver_y - eps) * y_cos, b - (driver_y - eps) * z_sin)

        U = (-boom_x, 0, b)
        B = (-boom_x, reflector_y * y_cos, b - reflector_y * z_sin)

        C, D, T = ry(B), ry(A), ry(S)

        tups = [
            Wire(S, A),
            Wire(B, U),
            Wire(U, C),
            Wire(D, T),
            Wire(T, S, ex=1 + 0j),
        ]

        for i in range(self.n_directors):
            U = (boom_x * (1 + i), 0, b)
            B = (boom_x * (1 + i), director_y * y_cos, b - director_y * z_sin)
            C = ry(B)
            tups.extend([Wire(B, U), Wire(U, C)])

        return tups
