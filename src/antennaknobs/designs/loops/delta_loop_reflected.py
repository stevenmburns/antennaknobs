"""A delta loop built as a hybrid: the Drone is a trig-free *point finder*, and
the codebase's own ``ry`` reflection + ``build_path`` do the assembly.

This is the most hybrid of the delta-loop variants. Like ``delta_loop_marked``
it is parameterized by the slant ``angle_deg`` and side length (no apex-height
formula), but it leans on three idioms at once:

  - the **Drone** flies (laying no wire) up the right slant to read off the top
    corner ``A`` -- the one point that would otherwise need trig; the sin/cos
    lives in the Drone's matrices, never in this script;
  - **reflection** across the y = 0 plane (``ry``) mirrors the right half to get
    the left corner ``B`` and feed terminal ``T`` for free;
  - **build_path** (the same helper ``delta_loop`` uses) stitches the four
    points into the S->A->B->T perimeter plus the T->S feed.

        B-----------A      top (A found by the Drone, B = ry(A))
         \\         /
          \\       /
           \\     /
            T~~~~S          feed gap; S seeds the Drone, T = ry(S)
"""

from types import MappingProxyType

from ... import AntennaBuilder, Drone


class Builder(AntennaBuilder):
    default_params = MappingProxyType(
        {
            "design_freq": 28.47,
            "freq": 28.47,
            "feed_height": 7.0,  # height of the bottom feed gap
            "length_factor": 1.0,  # each slant = (wavelength / 3) * this
            "angle_deg": 30.0,  # slant tilt from vertical (30 -> 60 apex)
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
        side = (wavelength / 3.0) * self.length_factor
        n_seg0 = self.nominal_nsegs
        n_seg1 = max(3, self.nominal_nsegs // 7)

        def build_path(lst, ns, ex):
            return ((a, b, ns, ex) for a, b in zip(lst[:-1], lst[1:]))

        def ry(p):
            return p[0], -p[1], p[2]

        # S is the right end of the bottom feed gap. Fly the drone (pen up, no
        # wire) from S up the right slant to read off the top corner A -- the
        # only point that would otherwise need trig.
        S = (0.0, eps, self.feed_height)
        A = (
            Drone(position=S)
            .face(heading=(0.0, 0.0, 1.0), up=(1.0, 0.0, 0.0))
            .yaw(-self.angle_deg)
            .forward(side)
            .position
        )

        # The left half is the right half mirrored across the y = 0 plane.
        B, T = ry(A), ry(S)

        # build_path stitches the points into edges.
        tups = []
        tups.extend(build_path([S, A, B, T], n_seg0, None))  # perimeter
        tups.extend(build_path([T, S], n_seg1, 1 + 0j))  # driven feed gap
        return tups
