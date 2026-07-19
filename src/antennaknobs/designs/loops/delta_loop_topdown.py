"""The shipped delta loop, built as a **top-down reflection flight**: the same
reflection hybrid as ``delta_loop_reflected``, but the flight starts *at the
top* — so the top height is right from move one and there is **no z-offset
pass**.

One of four interchangeable expressions of the *same* design. ``delta_loop``,
``delta_loop_flyby``, ``delta_loop_reflected`` and ``delta_loop_topdown`` (here)
all take the same knobs — ``base`` (top-edge height), ``length_factor`` (total
wire length in wavelengths) and ``angle_deg`` (slant tilt from horizontal) — and
produce byte-identical wires. They differ only in *how you specify the geometry*.

Everything else matches ``delta_loop_reflected`` -- the drone is a trig-free
point finder, ``ry`` mirrors the right half, and ``build_path`` stitches the
four corners. The *only* difference is the anchor: that build starts at the feed
(``z = 0``) and lifts the loop afterward with a z-offset pass to seat the top;
this one starts at the top centre, so no second pass is needed.

The flight: from the top centre, fly out to the top corner, turn down onto the
slant, and let ``forward_to_plane`` drop until it crosses the feed plane
``y = eps``. The feed height is emergent -- wherever the slant lands. The top
half-width is solved (``brentq``) so the total wire length hits the target
perimeter; ``ry`` mirrors the right half across ``y = 0`` for the left, and
``build_path`` lays the ``S -> A -> B -> T`` perimeter plus the ``T -> S`` feed.
"""

import math
from types import MappingProxyType

from antennaknobs import AntennaBuilder, Drone


class Builder(AntennaBuilder):
    default_params = MappingProxyType(
        {
            "design_freq": 28.47,
            "freq": 28.47,
            # Top-edge height -- the centre the flight starts from, and the same
            # knob as the shipped delta_loop.
            "base": 7.0,
            # Total wire length in wavelengths (~1 -> full-wave loop).
            "length_factor": 1.0800,
            # Slant tilt from horizontal.
            "angle_deg": 62.3894,
            "ui_params": MappingProxyType(
                {
                    "target_z0": 100.0,
                    "default_view": "yz",  # loop lies in the x = 0 plane
                    "length_factor": {"min": 0.95, "max": 1.15},
                    "angle_deg": {"min": 30.0, "max": 80.0},
                }
            ),
        }
    )

    def build_wires(self):
        from scipy.optimize import brentq

        eps = 0.05
        wavelength = 299.792458 / self.design_freq
        quarter = 0.25 * wavelength
        target = self.length_factor * wavelength
        n0 = self.nominal_nsegs

        def ry(p):
            return (p[0], -p[1], p[2])

        def build_path(lst, ns, ex):
            return [(a, b, ns, ex) for a, b in zip(lst[:-1], lst[1:])]

        def geometry(half_top):
            # Start at the top centre; fly the right half pen-up to find its two
            # vertices -- out to the top corner A, then down the slant until it
            # crosses the feed plane y = eps. The top is at `base` from move one.
            drone = Drone(nominal_nsegs=n0, ref=quarter)
            drone.move_to((0.0, 0.0, self.base))
            drone.face(heading=(0.0, 1.0, 0.0), up=(1.0, 0.0, 0.0))
            A = drone.forward(half_top).position
            drone.yaw(180.0 + self.angle_deg)  # turn down onto the slant
            S = drone.forward_to_plane((0.0, 1.0, 0.0, eps)).position
            B, T = ry(A), ry(S)
            n1 = self.segs_for(math.dist(T, S), math.dist(A, B))

            # build_path stitches the four corners into the perimeter and feed
            # gap -- the same helper delta_loop and delta_loop_reflected use. No
            # second drone pass: the flight only found the points A and S.
            return build_path([S, A, B, T], n0, None) + build_path([T, S], n1, 1 + 0j)

        def total(half_top):
            return sum(math.dist(p0, p1) for p0, p1, _ns, _ex in geometry(half_top))

        # Solve the top half-width so the total wire length hits the target.
        half_top = brentq(lambda w: total(w) - target, eps, wavelength)
        return geometry(half_top)
