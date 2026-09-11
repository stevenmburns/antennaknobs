"""The 400 m rung of Mike's ladder, specular against diffracted, on one plot.

Steve asked to see the difference in detail for one hill: the 9.5 λ hill, mast
200 m above the plain. Both far fields come from probe12's cache (the specular
one from the 2026-09-10 page, the diffracted one from the 2026-09-11 page), so
the overlay is exactly the two published lines. Top: the half-disc overlay.
Middle: the same two cuts on a linear elevation axis, downhill on the left of
the zenith and uphill on the right. Bottom: diffracted minus specular in dB.
"""

import argparse
import os
import pathlib
import sys

import matplotlib

matplotlib.use("Agg")

import matplotlib.pyplot as plt  # noqa: E402
import numpy as np  # noqa: E402

HERE = pathlib.Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

from probe9_mike_hillside import FREQ, LAMBDA, SOIL  # noqa: E402
from probe10_mike_elevation_figure import GRID, INK, INK2, MUTED  # noqa: E402
from probe11_mike_long_hillside import C_FACET, RMAX, RMIN, facet_line  # noqa: E402
from probe12_mike_hill_ladder import SLOPE, solve_facet  # noqa: E402

C_SPEC = "#d97706"
H = 400.0
MARKS = (3, 5, 10, 15, 20, 30, 45, 60, 75, 85)


