"""Which ingredient of the diffracted composer takes ~2 dB off the downhill comb
on the 400 m hill? Ablation through the composer's debug hook
(`terrain_utd._debug_skip`) and a filter on the reflection list:

  full        shadowed direct + tilted-mirror reflections (single + double) + UTD
  no-diff     the same without the wedge diffraction terms
  singles     no-diff, and only SINGLE reflections (the toe's double bounce removed)
  direct      shadowed direct radiation alone

against the specular page (horizontal-mirror facets, no shadowing). The
impedance solve is identical in every case; only the far-field composition
changes, so the variants share one solve through the engine.
"""

import os
import pathlib
import sys

import matplotlib

matplotlib.use("Agg")

import matplotlib.pyplot as plt  # noqa: E402
import numpy as np  # noqa: E402

HERE = pathlib.Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

import probe12_mike_hill_ladder as p12  # noqa: E402
from antennaknobs import terrain_utd as utd  # noqa: E402
from probe10_mike_elevation_figure import GRID, INK, INK2, MUTED  # noqa: E402
from probe11_mike_long_hillside import RMAX, RMIN, facet_line  # noqa: E402

H = 400.0
MARKS = (3, 5, 10, 15, 20, 25, 30, 35, 40, 45, 60, 75)
VARIANTS = ("full", "no-diff", "singles", "direct")
COLORS = {
    "specular": "#d97706",
    "full": "#2563eb",
    "no-diff": "#16a34a",
    "singles": "#9333ea",
    "direct": "#6b7280",
}


def solve_variant(cache, name):
    import dataclasses

    from antennaknobs.engines.momwire import MomwireEngine
    from probe9_mike_hillside import mike_terrain

    def make():
        p12.probe9.N_FACETS = p12.N_FACETS
        terrain = mike_terrain(H, p12.SLOPE, p12.F_MAST)
        terrain = dataclasses.replace(terrain, diffraction=True)
        e = MomwireEngine(
            p12.PlumbVerticalSurfaceRadials(), ground=("terrain", terrain)
        )
        skip = {
            "no-diff": {"diff"},
            "singles": {"diff"},
            "direct": {"refl", "diff"},
        }.get(name, set())
        orig = utd.reflections
        try:
            utd._debug_skip = skip
            if name == "singles":
                utd.reflections = lambda *a, **k: [
                    r for r in orig(*a, **k) if len(r.planes) == 1
                ]
            return e.impedance()[0], e.far_field()
        finally:
            utd._debug_skip = set()
            utd.reflections = orig

    return p12._cache_ff(
        cache / f"probe17_facet_H{H:.0f}_S{p12.SLOPE:.0f}_n{p12.N_FACETS}_{name}.npz",
        make,
    )


def main():
    cache = (
        pathlib.Path(os.environ.get("PROBE10_CACHE", ""))
        if os.environ.get("PROBE10_CACHE")
        else HERE / "cache"
    )
    ff_spec, _ = p12.solve_facet(cache, H, diffraction=False)
    ffs = {"specular": ff_spec}
    for v in VARIANTS:
        ffs[v], _ = solve_variant(cache, v)
    cuts = {k: facet_line(ff) for k, ff in ffs.items()}
    th = cuts["specular"][0]

    def at(k, e):
        return float(np.interp(e, cuts[k][0], np.asarray(cuts[k][1], float)))

    print(
        f"H = {H:.0f} m, downhill cut, dBi. 'full' is the 11 Sep page; 'specular' the 10 Sep page."
    )
    print(f"{'elev':>5s} | " + " ".join(f"{k:>9s}" for k in ffs))
    for e in MARKS:
        print(f"{e:5d} | " + " ".join(f"{at(k, e):9.1f}" for k in ffs))
    down = (th >= 2) & (th <= 40)
    g_spec = np.asarray(cuts["specular"][1], float)[down]
    print("\nmean over the downhill comb (2-40°) minus specular:")
    for k in VARIANTS:
        d = np.asarray(cuts[k][1], float)[down] - g_spec
        print(
            f"  {k:>8s}: mean {np.mean(d):+.2f} dB, min {np.min(d):+.2f}, max {np.max(d):+.2f}"
        )
    up = (th >= 100) & (th <= 130)
    print("uphill 50-80° (the tilted-mirror lobe) minus specular:")
    for k in VARIANTS:
        d = (
            np.asarray(cuts[k][1], float)[up]
            - np.asarray(cuts["specular"][1], float)[up]
        )
        print(f"  {k:>8s}: mean {np.mean(d):+.2f} dB")

    fig, axes = plt.subplots(1, 2, figsize=(11, 4.6), facecolor="white")
    for ax, (title, sel, xf) in zip(
        axes,
        (
            ("downhill (toward the plain)", th <= 90, lambda t: t),
            ("uphill (toward the crest)", th >= 90, lambda t: 180 - t),
        ),
        strict=True,
    ):
        for k, ff in ffs.items():
            t, g = cuts[k]
            g = np.clip(np.where(np.isfinite(g), g, RMIN), RMIN, None)
            o = np.argsort(xf(t[sel]))
            ax.plot(
                xf(t[sel])[o],
                np.asarray(g)[sel][o],
                color=COLORS[k],
                lw=1.9 if k == "full" else 1.2,
                ls=(0, (5, 2)) if k == "specular" else "-",
                label=k,
            )
        ax.set_title(title, fontsize=9.5, color=INK, loc="left")
        ax.set_xlim(0, 90)
        ax.set_ylim(RMIN, RMAX)
        ax.set_xticks(range(0, 91, 15))
        ax.set_xlabel("elevation above the true horizontal, °", fontsize=8, color=INK2)
        ax.grid(True, color=GRID, lw=0.6)
        ax.tick_params(labelsize=7.5, colors=INK2)
        for sp in ax.spines.values():
            sp.set_color(MUTED)
    axes[0].set_ylabel("dBi", fontsize=8.5, color=INK2)
    axes[0].legend(fontsize=8, frameon=False, loc="lower left")
    fig.suptitle(
        f"M0AGP's hill, H = {H:.0f} m: what each ingredient of the diffracted composer does",
        fontsize=11,
        color=INK,
        x=0.07,
        ha="left",
    )
    fig.tight_layout(rect=(0, 0, 1, 0.95))
    out = HERE / "mike_400m_ablation_2026-09-11"
    fig.savefig(out.with_suffix(".png"), dpi=170, facecolor="white")
    fig.savefig(out.with_suffix(".pdf"), facecolor="white")
    print("wrote", out.with_suffix(".png"), "and .pdf")


if __name__ == "__main__":
    main()
