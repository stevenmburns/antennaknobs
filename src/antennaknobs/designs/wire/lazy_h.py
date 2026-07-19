"""Lazy-H: two stacked collinear elements fed in phase (L. B. Cebik, W4RNL).

Two horizontal wires, each ~1 wavelength long, mounted one above the other and
separated by ~1/2 wavelength, fed IN PHASE. Each 1 wl wire behaves as a
collinear pair of half-waves (broadside gain over a single dipole); stacking
two of them in phase adds the vertical-stacking gain and narrows the elevation
lobe. The array is HORIZONTALLY POLARISED and bidirectional broadside off both
faces of the "H".

In Cebik's build each element is centre-fed with parallel line, and equal
lengths of that line run to a common junction -- so both elements see equal,
in-phase drive, and the junction is the (high-impedance) feedpoint taken to an
antenna tuner via 300-600 ohm open-wire line. The phasing harness exists only
to impose equal in-phase excitation; by the array's symmetry that is exactly
what two equal in-phase centre feeds produce, so we model it that way (cf.
the multi-feed convention in multiband/hexbeam_5band). This fills the
vertical-stacking gap: the catalog's other arrays phase elements side-by-side,
not collinear elements stacked in height.

Geometry, in the framework's (x, y, z) convention:
  - y : the long axis (both 1 wl wires run along y)
  - z : height; lower wire at `base`, upper at `base + spacing`
  - x : firing axis; radiation is broadside off +/- x
The structure is planar in x = 0.

    ===================F===================   z = base + spacing  (upper 1 wl)

    ===================F===================   z = base            (lower 1 wl)
                  (F = in-phase centre feed)
"""

from antennaknobs import AntennaBuilder
from types import MappingProxyType
import math


class Builder(AntennaBuilder):
    default_params = MappingProxyType(
        {
            "design_freq": 28.57,
            "freq": 28.57,
            # Height of the lower element above ground.
            "base": 7.0,
            # Element length as a fraction of a wavelength (~1.0 wl each).
            "elem_frac": 1.0,
            # Vertical stacking distance as a fraction of a wavelength
            # (~0.5 wl between the two elements).
            "spacing_frac": 0.5,
            "ui_params": MappingProxyType(
                {
                    # High-Z junction fed via open-wire line + tuner.
                    "target_z0": 300.0,
                    "default_view": "yz",
                    "elem_frac": {
                        "min": 0.8,
                        "max": 1.3,
                    },
                    "spacing_frac": {
                        "min": 0.3,
                        "max": 0.75,
                    },
                }
            ),
        }
    )

    def build_wires(self):
        eps = 0.05

        wavelength = 299.792458 / self.design_freq
        quarter = 0.25 * wavelength

        elem = self.elem_frac * wavelength
        spacing = self.spacing_frac * wavelength
        half = elem / 2

        def element(z):
            """A 1 wl horizontal wire along y at height z, centre-fed in
            phase (one-segment driven gap at y = 0)."""
            L = (0.0, -half, z)
            R = (0.0, half, z)
            C0 = (0.0, -eps, z)
            C1 = (0.0, eps, z)
            return [
                (L, C0, self.segs_for(half - eps, quarter), None),
                (C0, C1, self.segs_for(math.dist(C0, C1), quarter), 1 + 0j),
                (C1, R, self.segs_for(half - eps, quarter), None),
            ]

        tups = []
        tups.extend(element(self.base))  # lower element
        tups.extend(element(self.base + spacing))  # upper element
        return tups