def polar(ax, th, g_spec, g_utd):
    for g, c, lw, ls, label in (
        (
            g_spec,
            C_SPEC,
            1.5,
            (0, (5, 2)),
            "specular facets, no diffraction (10 Sep page)",
        ),
        (
            g_utd,
            C_FACET,
            1.8,
            "-",
            "shadowing + tilted mirrors + diffraction (11 Sep page)",
        ),
    ):
        g = np.clip(np.where(np.isfinite(g), g, RMIN), RMIN, None)
        ax.plot(
            np.radians(th),
            g,
            color=c,
            lw=lw,
            ls=ls,
            label=label,
            solid_joinstyle="round",
        )
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
    ax.tick_params(labelsize=7, colors=INK2, pad=1)
    ax.grid(True, color=GRID, lw=0.6)
    ax.spines["polar"].set_color(MUTED)
    for r in (-20, -10, 0):
        ax.text(
            np.radians(90),
            r,
            f" {r:+d}" if r else "  0 dBi",
            fontsize=6.5,
            color=INK2,
            ha="left",
            va="center",
        )
    ax.text(np.radians(8), RMAX + 1.5, "downhill →", fontsize=8, color=INK2, ha="left")
    ax.text(np.radians(172), RMAX + 1.5, "← uphill", fontsize=8, color=INK2, ha="right")
    ax.legend(
        loc="lower center",
        bbox_to_anchor=(0.5, -0.04),
        fontsize=7.5,
        frameon=False,
        ncol=1,
    )


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--cache", default=os.environ.get("PROBE10_CACHE", ""))
    args = ap.parse_args()
    cache = pathlib.Path(args.cache) if args.cache else HERE / "cache"
    cache.mkdir(parents=True, exist_ok=True)

    ff_spec, z_spec = solve_facet(cache, H, diffraction=False)
    ff_utd, z_utd = solve_facet(cache, H, diffraction=True)
    th, g_spec = facet_line(ff_spec)
    th2, g_utd = facet_line(ff_utd)
    assert np.allclose(th, th2)
    g_spec = np.asarray(g_spec, float)
    g_utd = np.asarray(g_utd, float)
    delta = g_utd - g_spec

    gsc = np.clip(np.where(np.isfinite(g_spec), g_spec, RMIN), RMIN, None)
    guc = np.clip(np.where(np.isfinite(g_utd), g_utd, RMIN), RMIN, None)
    delta = (
        guc - gsc
    )  # both floored at RMIN, so a null against a null reads 0, not infinity

    print(
        f"H = {H:.0f} m ({H / LAMBDA:.1f} λ), mast {H / 2:.0f} m above the plain, {FREQ} MHz, soil {SOIL}"
    )
    print(f"Z specular {z_spec:.4f}   Z diffracted {z_utd:.4f}")
    print(
        f"{'elev':>5s} | {'down spec':>9s} {'down utd':>8s} {'Δ':>6s} | {'up spec':>8s} {'up utd':>7s} {'Δ':>6s}"
    )
    for e in MARKS:
        ds = np.interp(e, th, g_spec)
        du = np.interp(e, th, g_utd)
        us = np.interp(180 - e, th, g_spec)
        uu = np.interp(180 - e, th, g_utd)
        print(
            f"{e:5d} | {ds:9.1f} {du:8.1f} {du - ds:+6.1f} | {us:8.1f} {uu:7.1f} {uu - us:+6.1f}"
        )
    up = th > 90.0
    print(
        f"uphill band 0-{SLOPE:.0f}° from the horizon: mean Δ {np.mean(delta[(th >= 180 - SLOPE) & (th < 179)]):+.1f} dB"
    )
    print(
        f"uphill {SLOPE:.0f}-85°: mean Δ {np.mean(delta[(th > 95) & (th <= 180 - SLOPE)]):+.1f} dB, max {np.max(delta[(th > 95) & (th <= 180 - SLOPE)]):+.1f}"
    )
    print(
        f"downhill 0-85°: mean |Δ| {np.mean(np.abs(delta[(th >= 0) & (th <= 85)])):.2f} dB, max |Δ| {np.max(np.abs(delta[(th >= 0) & (th <= 85)])):.2f}"
    )

    fig = plt.figure(figsize=(8.5, 11), facecolor="white")
    fig.text(
        0.07,
        0.965,
        f"M0AGP's hill at H = {H:.0f} m ({H / LAMBDA:.1f} λ), mast {H / 2:.0f} m above the plain: "
        "specular against diffracted",
        fontsize=12,
        color=INK,
        va="baseline",
    )
    fig.text(
        0.07,
        0.950,
        f"{FREQ} MHz, soil εr {SOIL[0]:.0f} / σ {SOIL[1]} S/m, plumb quarter-wave with four radials an inch up, "
        f"mid-slope on the {SLOPE:.0f}° hill.\nBoth lines are the published ones: the 10 Sep ladder page (specular) "
        "and the 11 Sep ladder page (diffracted), same cache.",
        fontsize=8.6,
        color=INK2,
        va="top",
    )

    ax0 = fig.add_axes([0.14, 0.585, 0.72, 0.34], projection="polar")
    polar(ax0, th, g_spec, g_utd)

    # Two columns, downhill and uphill, elevation from the horizon left to right on
    # both; gain on the top row, diffracted - specular on the bottom row.
    down = th <= 90.0
    up = th >= 90.0
    cols = (
        (
            "downhill (toward the plain)",
            th[down],
            gsc[down],
            guc[down],
            delta[down],
            False,
        ),
        (
            "uphill (toward the crest and plateau)",
            180.0 - th[up],
            gsc[up],
            guc[up],
            delta[up],
            True,
        ),
    )
    lim = min(40.0, max(6.0, np.nanmax(np.abs(delta)) * 1.05))
    for k, (title, el, gs_k, gu_k, dd_k, is_up) in enumerate(cols):
        o = np.argsort(el)
        el, gs_k, gu_k, dd_k = el[o], gs_k[o], gu_k[o], dd_k[o]
        x0 = 0.10 + k * 0.45
        ax1 = fig.add_axes([x0, 0.16, 0.38, 0.37])
        ax2 = fig.add_axes([x0, 0.02, 0.38, 0.05])
        ax2.set_visible(False)
        ax1.set_title(title, fontsize=8.5, color=INK, loc="left", pad=4)
        ax1.plot(el, gs_k, color=C_SPEC, lw=1.4, ls=(0, (5, 2)), label="specular")
        ax1.plot(el, gu_k, color=C_FACET, lw=1.7, label="diffracted")
        ax2.axhline(0, color=MUTED, lw=0.8)
        ax2.fill_between(el, 0, dd_k, where=dd_k >= 0, color=C_FACET, alpha=0.35, lw=0)
        ax2.fill_between(el, 0, dd_k, where=dd_k < 0, color=C_SPEC, alpha=0.35, lw=0)
        ax2.plot(el, dd_k, color=INK, lw=0.9)
        if is_up:
            for ax in (ax1, ax2):
                ax.axvspan(0, SLOPE, color=MUTED, alpha=0.12, lw=0)
            ax1.text(
                SLOPE / 2,
                RMAX - 2.5,
                "behind the crest",
                fontsize=7,
                color=INK2,
                ha="center",
            )
        ax1.set_ylim(RMIN, RMAX)
        ax2.set_ylim(-lim, lim)
        for ax in (ax1, ax2):
            ax.set_xlim(0, 90)
            ax.set_xticks(range(0, 91, 15))
            ax.tick_params(labelsize=7, colors=INK2)
            ax.grid(True, color=GRID, lw=0.6)
            for sp in ax.spines.values():
                sp.set_color(MUTED)
        ax1.set_xlabel(
            "elevation above the true horizontal, °", fontsize=7.5, color=INK2
        )
        if k == 0:
            ax1.set_ylabel("dBi", fontsize=8, color=INK2)
            ax2.set_ylabel("diffracted − specular, dB", fontsize=8, color=INK2)
            ax1.legend(fontsize=7.5, frameon=False, loc="lower left")
        else:
            ax1.set_yticklabels([])
            ax2.set_yticklabels([])
    fig.text(
        0.1,
        0.10,
        "Shaded: the uphill sky behind the 45° crest, which the specular model answered straight through the hill.\n"
        "The zenith: a plumb vertical radiates nothing straight up, so the specular null there is the antenna's own; the diffracted\n"
        "model fills it with the crest's and the toe's diffracted field. Read that it fills, not how far.",
        fontsize=7.5,
        color=INK2,
        va="top",
    )

    out = HERE / "mike_400m_overlay_2026-09-11"
    fig.savefig(out.with_suffix(".png"), dpi=170, facecolor="white")
    fig.savefig(out.with_suffix(".pdf"), facecolor="white")
    print("wrote", out.with_suffix(".png"), "and .pdf")


if __name__ == "__main__":
    main()
