r"""Bi-square: a two-wavelength loop worked as a vertical broadside curtain
(L. B. Cebik, W4RNL).

Take the half-square (a 1 wl conductor) and double it into a 2 wl loop with
four HALF-wave sides, hung as a square standing on one corner (a diamond) and
fed at the bottom corner. Current reverses every half wavelength -- i.e. at
every corner -- so by symmetry the horizontal (left/right) field components of
the four slanting sides cancel while the VERTICAL components add: the bi-square
is VERTICALLY POLARISED and fires bidirectionally broadside to the plane of the
loop. In free space its gain is modest (a couple of dB over a dipole), but
mounted low it is a strong LOW-ANGLE VP performer, the best-known member of
Cebik's "self-contained vertical" (SCV) loop family.

This fills the "vertical loop curtain" gap: the catalog's loops (delta,
diamond, quad) are ~1 wl radiators or horizontally polarised beams; the
bi-square is a 2 wl VP curtain needing no ground plane. Cebik's max-pattern
proportion runs the sides a touch over a half wave (~0.55 wl here).

Geometry, in the framework's (x, y, z) convention:
  - z : height; the loop's tall vertical extent is what makes it VP
  - y : the left/right corners splay to +/- y
  - x : firing axis; broadside off +/- x (planar in x = 0)

                    o  top corner             z = base + 2*hd
                   / \
       left corner o   o right corner         z = base + hd
                   \ /
                    F  bottom corner (fed)     z = base
"""

from antennaknobs import AntennaBuilder
from types import MappingProxyType
import math


class Builder(AntennaBuilder):
    default_params = MappingProxyType(
        {
            "design_freq": 28.57,
            "freq": 28.57,
            # Height of the bottom (fed) corner above ground.
            "base": 4.0,
            # Side length as a fraction of a wavelength (~half-wave per side;
            # four sides -> ~2 wl loop). ~0.55 wl is the modelled max-pattern
            # proportion. Pinned (hidden) because the geometry depends only on
            # the product side_frac * length_factor (see build_wires): exposing
            # both would be two knobs for one degree of freedom. length_factor
            # is the visible trim knob; this stays at Cebik's max-pattern value.
            "side_frac": 0.55,
            # Overall scale knob (peak gain / pattern, not a low-Z resonance,
            # is the design target -- the corner feed is high and reactive).
            "length_factor": 1.0,
            "ui_params": MappingProxyType(
                {
                    # Corner-fed 2 wl loop -> high, reactive feed; open-wire +
                    # tuner in practice.
                    "target_z0": 300.0,
                    "default_view": "yz",
                    # Degenerate with length_factor (product-only); pin it and
                    # let length_factor be the single scale knob.
                    "side_frac": {"hidden": True},
                    "length_factor": {
                        "min": 0.9,
                        "max": 1.1,
                    },
                }
            ),
        }
    )

    def build_wires(self):
        eps = 0.05
        wavelength = 299.792458 / self.design_freq
        quarter = 0.25 * wavelength

        side = self.side_frac * wavelength * self.length_factor
        # Square standing on a corner: the half-diagonal is side / sqrt(2).
        hd = side / math.sqrt(2)

        Bc = (0.0, 0.0, self.base)  # bottom corner (fed)
        Rc = (0.0, hd, self.base + hd)  # right corner
        Tc = (0.0, 0.0, self.base + 2 * hd)  # top corner
        Lc = (0.0, -hd, self.base + hd)  # left corner

        ns = self.segs_for(side, quarter)
        feed = 2 * eps
        # Feed gap on the lower-right side, a short `feed` distance up from the
        # bottom corner along the Bc -> Rc direction (unit (0, 1, 1)/sqrt(2)).
        u = hd / side  # = 1/sqrt(2)
        F = (0.0, feed * u, self.base + feed * u)

        tups = []
        tups.append(
            (Bc, F, self.segs_for(feed, quarter), 1 + 0j)
        )  # driven gap at the corner (length `feed` along the side)
        tups.append((F, Rc, self.segs_for(side - feed, quarter), None))
        tups.append((Rc, Tc, ns, None))  # upper-right side
        tups.append((Tc, Lc, ns, None))  # upper-left side
        tups.append((Lc, Bc, ns, None))  # lower-left side
        return tups
