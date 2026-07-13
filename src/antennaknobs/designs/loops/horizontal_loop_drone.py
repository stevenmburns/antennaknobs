r"""A horizontal square loop, vertex-fed, authored with the 3D-turtle Drone.

The simplest drone example there is: a flat square loop built by flying four
equal sides with a 90 degrees turn at each corner -- no trig at all. Contrast
``delta_loop_flyby``, whose slants are flown but whose top edge is laid by
flying through the symmetry plane; here every side is the same length and the
corners are just right angles.

The loop lies flat in the plane ``z = base``. Each side is a quarter wavelength
scaled by a common ``length_factor`` (so the perimeter is ~1 wavelength at
``length_factor = 1`` -- a full-wave horizontal loop). It is driven by a short
one-segment gap at one corner: a *vertex feed* (unlike ``horizontal_loop``,
which feeds the midpoint of a side).

For the pattern to stay symmetric the feed itself must sit on a mirror plane of
the square. A gap placed along one side starting at the corner does NOT -- it
skews the current distribution. So instead the two sides stop a hair short of
corner A and the driven segment bridges the corner *diagonally*; that segment is
bisected by the A-C diagonal, which is a mirror plane of the square, so the feed
(and the pattern) stays symmetric.

        D-----------C       (loop lies flat at z = base, viewed from above)
        |           |
        |           |
         \          |       driven segment cuts across corner A,
        A `\--------B       bisected by the A-C diagonal (a mirror plane)
"""

from types import MappingProxyType

from antennaknobs import AntennaBuilder, Drone


class Builder(AntennaBuilder):
    default_params = MappingProxyType(
        {
            "design_freq": 28.57,
            "freq": 28.57,
            # Height of the flat loop plane above ground.
            "base": 5.0,
            # Each side is a quarter wavelength times this; length_factor = 1
            # gives a ~1 wl perimeter (full-wave loop). The optimiser trims it
            # for resonance.
            "length_factor": 1.0,
            "ui_params": MappingProxyType(
                {
                    "target_z0": 100.0,
                    "default_view": "xy",
                    "length_factor": {"min": 0.9, "max": 1.1},
                }
            ),
        }
    )

    def build_wires(self):
        eps = 0.05
        wavelength = 299.792458 / self.design_freq
        quarter = 0.25 * wavelength

        side = quarter * self.length_factor  # each side ~ a quarter wave
        h = side / 2.0
        inset = eps  # how far short of corner A each adjacent side stops

        # The drone's default pose faces +x with 'up' = +z, so the loop is
        # horizontal and yaw(90) turns stay in the z = base plane -- no trig.
        # Start just past corner A on side A->B; we'll fly back to the matching
        # point on side D->A and let the driven segment bridge the corner.
        drone = Drone(
            position=(-h + inset, -h, self.base),
            nominal_nsegs=self.nominal_nsegs,
            ref=quarter,
        )

        drone.pay_out()
        drone.forward(side - inset)  # -> B   (rest of side A->B)
        drone.yaw(90).forward(side)  # B -> C
        drone.yaw(90).forward(side)  # C -> D
        drone.yaw(90).forward(side - inset)  # D -> just short of corner A
        drone.feed(1 + 0j).close(nsegs=1)  # diagonal feed across A, fly home

        return drone.wires()
