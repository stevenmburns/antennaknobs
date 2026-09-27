"""Hourglass loop — a crossed (bowtie-folded) rectangular loop."""

import itertools
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
        b = self.base

        wavelength = self.design_wavelength

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
       D------ex-------B
      /                  \ 
     /                    \
    /                      \
   /                        \
  /                          \
 E----------------------------F
    """

        B = (0, third / 2 * self.waist_factor, 0)
        A = (0, third / 2 * self.width_factor, third * self.height_factor)

        C, D = ry(A), ry(B)
        E, F = rz(C), rz(A)

        st = TransformStack()
        st.push(Transform.translate(0, 0, b - A[2]))

        def build_path(lst, ex=None):
            return (
                Wire(st.hit(a), st.hit(b), ex=ex) for a, b in itertools.pairwise(lst)
            )

        tups = []

        tups.extend(build_path([B, A, C, D]))
        tups.extend(build_path([B, F, E, D]))
        # The feed is the middle of ONE wire D-B (AK#1767): a separate short
        # gap wire's segment count stepped the impedance as the mesh refined.
        tups.extend(build_path([D, B], ex=1 + 0j))
        # Uniform-density mesh (issue #521): None counts resolve to the
        # design density automatically (auto_mesh is part of the stack).

        return tups
