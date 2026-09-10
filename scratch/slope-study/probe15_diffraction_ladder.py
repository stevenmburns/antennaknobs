"""Issue #1373 on the relief ladder of probe12: 40 / 100 / 200 / 400 / 1000 m
at 45°, mast mid-slope, the #534 specular path (dashed) against
`Terrain(diffraction=True)` (solid), one half-disc per hill. Answers: does
shadowing + diffraction soften the peaks and nulls of the plain's
height-gain comb as the hill grows?"""

import argparse
import os
import pathlib
import sys

import matplotlib

matplotlib.use("Agg")

import matplotlib.pyplot as plt  # noqa: E402
import numpy as np  # noqa: E402

from antennaknobs.engines.momwire import MomwireEngine  # noqa: E402
from antennaknobs.terrain import Terrain  # noqa: E402

HERE = pathlib.Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import probe9_mike_hillside as probe9  # noqa: E402
from probe4_azimuth_on_slope import gain_lookup  # noqa: E402
from probe9_mike_hillside import LAMBDA, mike_terrain  # noqa: E402
from probe10_mike_elevation_figure import (  # noqa: E402
    C_FLAT,
    C_MID,
    GRID,
    INK,
    INK2,
    MUTED,
    PlumbVerticalSurfaceRadials,
)
from probe11_mike_long_hillside import N_FACETS, _cache_ff, solve_level  # noqa: E402

SLOPE = 45.0
HILLS = (40.0, 100.0, 200.0, 400.0, 1000.0)
RMIN, RMAX = -30.0, 5.0


def solve(cache, H, diffraction):
    def make():
        probe9.N_FACETS = N_FACETS
        t = mike_terrain(H, SLOPE, 0.5)
        t = Terrain(sectors=t.sectors, diffraction=diffraction)
        e = MomwireEngine(PlumbVerticalSurfaceRadials(), ground=("terrain", t))
        return e.impedance()[0], e.far_field()

    tag = "utd" if diffraction else "spec"
    return _cache_ff(
        cache / f"probe15_{tag}_H{H:.0f}_S{SLOPE:.0f}_n{N_FACETS}.npz", make
    )


def half_disc(ff):
    g = gain_lookup(ff)
    els = np.arange(1.0, 90.0, 1.0)
    d = np.array([g(e, 0.0) for e in els])
    u = np.array([g(e, 180.0) for e in els])
    th = np.concatenate([els, 180.0 - els[::-1]])
    gain = np.concatenate([d, u[::-1]])
    return np.radians(th), np.clip(np.nan_to_num(gain, nan=RMIN), RMIN, None), els, d, u


def panel(ax, level, spec, utd, H):
    th, g, *_ = half_disc(level)
    ax.plot(th, g, color=C_FLAT, lw=1.2, ls=(0, (4, 3)), label="level ground")
    th, g, *_ = half_disc(spec)
    ax.plot(th, g, color=MUTED, lw=1.4, ls=(0, (2, 2)), label="specular only")
    th, g, *_ = half_disc(utd)
    ax.plot(th, g, color=C_MID, lw=1.9, label="shadowing + diffraction")
    th_s = np.radians(np.linspace(180.0 - SLOPE, 180.0, 40))
    ax.fill_between(th_s, RMIN, RMAX, color=MUTED, alpha=0.12, hatch="///", lw=0)
    ax.set_theta_zero_location("E")
    ax.set_theta_direction(1)
    ax.set_thetamin(0)
    ax.set_thetamax(180)
    ax.set_rlim(RMIN, RMAX)
    ax.set_rticks([-25, -20, -15, -10, -5, 0, 5])
    ax.set_yticklabels([])
    angles = list(range(0, 181, 30))
    ax.set_thetagrids(
        angles, labels=[f"{min(t, 180 - t)}°" if t != 90 else "" for t in angles]
    )
    ax.tick_params(labelsize=6.5, colors=INK2, pad=1)
    ax.grid(True, color=GRID, lw=0.6)
    ax.spines["polar"].set_color(MUTED)
    for r in (-20, -10, 0):
        ax.text(
            np.radians(90),
            r,
            f" {r:+d}" if r else "  0 dBi",
            fontsize=6,
            color=INK2,
            ha="left",
            va="center",
        )
    ax.set_title(
        f"H = {H:.0f} m ({H / LAMBDA:.2g} λ), mast {0.5 * H:.0f} m above the plain",
        fontsize=8.5,
        color=INK,
        pad=10,
    )


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--cache", default=os.environ.get("PROBE10_CACHE", ""))
    args = ap.parse_args()
    cache = pathlib.Path(args.cache) if args.cache else HERE / "cache"
    cache.mkdir(parents=True, exist_ok=True)
    level, _ = solve_level(cache)
    fig = plt.figure(figsize=(11, 8.2), facecolor="white")
    slots = [(0.02, 0.5), (0.35, 0.5), (0.68, 0.5), (0.02, 0.06), (0.35, 0.06)]
    print(f"{'hill':>6s} {'model':>9s} | down 3° / 10° / 20° / 30° | peak | up 30°")
    handles = None
    for H, (x, y) in zip(HILLS, slots, strict=True):
        spec, _ = solve(cache, H, False)
        utd, _ = solve(cache, H, True)
        for name, ff in (("specular", spec), ("utd", utd)):
            th, gg, els, d, u = half_disc(ff)
            gi = lambda e: d[int(e) - 1]  # noqa: E731
            print(
                f"{H:6.0f} {name:>9s} | {gi(3):5.1f} / {gi(10):5.1f} / {gi(20):5.1f} / {gi(30):5.1f} | {np.nanmax(d):5.1f} | {u[29]:5.1f}"
            )
        ax = fig.add_axes([x, y, 0.31, 0.42], projection="polar")
        panel(ax, level, spec, utd, H)
        handles = ax.get_legend_handles_labels()
    fig.legend(
        *handles, loc="center", bbox_to_anchor=(0.835, 0.25), fontsize=8, frameon=False
    )
    fig.text(
        0.835,
        0.15,
        "45° hill, mast mid-slope, 7.1 MHz\nplumb λ/4, four radials on the ground\nhatched: behind the crest",
        fontsize=8,
        color=INK2,
        ha="center",
    )
    out = HERE / "diffraction_ladder_2026-09-10.png"
    fig.savefig(out, dpi=150, bbox_inches="tight")
    print("wrote", out)


if __name__ == "__main__":
    main()
