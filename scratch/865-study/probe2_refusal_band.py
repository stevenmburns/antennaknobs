"""momwire#865 probe 2: the exact refusal band, and what NEC-5 does inside it.

momwire declines a band around the interface; the ladder showed it is
ASYMMETRIC (narrower above, wider below). This records each refusal in full
and samples NEC-5 finely through the band, because NEC-5 is the only engine
here that answers inside it and the shape of that answer is the evidence for
whether z = 0 is a removable limit or a real discontinuity.
"""

from antennaknobs.engines.momwire import MomwireEngine
from antennaknobs.engines.nec5 import NEC5Engine

import sys, pathlib  # noqa: E401

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
from probe1_z0_ladder import SOIL, at  # noqa: E402

print("=== momwire refusals in full ===")
for z in (
    0.0008,
    0.0005,
    0.0002,
    0.0,
    -0.0002,
    -0.0005,
    -0.001,
    -0.003,
    -0.005,
    -0.008,
):
    try:
        MomwireEngine(at(z), ground=SOIL).impedance()
        print(f"  h={z:+8.4f}  SERVED")
    except Exception as e:  # noqa: BLE001
        print(f"  h={z:+8.4f}  {type(e).__name__}: {' '.join(str(e).split())[:150]}")

print("\n=== NEC-5 through the band (momwire cannot answer here) ===")
print(f"{'h (mm)':>9s} {'h/a':>7s} {'R':>10s} {'X':>11s}")
fine = [
    3.0,
    2.0,
    1.5,
    1.0,
    0.7,
    0.5,
    0.3,
    0.1,
    -0.1,
    -0.3,
    -0.5,
    -0.7,
    -1.0,
    -1.5,
    -2.0,
    -3.0,
    -5.0,
    -10.0,
]
prev = prevmm = None
for mm in fine:
    z = mm / 1000.0
    try:
        zz = complex(NEC5Engine(at(z), ground=SOIL).impedance()[0])
        d = (
            f"   dR/dh {(zz.real - prev.real) / (mm - prevmm):+7.1f} ohm/mm"
            if prev
            else ""
        )
        print(f"{mm:9.2f} {abs(z) / 5e-4:7.1f} {zz.real:10.3f} {zz.imag:+11.3f}j{d}")
        prev, prevmm = zz, mm
    except Exception as e:  # noqa: BLE001
        print(
            f"{mm:9.2f} {abs(z) / 5e-4:7.1f}   {type(e).__name__}: {str(e).splitlines()[0][:50]}"
        )
