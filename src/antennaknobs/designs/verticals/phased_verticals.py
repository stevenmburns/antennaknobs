"""Two-element phased vertical array -- the 90-degree cardioid (L. B. Cebik,
W4RNL).

Two vertical radiators spaced a quarter wavelength apart and fed 90 degrees
out of phase. The spatial quarter-wave delay and the electrical 90-degree feed
phase add in the direction of the lagging element and cancel behind the
leading one, so the bidirectional figure-8 of a single vertical collapses into
a UNIDIRECTIONAL CARDIOID: ~3 dB of forward gain and a deep rearward null
(Cebik / Christman models reach 15-25+ dB front-to-back). This is the
canonical steered VP array and the basis of the four-square.

This fills the "phased vertical / cardioid" gap: the catalog's other VP wire
antennas (half_square, bobtail) are fixed broadside curtains; here the pattern
is steered by FEED PHASE. We model each radiator as a self-contained vertical
half-wave DIPOLE (so the array needs no ground plane and the cardioid is
visible in free space); the classic field version uses quarter-wave MONOPOLES
of half this height worked against a radial ground screen -- electrically the
same array, imaged in the ground.

Phasing: with the elements at x = 0 (rear) and x = +spacing (front), feeding
the FRONT element 90 degrees LAGGING (voltage -j) steers the main lobe to +x
and nulls -x.

Geometry, in the framework's (x, y, z) convention:
  - z : the radiator (vertical) axis -- VERTICALLY POLARISED
  - x : array/firing axis; rear element at x = 0, front at x = +spacing,
        cardioid main lobe toward +x with the null toward -x
  - y : 0 for both elements

      rear (x=0)        front (x=spacing)
        |                   |
        |  V = 1            |  V = -j      (front lags 90 deg)
        F                   F
        |                   |       cardioid main lobe --> +x
"""

from antennaknobs import AntennaBuilder
from types import MappingProxyType


class Builder(AntennaBuilder):
    default_params = MappingProxyType(
        {
            "design_freq": 28.57,
            "freq": 28.57,
            # Height of the lower tip of each vertical dipole.
            "base": 5.0,
            # Radiator length as a fraction of a wavelength (~half-wave
            # vertical dipole; the monopole version is half this over ground).
            "elem_frac": 0.5,
            # Element spacing as a fraction of a wavelength (~1/4 -> cardioid).
            "spacing_frac": 0.25,
            # Complex drive on the FRONT element relative to the rear (which is
            # 1+0j). Ideal theory wants -j (90 deg lag, equal magnitude); the
            # value here is tuned against the modelled mutual coupling so the
            # currents -- not just the voltages -- come out 90 deg apart and
            # equal, which is what actually deepens the rearward null. The 1.2
            # magnitude compensates the front element's lower driving-point
            # current (from the mutual coupling) so the null deepens past the
            # ~5 dB a naive equal-voltage feed gives.
            "front_voltage": -1.2j,
            "ui_params": MappingProxyType(
                {
                    "target_z0": 50.0,
                    # Array axis x, radiators along z -> the xz view is face-on.
                    "default_view": "xz",
                    "elem_frac": {
                        "min": 0.4,
                        "max": 0.6,
                    },
                    "spacing_frac": {
                        "min": 0.15,
                        "max": 0.35,
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
        zc = self.base + half  # geometric centre height of each vertical

        def vertical(x, voltage):
            """A vertical (z-axis) half-wave dipole at x, centre-fed."""
            B = (x, 0.0, zc - half)
            T = (x, 0.0, zc + half)
            C0 = (x, 0.0, zc - eps)
            C1 = (x, 0.0, zc + eps)
            return [
                (B, C0, self.segs_for(half - eps, quarter), None),
                (C0, C1, 1, voltage),
                (C1, T, self.segs_for(half - eps, quarter), None),
            ]

        tups = []
        tups.extend(vertical(0.0, 1 + 0j))  # rear, reference phase
        tups.extend(vertical(spacing, complex(self.front_voltage)))  # front lobe
        return tups
