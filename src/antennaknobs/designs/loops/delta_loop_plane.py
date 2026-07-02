"""The shipped delta loop's exact design, expressed by a top-down flight:
sized by total wire length (solved numerically) and anchored at the top with
**no second pass** -- the flight simply starts there.

One of three interchangeable expressions of the *final* design.
``delta_loop_hoisted``, this, and ``delta_loop`` all take the same parameter set
(``base`` = top-edge height, ``length_factor`` = total wire length in
wavelengths, ``angle_deg`` = slant tilt from horizontal) and produce identical
wires; they differ only in how much they lean on:

- ``delta_loop_hoisted``: solve numerically **and** a second-pass z recalc;
- here: still solve numerically, but start the flight *at* the top so the top
  height is right from the first move -- the second pass is gone;
- ``delta_loop``: no solve either -- a closed-form apex height.

The flight: from the top centre, fly out to the top corner, turn down onto the
slant, and let ``forward_to_plane`` drop until it crosses the feed plane
``y = eps``. The feed height is emergent -- wherever the slant lands. The top
half-width is solved so the total wire length hits the target perimeter.
"""

import math
from types import MappingProxyType

from ... import AntennaBuilder, Drone


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
        n1 = max(3, self.nominal_nsegs // 7)

        def ry(p):
            return (p[0], -p[1], p[2])

        def geometry(half_top):
            # Start at the top centre; fly the right half pen-up to find its two
            # vertices -- out to the top corner, then down the slant until it
            # crosses the feed plane y = eps. The top is at `base` from move one.
            drone = Drone(nominal_nsegs=n0, ref=quarter)
            drone.move_to((0.0, 0.0, self.base))
            drone.face(heading=(0.0, 1.0, 0.0), up=(1.0, 0.0, 0.0))
            R = drone.forward(half_top).position
            drone.yaw(180.0 + self.angle_deg)  # turn down onto the slant
            S = drone.forward_to_plane((0.0, 1.0, 0.0, eps)).position
            L, T = ry(R), ry(S)

            # Pin the four corners, stitch the perimeter, then the feed gap.
            drone.cut().move_to(S).mark("S")
            drone.move_to(R).mark("R")
            drone.move_to(L).mark("L")
            drone.move_to(T).mark("T")

            drone.move_to(S).pay_out()
            drone.line_to("R", nsegs=n0)  # up the right slant
            drone.line_to("L", nsegs=n0)  # across the top
            drone.line_to("T", nsegs=n0)  # down the left slant
            drone.cut().move_to(T).feed(1 + 0j).line_to("S", nsegs=n1)
            return drone.wires()

        def total(half_top):
            return sum(math.dist(p0, p1) for p0, p1, _ns, _ex in geometry(half_top))

        # Solve the top half-width so the total wire length hits the target.
        half_top = brentq(lambda w: total(w) - target, eps, wavelength)
        return geometry(half_top)
