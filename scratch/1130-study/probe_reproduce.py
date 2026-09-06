"""AK#1130 step 1: reproduce the table before diagnosing anything."""

import warnings

warnings.filterwarnings("ignore")

from antennaknobs import far_field  # noqa: E402
from antennaknobs.designs.verticals.raised_vertical import Builder  # noqa: E402
from antennaknobs.engines.momwire import MomwireEngine  # noqa: E402
from antennaknobs.engines.pynec import PyNECEngine  # noqa: E402

for ground in ("pec", ("finite", 13.0, 0.005)):
    print(f"\n=== ground {ground} ===")
    rows = []
    for name, cls in (("momwire", MomwireEngine), ("nec2++", PyNECEngine)):
        b = Builder()
        eng = cls(b, ground=ground)
        z = complex(eng.impedance()[0])
        ff = eng.far_field()
        frac = far_field.radiated_fraction(ff)
        rows.append((name, z, ff.max_gain, frac))
        print(
            f"  {name:8s} Z {z.real:8.3f}{z.imag:+8.3f}j   "
            f"max gain {ff.max_gain:7.3f} dBi   radiated {frac:.4f}"
        )
    (_, zm, _, fm), (_, zp, _, fp) = rows
    print(f"  fraction ratio  nec2++/momwire = {fp / fm:.4f}")
    print(f"  R ratio         momwire/nec2++ = {zm.real / zp.real:.4f}")
    print(f"  eta*R           {fm * zm.real:.3f} vs {fp * zp.real:.3f}")
