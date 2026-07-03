r"""The shipped delta loop, built as a **reflection hybrid**: the drone is a
trig-free *point finder*, an ``ry`` mirror gives the left half for free, and
``build_path`` stitches the corners.

One of four interchangeable expressions of the *same* design. ``delta_loop``,
``delta_loop_flyby``, ``delta_loop_reflected`` (here) and ``delta_loop_topdown``
all take the same knobs — ``base`` (top-edge height), ``length_factor`` (total
wire length in wavelengths) and ``angle_deg`` (slant tilt from horizontal) — and
produce byte-identical wires. They differ only in *how you specify the geometry*.

This one leans on three idioms at once, anchored at the **feed** and built up:

  - the **drone** flies pen-up (laying no wire) up the right slant to read off
    the top corner ``A`` — the one point that would otherwise need trig; the
    sin/cos lives in the drone's matrices, never in this script;
  - **reflection** across the ``y = 0`` plane (``ry``) mirrors the right half to
    the left corner ``B`` and feed terminal ``T`` for free;
  - **build_path** (the same helper ``delta_loop`` uses) stitches the four points
    into the S->A->B->T perimeter plus the T->S feed.

Two passes make it match the shipped design's knobs: ``brentq`` solves the slant
length so the total wire hits ``length_factor * wavelength`` (build it with the
feed at ``z = 0``, no top height involved yet), then a **z-offset pass** lifts
every ``z`` so the top edge seats at ``base``, the feed trailing below.

        B-----------A      top (A found by the drone, B = ry(A))
         \         /
          \       /
           \     /
            T~~~~S          feed gap; S seeds the drone, T = ry(S)
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

        # Size by total wire length, numerically (no closed-form corner position).
        side = brentq(lambda s: total(s) - target, 1e-3, 2.0 * wavelength)
        wires = geometry(side)

        # z-offset pass: lift the whole loop so the top edge seats at `base`.
        top_z = max(p[2] for e in wires for p in (e[0], e[1]))
        shift = self.base - top_z

        def lift(p):
            return (p[0], p[1], p[2] + shift)

        return [(lift(a), lift(b), ns, ex) for a, b, ns, ex in wires]
