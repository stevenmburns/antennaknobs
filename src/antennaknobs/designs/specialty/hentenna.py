"""Hentenna — the Japanese rectangular loop, fed off-center for vertical polarization."""

from antennaknobs import AntennaBuilder
from antennaknobs import Transform, TransformStack
from types import MappingProxyType


class Builder(AntennaBuilder):
    # z100 (100 Ω feed) overlays default_params (= z50, the 50 Ω tuning);
    # it states only the shape factors that differ.
    z100_params = MappingProxyType(
        {
            "top_height_factor": 0.4589,
            "mid_height_factor": 0.0962,
            "width_factor": 0.1841,
        }
    )

    z50_params = MappingProxyType(
        {
            "design_freq": 28.47,
            "freq": 28.47,
            "base": 10.0,
            "top_height_factor": 0.5081,
            "mid_height_factor": 0.1094,
            "width_factor": 0.1378,
        }
    )

    default_params = z50_params

    def build_wires(self):
        b = self.base

        wavelength = self.design_wavelength

        def ry(p):
            return p[0], -p[1], p[2]

        """
 C----------------------------A
 |                            |
 |                            |
 |                            |
 |                            |
 |                            |
 |                            |
 |                            |
 D-------------ex-------------B
 |                            |
 |                            |
 |                            |
 |                            |
 E----------------------------F
    """

        B = (
            0,
            wavelength * self.width_factor / 2,
            wavelength * (self.mid_height_factor - self.top_height_factor),
        )
        A = (0, wavelength * self.width_factor / 2, 0)
        F = (
            0,
            wavelength * self.width_factor / 2,
            wavelength * (-self.top_height_factor),
        )

        C, D = ry(A), ry(B)
        E = ry(F)

        st = TransformStack()
        st.push(Transform.translate(0, 0, b))

        st.path([B, A, C, D])
        st.path([B, F, E, D])
        # The feed is the middle of ONE wire D-B (AK#1767): a separate short
        # gap wire's segment count stepped the impedance as the mesh refined.
        st.path([D, B], ex=1 + 0j)
        # Uniform-density mesh (issue #521): None counts resolve to the
        # design density automatically (auto_mesh is part of the stack).

        return st.wires
