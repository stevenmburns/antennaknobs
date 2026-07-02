"""A delta loop flown *entirely* by the Drone, with NO explicit trig in the
script -- not even the closed-form apex height, and no ``ry`` reflection. Every
leg's length is discovered by flying to a plane, including the top edge, which
uses ``forward_to_plane(..., factor=2)`` to cross the symmetry plane ``y = 0``
and land on the mirrored corner in a single command.

The flight, given the feed height, the top height and the apex tilt:

    S --up the right slant--> A   (fly to the plane z = top)
    A --across the top------> B   (fly to the symmetry plane y = 0, factor=2)
    B --down the left slant-> T   (fly to the plane z = base)
    T --feed gap------------> S   (close)

The point of this variant is the *tradeoff* it exposes: the construction could
hardly be simpler -- no cos/sin/tan anywhere, the drone's matrices and the plane
solves carry all of it -- but the **parameterization pays for it**. You give the
two heights and the tilt; you do NOT set the loop's size or its resonance
directly. The perimeter is whatever falls out of ``(base, top, angle_deg)``, so
to tune resonance you nudge ``top`` and re-measure. The shipped ``delta_loop``
hands that knob back by solving the apex height in closed form (explicit trig) so
you can size by total wire length outright. Simple to build vs. convenient to
design with are different axes -- this loop trades the second for the first.

The loop is vertical (planar in x = 0), fed by a short driven gap at the bottom.
"""

from types import MappingProxyType

from ... import AntennaBuilder, Drone


class Builder(AntennaBuilder):
    default_params = MappingProxyType(
        {
            "design_freq": 28.47,
            "freq": 28.47,
            # Feed-gap height (the bottom point of the loop).
            "base": 7.0,
            # Top-edge height. The vertical extent (top - base) and the tilt set
            # the size; the perimeter is emergent, not a knob.
            "top": 10.0,
            # Slant tilt from horizontal (60 deg -> the classic ~equilateral
            # delta loop). Given to the drone as a plain yaw -- no trig here.
            "angle_deg": 60.0,
            "ui_params": MappingProxyType(
                {
                    "target_z0": 100.0,
                    "default_view": "yz",  # loop lies in the x = 0 plane
                    "top": {"min": 8.5, "max": 11.5},
                    "angle_deg": {"min": 45.0, "max": 75.0},
                }
            ),
        }
    )

    def build_wires(self):
        eps = 0.05
        wavelength = 299.792458 / self.design_freq
        quarter = 0.25 * wavelength
        n_body = self.nominal_nsegs
        n_feed = max(3, self.nominal_nsegs // 7)

        S = (0.0, eps, self.base)  # right feed terminal
        drone = Drone(position=S, nominal_nsegs=n_body, ref=quarter)

        # Nose out along the top edge with world +x as "up" so every yaw stays
        # in the loop plane (x = 0), then tilt up onto the right slant. No
        # direction cosines by hand -- the drone's rotation holds them.
        drone.face(heading=(0.0, 1.0, 0.0), up=(1.0, 0.0, 0.0))
        drone.yaw(self.angle_deg)

        drone.pay_out()
        drone.forward_to_plane((0.0, 0.0, 1.0, self.top))  # S -> A: up to the top
        drone.yaw(180.0 - self.angle_deg)  # exterior angle at the top-right corner A
        # A -> B: fly across the top to the symmetry plane y = 0 and the same
        # distance past it, landing on B without computing the top's width.
        drone.forward_to_plane((0.0, 1.0, 0.0, 0.0), factor=2.0)
        drone.yaw(180.0 - self.angle_deg)  # exterior angle at the top-left corner B
        drone.forward_to_plane((0.0, 0.0, 1.0, self.base))  # B -> T: down to the feed
        drone.feed(1 + 0j)
        drone.close(nsegs=n_feed)  # T -> S: the driven feed gap, fly home

        return drone.wires()
