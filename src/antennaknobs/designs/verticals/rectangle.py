"""Rectangle "magnetic slot" SCV: a flattened 1 wl loop (L. B. Cebik, W4RNL).

From Cebik's "SCVs: A Family Album" -- the same self-contained-vertical
family as the catalog's `half_square`, `bobtail`, `bruce`, and
`right_angle_delta`: 1 wl wire shapes that park their current maxima in
vertical wire sections, so the verticals' fields add (vertically polarised,
low takeoff, no radials) while the horizontal members largely cancel.

This member is the 1 wl loop flattened into a wide, short rectangle --
Cebik's 40 m numbers are 56' x 12.8' (~0.41 x 0.09 wl), fed at the CENTRE of
one short vertical side. The squashed proportions put both short sides'
current maxima to work and buy gain: 4.4 dBi free space, second only to the
half-square's 4.6 in the family album. This model reads ~5.1 vs its own
half-square's 4.9 -- it runs the whole family a few tenths hot and flips
Cebik's 0.2 dB ordering, but the robust claim survives: the two are the
family's top pair, over a dB clear of the delta. The "magnetic slot" name is
the marketing physics Cebik was debunking -- it behaves as a plain loop SCV,
no exotic mode.

The price is the feedpoint: flattening the loop drops the mid-side feed to
~15 ohm (Cebik's figure; this wire reads ~13 at length_factor 1.0325). Cebik
suggests voltage feed via a tapped parallel-tuned circuit; the
transmission-line fix modelled here is a QUARTER-WAVE TRANSFORMER of low-Z
line -- two paralleled 50 ohm coaxes make z0 ~ 25 ohm, and 25^2/13.1 lands
~48 ohm at the shack (this model: SWR 1.05, dead resonant). The
instructive contrast with `wire.edz`: the EDZ's series line works by
ROTATION around the SWR circle to its low-R crossing; here the feed is
already near-resonant, so the quarter-wave section is the classic R-SCALING
transformer (z_shack = z0^2 / z_feed) instead.

Extensions Cebik also modelled, worth knowing: the Double Magnetic Slot
(paralleled loops with a Mobius crossing; 4.7 dBi, a friendlier 80 ohm) and
the end-fed Open Double Slot (110.8' x 11.1'; 5.7 dBi, 30 ohm).

Geometry, in the framework's (x, y, z) convention:
  - y : the long horizontal wires run along y
  - z : height; bottom wire at `base`, top wire ~0.09 wl higher
  - x : broadside; bidirectional off +/- x with end-on rejection
The structure is planar in x = 0. The matching section is an electrical
element (a `TL` branch), not geometry.

    D===================================C   z = base + v  (top, ~0.41 wl)
    F                                   |
    |                                   |   F = feed, centre of the left
    A===================================B   z = base       short side
    :
    : quarter-wave low-Z section (TL branch, z0_match)
    S                                       S = shack feed (virtual port)
"""

from antennaknobs import AntennaBuilder
from antennaknobs.network import Driven, Network, PortOnWire, PortVirtual, TL, Wire
from types import MappingProxyType


class Builder(AntennaBuilder):
    default_params = MappingProxyType(
        {
            "design_freq": 28.57,
            "freq": 28.57,
            # Height of the bottom wire above ground. Low, like the other
            # SCVs: the short vertical sides do the work.
            "base": 3.0,
            # Long (horizontal) side as a fraction of a wavelength; Cebik's
            # 56' on 40 m.
            "horiz_frac": 0.407,
            # Short (vertical) side as a fraction of a wavelength; Cebik's
            # 12.8' -- the flattening that trades feed R for gain.
            "vert_frac": 0.093,
            # Quarter-wave transformer: characteristic impedance (ohm) and
            # physical length as a fraction of a wavelength. ~25 ohm is two
            # paralleled 50 ohm coaxes; sqrt(14 * 50) ~ 26 would be exact.
            "z0_match": 25.0,
            "match_len_frac": 0.25,
            # Overall scale knob; 1.0325 is resonance (X ~ 0 at the bare
            # feed) for this segmentation.
            "length_factor": 1.0325,
            "ui_params": MappingProxyType(
                {
                    "target_z0": 50.0,
                    "default_view": "yz",
                    "length_factor": {
                        "min": 0.9,
                        "max": 1.1,
                    },
                    "z0_match": {
                        "min": 10.0,
                        "max": 75.0,
                        "step": 0.5,
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
        wavelength = 299.792458 / self.design_freq
        lf = self.length_factor

        w = self.horiz_frac * wavelength * lf
        v = self.vert_frac * wavelength * lf
        half_w = w / 2
        zb = self.base
        zt = zb + v

        A = (0.0, -half_w, zb)  # bottom-left
        B = (0.0, half_w, zb)  # bottom-right
        C = (0.0, half_w, zt)  # top-right
        D = (0.0, -half_w, zt)  # top-left

        # Feed gap centred on the LEFT short side -- the current maximum.
        pe = 0.1  # feed-edge length, m
        F0 = (0.0, -half_w, zb + (v - pe) / 2)
        F1 = (0.0, -half_w, zb + (v + pe) / 2)

        return [
            # Left short side: bottom corner -> feed edge -> top corner.
            Wire(A, F0),
            Wire(F0, F1, name="feed"),
            Wire(F1, D),
            # Top, right side, and bottom close the loop.
            Wire(D, C),
            Wire(C, B),
            Wire(B, A),
        ]

    def build_network(self):
        wavelength = 299.792458 / self.design_freq
        return Network(
            ports={
                "feed": PortOnWire("feed"),  # centre of the left short side
                "shack": PortVirtual("shack"),  # bottom of the transformer
            },
            branches=[
                TL(
                    a="shack",
                    b="feed",
                    z0=self.z0_match,
                    length=self.match_len_frac * wavelength,
                ),
            ],
            sources=[Driven(port="shack", voltage=1 + 0j)],
        )
