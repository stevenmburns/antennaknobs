"""AK#1901 gates 1 and 5: the two-band fan dipole.

Through the workbench's own seam (`example_for(...).momwire_bands`, the
function /optimize's multi-band evals call).

1. ROOT (opt-in): resonance at both band frequencies on the two band lengths,
   from starts +/-5 % off a catalog variant. `current_physical` is the one
   variant resonant on momwire at today's geometry (X -1.8 / -3.2 ohm at its
   26.6 / 29.3 MHz); the s* variants were tuned under an older model and read
   up to 2 kohm off at their own frequencies, so s015 is run too, as the start
   that sits beside a parallel resonance. The default form (SWR minimax) on
   the same starts for comparison.
5. MINIMAX with ONE shared knob (the feed split `s`) for two SWR bands, at
   mean_weight 0, 0.2 and 0.5 (the default): the worst-band SWR reported must
   be the max of the per-band SWRs read.
"""

import time

from antennaknobs.web.examples import example_for
from antennaknobs.web.optimize_bands import optimize_bands, parse_bands

ex = example_for("multiband.twoband_fan_dipole")
cls = ex.builder_cls


def sweep(r, freqs):
    return ex.momwire_bands(r, freqs)


def line(res, dt):
    return (
        f"{res['method']} converged={res['converged']} "
        f"root_status={res['root_status']} evals={res['n_evals']} "
        f"builds={res['n_solves']} wall={dt:.2f}s"
    )


for variant in ("current_physical", "s015"):
    v = getattr(cls, f"{variant}_params")
    bands_param = [dict(b) for b in v["bands"]]
    len12, len10 = bands_param[0]["length"], bands_param[1]["length"]
    f12, f10 = bands_param[0]["freq"], bands_param[1]["freq"]
    req = {
        "geometry": "multiband.twoband_fan_dipole",
        "variant": variant,
        "bands": bands_param,
    }
    out = sweep(req, [f12, f10])
    print(f"== {variant}: Z at {f12}/{f10} MHz:", out["zs"][:, 0])
    free = [
        {"name": "bands.0.length", "min": 3.0, "max": 7.0},
        {"name": "bands.1.length", "min": 3.0, "max": 7.0},
    ]
    for s12, s10 in ((+1, -1), (-1, +1), (+1, +1), (-1, -1)):
        start = [dict(b) for b in bands_param]
        start[0]["length"] = len12 * (1 + s12 * 0.05)
        start[1]["length"] = len10 * (1 + s10 * 0.05)
        r = {**req, "bands": start}
        for mode, spec in (
            ("root", f"{f12}:res,{f10}:res"),
            ("minimax", f"{f12},{f10}"),
        ):
            t0 = time.perf_counter()
            res = optimize_bands(r, free, parse_bands(spec), sweep_fn=sweep, mode=mode)
            dt = time.perf_counter() - t0
            print(f"start {s12:+d}/{s10:+d} 5 % [{mode}]: {line(res, dt)}")
            for a, b in zip(res["bands_before"], res["bands_after"], strict=True):
                print(
                    f"  {a['freq_mhz']:6.2f} MHz  Z {a['z_re']:.1f}{a['z_im']:+.1f}j"
                    f" -> {b['z_re']:.2f}{b['z_im']:+.4f}j  SWR {a['swr']:.3f} -> "
                    f"{b['swr']:.4f}"
                )
            p = res["params"]
            print(
                f"  lengths {p['bands.0.length']:.4f} / {p['bands.1.length']:.4f}  "
                f"(variant {len12} / {len10})"
            )

print("== gate 5: one shared knob (s), two SWR bands, current_physical")
v = cls.current_physical_params
bp = [dict(b) for b in v["bands"]]
req = {"geometry": "multiband.twoband_fan_dipole", "variant": "current_physical"}
for w in (0.0, 0.2, 0.5):
    t0 = time.perf_counter()
    res = optimize_bands(
        {**req, "bands": bp, "s": 0.4},
        [{"name": "s", "min": 0.05, "max": 0.8}],
        parse_bands(f"{bp[0]['freq']},{bp[1]['freq']}"),
        sweep_fn=sweep,
        mean_weight=w,
    )
    dt = time.perf_counter() - t0
    per = [r["swr"] for r in res["bands_after"]]
    print(
        f"w={w}: {line(res, dt)} s={res['params']['s']:.4f} per-band SWR "
        + " ".join(f"{x:.4f}" for x in per)
        + f" | worst {res['objective_worst_after']:.4f} mean "
        f"{res['objective_mean_after']:.4f} J {res['objective_after']:.4f} "
        f"| worst_swr_after {res['worst_swr_after']:.4f} == max(per) "
        f"{res['worst_swr_after'] == max(per)}"
    )
