"""A delta loop built the most direct way: pick a *side length* and a *slant
angle*, then write the corner coordinates down outright.

``delta_loop`` sizes the triangle from a perimeter ``length_factor`` and then
solves a closed-form apex-height formula
``h = (cos·(d-2eps)+2eps)/(2(cos+1))`` for the corners -- the "scary trig" that
makes it a poor first example. This version drops the total-wire-length knob
entirely. Give the slant its length ``side`` and its tilt ``angle_deg`` from
horizontal, and each top corner is just the feed terminal plus one flown slant::

    A = (0, eps + side·cos θ, feed_height + side·sin θ)   # right top corner

Two ``cos``/``sin`` terms and the coordinate is in hand -- no apex formula, no
perimeter algebra. The left half is the right half mirrored across ``y = 0``,
so nothing else needs trig either. (Total wire length is still a useful knob --
it just belongs in ``delta_loop_solved``, which inverts a build-and-measure
model to hit a target perimeter.)

The loop is vertical, in the plane x = 0, fed by a short driven gap centred at
the bottom (height ``feed_height``) and opening upward:

        B-----------------A      top corner A = feed terminal + one slant
         \\               /
          \\             /       two equal slants, each (angle_deg, side)
           \\  θ from   /
            \\ horiz.  /
                T---S            short driven feed gap at the bottom, on the y axis
"""

import math
from types import MappingProxyType

from ... import AntennaBuilder


class Builder(AntennaBuilder):
    default_params = MappingProxyType(
        {
            "design_freq": 28.47,
            "freq": 28.47,
            # Height of the bottom feed gap above ground.
            "feed_height": 7.0,
            # Each slanted side is a third of a wavelength times this (three
            # ~equal sides -> a ~1 wl perimeter full-wave loop). Tunes resonance.
            "length_factor": 1.0,
            # Tilt of each slant from horizontal. 60deg -> a 60deg apex, the
            # classic near-equilateral delta loop.
            "angle_deg": 60.0,
            "ui_params": MappingProxyType(
                {
                    "target_z0": 100.0,
                    "default_view": "yz",  # loop lies in the x = 0 plane
                    "length_factor": {"min": 0.85, "max": 1.15},
                    "angle_deg": {"min": 30.0, "max": 80.0},
                }
            ),
        }
    )

    def build_wires(self):
        eps = 0.05
        wavelength = 299.792458 / self.design_freq
        side = (wavelength / 3.0) * self.length_factor
        theta = math.radians(self.angle_deg)  # slant tilt from horizontal
        dy, dz = side * math.cos(theta), side * math.sin(theta)

        def ry(p):
            return (p[0], -p[1], p[2])  # mirror across the y = 0 plane

        # Feed gap: a short horizontal driven segment centred on the y axis at
        # height `feed_height`. Its right end S seeds the right slant; T is S mirrored.
        S = (0.0, eps, self.feed_height)  # right feed terminal
        T = ry(S)  # left feed terminal

        # Top corners, written down directly: fly one slant out-and-up from the
        # feed terminal. Two cos/sin terms give the coordinate -- no apex
        # formula. The left corner is the right one mirrored across y = 0.
        A = (0.0, eps + dy, self.feed_height + dz)  # right top corner
        B = ry(A)  # left top corner

        def build_path(lst, ns, ex):
            return ((a, b, ns, ex) for a, b in zip(lst[:-1], lst[1:]))

        n0 = self.nominal_nsegs
        n1 = max(3, self.nominal_nsegs // 7)

        tups = []
        tups.extend(
            build_path([S, A, B, T], n0, None)
        )  # S->A slant, A->B top, B->T slant
        tups.extend(build_path([T, S], n1, 1 + 0j))  # T->S driven feed gap
        return tups
