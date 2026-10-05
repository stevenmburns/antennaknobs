"""AK#1901 gate 2: the five-band fan dipole, five lengths <-> five resonances.

`fandipole:five_band` through the workbench's seam (`momwire_bands`), from
+/-5 % perturbed starts: ROOT (opt-in; does a root exist in the box?),
SEQUENTIAL (each band by its own length_factor), and the default SWR minimax
for comparison.
"""

import sys
import time

from antennaknobs.web.examples import example_for
from antennaknobs.web.optimize_bands import optimize_bands, parse_bands

ex = example_for("multiband.fandipole")
cls = ex.builder_cls
v = cls.five_band_params
bands_param = [dict(b) for b in v["bands"]]
freqs = [b["freq"] for b in bands_param]
req = {"geometry": "multiband.fandipole", "variant": "five_band", "bands": bands_param}
free = [
    {"name": f"bands.{i}.length_factor", "min": 0.40, "max": 0.55} for i in range(5)
]
spec = ",".join(f"{f}:res:knobs=bands.{i}.length_factor" for i, f in enumerate(freqs))
SPECS = {
    "root": parse_bands(spec),
    "sequential": parse_bands(spec),
    "minimax": parse_bands(",".join(str(f) for f in freqs)),
}


def sweep(r, fs):
    return ex.momwire_bands(r, fs)


out = sweep(req, freqs)
print("variant Z:", [f"{z:.1f}" for z in out["zs"][:, 0]], f"{out['solve_ms']:.0f} ms")

signs = [(+1, -1, +1, -1, +1), (-1, +1, -1, +1, -1), (+1, +1, +1, +1, +1)]
modes = sys.argv[1:] or ["root", "sequential", "minimax"]
for mode in modes:
    for sg in signs:
        start = [dict(b) for b in bands_param]
        for i, s in enumerate(sg):
            start[i]["length_factor"] *= 1 + 0.05 * s
        t0 = time.perf_counter()
        res = optimize_bands(
            {**req, "bands": start}, free, SPECS[mode], sweep_fn=sweep, mode=mode
        )
        dt = time.perf_counter() - t0
        print(
            f"[{mode}] start {sg}: {res['method']} converged={res['converged']} "
            f"root_status={res['root_status']} "
            f"evals={res['n_evals']} builds={res['n_solves']} "
            f"band-solves={res['n_freq_solves']} passes={res['passes']} "
            f"wall={dt:.1f}s antiresonant={res['antiresonant_bands']}"
        )
        for a, b in zip(res["bands_before"], res["bands_after"], strict=True):
            print(
                f"  {a['freq_mhz']:8.4f} MHz  X {a['z_im']:+9.3f} -> {b['z_im']:+.4f}"
                f"  R {b['z_re']:.2f}  SWR {a['swr']:.3f} -> {b['swr']:.4f}"
            )
        p = res["params"]
        print(
            "  factors",
            " ".join(f"{p[f'bands.{i}.length_factor']:.4f}" for i in range(5)),
            " variant",
            " ".join(f"{b['length_factor']:.4f}" for b in bands_param),
        )
