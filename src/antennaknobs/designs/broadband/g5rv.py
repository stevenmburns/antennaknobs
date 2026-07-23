"""G5RV doublet with a matched-line section (analysed at length by L. B. Cebik,
W4RNL, "The G5RV Antenna").

The G5RV is NOT a resonant antenna in the usual sense: it is a flat-top doublet
about 1.5 wavelengths long on its design band, fed not directly but through a
fixed section of high-impedance PARALLEL LINE that acts as an impedance
TRANSFORMER. At the design band the doublet's centre impedance (a few tens to a
couple hundred ohms, reactive) is converted by the line section to something a
coax + tuner can live with; the "match" is really a compromise that the line
length is chosen to make tolerable across several bands at once. Cebik's
analyses stressed two truths the model should show: the flat-top GAIN and
PATTERN are those of a 1.5 wl doublet (a HORIZONTALLY POLARISED multi-lobe
broadside pattern, a few dB over a dipole), while the feedpoint impedance seen
at the bottom of the line is a strong function of the line section and is the
part everyone argues about.

This fills the "matched-line / impedance-transformer feed" gap and is a
methodology stress case for the network layer: a single ideal transmission-line
branch (a real PortOnWire at the doublet centre, a virtual port at the shack)
feeding a NON-resonant, reactive antenna port. The driving-point impedance the
engines report is the SHACK-side impedance after the line transforms the
doublet -- a direct test of the network reducer's TL + virtual-port reduction
against PyNEC's tl_card.

Geometry, in the framework's (x, y, z) convention:
  - y : the flat-top axis (centre-fed doublet, ~1.5 wl, along y)
  - z : constant height `base`
  - x : broadside; the 1.5 wl doublet has a multi-lobe broadside pattern.
The matching line is an electrical element (a network branch), not geometry.

    L=====================C===================R   z = base  (~1.5 wl doublet)
                          |
                          | matched line section (TL branch, z0_match)
                          S                       S = shack feed (virtual port)
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
            # Flat-top length as a fraction of a wavelength. ~1.5 wl is the
            # classic G5RV proportion (a centre current maximum -> moderate,
            # reactive centre impedance the line then transforms).
            "top_frac": 1.5,
            # Matched parallel-line section: characteristic impedance (ohm) and
            # physical length as a fraction of a wavelength. ~450 ohm window
            # line; the length is the knob that sets the shack-side impedance.
            "z0_match": 450.0,
            # Just off a half wave: a real G5RV's design-band section is ~lambda/2
            # (it ~repeats the doublet's centre impedance up to the shack), but
            # an IDEAL lossless line is singular at exactly k*lambda/2, so the
            # model sits a hair below it (see module docstring).
            "match_len_frac": 0.46,
            # Overall scale knob.
            "length_factor": 1.0,
            "ui_params": MappingProxyType(
                {
                    "target_z0": 50.0,
                    "default_view": "yz",
                    # Degenerate with top_frac (top = top_frac * wl *
                    # length_factor); pin length_factor and keep top_frac, the
                    # curated ~1.5 wl knob.
                    "length_factor": {"hidden": True},
                    "top_frac": {
                        "min": 1.0,
                        "max": 2.0,
                    },
                    "z0_match": {
                        "min": 200.0,
                        "max": 600.0,
                        "step": 1.0,
                        "precision": 1,
                    },
                    "match_len_frac": {
                        "min": 0.1,
                        "max": 0.9,
                    },
                }
            ),
        }
    )

    def build_wires(self):
        eps = 0.05
        wavelength = 299.792458 / self.design_freq

        top = self.top_frac * wavelength * self.length_factor
        half = top / 2.0
        z = self.base

        L = (0.0, -half, z)
        C0 = (0.0, -eps, z)
        C1 = (0.0, eps, z)
        R = (0.0, half, z)
        # Centre-fed doublet; the named centre gap "feed" is the antenna-side
        # port the matched line connects to (no direct voltage source here).
        return [
            Wire(L, C0),
            Wire(C0, C1, name="feed"),
            Wire(C1, R),
        ]

    def build_network(self):
        wavelength = 299.792458 / self.design_freq
        match_len = self.match_len_frac * wavelength
        return Network(
            ports={
                "feed": PortOnWire("feed"),  # doublet centre
                "shack": PortVirtual("shack"),  # bottom of the matched line
            },
            branches=[
                TL(a="shack", b="feed", z0=self.z0_match, length=match_len),
            ],
            sources=[Driven(port="shack", voltage=1 + 0j)],
        )
