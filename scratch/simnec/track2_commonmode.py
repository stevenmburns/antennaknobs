"""SimNEC comparison, Track 2 (divergence): the common-mode "money shot".

Uses the BALANCED design wire.doublet_balanced_tuner (14.1 MHz, momwire/BSpline
only -- PortAtEnd arm-end feed is not supported on Sinusoidal yet).

Key finding: under a SYMMETRIC doublet the rig answer is BIT-IDENTICAL across
line_zcomm (no common mode is excited) -- so the handoff doc's headline
Scenario 3 must break symmetry. With one arm ~15% longer, the rig answer MOVES
with zcomm; SimNEC's single-ended differential cascade cannot follow it (one
fixed number, no zcomm knob). That spread-vs-point contrast IS the result.

Run:  python scratch/simnec/track2_commonmode.py
"""
from antennaknobs.designs.wire.doublet_balanced_tuner import Builder
from antennaknobs.engines.momwire import MomwireEngine
from antennaknobs.network import Wire


def swr(z):
    g = abs((z - 50) / (z + 50))
    return (1 + g) / (1 - g)


class AsymBuilder(Builder):
    """Same design; right arm scaled by an ``_asym`` instance attribute to break
    symmetry. NB: do NOT give ``_asym`` a class-attribute default — AntennaBuilder
    routes instance assignments through a custom __setattr__/__getattr__, and a
    class attribute shadows that routing (normal lookup succeeds, so the routed
    instance value is never seen). Set ``b._asym = ...`` and read it with getattr."""

    def build_wires(self):
        wl = self.design_wavelength
        arm = 0.5 * self.length_factor * wl
        z = self.height_factor * wl
        gap = 0.02 * wl
        asym = getattr(self, "_asym", 1.0)
        return [
            Wire((0.0, -gap, z), (0.0, -arm, z), name="armL"),
            Wire((0.0, gap, z), (0.0, arm * asym, z), name="armR"),
        ]


def rig(asym, zcomm):
    b = AsymBuilder(dict(Builder.default_params, line_zcomm=zcomm))
    b._asym = asym
    z = complex(MomwireEngine(b, ground=None).impedance()[0])
    return z, swr(z)


if __name__ == "__main__":
    for asym, tag in ((1.0, "SYMMETRIC (null case: SimNEC and AntennaKNoBs agree)"),
                      (1.15, "ASYMMETRIC R+15% (the divergence SimNEC cannot follow)")):
        print(f"=== {tag} ===")
        for zc in (25.0, 100.0, 250.0, 400.0):
            z, s = rig(asym, zc)
            print(f"   line_zcomm={zc:5.0f}:  Z_rig = {z.real:7.2f} {z.imag:+7.2f} j   SWR = {s:6.3f}")
        print()
    print("SimNEC side: build the differential cascade ONCE (450ohm line, balanced")
    print("L-tuner as one series 2.8uH + one shunt 74pF, 1:1 balun, 50ohm gen) and")
    print("record the single value. It has no zcomm knob -> one number vs the spread above.")
