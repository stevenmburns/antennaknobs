"""Triangular horizontal full-wave loop ("skyloop"), fed at a corner.

A single closed loop whose perimeter is about one wavelength, lying FLAT in a
plane of constant height (z = base) like the square horizontal_loop skywire --
but bent into an EQUILATERAL TRIANGLE and fed at one CORNER rather than at the
midpoint of a side. Strung over real ground it is a strong NVIS radiator (it
fires nearly straight up, filling the close-in skip zone); in free space it is
horizontally polarised with its main lobe broadside to the loop plane, along
+/- z. A full-wave loop presents a moderate, near-resistive feed; a corner feed
on a triangle runs a touch higher than the ~100 ohm of a side-fed loop.

Default design frequency is 3.8 MHz -- the centre of the 75 m voice band (the
3.6-4.0 MHz phone segment of 80 m), where a full-size triangular skyloop is a
classic high-and-flat NVIS/rag-chew antenna.

Methodology purpose: a LARGE single closed loop with the feed placed AT A
VERTEX (the two sides meet at 60 deg there and the driven segment is the first
segment leaving the corner), exercising the engines' closed-loop assembly with
an asymmetric, corner-anchored feed rather than the symmetric mid-side gap of
horizontal_loop.

Geometry, in the framework's (x, y, z) convention:
  - z : height; the whole triangle sits in the plane z = base (HORIZONTAL)
  - x, y : the equilateral triangle, apex toward +y, base toward -y
  - feed F at the +y apex corner; main lobe along +/- z (toward zenith)

              V_top  (0, +R)          feed F at this corner
               /\\
              /  \\
             /    \\                   (triangle lies flat at z = base;
            /      \\                   viewed from above)
           /        \\
     V_left ---------- V_right
     (-s/2, -R/2)      (+s/2, -R/2)
"""

import math
from types import MappingProxyType

from ... import AntennaBuilder


class Builder(AntennaBuilder):
    default_params = MappingProxyType(
        {
            # Centre of the 75 m voice band (3.6-4.0 MHz phone segment).
            "design_freq": 3.8,
            "freq": 3.8,
            # Height of the (flat) loop plane above ground. In free space this
            # only shifts the structure; over real ground it sets the NVIS
            # takeoff. A full-size 75 m loop typically hangs high in tall trees.
            "base": 15.0,
            # Perimeter in wavelengths, and the single scale/tuning knob. Each
            # side is length_factor/3 of a wavelength, so length_factor = 1 is a
            # nominal one-wavelength loop; a full-wave loop resonates a few
            # percent long, so the free-space feed is near resonant (X ~ 0,
            # ~113 ohm) at length_factor = 1.05.
            "length_factor": 1.05,
            "ui_params": MappingProxyType(
                {
                    # Full-wave loop, corner-fed -> moderate near-resistive feed.
                    # Free-space solve at the default 1.05 is ~113 - j5 ohm, so
                    # 112 shows a near-1:1 SWR there.
                    "target_z0": 112.0,
                    # The triangle lies flat in z = base; its x and y spans are
                    # the two largest, so the xy view shows the loop face-on.
                    "default_view": "xy",
                    "length_factor": {
                        "min": 0.95,
                        "max": 1.15,
                    },
                }
            ),
        }
    )

    def build_wires(self):
        eps = 0.05

        wavelength = 299.792458 / self.design_freq
        quarter = 0.25 * wavelength

        # Equilateral triangle, so each side is a third of the perimeter; the
        # perimeter is length_factor wavelengths (length_factor = 1 -> a nominal
        # one-wavelength loop).
        side = (wavelength / 3.0) * self.length_factor
        # Equilateral triangle: circumradius R = side / sqrt(3). Centroid at the
        # origin, apex toward +y, base edge toward -y, all at z = base.
        r = side / math.sqrt(3.0)
        z = self.base

        v_top = (0.0, r, z)
        v_left = (-side / 2.0, -r / 2.0, z)
        v_right = (side / 2.0, -r / 2.0, z)

        # Corner feed at the +y apex: a one-segment driven gap that is the first
        # segment of the v_top -> v_right side, anchored exactly at the corner.
        feed = 2 * eps
        ux = (v_right[0] - v_top[0]) / side  # unit vector along v_top -> v_right
        uy = (v_right[1] - v_top[1]) / side
        f0 = v_top  # gap start, at the corner
        f1 = (v_top[0] + feed * ux, v_top[1] + feed * uy, z)  # gap end

        tups = []
        # Driven gap leaving the corner, then close the triangle back to it.
        tups.append((f0, f1, 1, 1 + 0j))  # one-segment driven gap
        tups.append((f1, v_right, self.segs_for(side - feed, quarter), None))
        tups.append((v_right, v_left, self.segs_for(side, quarter), None))
        tups.append(
            (v_left, v_top, self.segs_for(side, quarter), None)
        )  # closes to corner
        return tups
