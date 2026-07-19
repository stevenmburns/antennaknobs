"""Terminated rhombic: a traveling-wave directional long-wire (L. B. Cebik,
W4RNL, "Long-Wire Antennas" / "The Terminated Vee-Beam and Rhombic").

Four long wires (each 1-4 wavelengths) arranged as a horizontal diamond. The
antenna is fed at one acute apex and TERMINATED at the opposite apex with a
non-inductive resistor (~600-800 ohm). The resistor absorbs the forward
traveling wave when it reaches the far apex, so almost no wave reflects back:
the current is a progressive (traveling) wave rather than a standing wave, and
the pattern is UNIDIRECTIONAL toward the terminated end. This is the catalog's
first non-resonant antenna -- its behaviour is set by wire length and the
termination, not by resonance, so it is inherently broadband (the driving-point
impedance stays near the termination value across a wide band).

The legs each make a small "tilt" angle with the main axis so that the
long-wire radiation lobes of the four legs add along the axis. Gain runs a few
dB over a dipole with a 10-15 dB front-to-back ratio; roughly half the input
power is dissipated in the terminating resistor (the price of the clean
unidirectional, broadband pattern).

Geometry, in the framework's (x, y, z) convention:
  - x : main axis; feed apex at x=0, terminated apex at x=2d; beam --> +x
  - y : transverse; the side apexes sit at (d, +/-w)
  - z : constant height `base` (a horizontal antenna over ground)
with d = L*cos(tilt), w = L*sin(tilt), L the leg length. Horizontally
polarised.

              (d, +w)
             /        \\
   feed --> 0          2d --> [R termination], beam --> +x
             \\        /
              (d, -w)
"""

from antennaknobs import AntennaBuilder
from antennaknobs.network import Driven, Load, Network, PortOnWire
import math
from types import MappingProxyType


class Builder(AntennaBuilder):
    default_params = MappingProxyType(
        {
            "design_freq": 28.57,
            "freq": 28.57,
            # Height above ground (a horizontal traveling-wave antenna).
            "base": 10.0,
            # Leg length as a fraction of a wavelength (each of the 4 legs).
            "leg_factor": 3.0,
            # Tilt angle (leg to main axis), degrees. Small -> long, narrow
            # diamond; tuned so the long-wire lobes add along the axis.
            "tilt_deg": 18.0,
            # Terminating resistance (ohm) at the far apex; absorbs the
            # forward wave to make the pattern unidirectional.
            "term_r": 700.0,
            "ui_params": MappingProxyType(
                {
                    # Driving-point impedance tracks the termination (~700 ohm),
                    # fed via open-wire line; reference SWR there.
                    "target_z0": 700.0,
                    "default_view": "xy",
                    "leg_factor": {
                        "min": 1.0,
                        "max": 5.0,
                        "step": 0.05,
                        "precision": 3,
                    },
                    "tilt_deg": {
                        "min": 8.0,
                        "max": 35.0,
                        "step": 0.5,
                        "precision": 2,
                    },
                    "term_r": {"min": 400.0, "max": 1000.0, "step": 10.0},
                }
            ),
        }
    )

    def build_wires(self):
        eps = 0.05  # half-gap at the feed / termination apexes
        wavelength = 299.792458 / self.design_freq
        quarter = 0.25 * wavelength

        L = self.leg_factor * wavelength
        tilt = math.radians(self.tilt_deg)
        d = L * math.cos(tilt)
        w = L * math.sin(tilt)
        z = self.base

        leg = self.segs_for(L, quarter)
        FU = (0.0, eps, z)  # feed apex, upper terminal
        FL = (0.0, -eps, z)  # feed apex, lower terminal
        SU = (d, w, z)  # upper side apex
        SD = (d, -w, z)  # lower side apex
        TU = (2 * d, eps, z)  # terminated apex, upper terminal
        TL = (2 * d, -eps, z)  # terminated apex, lower terminal

        return [
            # feed gap at the rear apex (driven via build_network)
            (FU, FL, self.segs_for(2 * eps, quarter), None, "feed"),
            # four legs
            (FU, SU, leg, None, None),  # rear upper
            (FL, SD, leg, None, None),  # rear lower
            (SU, TU, leg, None, None),  # front upper
            (SD, TL, leg, None, None),  # front lower
            # termination gap at the far apex (resistor via build_network)
            (TU, TL, self.segs_for(2 * eps, quarter), None, "term"),
        ]

    def build_network(self):
        return Network(
            ports={"feed": PortOnWire("feed"), "term": PortOnWire("term")},
            branches=[Load(port="term", r=self.term_r)],
            sources=[Driven(port="feed", voltage=1 + 0j)],
        )
