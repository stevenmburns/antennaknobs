"""Bobtail curtain: a 3-element vertically-polarised broadside array
(L. B. Cebik, W4RNL).

The bobtail is the electrical big brother of the half-square: THREE roughly
1/4-wavelength vertical radiators, spaced about 1/2 wavelength apart, joined
along the top by a continuous ~1-wavelength phasing wire. All three verticals
end up driven in phase, so the array is VERTICALLY POLARISED and fires
bidirectionally broadside to the plane of the wires, with a tighter pattern
and a few dB more gain than the half-square (~6.4 dBi here, max at a low
elevation over ground).

Only the centre vertical is fed; the two OUTER verticals are passive, open at
the bottom, and excited entirely through the top phasing wire.

FEEDPOINT -- where we tap the centre vertical. The classic bobtail is fed at
the BASE of the centre wire ("the matching tank at the bottom"), which sits at
a current NULL: the impedance there is high (thousands of ohms) and strongly
reactive, so the real antenna resonates it out with a parallel-tuned tank, not
a broadband unun. That base point is also a poor MODELLING point -- being a
current minimum, the computed Z is ill-conditioned (it neither converges with
segmentation nor agrees between solver bases), exactly the high-impedance-
feedpoint hazard Cebik warned about. So, like the catalog's `half_square`
(which feeds its top corner rather than a leg end), we instead tap the centre
vertical partway up, at a CURRENT MAXIMUM: `feed_height_frac` of the way from
the base to the top. At the default mid-element tap the driving point is a low,
near-resonant ~50 ohm -- coax-direct, well-conditioned, and identical in gain
and pattern to the base-fed version (the feed only taps the standing wave; it
does not change the radiation). A real shunt/gamma-fed coax bobtail does this.

Cebik's 40 m proportions: verticals ~0.243 wl, half-span (centre-to-outer)
~0.541 wl, so the full top wire is ~1.083 wl.

Geometry, in the framework's (x, y, z) convention:
  - y : the long axis (the three verticals sit at y = -span, 0, +span)
  - z : height; leg bottoms at `base`, top wire at `base + vert`
  - x : firing axis; radiation is broadside off +/- x
The structure is planar in x = 0.

    C1=========C2=========C3    z = base + vert   (top wire, ~1.08 wl)
    |          |          |
    |          F          |     three verticals, ~0.243 wl; centre tapped
    |          |          |     at a current max (feed_height_frac up)
    A1         A2         A3     z = base   (outer ends open; A2 = open base)
"""

from antennaknobs import AntennaBuilder
from types import MappingProxyType


class Builder(AntennaBuilder):
    default_params = MappingProxyType(
        {
            "design_freq": 28.57,
            "freq": 28.57,
            # Height of the open leg ends above ground.
            "base": 3.0,
            # Vertical-radiator length as a fraction of a wavelength
            # (Cebik's 40 m model: ~0.243 wl).
            "vert_frac": 0.243,
            # Half-span: centre-to-outer horizontal spacing as a fraction of
            # a wavelength (~0.541 wl) -> full top wire ~1.083 wl.
            "span_frac": 0.541,
            # Tap height of the feed on the centre vertical, as a fraction of
            # its length from the base (0 = base/current-null/high-Z tank
            # point, 1 = top/junction). ~0.5 taps a current maximum -> ~50 ohm.
            "feed_height_frac": 0.5,
            # Overall scale knob. length_factor ~1.0 is Cebik's max-gain
            # proportion; near the mid tap it is also near-resonant (X -> 0).
            "length_factor": 1.0,
            "ui_params": MappingProxyType(
                {
                    # Mid-element current-max tap -> low, near-resonant feed;
                    # reference SWR to 50 ohm coax.
                    "target_z0": 50.0,
                    "default_view": "yz",
                    "length_factor": {
                        "min": 0.9,
                        "max": 1.1,
                    },
                    # Tap position: stay off the ill-conditioned base (0) and
                    # top-junction (1) extremes.
                    "feed_height_frac": {
                        "min": 0.25,
                        "max": 0.85,
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
        span = self.span_frac * wavelength * self.length_factor

        z_bot = self.base
        z_top = self.base + vert

        tups = []

        # Top phasing wire: -span -> 0 -> +span, split at the centre so the
        # centre vertical shares the junction node.
        tups.append(
            (
                (0.0, -span, z_top),
                (0.0, 0.0, z_top),
                self.segs_for(span, quarter),
                None,
            )
        )
        tups.append(
            ((0.0, 0.0, z_top), (0.0, span, z_top), self.segs_for(span, quarter), None)
        )

        # Outer verticals (passive, open at the bottom).
        tups.append(
            (
                (0.0, -span, z_top),
                (0.0, -span, z_bot),
                self.segs_for(vert, quarter),
                None,
            )
        )
        tups.append(
            (
                (0.0, span, z_top),
                (0.0, span, z_bot),
                self.segs_for(vert, quarter),
                None,
            )
        )

        # Centre vertical: a one-segment driven gap tapped `feed_height_frac`
        # of the way up (a current maximum), with passive wire above and below.
        # zf is the lower edge of the gap.
        feed = 2 * eps
        zf = z_bot + self.feed_height_frac * (vert - feed)
        tups.append(
            (
                (0.0, 0.0, z_top),
                (0.0, 0.0, zf + feed),
                self.segs_for(z_top - (zf + feed), quarter),
                None,
            )
        )
        tups.append(((0.0, 0.0, zf + feed), (0.0, 0.0, zf), 1, 1 + 0j))
        tups.append(
            (
                (0.0, 0.0, zf),
                (0.0, 0.0, z_bot),
                self.segs_for(zf - z_bot, quarter),
                None,
            )
        )

        return tups
