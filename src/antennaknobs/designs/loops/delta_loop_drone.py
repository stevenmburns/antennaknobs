"""The same feed-anchored delta loop as ``delta_loop_sides``, authored with the
3D-turtle :class:`~antennaknobs.drone.Drone` -- *describe the flight* instead of
writing the corner coordinates.

Same simple knobs as ``delta_loop_sides``: a feed height ``feed_height``, a slant
length (``length_factor`` thirds of a wavelength) and the apex tilt
``angle_deg`` from horizontal. Fly the right slant, turn the exterior angle, fly
the top, turn, fly the left slant, then close the feed gap back to the start.

Because the slant length is *given* and the turn angles live in the drone's
rotation matrix, the flight has to compute exactly **one** distance: the
horizontal top edge, ``2 * (side * cos(angle_deg) + eps)``. That lone trig
distance is the thing ``delta_loop_flown`` removes, by flying the top to the
loop's symmetry plane instead of measuring it.
"""

import math
from types import MappingProxyType

from ... import AntennaBuilder, Drone


class Builder(AntennaBuilder):
    default_params = MappingProxyType(
        {
            "design_freq": 28.47,
            "freq": 28.47,
            # Height of the bottom feed gap above ground.
            "feed_height": 7.0,
            # Each slanted side is a third of a wavelength times this.
            "length_factor": 1.0,
            # Tilt of each slant from horizontal (60 deg -> a 60 deg apex).
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
        quarter = 0.25 * wavelength
        side = (wavelength / 3.0) * self.length_factor

        # The one distance the flight must compute: the horizontal top edge.
        # cos of the tilt-from-horizontal gives each top corner's offset from
        # the centre line; + eps for the half feed gap, times two for A -> B.
        top = 2.0 * (side * math.cos(math.radians(self.angle_deg)) + eps)

        n_body = self.nominal_nsegs
        n_feed = max(3, self.nominal_nsegs // 7)

        S = (0.0, eps, self.feed_height)  # right feed terminal; loop is planar in x = 0
        drone = Drone(position=S, nominal_nsegs=n_body, ref=quarter)

        # Nose out along the top edge with world +x as "up" so every yaw stays
        # in the loop plane, then tilt up onto the right slant -- the sin/cos of
        # that tilt lives in the drone's rotation, not on the page.
        drone.face(heading=(0.0, 1.0, 0.0), up=(1.0, 0.0, 0.0))
        drone.yaw(self.angle_deg)

        drone.pay_out()
        drone.forward(side, nsegs=n_body)  # S -> A  (right slant, given length)
        drone.yaw(180.0 - self.angle_deg)  # exterior angle at A
        drone.forward(top, nsegs=n_body)  # A -> B  (top edge, the computed leg)
        drone.yaw(180.0 - self.angle_deg)  # exterior angle at B
        drone.forward(side, nsegs=n_body)  # B -> T  (left slant, given length)
        drone.feed(1 + 0j)
        drone.close(nsegs=n_feed)  # T -> S  (driven feed gap, fly home)

        return drone.wires()
