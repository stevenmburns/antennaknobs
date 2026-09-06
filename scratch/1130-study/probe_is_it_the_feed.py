"""AK#1130 step 5: is nec2++'s low R general, or this deck's feed segment?

The deck feeds a ONE-SEGMENT 5 cm gap (lambda/420 at 14.27 MHz) whose lower
end is also a 4-way junction with two radials and the mast. NEC-2 is sensitive
to a short source segment at a junction. If nec2++ agrees with the others on a
plain dipole and only disagrees here, the cause is nameable and deck-side; if
it disagrees everywhere, it is the engine's own accounting.
"""

import warnings

import numpy as np

warnings.filterwarnings("ignore")

from antennaknobs import far_field  # noqa: E402
from antennaknobs.builder import AntennaBuilder  # noqa: E402
from antennaknobs.designs.verticals.raised_vertical import Builder  # noqa: E402
from antennaknobs.engines.momwire import MomwireEngine  # noqa: E402
from antennaknobs.engines.nec5 import NEC5Engine  # noqa: E402
from antennaknobs.engines.pynec import PyNECEngine  # noqa: E402
from antennaknobs.wire_catalog import Wire  # noqa: E402

ENGINES = (("momwire", MomwireEngine), ("nec2++", PyNECEngine), ("NEC-5", NEC5Engine))


class PlainDipole(AntennaBuilder):
    """No junction, no short gap: one wire, odd segment count, centre-fed."""

    default_params = {"freq": 14.27, "design_freq": 14.27, "half": 5.0}

    def build_wires(self):
        h = self.half
        return [Wire((-h, 0.0, 8.0), (h, 0.0, 8.0), 21, 1 + 0j)]


def row(label, b, ground):
    out = []
    for name, cls in ENGINES:
        try:
            eng = cls(b, ground=ground)
            z = complex(eng.impedance()[0])
            frac = far_field.radiated_fraction(eng.far_field())
            out.append((name, z, frac))
        except Exception as e:  # noqa: BLE001 - a probe; the reason is printed
            out.append((name, None, f"{type(e).__name__}: {str(e)[:40]}"))
    print(f"\n{label}")
    for name, z, frac in out:
        if z is None:
            print(f"  {name:8s} {frac}")
        else:
            print(f"  {name:8s} R {z.real:8.3f}  X {z.imag:+8.3f}  radiated {frac:.4f}")
    rs = [z.real for _, z, _ in out if z is not None]
    if len(rs) == 3:
        print(
            f"  spread on R: nec2++ vs momwire {100 * (rs[1] / rs[0] - 1):+.2f} %, "
            f"NEC-5 vs momwire {100 * (rs[2] / rs[0] - 1):+.2f} %"
        )


row(
    "plain centre-fed dipole over PEC (no junction, no short gap)", PlainDipole(), "pec"
)
row("raised_vertical over PEC (the issue's deck)", Builder(), "pec")

b = Builder()
print(
    f"\nthe issue deck's feed wire: {np.round(np.asarray(b.build_wires()[0][0]), 4)}"
    f" -> {np.round(np.asarray(b.build_wires()[0][1]), 4)}, n_seg="
    f"{b.build_wires()[0][2]}"
)
