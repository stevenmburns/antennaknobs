"""AK#1025 probe 6: the fix, end to end through the wrapper.

Three things must hold at once: the wholly-buried class now tracks momwire,
the CONTACT class is unmoved (its bonded end still needs ground flag 1), and
above-ground decks are untouched.
"""

from antennaknobs import AntennaBuilder
from antennaknobs.engines.momwire import MomwireEngine
from antennaknobs.engines.nec5 import NEC5Engine
from antennaknobs.wire_catalog import Wire

SOIL = ("finite", 13.0, 0.005)


class Contact(AntennaBuilder):
    """The momwire#567 anchor class, as tests/test_nec5_engine.py spells it."""

    default_params = {"freq": 7.0}

    def build_wires(self):
        mono = Wire((0, 0, 10.0), (0, 0, 0.0), n_seg=14, ex=1 + 0j)
        return [mono] + [
            Wire((0, 0, -0.15), (5 * dx, 5 * dy, -0.15), n_seg=10)
            for dx, dy in ((1, 0), (0, 1), (-1, 0), (0, -1))
        ]


b = Contact()
eng = NEC5Engine(b, ground=SOIL)
ge = [ln for ln in eng.deck([7.0]).splitlines() if ln.startswith("GE")]
print(f"contact deck GE card: {ge}   (must stay ground-flag 1: it bonds at z=0)")
print(f"contact deck Z      : {complex(eng.impedance()[0]):.4f}")
print("   momwire#567 banked NEC-5 four-radial anchor: 90.0510-70.7310j")

print()
from antennaknobs.designs.specialty.buried_dipole import Builder  # noqa: E402

for depth in (0.15, 1.0, 2.0):
    b = Builder()
    b.depth = depth
    n5 = complex(NEC5Engine(b, ground=SOIL).impedance()[0])
    mw = complex(MomwireEngine(b, ground=SOIL).impedance()[0])
    dr = 100 * abs(n5.real - mw.real) / abs(mw.real)
    dx = 100 * abs(n5.imag - mw.imag) / abs(mw.imag)
    gecard = [
        ln
        for ln in NEC5Engine(b, ground=SOIL).deck([7.1]).splitlines()
        if ln.startswith("GE")
    ][0]
    print(f"buried_dipole depth {depth:4.2f} m  [{gecard}]")
    print(f"   NEC-5   {n5.real:10.4f}{n5.imag:+10.4f}j")
    print(
        f"   momwire {mw.real:10.4f}{mw.imag:+10.4f}j    dR {dr:5.2f}%  dX {dx:5.2f}%"
    )
