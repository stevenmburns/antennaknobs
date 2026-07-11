"""Hentenna — the Japanese rectangular loop, fed off-center for vertical polarization."""

from ... import AntennaBuilder
from ... import Transform, TransformStack

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
        eps = 0.05
        b = self.base

        wavelength = 299.792458 / self.design_freq

        def ry(p):
            return p[0], -p[1], p[2]

        n_seg0 = self.nominal_nsegs
        n_seg1 = max(3, self.nominal_nsegs // 7)

        """
 C----------------------------A
 |                            |
 |                            |
 |                            |
 |                            |
 |                            |
 |                            |
 |                            |
 D------------T--S------------B
 |                            |
 |                            |
 |                            |
 |                            |
 E----------------------------F
    """

        S = (0, eps, wavelength * (self.mid_height_factor - self.top_height_factor))
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

        C, D, T = ry(A), ry(B), ry(S)
        E = ry(F)

        st = TransformStack()
        st.push(Transform.translate(0, 0, b))

        def build_path(lst, ns, ex):
            return ((st.hit(a), st.hit(b), ns, ex) for a, b in zip(lst[:-1], lst[1:]))

        tups = []

        tups.extend(build_path([B, A, C, D], n_seg0, None))
        tups.extend(build_path([B, F, E, D], n_seg0, None))
        tups.extend(build_path([S, B], n_seg0, None))
        tups.extend(build_path([D, T], n_seg0, None))
        tups.extend(build_path([T, S], n_seg1, 1 + 0j))

        return tups
