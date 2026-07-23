"""Four-square phased vertical array -- the diagonal-firing quadrature box
(L. B. Cebik, W4RNL).

Four vertical radiators at the corners of a square ~0.25-0.3 wavelength on a
side, fed in QUADRATURE so the array fires along a diagonal of the square. The
side corners are fed at slightly less than unit magnitude so the CURRENTS (not
just the voltages) balance against the mutual coupling. With the
back corner taken as the 0-degree reference, the two side corners fed -90
degrees and the front corner fed -180 degrees, the spatial corner-to-corner
delays and the electrical feed phases add toward the front corner and cancel
toward the back: the omnidirectional figure of a lone vertical collapses into a
steerable, VERTICALLY-POLARISED cardioid with strong front-to-back. This is the
classic ham four-square (switch the phasing among the four corners and the lobe
hops 90 degrees), the 2-D big brother of the two-element `phased_verticals`
cardioid.

MODELLING CHOICE: a real four-square uses quarter-wave MONOPOLES standing over
a radial/ground screen, imaged in the earth. To stay self-contained in free
space (the catalog convention -- no ground card), each corner is modelled
instead as a centre-fed half-wave VERTICAL DIPOLE. This preserves the phased-
array physics -- the whole point of the design -- while avoiding a ground
model; it is exactly the free-space-dipole substitution `phased_verticals`
already makes (a quarter-wave monopole over a perfect ground is the lower half
of this dipole, imaged).

METHODOLOGY PURPOSE: this is the catalog's densest MULTI-FEED case -- four
simultaneous complex-voltage feeds spread over a 2-D footprint -- so it stresses
the engines' multi-port excitation handling harder than any single-feed or
collinear-feed design.

Phasing for a lobe toward the (+x, +y) corner: back corner (-x,-y) = 1 (0 deg
reference), the two side corners (+x,-y) and (-x,+y) = -1j (-90 deg), front
corner (+x,+y) = -1 (-180 deg). The progressive -90 deg per quarter-wave step
along each diagonal arm fires the array toward +x,+y and nulls -x,-y.

Geometry, in the framework's (x, y, z) convention:
  - z : the radiator (vertical) axis -- VERTICALLY POLARISED
  - x, y : the square footprint; corners at (+/- s/2, +/- s/2), s = spacing
  - the cardioid main lobe points along the +x,+y diagonal at low elevation

        (-x,+y) V=-1j          (+x,+y) V=-1      main lobe
             F----------------------F           --> +x,+y corner
             |                      |
             |        square        |
             |     s ~ 1/4 wl       |
             F----------------------F
        (-x,-y) V=1            (+x,-y) V=-1j
           (back, reference)
"""

from antennaknobs import AntennaBuilder
from antennaknobs.network import Wire
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
            # Square side as a fraction of a wavelength. ~0.3 wl here: a touch
            # wider than the textbook 1/4 wl, which (with the trims below) lands
            # all four driving-point resistances in a sane ~20-30 ohm range and
            # buys a deeper rearward null than the 1/4 wl box gives.
            "spacing_frac": 0.30,
            # Overall element-length scale the optimiser tunes for resonance.
            # In a tightly-coupled array the per-element reactances will not be
            # exactly zero; this trims the driven-element resistances into a
            # sane range (and keeps the front element's R positive -- with full
            # element length the heavily-driven -180 deg corner presents a
            # negative driving-point resistance under the mutual coupling).
            "length_factor": 0.95,
            # Magnitude applied to the -90 deg side-corner feeds. Ideal theory
            # wants unit magnitude at -1j; trimming it BELOW unity balances the
            # currents -- not just the voltages -- against the mutual coupling,
            # which is what actually deepens the rearward null (FB ~28 dB here
            # vs ~13 dB for the naive equal-magnitude quadrature feed).
            "side_mag": 0.6,
            "ui_params": MappingProxyType(
                {
                    "target_z0": 50.0,
                    # Footprint lies in the x-y plane -> xy view shows the box.
                    "default_view": "xy",
                    # Degenerate with length_factor (elem = elem_frac * wl *
                    # length_factor); pin it and keep length_factor as the knob.
                    "elem_frac": {"hidden": True},
                    "length_factor": {
                        "min": 0.8,
                        "max": 1.2,
                    },
                    "side_mag": {
                        "min": 0.5,
                        "max": 1.5,
                        "step": 0.01,
                        "precision": 2,
                    },
                }
            ),
        }
    )

    def build_wires(self):
        eps = 0.05
        wavelength = 299.792458 / self.design_freq

        elem = self.elem_frac * wavelength * self.length_factor
        spacing = self.spacing_frac * wavelength
        half = elem / 2
        zc = self.base + half  # geometric centre height of each vertical
        s2 = spacing / 2

        def vertical(x, y, voltage):
            """A vertical (z-axis) half-wave dipole at (x, y), centre-fed by a
            one-segment driven gap with the given complex excitation."""
            B = (x, y, zc - half)
            T = (x, y, zc + half)
            C0 = (x, y, zc - eps)
            C1 = (x, y, zc + eps)
            return [
                Wire(B, C0),
                Wire(C0, C1, ex=voltage),
                Wire(C1, T),
            ]

        side = complex(self.side_mag) * (-1j)

        tups = []
        # Back corner (reference), two side corners (-90 deg), front (-180 deg).
        tups.extend(vertical(-s2, -s2, 1 + 0j))  # back  (reference phase)
        tups.extend(vertical(+s2, -s2, side))  # side  (-90 deg)
        tups.extend(vertical(-s2, +s2, side))  # side  (-90 deg)
        tups.extend(vertical(+s2, +s2, -1 + 0j))  # front (-180 deg)
        return tups
