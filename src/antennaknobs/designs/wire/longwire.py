"""Resonant multi-wavelength long-wire (L. B. Cebik, W4RNL).

A single straight wire several wavelengths long is the canonical "long-wire"
antenna. While a half-wave dipole fires broadside, a wire grown past 1 wl no
longer does: as it passes 1 wl, 2 wl, 3 wl ... its azimuth pattern breaks into
more and more lobes, and those lobes form CONES tilted toward the wire's own
axis. The more wavelengths of wire, the more lobes, the more the strongest
lobes swing toward the ends, and the higher the gain. This model is a
CENTER-FED wire about 3.5 wl long (seven half-waves): center feeding it at an
odd number of quarter-waves from each end lands the driving point on a current
maximum, keeping the impedance moderate and well-conditioned -- an END feed
would sit at a high-impedance voltage antinode (thousands of ohms) instead,
and a 3.0 wl center feed would sit on a current null for the same reason. The
wire lies horizontal along one axis, so it is HORIZONTALLY POLARISED.

Methodology purpose: this is the catalog's longest single open conductor, so
it stresses the engines' segmentation of a long, multi-half-wave standing-wave
structure and the resulting multi-lobe far field -- a different stress from the
compact resonant antennas. It is the simplest standing-wave member of the
long-wire family that the catalog's `vbeam` and `rhombic` build on (a V-beam
is two such wires at an apex; a rhombic is two V-beams nose to nose).

Geometry, in the framework's (x, y, z) convention:
  - y : the wire axis; the wire runs from -L/2 to +L/2 along y
  - z : constant height `base` (the wire lies horizontal)
  - x : the pattern fans out in cones about the y axis; broadside is +/- x
The structure is a single straight conductor in x = 0, z = base.

    A=========F=========B     z = base   (single ~3.5 wl wire along y)
    |         |         |
  -L/2     centre     +L/2    F: one-segment driven gap at the current max
"""

from antennaknobs import AntennaBuilder
from antennaknobs.network import Wire
from types import MappingProxyType


class Builder(AntennaBuilder):
    default_params = MappingProxyType(
        {
            "design_freq": 28.57,
            "freq": 28.57,
            # Height of the horizontal wire above ground.
            "base": 7.0,
            # Overall wire length as a fraction of a wavelength. ~3.5 wl is
            # SEVEN half-waves total -> each half is an odd number of quarter
            # waves, so the centre feed lands on a current maximum and the
            # driving-point R stays moderate (a 3.0 wl wire, by contrast, is
            # six half-waves: the centre is a current null at thousands of
            # ohms). 3.48 wl trims the reactance toward resonance.
            "length_frac": 3.48,
            # Overall scale knob the optimiser tunes for resonance (X -> 0).
            "length_factor": 1.0,
            "ui_params": MappingProxyType(
                {
                    # Center-fed at a current maximum of a ~3.5 wl wire -> a
                    # moderate, low-hundreds-of-ohms resistance (~140 ohm).
                    "target_z0": 140.0,
                    # Wire runs along y in the plane x=0; the yz view shows it
                    # face-on (length along y, height along z).
                    "default_view": "yz",
                    # Degenerate with length_factor (length = length_frac * wl *
                    # length_factor); pin it and keep length_factor as the knob.
                    "length_frac": {"hidden": True},
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

        length = self.length_frac * wavelength * self.length_factor
        half = length / 2

        z = self.base

        # Single straight wire along y, with a driven gap at the centre (the
        # current maximum). Split into a passive left half, the driven gap,
        # and a passive right half (cf. half_square / lazy_h centre-feed
        # idiom).
        left_end = (0.0, -half, z)
        gap_m = (0.0, -eps, z)
        gap_p = (0.0, eps, z)
        right_end = (0.0, half, z)

        return [
            # Left half (end -> -eps), passive.
            Wire(left_end, gap_m),
            # Driven feed gap across the centre.
            Wire(gap_m, gap_p, ex=1 + 0j),
            # Right half (+eps -> end), passive.
            Wire(gap_p, right_end),
        ]
