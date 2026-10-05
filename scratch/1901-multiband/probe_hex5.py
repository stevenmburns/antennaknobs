"""AK#1901 gate 3: hexbeam_5band on its per-band shape knobs (halfdriver_factor,
t0_factor per band: 10 knobs).

(a) multi-feed (daisy_chain False): band i read at feed i; (b) the one-coax
TL-jumper form (daisy_chain True): every band read at feed 0. Each starts from
`opt` and is compared with the variant tuned for that form (`opt_coupled` for
(a), which scripts/tune_hexbeam_5band_coupled.py made by minimising |Z - z0|
per band on PyNEC, not by root-finding; `opt_physical` for (b)), on momwire
in free space, through the workbench's seam (`momwire_bands`).

Forms: the default SWR minimax; ROOT on match_z0 (opt-in: does a root exist
in the box?); SEQUENTIAL on match_z0 (each band by its own two knobs, as the
script tuned it).

    python probe_hex5.py [multi|coax]:[minimax|root|sequential] ...
"""

import sys
import time

from antennaknobs.web.examples import example_for
from antennaknobs.web.optimize_bands import optimize_bands, parse_bands

ex = example_for("multiband.hexbeam_5band")
cls = ex.builder_cls
KNOBS = ("halfdriver_factor", "t0_factor")


def sweep(r, fs):
    return ex.momwire_bands(r, fs)


def swr(z):
    g = abs((z - 50) / (z + 50))
    return (1 + g) / (1 - g)


def req_for(variant, daisy):
    bp = [dict(b) for b in getattr(cls, f"{variant}_params")["bands"]]
    return {
        "geometry": "multiband.hexbeam_5band",
        "variant": variant,
        "bands": bp,
        "daisy_chain": daisy,
    }, bp


def band_spec(freqs, daisy, objective):
    return ",".join(
        f"{f}:{objective}:feed={0 if daisy else i}:knobs="
        + "+".join(f"bands.{i}.{k}" for k in KNOBS)
        for i, f in enumerate(freqs)
    )


free = [
    {
        "name": f"bands.{i}.{k}",
        "min": 0.05 if k == "t0_factor" else 0.9,
        "max": 0.30 if k == "t0_factor" else 1.2,
    }
    for i in range(5)
    for k in KNOBS
]
args = sys.argv[1:] or [
    "multi:minimax",
    "multi:root",
    "multi:sequential",
    "coax:minimax",
    "coax:root",
    "coax:sequential",
]
for arg in args:
    form, mode = arg.split(":")
    daisy = form == "coax"
    ref = "opt_physical" if daisy else "opt_coupled"
    req0, bp = req_for("opt", daisy)
    freqs = [b["freq"] for b in bp]
    feeds = [0 if daisy else i for i in range(5)]
    reqr, _ = req_for(ref, daisy)
    zr = sweep(reqr, freqs)["zs"]
    zref = [zr[k, fd] for k, fd in enumerate(feeds)]
    print(
        f"== {form}: reference {ref}: |Z-50| "
        + " ".join(f"{abs(z - 50):.2f}" for z in zref)
        + "  SWR "
        + " ".join(f"{swr(z):.3f}" for z in zref)
        + f"  (worst SWR {max(swr(z) for z in zref):.3f})"
    )
    bands = parse_bands(band_spec(freqs, daisy, "swr" if mode == "minimax" else "z0"))
    t0 = time.perf_counter()
    res = optimize_bands(req0, free, bands, sweep_fn=sweep, mode=mode, max_evals=400)
    dt = time.perf_counter() - t0
    print(
        f"[{form} {mode}] {res['method']} converged={res['converged']} "
        f"root_status={res['root_status']} ({res['root_reason']}) "
        f"evals={res['n_evals']} builds={res['n_solves']} "
        f"band-solves={res['n_freq_solves']} passes={res['passes']} wall={dt:.1f}s"
    )
    for a, b in zip(res["bands_before"], res["bands_after"], strict=True):
        za, zb = complex(a["z_re"], a["z_im"]), complex(b["z_re"], b["z_im"])
        print(
            f"  {a['freq_mhz']:8.4f} MHz feed {a['feed']} |Z-50| "
            f"{abs(za - 50):7.3f} -> {abs(zb - 50):7.4f}  SWR {a['swr']:.3f} -> "
            f"{b['swr']:.4f}  Z {b['z_re']:.2f}{b['z_im']:+.2f}j"
        )
    print(
        f"  worst SWR {res['worst_swr_before']:.4f} -> {res['worst_swr_after']:.4f}"
        f"; J {res['objective_before']:.4f} -> {res['objective_after']:.4f} "
        f"(w={res['mean_weight']}, worst {res['objective_worst_after']:.4f}, "
        f"mean {res['objective_mean_after']:.4f})"
    )
    p = res["params"]
    for i in range(5):
        print(
            f"  band {i}: " + " ".join(f"{k}={p[f'bands.{i}.{k}']:.5f}" for k in KNOBS)
        )
