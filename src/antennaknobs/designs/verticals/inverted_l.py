"""Inverted-L: a bent, top-loaded vertical (L. B. Cebik, W4RNL).

A quarter-wavelength (or a bit more) of wire run straight up from the
feedpoint and then bent horizontally for the remainder -- the shape of an
upside-down "L". The vertical riser does most of the radiating (mostly
VERTICALLY POLARISED, low takeoff angle); the horizontal top section acts
largely as top-loading/capacitance that lets the riser be shorter than a full
quarter wave while keeping the feed near resonance. It is the classic
"no-room-for-a-full-vertical" low-band antenna.

This fills the "bent / top-loaded monopole" gap: the catalog's verticals
(vertical, raised_vertical) are straight whips; the inverted-L bends the top
over. Like the framework's `vertical`, we give it a small set of elevated
RADIALS as its counterpoise and model it in free space (self-contained, no
ground card); a real install works it against earth or a buried radial field
whose loss adds a few ohms of feed resistance.

Geometry, in the framework's (x, y, z) convention:
  - z : the riser axis, fed at its base against the radial counterpoise
  - y : the horizontal top-wire axis
  - x : the radials spread in x/y; the riser+top section are planar in x = 0

       (0, horiz, vert) o------------------o   horizontal top section
                                            |
                                            |    vertical riser
                          radials           |
                       \\     |     /        F   (base feed)
                        \\    |    /     ____/
"""

from antennaknobs import AntennaBuilder
import math
from types import MappingProxyType


class Builder(AntennaBuilder):
    default_params = MappingProxyType(
        {
            "design_freq": 28.57,
            "freq": 28.57,
            # Height of the radial counterpoise (and feedpoint) above ground.
            "base": 5.0,
            # Vertical riser height as a fraction of a wavelength.
            "vert_frac": 0.17,
            # Horizontal top section length as a fraction of a wavelength.
            # vert + horiz ~ 0.255 wl total: the bent, top-loaded geometry
            # resonates a good bit shorter than a straight quarter-wave whip.
            "horiz_frac": 0.085,
            # Overall scale knob the optimiser tunes for resonance (X -> 0).
            "length_factor": 1.0,
            "ui_params": MappingProxyType(
                {
                    # Top-loaded monopole feed -> low R (~25-45 ohm).
                    "target_z0": 50.0,
                    # Riser along z, top wire along y -> yz view is face-on.
                    "default_view": "yz",
                    "length_factor": {
                        "min": 0.85,
                        "max": 1.2,
                    },
                }
            ),
        }
    )

    def build_wires(self):
        eps = 0.05
        wavelength = 299.792458 / self.design_freq
        quarter = 0.25 * wavelength

        vert = self.vert_frac * wavelength * self.length_factor
        horiz = self.horiz_frac * wavelength * self.length_factor
        z = self.base

        # Radials refine with the mesh like every other wire (issue #477; the
        # old hard-coded 5 left 0.5 m radial segments meeting millimetre riser
        # segments at the feed junction on fine meshes — a graded-junction
        # ratio the pulse/sinusoidal bases handle badly, so PyNEC/sin diverged
        # up the convergence ladder while BSpline d=2 stayed flat).
        n_seg_radials = self.segs_for(quarter, quarter)
        n_radials = 4
        radial_len = quarter  # quarter-wave radials, like a ground-plane vert

        tups = []
        # Base feed: a one-segment driven gap at the foot of the riser, against
        # the radial counterpoise (cf. designs/vertical.py).
        tups.append(
            ((0.0, 0.0, z), (0.0, 0.0, z + eps), self.segs_for(eps, quarter), 1 + 0j)
        )
        # Vertical riser, then the horizontal top section.
        tups.append(
            (
                (0.0, 0.0, z + eps),
                (0.0, 0.0, z + vert),
                self.segs_for(vert, quarter),
                None,
            )
        )
        tups.append(
            (
                (0.0, 0.0, z + vert),
                (0.0, horiz, z + vert),
                self.segs_for(horiz, quarter),
                None,
            )
        )

        # Elevated radials spreading from the feedpoint in the x/y plane.
        for i in range(n_radials):
            theta = 2 * math.pi / n_radials * i
            rx = radial_len * math.cos(theta)
            ry = radial_len * math.sin(theta)
            tups.append(((0.0, 0.0, z), (rx, ry, z), n_seg_radials, None))

        return tups
