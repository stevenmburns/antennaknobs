"""W8JK flat-top beam: a 2-element all-driven 180-degree array (L. B. Cebik,
W4RNL, after John Kraus W8JK).

Two horizontal wires run parallel, close-spaced (~1/8 wavelength), and are fed
180 degrees OUT OF PHASE -- in the real antenna by a parallel feeder with one
side given a half-twist between the two element centres. The out-of-phase,
close-spaced pair radiates BIDIRECTIONALLY endfire (off the +/- x ends of the
boom, in the plane of the wires) with a deep broadside null. Using "extended"
elements longer than a half-wave (~0.64 wl each, the Kraus extended-double-Zepp
length) puts the collinear gain on top of the array gain, so the flat-top beats
a plain dipole by several dB while staying dead simple and feedline-tunable.

This fills the "out-of-phase driven array" gap: the catalog's lazy_h feeds two
elements IN phase (broadside), the hb9cv feeds them ~135 degrees apart
(unidirectional endfire); the W8JK is the 180-degree, bidirectional member of
the family. Because the two elements are mirror images across the y-z plane and
are driven with equal-and-opposite voltages, the antisymmetric excitation
forces equal-magnitude, opposite-phase currents -- exactly the 180-degree
phasing the half-twist feeder produces -- so we model it as two centre feeds at
+1 and -1 rather than as an explicit crossed line.

Cebik / Kraus proportions: elements 0.5-1.25 wl long (0.64 wl "extended" here),
spacing 1/8 to 1/2 wl (0.125 wl here). HORIZONTALLY POLARISED.

Geometry, in the framework's (x, y, z) convention:
  - y : the element length axis (both wires run along y)
  - x : boom/firing axis; the two wires sit at x = -spacing/2 and +spacing/2,
        and the beam fires bidirectionally off +/- x
  - z : constant height `base`

    x = -s/2   ====================F====================   (rear,  V = -1)
    x = +s/2   ====================F====================   (front, V = +1)
                          beam <--> +/- x   (broadside null off +/- y)
"""

from antennaknobs import AntennaBuilder
from types import MappingProxyType


class Builder(AntennaBuilder):
    default_params = MappingProxyType(
        {
            "design_freq": 28.57,
            "freq": 28.57,
            "base": 7.0,
            # Element length as a fraction of a wavelength. ~0.64 wl is the
            # Kraus "extended" length that adds collinear gain.
            "elem_frac": 0.64,
            # Element-to-element spacing as a fraction of a wavelength (~1/8).
            "spacing_frac": 0.125,
            "ui_params": MappingProxyType(
                {
                    # Out-of-phase close-spaced feed -> low, reactive driving
                    # point; in practice tuned via the parallel feeder. Use a
                    # representative open-wire reference.
                    "target_z0": 100.0,
                    # Wires span y, boom along x -> the xy view is face-on.
                    "default_view": "xy",
                    "elem_frac": {
                        "min": 0.5,
                        "max": 1.25,
                    },
                    "spacing_frac": {
                        "min": 0.1,
                        "max": 0.5,
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
        z = self.base

        def element(x, voltage):
            """A horizontal wire along y at (x, z), centre-fed with `voltage`."""
            L = (x, -half, z)
            R = (x, half, z)
            C0 = (x, -eps, z)
            C1 = (x, eps, z)
            return [
                (L, C0, self.segs_for(half - eps, quarter), None),
                (C0, C1, 1, voltage),
                (C1, R, self.segs_for(half - eps, quarter), None),
            ]

        tups = []
        tups.extend(element(-spacing / 2, -1 + 0j))  # rear, anti-phase
        tups.extend(element(spacing / 2, 1 + 0j))  # front
        return tups
