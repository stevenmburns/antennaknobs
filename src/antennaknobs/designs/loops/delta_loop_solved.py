"""A delta loop built the same hybrid way as ``delta_loop_reflected`` (Drone as
a trig-free point finder + ``ry`` reflection + ``build_path``), but parameterized
by ``length_factor`` -- and the side length is found NUMERICALLY.

``delta_loop`` solves a closed-form apex-height formula to make the perimeter
equal ``length_factor * wavelength``. Here we don't derive that formula at all:
we build the loop for a trial ``side``, MEASURE its total wire length, and hand
the residual to a scipy root finder to recover the ``side`` that hits the
target. The geometry function is the model; scipy inverts it.

So none of the trig (or algebra) lives in this script -- the Drone computes the
corner, ``math.dist`` measures the wires, and ``brentq`` does the inversion.
"""

import math
from types import MappingProxyType

from ... import AntennaBuilder, Drone


class Builder(AntennaBuilder):
    default_params = MappingProxyType(
        {
            "design_freq": 28.47,
            "freq": 28.47,
            "feed_height": 7.0,  # height of the bottom feed gap
            # Total wire length as a multiple of a wavelength (~1 -> full-wave
            # loop). The side length is solved to hit this exactly.
            "length_factor": 1.0,
            "angle_deg": 30.0,  # slant tilt from vertical (30 -> 60 apex)
            "ui_params": MappingProxyType(
                {
                    "target_z0": 100.0,
                    "default_view": "yz",  # loop lies in the x = 0 plane
                    "length_factor": {"min": 0.85, "max": 1.15},
                    "angle_deg": {"min": 10.0, "max": 60.0},
                }
            ),
        }
    )

    def build_wires(self):
        eps = 0.05
        wavelength = 299.792458 / self.design_freq
        n_seg0 = self.nominal_nsegs
        n_seg1 = max(3, self.nominal_nsegs // 7)

        def build_path(lst, ns, ex):
            return [(a, b, ns, ex) for a, b in zip(lst[:-1], lst[1:])]

        def ry(p):
            return p[0], -p[1], p[2]

        def geometry(side):
            # Same construction as delta_loop_reflected: the Drone flies pen-up
            # to find the top corner A, reflection mirrors the left half, and
            # build_path stitches the perimeter and feed.
            S = (0.0, eps, self.feed_height)
            A = (
                Drone(position=S)
                .face(heading=(0.0, 0.0, 1.0), up=(1.0, 0.0, 0.0))
                .yaw(-self.angle_deg)
                .forward(side)
                .position
            )
            B, T = ry(A), ry(S)
            return build_path([S, A, B, T], n_seg0, None) + build_path(
                [T, S], n_seg1, 1 + 0j
            )

        def total_wire_length(side):
            return sum(math.dist(p0, p1) for p0, p1, _ns, _ex in geometry(side))

        # Invert numerically: find the side whose loop has total wire length
        # length_factor * wavelength. The length grows monotonically with side,
        # so [tiny, a couple of wavelengths] brackets the single root.
        from scipy.optimize import brentq

        target = self.length_factor * wavelength
        side = brentq(lambda s: total_wire_length(s) - target, 1e-3, 2.0 * wavelength)

        return geometry(side)
