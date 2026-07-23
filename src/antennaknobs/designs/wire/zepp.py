"""End-fed half-wave "Zepp" with a tuned-stub feeder (L. B. Cebik, W4RNL).

The Zeppelin antenna is a half-wave radiator fed at ONE END through a section
of open-wire "tuned feeder". The end of a half-wave sits at a current MINIMUM /
voltage MAXIMUM, so the driving-point impedance there is very HIGH (thousands of
ohms) and strongly reactive; the quarter-wave-ish stub transforms that down to
something a rig can drive. The radiator is HORIZONTALLY POLARISED with the usual
half-wave dipole pattern (the feeder is meant to be non-radiating).

This is the IDEAL-TRANSMISSION-LINE cousin of the catalog's `jpole`, and the
contrast is the point. `jpole` builds the matching stub as PHYSICAL parallel
wires (real geometry, modelled by the MoM solver), whereas here the feeder is an
IDEAL series `TL` network branch from the antenna's end port to a virtual shack
port. That makes the Zepp a deliberate METHODOLOGY PROBE with two findings:

  1. Feeding the network layer at a near-OPEN antenna port (a current null) is
     ILL-CONDITIONED: the bare end impedance varies ~2x between solver bases
     (e.g. ~2900 -19900j ohm on NEC2/sinusoidal vs ~1400 -13700j on the rooftop
     bases) -- the same current-null hazard as `bobtail`'s and `bruce`'s feeds.
     The series stub transforms that spread along with the impedance: the shack
     R agrees across bases but the shack REACTANCE inherits the spread.
  2. A LOSSLESS line preserves the reflection magnitude, and an end-fed half
     wave is nearly total reflection, so NO single series feeder length can
     bring the shack impedance near 50 ohm -- it only rotates around the rim of
     the Smith chart (R stays a few ohms, X swings through +/- a kilohm). The
     historical Zepp ran its tuned feeders to an antenna TUNER for exactly this
     reason; a coax-direct match needs a PARALLEL shorted stub, which is what
     `jpole` realises in physical wire. We model the honest tuner-fed feeder.

As always the radiator's GAIN and PATTERN are basis-stable (~2.1 dBi dipole);
the transformed feed impedance is indicative and tuner-fed, not a 50 ohm match.

Geometry, in the framework's (x, y, z) convention:
  - y : the half-wave radiator axis (end-fed at y = 0, open at y = +half)
  - z : constant height `base`
  - x : broadside (figure-8 dipole pattern)
The tuned feeder is an electrical element (a `TL` branch), not geometry.

    F=========================================>   z = base  (half-wave radiator)
    |  (end feed, high-Z voltage antinode)
    | tuned stub (TL branch, z0_stub)
    S                                              S = shack feed (virtual port)
"""

from antennaknobs import AntennaBuilder
from antennaknobs.network import Driven, Network, PortOnWire, PortVirtual, TL, Wire
from types import MappingProxyType


class Builder(AntennaBuilder):
    default_params = MappingProxyType(
        {
            "design_freq": 28.57,
            "freq": 28.57,
            "base": 10.0,
            # Radiator length as a fraction of a wavelength (~half wave).
            "length_frac": 0.48,
            # Tuned-stub feeder: characteristic impedance (ohm) and physical
            # length as a fraction of a wavelength. A ~quarter-wave high-Z stub
            # transforms the very high end impedance down toward the rig.
            "z0_stub": 600.0,
            "stub_len_frac": 0.25,
            "length_factor": 1.0,
            "ui_params": MappingProxyType(
                {
                    "target_z0": 50.0,
                    "default_view": "yz",
                    # Degenerate with length_frac (length = length_frac * wl *
                    # length_factor); pin length_factor and keep length_frac, the
                    # curated knob.
                    "length_factor": {"hidden": True},
                    "length_frac": {
                        "min": 0.40,
                        "max": 0.55,
                    },
                    "z0_stub": {
                        "min": 300.0,
                        "max": 800.0,
                        "step": 1.0,
                        "precision": 1,
                    },
                    "stub_len_frac": {
                        "min": 0.1,
                        "max": 0.45,
                    },
                }
            ),
        }
    )

    def build_wires(self):
        eps = 0.05
        wavelength = 299.792458 / self.design_freq

        length = self.length_frac * wavelength * self.length_factor
        z = self.base

        # End feed: a short named gap "ant" at y=0 (the open end / voltage
        # antinode), then the half-wave radiator running out to y=+length.
        # No direct voltage source -- the tuned stub drives this port.
        return [
            Wire((0.0, 0.0, z), (0.0, eps, z), name="ant"),
            Wire((0.0, eps, z), (0.0, length, z)),
        ]

    def build_network(self):
        wavelength = 299.792458 / self.design_freq
        stub_len = self.stub_len_frac * wavelength
        return Network(
            ports={
                # high-Z end of the radiator; distributed = the port is the
                # named wire's fixed physical extent, so the readout no
                # longer jumps when the mesh subdivides it (issue #477)
                "ant": PortOnWire("ant", distributed=True),
                "shack": PortVirtual("shack"),  # bottom of the tuned stub
            },
            branches=[
                TL(a="shack", b="ant", z0=self.z0_stub, length=stub_len),
            ],
            sources=[Driven(port="shack", voltage=1 + 0j)],
        )
