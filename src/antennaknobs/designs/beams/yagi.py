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
            # Every element built on the same core: a centre wire of +-eps and
            # arms out to the director's half-length, the driver and reflector
            # reaching their own lengths through extension wires. Equal wires
            # mesh equally, and the elements sit at equal boom spacing, so the
            # pairs between any two elements repeat and pair_reuse copies them.
            "uniform_cores": False,
        }
    )

    def build_wires(self):
        eps = 0.05
        b = self.base

        wavelength = self.design_wavelength

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

        if self.uniform_cores:
            return self._uniform_core_wires(
                b, eps, driver_y, reflector_y, director_y, boom_x, y_cos, z_sin
            )

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

    def _uniform_core_wires(
        self, b, eps, driver_y, reflector_y, director_y, boom_x, y_cos, z_sin
    ):
        """Each element: centre wire (-eps, eps), core arms (eps, director_y)
        on both sides, then extension arms out to the element's own half
        length. The driver is fed on its centre wire.

        Every element bends at +-eps, as the default driver does, so all
        cores are congruent. At angle_deg != 0 the reflector and directors
        therefore droop from +-eps rather than from the boom, which moves
        their tips out by eps * (1 - cos(angle)) and up by eps * sin(angle)
        at the same wire length; flat, they are the default layout's
        elements exactly."""

        def at(x, t):
            # t is the distance along the element from its centre.
            if abs(t) <= eps:
                return (x, t, b)
            r = abs(t) - eps
            return (x, math.copysign(eps + r * y_cos, t), b - r * z_sin)

        def element(x, half, ex=None):
            wires = [
                Wire(at(x, -eps), at(x, eps), **({"ex": ex} if ex is not None else {})),
                Wire(at(x, eps), at(x, director_y)),
                Wire(at(x, -director_y), at(x, -eps)),
            ]
            if half > director_y:
                wires += [
                    Wire(at(x, director_y), at(x, half)),
                    Wire(at(x, -half), at(x, -director_y)),
                ]
            return wires

        tups = element(0.0, driver_y, ex=1 + 0j)
        tups += element(-boom_x, reflector_y)
        for i in range(self.n_directors):
            tups += element(boom_x * (1 + i), director_y)
        return tups
