"""M0AGP's 160 m inverted L, and his "DX gain" comparison with a full-size vertical.

From M0AGP's QRZ thread "Inverted L vs full-size vertical — 'DX Gain'
comparison" (thread 1005128, first post). He asks how much a 160 m inverted
L gives up against a full-size quarter-wave vertical as its vertical section
gets shorter, with the top wire re-cut for resonance at every height. This
design is his antenna, and its own study (`build_studies`) is his table.

The antenna, in the framework's (x, y, z) convention:

- a 5 cm driven gap at the foot of the riser, `base` above ground;
- the vertical section rises `vert_ft` FEET from the feed along z;
- the top wire runs `horiz_ft` FEET along +y from its top. A top wire of 0 ft
  is no top wire at all, so the full-size vertical is a setting of this same
  design (a state), with the same feed and the same radials;
- `n_radials` quarter-wave radials at the feed height, spread evenly from +x.
  Two of them run along +x and -x, perpendicular to the top wire, which is
  the orientation his numbers fit.

The design itself carries no ground (free space, like the rest of the
catalog); the study states his: Sommerfeld average ground, 13 / 0.005 S/m.

His figure of merit is DX gain: the power average of the gain over 2-10
degrees of elevation, 0.1 degree apart, converted back to dB. He reports
each inverted L relative to the vertical, two radials 5 ft up over average
ground, modelled on NEC-5. His azimuth isn't stated; the elevation cut at
azimuth 0 (along the radials, broadside to the top wire) is the one that
reproduces his table, so the study states it.

The study, `verticals.m0agp_invl:DX gain vs the vertical`, sweeps the
vertical section over 20-100 ft and holds the top wire at resonance at every
height. Each inverted L reads relative to the vertical (a FIXED reference: it
sets the swept knob, so it is solved once and drawn flat). On momwire at
azimuth 0, the DX gain relative to the vertical (dB):

    vert_ft   100     90     80     70     60     50     40     30     20
    dB     -0.196 -0.365 -0.615 -0.984 -1.532 -2.367 -3.689 -5.845 -9.495

Run it with `antennaknobs analyze --study "verticals.m0agp_invl:DX gain vs
the vertical"`, or from the design's Studies tab in the app.
"""

import math
from types import MappingProxyType

import antennaknobs.analyses as an
from antennaknobs import AntennaBuilder
from antennaknobs.network import Wire

#: One foot, in metres.
FT = 0.3048

#: The full-size vertical: resonant with no top wire at 1.83 MHz over
#: Sommerfeld 13/0.005 with these two radials (131.22 ft on NEC-5, 131.10 ft
#: on momwire).
VERTICAL_FT = 131.2


class Builder(AntennaBuilder):
    default_params = MappingProxyType(
        {
            "design_freq": 1.83,
            "freq": 1.83,
            # The feed and the radials: 5 ft up.
            "base": 1.524,
            # The vertical section and the top wire, in feet. The top wire
            # is cut for resonance at 70 ft of vertical section.
            "vert_ft": 70.0,
            "horiz_ft": 63.9,
            "n_radials": 2,
            "ui_params": MappingProxyType(
                {
                    # Riser along z, top wire along y, radials along x: no
                    # single 2D projection shows the L and its radials.
                    "default_view": "iso",
                    "base": {"min": 0.5, "max": 10.0, "unit": "m"},
                    "vert_ft": {"min": 10.0, "max": 140.0, "unit": "ft"},
                    # The hold's bounds: every resonant top from 100 ft of
                    # vertical (33 ft) to 20 ft (112 ft) is inside, and the
                    # top end stays clear of the half-wave antiresonance.
                    "horiz_ft": {"min": 1.0, "max": 135.0, "unit": "ft"},
                    "n_radials": {"min": 1, "max": 16},
                }
            ),
        }
    )

    def build_wires(self):
        eps = 0.05
        z = self.base
        vert = self.vert_ft * FT
        horiz = self.horiz_ft * FT
        radial_len = 0.25 * self.design_wavelength

        tups = [Wire((0.0, 0.0, z), (0.0, 0.0, z + eps), ex=1 + 0j)]
        tups.append(Wire((0.0, 0.0, z + eps), (0.0, 0.0, z + vert)))
        if horiz > 0:
            # No top wire at all is the plain vertical (a zero-length wire
            # would not mesh).
            tups.append(Wire((0.0, 0.0, z + vert), (0.0, horiz, z + vert)))
        n = int(self.n_radials)
        for i in range(n):
            a = 2 * math.pi / n * i
            tups.append(
                Wire(
                    (0.0, 0.0, z),
                    (radial_len * math.cos(a), radial_len * math.sin(a), z),
                )
            )
        return tups

    def build_studies(self):
        """DX gain against the vertical section, 20-100 ft, each inverted L
        relative to the full-size vertical (a FIXED reference: it sets the
        swept knob, so it is solved once and drawn flat), the top wire held
        at resonance at every height."""
        me = "verticals.m0agp_invl"
        dx = an.ElevationWindow("DX gain", 2, 10, step=0.1, mean="power", az=0)
        return [
            an.Analysis(
                "DX gain vs the vertical",
                an.Sweep(
                    "vert_ft",
                    values=(20.0, 30.0, 40.0, 50.0, 60.0, 70.0, 80.0, 90.0, 100.0),
                ),
                cross=an.Cross(
                    states=(
                        an.State("inverted L", design=me),
                        an.State(
                            "vertical", design=me, vert_ft=VERTICAL_FT, horiz_ft=0.0
                        ),
                    )
                ),
                hold=an.Hold("resonance", adjust=("horiz_ft",)),
                views=(an.MetricPlot(dx, relative_to="vertical"), an.Knobs()),
                ground="finite:13,0.005",
            ),
        ]
