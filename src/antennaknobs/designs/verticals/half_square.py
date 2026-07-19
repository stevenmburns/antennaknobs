"""Half-square: a vertically-polarised wire antenna (L. B. Cebik, W4RNL).

The half-square is "two (roughly) 1/4-wavelength vertical legs connected by a
(roughly) 1/2-wavelength horizontal wire" -- a rectangle missing its bottom
side. Electrically it is a ~1-wavelength conductor (1/4 + 1/2 + 1/4) bent into
that shape, with the two open leg-ends as voltage (current-null) points. The
current maxima sit at the two top corners, so the radiation is dominated by
the two vertical legs fed in phase: the antenna is VERTICALLY POLARISED and
fires bidirectionally broadside to the plane of the wire, with deep nulls off
the ends (Cebik: side rejection "from 10 to well over 15 dB") and a low
takeoff angle that makes it a modest DX antenna.

Cebik's max-gain proportions are frequency-independent: the horizontal:vertical
length ratio is about 1.6:1 (top ~0.454 wl, legs ~0.283 wl), giving ~4.6-4.7
dBi free-space gain. We feed at one top corner -- the current maximum -- which
is a low, near-resonant impedance (~65 ohm in Cebik's models) rather than the
high-impedance end feed of the classic "feed the bottom of one leg" version.

Geometry, in the framework's (x, y, z) convention:
  - y : the long axis (the horizontal top wire runs along y)
  - z : height; leg bottoms at `base`, top wire at `base + vert`
  - x : firing axis; the antenna radiates broadside off +/- x
The structure is planar in x = 0.

    C===============D     z = base + vert   (top wire, ~0.454 wl)
    |               |
    F               |     legs ~0.283 wl; feed F just below corner C
    |               |
    A               B     z = base          (open leg ends, voltage nulls)
"""

from antennaknobs import AntennaBuilder
from types import MappingProxyType


class Builder(AntennaBuilder):
    default_params = MappingProxyType(
        {
            "design_freq": 28.57,
            "freq": 28.57,
            # Height of the open leg ends above ground. Low for a VP DX
            # antenna; the top wire sits `vert` higher.
            "base": 3.0,
            # Leg (vertical) length as a fraction of a wavelength. Cebik's
            # max-gain proportion is ~0.283 wl.
            "vert_frac": 0.283,
            # Top-wire (horizontal) length as a fraction of a wavelength,
            # ~0.454 wl -> a horizontal:vertical ratio of ~1.6:1.
            "horiz_frac": 0.454,
            # Overall scale knob the optimiser tunes for resonance (X -> 0).
            "length_factor": 1.0,
            "ui_params": MappingProxyType(
                {
                    # Fed at a current maximum -> low impedance; reference SWR
                    # to a typical 50 ohm line.
                    "target_z0": 50.0,
                    # Planar in x=0; the y (top) and z (legs) spans are the
                    # two largest, so the yz view shows the antenna face-on.
                    "default_view": "yz",
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

        vert = self.vert_frac * wavelength * self.length_factor
        horiz = self.horiz_frac * wavelength * self.length_factor

        y_left, y_right = -horiz / 2, horiz / 2
        z_bot = self.base
        z_top = self.base + vert

        # Keep the per-segment length roughly uniform across wires of
        # different lengths (good NEC practice at the corner junctions):
        # scale each wire's segment count by its length relative to a
        # quarter wave. Odd counts so the centre falls on a segment.
        # A short feed gap just below the left top corner, at the current
        # maximum. One segment carries the excitation (cf. moxon.py).
        feed = 2 * eps
        A = (0.0, y_left, z_bot)
        F = (0.0, y_left, z_top - feed)
        C = (0.0, y_left, z_top)
        D = (0.0, y_right, z_top)
        B = (0.0, y_right, z_bot)

        tups = []
        # Left leg (bottom -> just below corner), passive.
        tups.append((A, F, self.segs_for(vert - feed, quarter), None))
        # Feed segment at the corner, driven.
        tups.append((F, C, self.segs_for(feed, quarter), 1 + 0j))
        # Top wire, passive.
        tups.append((C, D, self.segs_for(horiz, quarter), None))
        # Right leg (corner -> bottom), passive.
        tups.append((D, B, self.segs_for(vert, quarter), None))

        return tups
