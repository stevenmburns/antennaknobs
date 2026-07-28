"""SimNEC comparison, Track 2 (divergence): the common-mode "money shot".

Uses the BALANCED design wire.doublet_balanced_tuner (14.1 MHz, momwire/BSpline
only -- PortAtEnd arm-end feed is not supported on Sinusoidal yet).

Two findings, in two feed definitions:

1. FEED DEFINITION matters for the absolute baseline. The stock design feeds the
   doublet across a 0.04 lambda arm-end gap (PortAtEnd); SimNEC's NEC can only
   center-feed (a delta-gap on the middle segment). Shrinking the AntennaKNoBs
   feed gap toward zero converges the symmetric rig answer onto SimNEC's:

       center-fed AntennaKNoBs (0.004 lambda gap): 28.75 + j27.03  (SWR 2.41)
       center-fed SimNEC        (delta-gap):        28.95 + j25.18  (SWR 2.31)

   ~2 ohm apart -- the same agreement order as Track 1 (the residual is the
   delta-gap convergence caveat, handoff correction 3). Compare tools with the
   SAME feed definition; the arm-end 51.8 ohm / SWR 1.04 figure is a different
   (momwire-only) feedpoint and is NOT what SimNEC solves.

2. COMMON MODE is the divergence. Under a SYMMETRIC doublet the rig answer is
   BIT-IDENTICAL across line_zcomm (no common mode is excited) in EITHER feed
   definition -- so Scenario 3 must break symmetry. With one arm ~15% longer the
   rig answer MOVES with zcomm; SimNEC's single-ended differential cascade cannot
   follow it (one fixed number, no zcomm knob). That spread-vs-point contrast IS
   the result.

Run:  python scratch/simnec/track2_commonmode.py
"""

from antennaknobs.designs.wire.doublet_balanced_tuner import Builder
from antennaknobs.engines.momwire import MomwireEngine
from antennaknobs.network import Wire

# Feed-gap half-width as a wavelength factor. The stock design uses 0.02 (a
# 0.04 lambda arm-end gap); shrinking it toward 0 approaches a center-fed
# delta-gap. 0.002 (0.004 lambda) lands on SimNEC's center-fed value.
GAP_ARMEND = 0.02
GAP_CENTER = 0.002


def swr(z):
    g = abs((z - 50) / (z + 50))
    return (1 + g) / (1 - g)


class Doublet(Builder):
    """Same design with two instance knobs: ``_gap_factor`` (feed-gap half-width
    as a wavelength factor, default the stock 0.02 arm-end gap) and ``_asym``
    (right-arm length scale, to break symmetry).

    NB: do NOT give either knob a class-attribute default -- AntennaBuilder routes
    instance assignments through a custom __setattr__/__getattr__, and a class
    attribute shadows that routing (normal lookup succeeds, so the routed instance
    value is never seen). Set ``b._asym = ...`` / ``b._gap_factor = ...`` on the
    instance and read them with getattr and a literal default here."""

    def build_wires(self):
        wl = self.design_wavelength
        arm = 0.5 * self.length_factor * wl
        z = self.height_factor * wl
        gap = getattr(self, "_gap_factor", GAP_ARMEND) * wl
        asym = getattr(self, "_asym", 1.0)
        return [
            Wire((0.0, -gap, z), (0.0, -arm, z), name="armL"),
            Wire((0.0, gap, z), (0.0, arm * asym, z), name="armR"),
        ]


def rig(asym, zcomm, gap_factor):
    b = Doublet(dict(Builder.default_params, line_zcomm=zcomm))
    b._asym = asym
    b._gap_factor = gap_factor
    z = complex(MomwireEngine(b, ground=None).impedance()[0])
    return z, swr(z)


if __name__ == "__main__":
    for gap_factor, feed in (
        (GAP_ARMEND, "ARM-END feed (0.04 lambda gap, PortAtEnd — momwire-only)"),
        (GAP_CENTER, "CENTER-FED (0.004 lambda gap ≈ SimNEC delta-gap)"),
    ):
        print(f"##### {feed} #####")
        for asym, tag in (
            (1.0, "SYMMETRIC (null case: flat across zcomm; tools agree)"),
            (1.15, "ASYMMETRIC R+15% (the divergence SimNEC cannot follow)"),
        ):
            print(f"  --- {tag} ---")
            for zc in (25.0, 100.0, 250.0, 400.0):
                z, s = rig(asym, zc, gap_factor)
                print(
                    f"    line_zcomm={zc:5.0f}:  Z_rig = {z.real:7.2f} {z.imag:+7.2f} j   SWR = {s:6.3f}"
                )
        print()
    print("SimNEC side: build the differential cascade ONCE (450ohm line, balanced")
    print("L-tuner as one series 2.8uH + one shunt 74pF, 1:1 balun, 50ohm gen) and")
    print("record the single value (center-fed doublet -> ~28.95 + j25.18, SWR 2.31,")
    print("matching the CENTER-FED symmetric row above). It has no zcomm knob -> one")
    print("number vs the asymmetric spread above.")
