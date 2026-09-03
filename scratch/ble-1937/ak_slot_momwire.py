"""AK slot (buried_radial_vertical) at the NEC-5 Validation Manual App. B parameters, momwire bspline.
usage: ak_slot.py DEPTH RF N [N ...]"""

import math
import sys
import time
from antennaknobs.designs.verticals.buried_radial_vertical import Builder
from antennaknobs.engines.momwire import MomwireEngine

f = 1.0
eps = 15.0
sigma = 15.0 * 2 * math.pi * f * 1e6 * 8.8541878128e-12
depth = float(sys.argv[1])
rf = float(sys.argv[2])
for n in [int(x) for x in sys.argv[3:]]:
    p = dict(Builder.default_params)
    p.update(
        freq=f,
        design_freq=f,
        design_eps_r=eps,
        design_sigma=sigma,
        length_factor=1.0,
        radial_factor=rf,
        depth=depth,
        n_radials=n,
    )
    b = Builder(params=p)
    e = MomwireEngine(b, ground=("finite", eps, sigma), ground_z=0.0)
    t0 = time.perf_counter()
    try:
        z = e.impedance()
        print(
            f"depth={depth} rf={rf} N={n}: Z = {z}  {time.perf_counter() - t0:.1f}s",
            flush=True,
        )
    except Exception as ex:  # noqa: BLE001 — a probe: the refusal text IS the result
        print(
            f"depth={depth} rf={rf} N={n}: FAILED {type(ex).__name__}: {str(ex)[:300]}",
            flush=True,
        )
