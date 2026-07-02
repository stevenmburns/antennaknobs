"""A delta loop built a third way: reparameterized by slant *angle* and *side
length*, with NO trig in the script.

``delta_loop`` (and its drone twin ``delta_loop_drone``) size the triangle from
a perimeter ``length_factor`` and then solve an apex-height formula
``h = (cos·(d-2eps)+2eps)/(2(cos+1))`` for the corner coordinates. That closed
form is the "scary trig" this version avoids.

The reparameterization: give the two equal slanted sides directly (their length
``side`` and their tilt ``angle_deg`` from vertical). Then the only edge whose
length still needs trig is the horizontal *top* -- so we don't compute it. We
fly each slant with the 3D-turtle ``Drone`` (``yaw`` by the angle, ``forward``
by the side -- the sin/cos lives inside the Drone, never in this script), drop a
labelled pin at the right corner, fly the left slant, and ``line_to`` that pin
to lay the top. The Drone works out the top segment from the two corner
positions it has been tracking.

The loop is vertical, in the plane x = 0, fed by a short driven gap centred at
the bottom (height ``feed_height``) and opening upward:

        L-----------R      top, drawn corner-to-corner (line_to a marked node)
         \\         /
          \\       /        two equal slants, each flown from (angle, side)
           \\     /
            T~~~~S          short driven feed gap at the bottom, on the y axis
"""

from types import MappingProxyType

from ... import AntennaBuilder, Drone


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
            # Tilt of each slant from vertical. 30deg -> a 60deg apex, the
            # classic near-equilateral delta loop.
            "angle_deg": 30.0,
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
        quarter = 0.25 * wavelength
        side = (wavelength / 3.0) * self.length_factor

        # Bottom feed gap: a short horizontal segment centred on the y axis at
        # height `feed_height`. Its two ends seed the slants; T is just S mirrored, so
        # no trig -- and everything above is flown by the drone.
        S = (0.0, eps, self.feed_height)  # right end of the feed gap
        T = (0.0, -eps, self.feed_height)  # left end

        drone = Drone(nominal_nsegs=self.nominal_nsegs, ref=quarter)

        # Right slant: from S, nose straight up, tilt `angle_deg` toward +y,
        # fly one side up to the right top corner; pin it as "R".
        drone.move_to(S).mark("S")
        drone.face(heading=(0.0, 0.0, 1.0), up=(1.0, 0.0, 0.0))
        drone.yaw(-self.angle_deg)
        drone.pay_out().forward(side)  # S -> R
        drone.mark("R")

        # Left slant: same from T, tilted the other way, up to the left corner.
        drone.cut().move_to(T)
        drone.face(heading=(0.0, 0.0, 1.0), up=(1.0, 0.0, 0.0))
        drone.yaw(self.angle_deg)
        drone.pay_out().forward(side)  # T -> L

        # Top wire: connect the left corner to the pinned right corner. The
        # drone computes the segment -- no trig for the top's length.
        drone.line_to("R")  # L -> R

        # Feed: the short driven gap across the bottom, T -> S (one segment).
        drone.cut().move_to(T)
        drone.feed(1 + 0j).line_to("S", nsegs=1)  # T -> S

        return drone.wires()
