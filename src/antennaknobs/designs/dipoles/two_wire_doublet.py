"""One straight wire fed anywhere along it: the resonant splits, from the centre-fed half wave through the OCF and EFHW to the 1 λ doublet (AK#2037).

A QRZ thread ("The lengths required to turn a wire into a resonant dipole or
doublet") asks which splits of one 14 MHz wire into a long side L and a short
side M leave the feed resonant (X = 0), and finds the centre-fed half wave,
the OCF, the EFHW and the centre-fed 1-wavelength doublet on one family. The
knobs are the thread's own: L and M, in feet.

The "resonance map" draws X over (L, M) in free space; its X = 0 contour is
the thread's M-vs-L plot, two branches meeting in a hook near L = 33 ft:

- the low-R branch, a line from the centre-fed half wave (L = M, about 17 ft)
  down to the hook, walked by stepping L and holding M at resonance;
- the high-R branch, nearly vertical at L of about 33.6 ft from the hook up
  to the centre-fed doublet (L = M, about 33 ft), walked by stepping M and
  holding L. Each branch's Knobs view is that half of the thread's plot.

    o--------F==============================o      z = height, along y
    |<- M -->|<------------- L ------------>|

The feed is a knot: the two sides are separate wires meeting at F, and the
source is a series gap AT that junction (`PortAtVertex`), which is NEC-5's
own knot source. It serves on bs2, razor-2p and sinusoidal-galerkin. On the
high-R branch (a few kilohms) bs2 holds still under refinement and razor-2p
walks toward it at its usual first-order rate; sinusoidal-galerkin's point gap
there drifts by a few hundred ohms in X as the mesh refines, so read that
branch on bs2 or razor-2p. Measured 2026-10-23, free space, nominal_nsegs
15/30/60 at L = 33.6 ft, M = 6 ft:
bs2 3106.6-j309 / 3105.0-j324 / 3103.5-j336;
razor-2p 3085.4-j129 / 3099.4-j213 / 3103.7-j265;
SG 3121.1+j219 / 3138.4-j13 / 3132.6-j150.
"""

from types import MappingProxyType

from antennaknobs import AntennaBuilder, WireSpec
from antennaknobs import analyses as an
from antennaknobs.network import Driven, Network, PortAtVertex

FT = 0.3048  # metres per foot
# Copper #16 AWG (1.291 mm diameter): the thread's AutoEZ sheet uses copper
# loss, and #16 reproduces its table to about 0.3 % (#14 and #18 do not).
COPPER_16_AWG = WireSpec(radius=0.6452e-3, conductivity=5.8e7)


class Builder(AntennaBuilder):
    label = "Two-wire doublet (resonant splits)"

    default_params = MappingProxyType(
        {
            # The band, for the app's band selector and segment density. The
            # lengths below are absolute and do not scale with it.
            "design_freq": 14.0,
            "freq": 14.0,
            "long_ft": 17.066,  # L, the long side
            "short_ft": 17.066,  # M, the short side
            # Height only matters over ground; the analyses run in free space.
            "height": 10.0,
            "ui_params": MappingProxyType(
                {
                    "default_view": "yz",
                    "target_z0": 50.0,
                    "long_ft": {"min": 15.0, "max": 36.0},
                    "short_ft": {"min": 1.0, "max": 34.0},
                }
            ),
        }
    )

    def build_wire_material(self):
        return COPPER_16_AWG

    def build_wires(self):
        m_side = self.short_ft * FT
        l_side = self.long_ft * FT
        z = self.height
        # None meshes each side at the design density (nominal_nsegs per
        # quarter wave at design_freq), so both sides share a segment size.
        return [
            ((0.0, -m_side, z), (0.0, 0.0, z), None, None),
            ((0.0, 0.0, z), (0.0, l_side, z), None, None, "long"),
        ]

    def build_network(self):
        # The source sits at the knot where the two sides meet: a series gap
        # in the long side's connection to it (either side gives the same Z).
        return Network(
            ports={"feed": PortAtVertex("long", "p0")},
            branches=[],
            sources=[Driven(port="feed", voltage=1 + 0j)],
        )

    def build_analyses(self):
        splits = "Resonant splits"
        return [
            an.Analysis(
                "resonance map",
                (
                    an.Sweep("long_ft", 16.0, 36.0, points=41),
                    an.Sweep("short_ft", 1.0, 34.0, points=34),
                ),
                views=(an.Map(),),
                references=an.Ref(x=(0,)),
                ground="free",
                group=splits,
            ),
            # Step L from the centre-fed half wave toward the hook, holding M.
            an.Analysis(
                "low-R branch (dipole to OCF)",
                an.Sweep("long_ft", 17.066, 32.5, points=32),
                hold=an.Hold("resonance", adjust=("short_ft",)),
                views=(an.Rx(), an.Knobs()),
                ground="free",
                group=splits,
            ),
            # Step M down from the centre-fed doublet to the hook, holding L.
            # Downward on purpose: at M = 33 ft the only resonant L in the
            # knob's range is the doublet's, so the first solve lands on this
            # branch; at small M the low-R branch also has a root in range
            # (L about 30 ft at M = 4.5 ft), and a cold start there takes it.
            an.Analysis(
                "high-R branch (1-wavelength doublet to EFHW)",
                an.Sweep("short_ft", 33.0, 3.5, points=31),
                hold=an.Hold("resonance", adjust=("long_ft",)),
                views=(an.Rx(), an.Knobs()),
                ground="free",
                group=splits,
            ),
        ]
