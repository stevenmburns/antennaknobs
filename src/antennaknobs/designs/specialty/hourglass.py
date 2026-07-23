"""Hourglass loop — a crossed (bowtie-folded) rectangular loop."""

from antennaknobs import AntennaBuilder
from antennaknobs import Transform, TransformStack
from antennaknobs.network import Wire
from types import MappingProxyType


class Builder(AntennaBuilder):
    default_params = MappingProxyType(
        {
            "design_freq": 28.47,
            "freq": 28.47,
            "base": 10.0,
            "height_factor": 0.9324,
            "width_factor": 0.7030,
            "waist_factor": 0.3669,
        }
    )

    def build_wires(self):
        eps = 0.05
        b = self.base

        wavelength = 299.792458 / self.design_freq

        third = wavelength / 3

        def ry(p):
            return p[0], -p[1], p[2]

        def rz(p):
            return p[0], p[1], -p[2]

        r"""
 C----------------------------A
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
 E----------------------------F
    """

        S = (0, eps, 0)
        B = (0, third / 2 * self.waist_factor, 0)
        A = (0, third / 2 * self.width_factor, third * self.height_factor)

        C, D, T = ry(A), ry(B), ry(S)
        E, F = rz(C), rz(A)

        st = TransformStack()
        st.push(Transform.translate(0, 0, b - A[2]))

        def build_path(lst, ex=None):
            return (
                Wire(st.hit(a), st.hit(b), ex=ex) for a, b in zip(lst[:-1], lst[1:])
            )

        tups = []

        tups.extend(build_path([B, A, C, D]))
        tups.extend(build_path([B, F, E, D]))
        tups.extend(build_path([S, B]))
        tups.extend(build_path([D, T]))
        tups.extend(build_path([T, S], ex=1 + 0j))
        # Uniform-density mesh (issue #521): None counts resolve to the
        # design density automatically (auto_mesh is part of the stack).

        return tups
