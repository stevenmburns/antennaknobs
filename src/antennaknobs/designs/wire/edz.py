"""Extended Double Zepp: 1.25 wl centre-fed doublet + series match (L. B.
Cebik, W4RNL).

The EDZ is a centre-fed doublet stretched to ~1.25 wavelengths -- Cebik's
"magic length": the LONGEST a centre-fed wire can get before the single
broadside lobe splits apart. Each arm is ~5/8 wl, so the current
distribution adds ~2-3 dB of broadside gain over a half-wave dipole
(~4.5-5 dBi free space) while the first off-axis sidelobes are only just
emerging. The same 1.25 wl number generates Cebik's 44'/88' doublets and,
stacked, the expanded lazy-H; the catalog's `lazy_h` and `w8jk` elements are
its shorter 1 wl cousins.

The price of the stretch is the feedpoint: past resonance the centre sits
well off 50 ohm with a large CAPACITIVE reactance -- Cebik quotes ~100-140
ohm and -j500-600 for typical builds; this model's wire at exactly 1.25 wl
reads ~150 -j800 ohm. Cebik's "Feeding the EDZ" catalogs the fixes -- ladder
line + tuner, a reactance-cancelling stub, or the one modelled here (the
scheme of WB4HFL's 10 m build): a short SERIES SECTION of parallel line
whose length rotates the feedpoint around the line's SWR circle to its
low-resistance crossing, for direct coax.

That the series line CAN match here is the instructive contrast with `zepp`
finding #2. An end-fed half wave reflects almost totally (|Gamma| ~ 1), so
its low-R crossing is a few ohms and no series line reaches 50 ohm. The EDZ
centre, mismatched as it looks, reflects at only |Gamma| ~ 0.84 against a
600 ohm line -- and the crossing Z0 * (1-|Gamma|)/(1+|Gamma|) ~ 53 ohm lands
almost exactly on coax (the catalog's `openwire-600`; WB4HFL's 450 ohm
window line put his thicker-wire build's crossing in the same place). At
~0.15 wl of line the model sees ~53 +0j ohm, and the match is narrow-band
(~600 kHz at 2:1 on 10 m -- matching WB4HFL's measured bandwidth), which the
SWR sweep shows off.

Geometry, in the framework's (x, y, z) convention:
  - y : the doublet axis (centre-fed, ~1.25 wl, along y)
  - z : constant height `base`
  - x : broadside; a slightly-split figure-8 with emerging ~50 deg sidelobes.
The matching section is an electrical element (a `TL` branch), not geometry.

    L=====================C===================R   z = base  (~1.25 wl doublet)
                          |
                          | series matching section (TL branch, z0_match)
                          S                       S = shack feed (virtual port)
"""

from antennaknobs import AntennaBuilder
from antennaknobs.network import Driven, Network, PortOnWire, PortVirtual, TL
from types import MappingProxyType


class Builder(AntennaBuilder):
    default_params = MappingProxyType(
        {
            "design_freq": 28.57,
            "freq": 28.57,
            "base": 10.0,
            # Doublet length as a fraction of a wavelength. 1.25 wl is the
            # EDZ proportion -- the longest centre-fed wire whose broadside
            # lobe has not yet split.
            "elem_frac": 1.25,
            # Series matching section: characteristic impedance (ohm) and
            # physical length as a fraction of a wavelength. ~600 ohm open
            # wire; the length is tuned so the shack sees the SWR circle's
            # low-resistance (~53 ohm) crossing.
            "z0_match": 600.0,
            "match_len_frac": 0.150,
            # Overall scale knob.
            "length_factor": 1.0,
            "ui_params": MappingProxyType(
                {
                    "target_z0": 50.0,
                    "default_view": "yz",
                    # Degenerate with elem_frac (length = elem_frac * wl *
                    # length_factor); pin length_factor and keep elem_frac,
                    # the curated ~1.25 wl knob.
                    "length_factor": {"hidden": True},
                    "elem_frac": {
                        "min": 0.9,
                        "max": 1.4,
                    },
                    "z0_match": {
                        "min": 200.0,
                        "max": 800.0,
                        "step": 1.0,
                        "precision": 1,
                    },
                    "match_len_frac": {
                        "min": 0.05,
                        "max": 0.45,
                    },
                }
            ),
        }
    )

    def build_wires(self):
        eps = 0.05
        wavelength = 299.792458 / self.design_freq
        quarter = 0.25 * wavelength

        length = self.elem_frac * wavelength * self.length_factor
        half = length / 2.0
        z = self.base

        L = (0.0, -half, z)
        C0 = (0.0, -eps, z)
        C1 = (0.0, eps, z)
        R = (0.0, half, z)
        arm = self.segs_for(half - eps, quarter)
        # Centre-fed doublet; the named centre gap "feed" is the antenna-side
        # port the matching section connects to (no direct voltage source).
        return [
            (L, C0, arm, None, None),
            (C0, C1, 1, None, "feed"),
            (C1, R, arm, None, None),
        ]

    def build_network(self):
        wavelength = 299.792458 / self.design_freq
        match_len = self.match_len_frac * wavelength
        return Network(
            ports={
                "feed": PortOnWire("feed"),  # doublet centre
                "shack": PortVirtual("shack"),  # bottom of the series section
            },
            branches=[
                TL(a="shack", b="feed", z0=self.z0_match, length=match_len),
            ],
            sources=[Driven(port="shack", voltage=1 + 0j)],
        )
