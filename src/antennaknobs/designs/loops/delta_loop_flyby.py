"""The shipped delta loop, laid down as a full **drone flyby** — fly the whole
perimeter and let the flight do the work, no coordinates written.

One of four interchangeable expressions of the *same* design. ``delta_loop``,
``delta_loop_flyby`` (here), ``delta_loop_reflected`` and ``delta_loop_topdown``
all take the same knobs — ``base`` (top-edge height), ``length_factor`` (total
wire length in wavelengths) and ``angle_deg`` (slant tilt from horizontal) — and
produce byte-identical wires. They differ only in *how you specify the geometry*:
``delta_loop`` writes the corner coordinates from a closed-form expression for
the top corner; this one flies them.

The flight is anchored at the **feed** and built from the bottom up:

  - start at the right feed terminal (``z = 0`` for now), tilt up onto the right
    slant and ``forward(side)`` to the top-right corner;
  - ``forward_through_plane((0, 1, 0, 0))`` flies *through* the symmetry plane
    ``y = 0`` to an equal distance past it, laying the whole top edge in one move
    and landing on the mirror corner — no length computed, no reflection;
  - ``forward(side)`` down the left slant, then ``close()`` lays the driven feed
    gap back to the start.

Two passes make it match the shipped design's knobs: ``brentq`` solves the slant
length so the total wire hits ``length_factor * wavelength`` (the drone builds
never use delta_loop's closed form), then a **z-offset pass** lifts every ``z``
so the
top edge seats at ``base`` — the feed trailing below, its height emergent.
"""

import math
from types import MappingProxyType

from antennaknobs import AntennaBuilder, Drone


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
        quarter = 0.25 * wavelength
        target = self.length_factor * wavelength
        n_body = self.nominal_nsegs

        def geometry(side):
            # Fly the whole loop with the feed at z = 0 -- the top height is
            # added by the z-offset pass below, not known during the flight.
            S = (0.0, eps, 0.0)  # right feed terminal; loop is planar in x = 0
            drone = Drone(position=S, nominal_nsegs=n_body, ref=quarter)

            # Nose out along the top edge, then tilt up onto the right slant.
            drone.face(heading=(0.0, 1.0, 0.0), up=(1.0, 0.0, 0.0))
            drone.yaw(self.angle_deg)

            drone.pay_out()
            drone.forward(side, nsegs=n_body)  # S -> A  (right slant, given length)
            drone.yaw(180.0 - self.angle_deg)  # exterior angle at A
            # A -> B: fly through the symmetry plane y = 0 to an equal distance
            # past it, landing on the mirror corner -- the top edge, no length
            # computed and nothing reflected.
            drone.forward_through_plane((0.0, 1.0, 0.0, 0.0), nsegs=n_body)
            drone.yaw(180.0 - self.angle_deg)  # exterior angle at B
            drone.forward(side, nsegs=n_body)  # B -> T  (left slant, given length)
            n_feed = self.segs_for(math.dist(drone.position, S), side)
            drone.feed(1 + 0j)
            drone.close(nsegs=n_feed)  # T -> S  (driven feed gap, fly home)
            return drone.wires()

        def total(side):
            return sum(math.dist(p0, p1) for p0, p1, _ns, _ex in geometry(side))

        # Size by total wire length, numerically (the drone builds never use the
        # closed-form top-corner position the shipped delta_loop leans on).
        side = brentq(lambda s: total(s) - target, 1e-3, 2.0 * wavelength)
        wires = geometry(side)

        # z-offset pass: lift the whole loop so the top edge seats at `base`.
        top_z = max(p[2] for e in wires for p in (e[0], e[1]))
        shift = self.base - top_z

        def lift(p):
            return (p[0], p[1], p[2] + shift)

        return [(lift(a), lift(b), ns, ex) for a, b, ns, ex in wires]
