"""The same feed-anchored delta loop as ``delta_loop_drone`` -- but with the one
remaining computed distance removed, so there is **no explicit trig anywhere**.

``delta_loop_drone`` flies the two slants by the given ``side`` and computes the
last leg, the top edge, by trig. This version lays that top edge by *flight*
instead: ``forward_through_plane((0, 1, 0, 0))`` flies through the loop's
symmetry plane ``y = 0`` to an equal distance past it, landing squarely on the
mirrored corner. Nothing is measured and nothing is reflected -- the slants are
the given length, the turns are plain yaws, and the top falls out of the
symmetry.

Same simple knobs as ``delta_loop_sides`` / ``delta_loop_drone``: feed height
``feed_height``, slant length (``length_factor``), apex tilt ``angle_deg`` from
horizontal. The loop is vertical (planar in x = 0), fed at the bottom.
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

        n_body = self.nominal_nsegs
        n_feed = max(3, self.nominal_nsegs // 7)

        S = (0.0, eps, self.feed_height)  # right feed terminal; loop is planar in x = 0
        drone = Drone(position=S, nominal_nsegs=n_body, ref=quarter)

        # Nose out along the top edge, then tilt up onto the right slant.
        drone.face(heading=(0.0, 1.0, 0.0), up=(1.0, 0.0, 0.0))
        drone.yaw(self.angle_deg)

        drone.pay_out()
        drone.forward(side, nsegs=n_body)  # S -> A  (right slant, given length)
        drone.yaw(180.0 - self.angle_deg)  # exterior angle at A
        # A -> B: fly through the symmetry plane y = 0 to an equal distance past
        # it, landing on the mirror corner -- the top edge, no length computed.
        drone.forward_through_plane((0.0, 1.0, 0.0, 0.0), nsegs=n_body)
        drone.yaw(180.0 - self.angle_deg)  # exterior angle at B
        drone.forward(side, nsegs=n_body)  # B -> T  (left slant, given length)
        drone.feed(1 + 0j)
        drone.close(nsegs=n_feed)  # T -> S  (driven feed gap, fly home)

        return drone.wires()
