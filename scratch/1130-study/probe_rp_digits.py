"""AK#1130 step 2: which RP digits is the gain being read under?

`_collect_pattern` issues `rp_card(0, n_theta, n_phi+1, 0, 5, 0, 0, 0, 0, ...)`.
On NEC's RP card the four digits after the counts are XNDA: output format,
NORMALIZATION, D (0 = power gain, 1 = directive gain) and A (averaging). The
shipped call therefore asks for N=5 -- "normalize total gain" -- and D=0.

If `get_gain` hands back the NORMALIZED number, the fraction is being computed
from a rescaled pattern, which would explain an excess that tracks nothing
physical. This sweeps N and D and reports the fraction each way.
"""

import warnings

import numpy as np

warnings.filterwarnings("ignore")

from antennaknobs import far_field  # noqa: E402
from antennaknobs.designs.verticals.raised_vertical import Builder  # noqa: E402
from antennaknobs.engines.pynec import PyNECEngine  # noqa: E402
from antennaknobs.engine import FarField  # noqa: E402

N_THETA, N_PHI, DTH, DPH = 90, 360, 1, 1


def pattern(norm, d_digit):
    eng = PyNECEngine(Builder(), ground="pec")
    eng._set_freq_and_execute()
    eng.c.rp_card(0, N_THETA, N_PHI + 1, 0, norm, d_digit, 0, 0, 0, DTH, DPH, 0, 0)
    thetas = np.linspace(0, 90 - DTH, N_THETA)
    phis = np.linspace(0, 360, N_PHI + 1)
    rings = [
        [eng.c.get_gain(0, ti, pi) for pi, _ in enumerate(phis)]
        for ti, _ in enumerate(thetas)
    ]
    ff = FarField(
        rings=rings,
        max_gain=eng.c.get_gain_max(0),
        min_gain=eng.c.get_gain_min(0),
        thetas=thetas,
        phis=phis,
    )
    return far_field.radiated_fraction(ff), ff.max_gain


print("N = normalization digit, D = 0 power gain / 1 directive gain")
print(f"{'N':>3s} {'D':>3s}  {'radiated':>10s}  {'max gain dBi':>13s}")
for norm in (0, 5):
    for d in (0, 1):
        try:
            frac, mx = pattern(norm, d)
            print(f"{norm:3d} {d:3d}  {frac:10.4f}  {mx:13.3f}")
        except Exception as e:  # noqa: BLE001 - a probe; the reason is printed
            print(f"{norm:3d} {d:3d}  {type(e).__name__}: {str(e)[:50]}")
