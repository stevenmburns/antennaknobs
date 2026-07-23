"""Hourglass loop tilted out of the vertical plane."""

import math

from antennaknobs import AntennaBuilder
from antennaknobs import Transform, TransformStack

from types import MappingProxyType


class Builder(AntennaBuilder):
    default_params = MappingProxyType(
        {
            "design_freq": 28.47,
            "freq": 28.47,
            "base": 10.0,
            "height_factor": 0.8867,
            "width_factor": 0.7326,
            "waist_factor": 0.4198,
            "slant_deg": 30.0,
        }
    )

    def build_wires(self):
        eps = 0.05
        b = self.base

        wavelength = 299.792458 / self.design_freq

        third = wavelength / 3

        def ry(p):
            return p[0], -p[1], p[2]

        slant_radians = math.radians(self.slant_deg)
        slant_cos = math.cos(slant_radians)
        slant_sin = math.sin(slant_radians)

        r"""
    Add an invvee like slant, 0 degrees is horizontal

 C-------------AA-------------A
  \                          /
   \                        /
    \                      /
     \                    /
      \                  /
       D------T--S------B
      /                  \ 
     /                    \
    /                      \
   /                        \
  /                          \
 E-------------FF-------------F
    """

        S = (0, eps, 0)
        B = (
            0,
            third / 2 * self.waist_factor * slant_cos,
            -third / 2 * self.waist_factor * slant_sin,
        )
        AA = (0, 0, third * self.height_factor)
        A = (
            0,
            third / 2 * self.width_factor * slant_cos,
            third * self.height_factor - third / 2 * self.width_factor * slant_sin,
        )

        FF = (0, 0, -third * self.height_factor)
        F = (
            0,
            third / 2 * self.width_factor * slant_cos,
            -third * self.height_factor - third / 2 * self.width_factor * slant_sin,
        )

        C, D, T, E = ry(A), ry(B), ry(S), ry(F)

        st = TransformStack()
        st.push(Transform.translate(0, 0, b - AA[2]))

        def build_path(lst, ns, ex):
            return ((st.hit(a), st.hit(b), ns, ex) for a, b in zip(lst[:-1], lst[1:]))

        tups = []

        tups.extend(build_path([B, A, AA, C, D], None, None))
        tups.extend(build_path([B, F, FF, E, D], None, None))
        tups.extend(build_path([S, B], None, None))
        tups.extend(build_path([D, T], None, None))
        tups.extend(build_path([T, S], None, 1 + 0j))
        # Uniform-density mesh (issue #521): the old per-edge nominal
        # count over-densified the short edges 4-6x; the longest edge now
        # carries nominal_nsegs and every wire meshes at its density.
        tups = self.auto_mesh(tups)

        return tups
