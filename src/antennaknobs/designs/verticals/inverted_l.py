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

The `topband` variant is the 160 m inverted L of M0AGP's comparison with a
full-size vertical (QRZ thread 1005128; AK#1828): two radials 5 ft up, and
the vertical section and the top wire as knobs in feet (`in_feet`). Its
`Builder.build_studies()` is that comparison, DX gain against the vertical
section relative to the full vertical, which reproduces his NEC-5 table
(scratch/1828-m0agp/README.md).

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
from antennaknobs import analyses as an
from antennaknobs.network import Wire
import math
from types import MappingProxyType

#: One foot, in metres: the 160 m variant's knobs are in feet, as M0AGP's
#: comparison (QRZ thread 1005128) gives them.
FT = 0.3048


#: The 160 m variant's top wire, resonant at 70 ft of vertical section, and
#: the full-size vertical's height, resonant with no top wire (AK#1828: X = 0
#: on NEC-5 at 1.83 MHz, two radials 5 ft up over Sommerfeld 13/0.005; momwire
#: puts both within 0.15 ft of these, scratch/1828-m0agp/reproduce.py).
TOPBAND_HORIZ_FT = 63.9
TOPBAND_VERTICAL_FT = 131.2


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
            # The elevated radial counterpoise: how many, spread evenly from
            # the feed (AK#1828: M0AGP's comparison uses two).
            "n_radials": 4,
            # The vertical section and the top wire in FEET instead of the
            # fractions above (the 160 m variant's, `topband_params`): off
            # here, so these two are hidden and the fractions build it.
            "in_feet": False,
            "vert_ft": 70.0,
            "horiz_ft": TOPBAND_HORIZ_FT,
            "ui_params": MappingProxyType(
                {
                    "n_radials": {"min": 1, "max": 16},
                    "in_feet": {"hidden": True},
                    "vert_ft": {"hidden": True, "min": 10.0, "max": 140.0},
                    "horiz_ft": {"hidden": True, "min": 0.0, "max": 160.0},
                    # Top-loaded monopole feed -> low R (~25-45 ohm).
                    "target_z0": 50.0,
                    # Riser along z, top wire along y -> not planar in any
                    # single 2D projection -> iso shows the L shape.
                    "default_view": "iso",
                    "length_factor": {
                        "min": 0.85,
                        "max": 1.2,
                    },
                }
            ),
        }
    )

    # The 160 m inverted L of M0AGP's comparison with a full-size vertical
    # (AK#1828): two radials 5 ft up, and the vertical section and the top
    # wire in FEET (`vert_ft`, `horiz_ft`, which replace the fractions of a
    # wavelength). The top wire is cut for resonance at 70 ft of vertical
    # section; a top wire of 0 ft is no top wire, the plain vertical.
    topband_params = MappingProxyType(
        {
            "design_freq": 1.83,
            "freq": 1.83,
            "base": 1.524,
            "n_radials": 2,
            "in_feet": True,
            "vert_ft": 70.0,
            "horiz_ft": TOPBAND_HORIZ_FT,
            "ui_params": MappingProxyType(
                {
                    "vert_frac": {"hidden": True},
                    "horiz_frac": {"hidden": True},
                    "length_factor": {"hidden": True},
                    "base": {"min": 0.5, "max": 10.0},
                    "vert_ft": {"hidden": False},
                    # The hold's bounds (step 6 holds a knob inside its
                    # ui_params range): every resonant top from 100 ft of
                    # vertical (33 ft) down to 20 ft (112 ft) is inside, and
                    # the top end stays clear of the half-wave antiresonance,
                    # where X changes sign the other way.
                    "horiz_ft": {"hidden": False, "min": 1.0, "max": 135.0},
                }
            ),
        }
    )

    def build_studies(self):
        """M0AGP's "DX gain" comparison (AK#1828, QRZ thread 1005128): the
        power average of the gain over 2-10 degrees of elevation, 0.1 degree
        apart, of the 160 m inverted L as its vertical section shortens,
        relative to the full-size vertical (the same antenna with no top
        wire, its vertical cut for resonance, a FIXED reference), with the
        top wire held at resonance at every point.

        His azimuth is not stated, and the L is asymmetric, so the study
        states one: the elevation cut at azimuth 0, along the radials and
        broadside to the top wire. That cut reproduces his table on NEC-5
        within 0.16 dB at eight of its nine points (0.7 dB at 30 ft); the
        cut through the peak (`PEAK_AZ`, away from the top wire) and the
        azimuth average do not (scratch/1828-m0agp/README.md)."""
        dx = an.ElevationWindow("DX gain", 2, 10, step=0.1, az=0)
        me = "verticals.inverted_l"
        return [
            an.Analysis(
                "DX gain vs the vertical (M0AGP)",
                an.Sweep(
                    "vert_ft",
                    values=(20.0, 30.0, 40.0, 50.0, 60.0, 70.0, 80.0, 90.0, 100.0),
                ),
                cross=an.Cross(
                    states=(
                        an.State("inverted L", design=me, variant="topband"),
                        an.State(
                            "vertical",
                            design=me,
                            variant="topband",
                            vert_ft=TOPBAND_VERTICAL_FT,
                            horiz_ft=0.0,
                        ),
                    )
                ),
                hold=an.Hold("resonance", adjust=("horiz_ft",)),
                views=(an.MetricPlot(dx, relative_to="vertical"), an.Knobs()),
                ground="finite",
            ),
        ]

    def build_wires(self):
        eps = 0.05
        wavelength = self.design_wavelength
        quarter = 0.25 * wavelength

        if self.in_feet:
            # The 160 m variant's knobs, in feet (`topband_params`).
            vert = self.vert_ft * FT
            horiz = self.horiz_ft * FT
        else:
            vert = self.vert_frac * wavelength * self.length_factor
            horiz = self.horiz_frac * wavelength * self.length_factor
        z = self.base

        # Radials refine with the mesh like every other wire (issue #477; the
        # old hard-coded 5 left 0.5 m radial segments meeting millimetre riser
        # segments at the feed junction on fine meshes — a graded-junction
        # ratio the pulse/sinusoidal bases handle badly, so PyNEC/sin diverged
        # up the convergence ladder while BSpline d=2 stayed flat).
        n_radials = int(self.n_radials)
        radial_len = quarter  # quarter-wave radials, like a ground-plane vert

        tups = []
        # Base feed: a one-segment driven gap at the foot of the riser, against
        # the radial counterpoise (cf. designs/vertical.py).
        tups.append(Wire((0.0, 0.0, z), (0.0, 0.0, z + eps), ex=1 + 0j))
        # Vertical riser, then the horizontal top section.
        tups.append(Wire((0.0, 0.0, z + eps), (0.0, 0.0, z + vert)))
        if horiz > 0:
            # No top wire at all is the straight vertical (a zero-length wire
            # would not mesh).
            tups.append(Wire((0.0, 0.0, z + vert), (0.0, horiz, z + vert)))

        # Elevated radials spreading from the feedpoint in the x/y plane.
        for i in range(n_radials):
            theta = 2 * math.pi / n_radials * i
            rx = radial_len * math.cos(theta)
            ry = radial_len * math.sin(theta)
            tups.append(Wire((0.0, 0.0, z), (rx, ry, z)))

        return tups
