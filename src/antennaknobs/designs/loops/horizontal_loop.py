"""Horizontal full-wave loop / "loop skywire" (L. B. Cebik, W4RNL).

A single closed loop whose perimeter is about one wavelength, lying FLAT in a
plane of constant height (z = base) and fed at the midpoint of one side. The
horizontal full-wave loop is the classic all-band "loop skywire": strung low
over real ground it is a strong NVIS radiator (it fires nearly straight up, the
near-vertical-incidence skywave that fills the close-in skip zone), while in
free space it is HORIZONTALLY POLARISED with its main lobe broadside to the
loop plane -- i.e. straight up and straight down, along +/- z. A full-wave loop
presents a moderate, near-resistive feedpoint of roughly 100-130 ohm. We use a
SQUARE loop (side = perimeter / 4, ~0.25-0.27 wl per side); Cebik's max-pattern
full-wave loop runs the perimeter a few percent over 1.0 wl, so the side is a
touch over a quarter wave.

Methodology purpose: this is a LARGE single closed loop with ONE feed in a NEW
orientation (horizontal, in a constant-z plane). It exercises the engines'
closed-loop Y assembly and the overhead-hemisphere (zenith-pointing) far field.
Single-port closed loops are already supported by every engine, so this serves
partly as a control case and partly as a new-orientation / large-loop check.

Geometry, in the framework's (x, y, z) convention:
  - z : height; the whole loop sits in the plane z = base (it is HORIZONTAL)
  - x, y : the square's four corners at (+/- h, +/- h, base)
  - main lobe along +/- z (broadside to the loop plane -> toward zenith)

        D-----------C       y = +h
        |           |
        |           |       (loop lies flat at z = base; viewed from above)
        F           |       feed F at the midpoint of side A->D
        |           |
        A-----------B       y = -h
        x=-h        x=+h
"""

from antennaknobs import AntennaBuilder
from types import MappingProxyType


class Builder(AntennaBuilder):
    default_params = MappingProxyType(
        {
            "design_freq": 28.57,
            "freq": 28.57,
            # Height of the (flat) loop plane above ground. In free space this
            # only shifts the structure; over real ground it sets the NVIS
            # takeoff. Low for a skywire.
            "base": 5.0,
            # Side length as a fraction of a wavelength. Four sides -> a ~1 wl
            # perimeter; ~0.264 wl per side runs the perimeter a few percent
            # over 1.0 wl (Cebik's max-pattern full-wave-loop proportion) and
            # is tuned so the free-space feed is near resonant (X ~ 0) at
            # length_factor = 1.
            "side_frac": 0.2635,
            # Overall scale knob the optimiser tunes for resonance (X -> 0).
            # A full-wave loop is naturally a bit inductive; this trims it.
            "length_factor": 1.0,
            "ui_params": MappingProxyType(
                {
                    # Full-wave loop -> moderate, near-resistive feed ~100 ohm.
                    "target_z0": 100.0,
                    # The loop lies flat in z = base; its x and y spans are the
                    # two largest, so the xy view shows the loop face-on.
                    "default_view": "xy",
                    # Degenerate with length_factor (side = side_frac * wl *
                    # length_factor); pin it and keep length_factor as the knob.
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
        h = side / 2.0
        z = self.base

        # Keep the per-segment length roughly uniform across wires (good NEC
        # practice at the corner junctions). Odd counts so the side centre
        # falls on a segment.
        # Four corners of the flat square, all at z = base.
        A = (-h, -h, z)
        B = (h, -h, z)
        C = (h, h, z)
        D = (-h, h, z)

        # Feed gap at the midpoint of side A->D (the wire runs along +y here).
        feed = 2 * eps
        F0 = (-h, -feed / 2.0, z)  # gap start, just below the midpoint
        F1 = (-h, feed / 2.0, z)  # gap end, just above the midpoint

        tups = []
        # Side A->D split into: A->gap-start (passive), gap (driven, 1 seg),
        # gap-end->D (passive). The remaining three sides close the loop.
        tups.append((A, F0, self.segs_for(h - feed / 2.0, quarter), None))
        tups.append((F0, F1, 1, 1 + 0j))  # one-segment driven gap
        tups.append((F1, D, self.segs_for(h - feed / 2.0, quarter), None))
        tups.append((D, C, self.segs_for(side, quarter), None))  # top side
        tups.append((C, B, self.segs_for(side, quarter), None))  # right side
        tups.append(
            (B, A, self.segs_for(side, quarter), None)
        )  # bottom side, closes the loop
        return tups
