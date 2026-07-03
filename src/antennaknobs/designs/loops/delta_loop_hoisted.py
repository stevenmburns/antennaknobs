"""The shipped delta loop's exact design, expressed a third way: sized by total
wire length (solved numerically) and anchored at the top by a **second pass**
that recalcs z.

This is the first of three interchangeable expressions of the *final* design --
``delta_loop_hoisted`` (here), ``delta_loop_plane`` and ``delta_loop`` all take
the same parameter set (``base`` = top-edge height, ``length_factor`` = total
wire length in wavelengths, ``angle_deg`` = slant tilt from horizontal) and
produce identical wires. They differ only in *how much machinery* they lean on:

- here: solve for the side length numerically **and** lift the loop with a
  second pass to seat the top;
- ``delta_loop_plane``: still solve numerically, but start the flight at the top
  so no second pass is needed;
- ``delta_loop``: no solve and no second pass -- a closed-form apex height.

The second pass is the tell: build the loop with its feed at ``z = 0`` (no top
height involved yet), then add a constant to every ``z`` so the top edge seats
at ``base``, the feed trailing below.
"""

import math
from types import MappingProxyType

from ... import AntennaBuilder, Drone


class Builder(AntennaBuilder):
    default_params = MappingProxyType(
        {
            "design_freq": 28.47,
            "freq": 28.47,
            # Top-edge height -- the same knob as the shipped delta_loop.
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
        target = self.length_factor * wavelength
        n0 = self.nominal_nsegs
        n1 = max(3, self.nominal_nsegs // 7)

        def ry(p):
            return (p[0], -p[1], p[2])

        def build_path(lst, ns, ex):
            return [(a, b, ns, ex) for a, b in zip(lst[:-1], lst[1:])]

        def geometry(side):
            # Build with the feed at z = 0 (no top height involved yet). Fly the
            # right slant pen-up to read off corner A, reflect for the left half.
            S = (0.0, eps, 0.0)
            A = (
                Drone(position=S)
                .face(heading=(0.0, 1.0, 0.0), up=(1.0, 0.0, 0.0))
                .yaw(self.angle_deg)
                .forward(side)
                .position
            )
            B, T = ry(A), ry(S)
            return build_path([S, A, B, T], n0, None) + build_path([T, S], n1, 1 + 0j)

        def total(side):
            return sum(math.dist(p0, p1) for p0, p1, _ns, _ex in geometry(side))

        # Size by total wire length, numerically (same inversion as solved).
        side = brentq(lambda s: total(s) - target, 1e-3, 2.0 * wavelength)
        wires = geometry(side)

        # Second pass: lift the whole loop so the top edge seats at `base`.
        top_z = max(p[2] for e in wires for p in (e[0], e[1]))
        shift = self.base - top_z

        def lift(p):
            return (p[0], p[1], p[2] + shift)

        return [(lift(a), lift(b), ns, ex) for a, b, ns, ex in wires]
