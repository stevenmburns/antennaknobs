"""ZL-Special / HB9CV: a 2-element all-driven phased beam (L. B. Cebik, W4RNL).

Unlike a Yagi -- where one element is driven and the second is a parasite --
BOTH elements here are driven, through a short CROSSED ("half-twist") phasing
line. The crossing supplies a 180-degree reversal and the line's ~45-degree
electrical length subtracts ~45 degrees, so the two elements run roughly 135
degrees out of phase. With ~1/8-wavelength spacing that phasing produces an
endfire pattern -- forward gain comparable to a 2-element Yagi but with a very
deep, sharply tuned front-to-back null (Cebik models 25-45+ dB). This fills
the "phased driven array" gap: gain from feed phasing, not from a parasite.

Cebik's proportions (straight dipoles, 10 m): spacing ~0.12-0.15 wl, phasing
line length ~= the spacing (~45 deg electrical), characteristic impedance
~67 ohm. Equal-length elements work and make the beam reversible; the front
element is made slightly short here so the feed lands near 50 ohm. The line
is modeled as an ideal crossed TL (the TL `transposed` flag); at VF = 1 its
physical length equals the spacing, which is the wanted ~45 deg.

Geometry, in the framework's (x, y, z) convention:
  - x : boom axis; rear element at x = -spacing, front at x = 0; beam --> +x
  - y : the dipole length axis (both horizontal, centre at y = 0)
  - z : constant height `base`
Horizontally polarised. Fed at the front element; the crossed phasing line
carries drive to the rear.

CAVEAT -- front-to-back: the phasing line is modeled as a single-ended IDEAL
crossed TL between the two element centres. That gets the forward gain
(~6.8 dBi), the endfire direction, and the ~50 ohm inductive feed right, but
the very deep F/B null Cebik reports (25-45 dB) needs a precise simultaneous
phase-AND-current-magnitude match that the single-ended ideal line does not
reach -- it tops out near ~8 dB here. The genuinely deep null wants a fine
multi-variable optimisation (or real, near-field-coupled feedline conductors
in place of the ideal line). Treat F/B as "real but shallow" in this model.
"""

from antennaknobs import AntennaBuilder
from antennaknobs.network import Driven, Network, PortOnWire, TL, Wire
from types import MappingProxyType


class Builder(AntennaBuilder):
    default_params = MappingProxyType(
        {
            "design_freq": 28.57,
            "freq": 28.57,
            "base": 7.0,
            # Element half-lengths as fractions of a quarter wave (~half-wave
            # dipoles). Rear slightly longer, front slightly shorter -- the
            # small asymmetry that, with the phasing, sets up the F/B null.
            "rear_factor": 1.03,
            "front_factor": 0.99,
            # Element spacing as a fraction of a wavelength (~1/8 wl).
            "spacing_frac": 0.13,
            # Crossed phasing-line length as a fraction of a wavelength
            # (~= spacing -> ~45 deg electrical at VF = 1).
            "phasing_frac": 0.14,
            # Phasing-line characteristic impedance (ohm); modeled crossed.
            "z0": 50.0,
            "ui_params": MappingProxyType(
                {
                    "target_z0": 50.0,
                    "default_view": "xy",
                    "rear_factor": {
                        "min": 0.95,
                        "max": 1.08,
                    },
                    "front_factor": {
                        "min": 0.9,
                        "max": 1.03,
                    },
                    "spacing_frac": {
                        "min": 0.08,
                        "max": 0.2,
                    },
                    "phasing_frac": {
                        "min": 0.08,
                        "max": 0.25,
                    },
                }
            ),
        }
    )

    def build_wires(self):
        eps = 0.05
        wavelength = 299.792458 / self.design_freq
        quarter = 0.25 * wavelength

        spacing = self.spacing_frac * wavelength
        h_rear = quarter * self.rear_factor
        h_front = quarter * self.front_factor
        z = self.base

        def dipole(x, h, name):
            L = (x, -h, z)
            C0 = (x, -eps, z)
            C1 = (x, eps, z)
            R = (x, h, z)
            return [
                Wire(L, C0),
                Wire(C0, C1, name=name),
                Wire(C1, R),
            ]

        tups = []
        tups.extend(dipole(-spacing, h_rear, "rear"))
        tups.extend(dipole(0.0, h_front, "front"))
        return tups

    def build_network(self):
        wavelength = 299.792458 / self.design_freq
        length = self.phasing_frac * wavelength
        return Network(
            ports={"rear": PortOnWire("rear"), "front": PortOnWire("front")},
            # Crossed ("half-twist") phasing line between the two driven elements.
            branches=[
                TL(a="rear", b="front", z0=self.z0, length=length, transposed=True)
            ],
            sources=[Driven(port="front", voltage=1 + 0j)],
        )
