"""Between the 40 m hill and the 1000 m one: a ladder of relief at 45°, the
mast mid-slope, through the specular-facet terrain (issue #534).

`--diffraction` runs the #1373 composer instead — shadowing, tilted mirrors and
UTD wedge diffraction at the breaks. Expect the uphill band below 45° to collapse
rather than brighten: the specular ladder answers straight through each hill. One
half-disc elevation plot per hill, each with level ground (dashed) and the
rotated-sky planar-slope solve (orange, its below-horizontal lobe not
drawn) for reference. The question: how the picture moves from the
half-wavelength hill of probe10 (one broad null from the plain's reflection)
to the 24 λ hill of probe11 (the plain's fine height-gain comb).

Antenna and soil as probe10/11: AC6LA's plumb 0.956 λ/4 with four radials
an inch above the ground, 7.1 MHz, soil 13 / 0.005. Every hill uses the
same facet count so the ladder differs only in relief.
"""

import argparse
import dataclasses
import os
import pathlib
import sys

import matplotlib

matplotlib.use("Agg")

import matplotlib.pyplot as plt  # noqa: E402
import numpy as np  # noqa: E402
from matplotlib.patches import Polygon  # noqa: E402

from antennaknobs.engines.momwire import MomwireEngine  # noqa: E402

HERE = pathlib.Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import probe9_mike_hillside as probe9  # noqa: E402
from probe4_azimuth_on_slope import gain_lookup  # noqa: E402
from probe5_invvee_on_slope import true_cut  # noqa: E402
from probe9_mike_hillside import FREQ, LAMBDA, SOIL, mike_terrain  # noqa: E402
from probe10_mike_elevation_figure import (  # noqa: E402
    C_FLAT,
    GRID,
    GROUND,
    INK,
    INK2,
    MUTED,
    PlumbVerticalSurfaceRadials,
)
from probe11_mike_long_hillside import (  # noqa: E402
    C_FACET,
    C_PLANAR,
    N_FACETS,
    RMAX,
    RMIN,
    _cache_ff,
    facet_line,
    solve_level,
    solve_planar,
)

SLOPE = 45.0
F_MAST = 0.5
HILLS = (40.0, 100.0, 200.0, 400.0, 1000.0)


def solve_facet(cache, H, *, diffraction=False):
    def make():
        probe9.N_FACETS = N_FACETS
        terrain = mike_terrain(H, SLOPE, F_MAST)
        if diffraction:
            terrain = dataclasses.replace(terrain, diffraction=True)
        e = MomwireEngine(PlumbVerticalSurfaceRadials(), ground=("terrain", terrain))
        return e.impedance()[0], e.far_field()

    # The field is part of the CACHE NAME. Sharing it would let a flipped flag
    # read the other page's far fields back and plot them under the new title.
    tag = "_utd" if diffraction else ""
    return _cache_ff(
        cache / f"probe11_facet_H{H:.0f}_S{SLOPE:.0f}_n{N_FACETS}{tag}.npz", make
    )


def panel(ax, H, level, facet, planar):
    def draw(th_deg, g, color, lw, ls, label):
        g = np.asarray(g, dtype=float)
        g = np.clip(np.where(np.isfinite(g), g, RMIN), RMIN, None)
        keep = th_deg >= 0.0
        ax.plot(
            np.radians(th_deg[keep]),
            g[keep],
            color=color,
            lw=lw,
            ls=ls,
            label=label,
            solid_joinstyle="round",
        )

    th, g = facet_line(level)
    draw(th, g, C_FLAT, 1.3, (0, (4, 3)), "level ground")
    ang, gp = true_cut(planar, SLOPE)
    draw(np.asarray(ang), gp, C_PLANAR, 1.3, "-", "rotated sky (infinite 45° plane)")
    th, g = facet_line(facet)
    draw(th, g, C_FACET, 1.8, "-", "facet model, mast mid-slope")
    th_s = np.radians(np.linspace(180.0 - SLOPE, 180.0, 40))
    ax.fill_between(th_s, RMIN, RMAX, color=MUTED, alpha=0.14, hatch="///", lw=0)
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


def sketch_axes(ax):
    """Mike's drawing, generic: plateau left, 45° slope, plain right, the
    mast half way up; H is the rung of the ladder."""
    H = 100.0
    run_m = H
    left, right = -0.9 * run_m, 1.9 * run_m
    ground = [
        (left, H),
        (0.0, H),
        (run_m, 0.0),
        (right, 0.0),
        (right, -22.0),
        (left, -22.0),
    ]
    ax.add_patch(Polygon(ground, closed=True, facecolor=GROUND, edgecolor=INK2, lw=1.0))
    x, z = 0.5 * run_m, 0.5 * H
    ax.plot([x, x], [z, z + 24], color=C_FACET, lw=2.4, solid_capstyle="round")
    ax.plot([x - 9, x + 9], [z + 1, z + 1], color=C_FACET, lw=1.2, alpha=0.8)
    ax.text(
        x + 8, z + 22, "mast, mid-slope", ha="left", va="top", fontsize=8, color=INK
    )
    xa = -0.45 * run_m
    ax.annotate(
        "",
        xy=(xa, H),
        xytext=(xa, 0),
        arrowprops=dict(arrowstyle="<->", color=INK2, lw=0.9),
    )
    ax.text(
        xa - 6,
        H / 2,
        "H",
        va="center",
        ha="right",
        fontsize=9,
        color=INK,
        style="italic",
    )
    ax.text(0.30 * run_m, 0.14 * H, "45°", fontsize=8, color=INK, ha="center")
    ax.text(right - 6, -11, "plain", fontsize=8, color=INK2, style="italic", ha="right")
    ax.text(
        -0.45 * run_m,
        H - 14,
        "plateau",
        fontsize=8,
        color=INK2,
        style="italic",
        ha="center",
    )
    ax.text(left + 4, H + 30, "← uphill", fontsize=7.5, color=INK2)
    ax.text(right - 4, H + 30, "downhill →", fontsize=7.5, color=INK2, ha="right")
    ax.set_xlim(left, right)
    ax.set_ylim(-22, H + 42)
    ax.set_aspect("equal")
    ax.axis("off")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--cache", default=os.environ.get("PROBE10_CACHE", ""))
    ap.add_argument(
        "--diffraction",
        action="store_true",
        help="compose the #1373 diffracted field instead of the #534 specular one",
    )
    args = ap.parse_args()
    utd = bool(args.diffraction)
    cache = pathlib.Path(args.cache) if args.cache else HERE / "cache"
    cache.mkdir(parents=True, exist_ok=True)

    level, _ = solve_level(cache)
    planar, _ = solve_planar(cache, SLOPE)
    facets = {H: solve_facet(cache, H, diffraction=utd)[0] for H in HILLS}
    gl = gain_lookup(level)
    ang, gp = true_cut(planar, SLOPE)
    print(f"{'hill':>8s} {'λ':>5s} | down 3° / 10° / 20° / 30° | peak above horizontal")
    print(
        f"{'level':>8s} {'':>5s} | {gl(3, 0):5.1f} / {gl(10, 0):5.1f} / {gl(20, 0):5.1f} / {gl(30, 0):5.1f}"
    )
    print(
        f"{'planar':>8s} {'':>5s} | {np.interp(3, ang, gp):5.1f} / {np.interp(10, ang, gp):5.1f} / "
        f"{np.interp(20, ang, gp):5.1f} / {np.interp(30, ang, gp):5.1f}"
    )
    for H in HILLS:
        g = gain_lookup(facets[H])
        th, gg = facet_line(facets[H])
        print(
            f"{H:8.0f} {H / LAMBDA:5.1f} | {g(3, 0):5.1f} / {g(10, 0):5.1f} / {g(20, 0):5.1f} / {g(30, 0):5.1f} | "
            f"{np.nanmax(gg[th <= 90]):5.1f}"
        )

    fig = plt.figure(figsize=(8.5, 11), facecolor="white")
    fig.text(
        0.07,
        0.968,
        (
            "M0AGP's hillside, shadowed and diffracted: a ladder of relief"
            if utd
            else "M0AGP's hillside from half a wavelength to twenty-four: "
            "a ladder of relief"
        ),
        fontsize=12.5,
        color=INK,
        va="baseline",
    )
    fig.text(
        0.07,
        0.955,
        f"{FREQ} MHz, soil εr {SOIL[0]:.0f} / σ {SOIL[1]} S/m. Plumb quarter-wave, four radials an inch above the "
        f"ground, mid-slope on a {SLOPE:.0f}° hill\nbetween a plain and a plateau; only the hill's relief changes "
        "from panel to panel.\nElevation above the true horizontal, downhill on the right.",
        fontsize=8.8,
        color=INK2,
        va="top",
    )
    r_in = 1.75
    w, h, r_h = 2 * r_in / 8.5, 2 * r_in / 11, r_in / 11
    slots = [(0.28, 0.865), (0.72, 0.865), (0.28, 0.605), (0.72, 0.605), (0.28, 0.345)]
    handles = None
    for H, (cx, top) in zip(HILLS, slots, strict=True):
        cy = top - r_h / 2  # 0–180 wedge centred in a square box: top at cy + r_h/2
        ax = fig.add_axes([cx - w / 2, cy - h / 2, w, h], projection="polar")
        panel(ax, H, level, facets[H], planar)
        handles = ax.get_legend_handles_labels()
        fig.text(
            cx,
            top + 0.012,
            f"H = {H:.0f} m  ({H / LAMBDA:.2g} λ), mast {0.5 * H:.0f} m above the plain",
            fontsize=8.8,
            color=INK,
            ha="center",
            va="bottom",
        )
    ax_s = fig.add_axes([0.52, 0.255, 0.40, 0.105])
    sketch_axes(ax_s)
    fig.text(
        0.72,
        0.365,
        "the profile: mast half way up a 45° hill of relief H",
        fontsize=8.8,
        color=INK,
        ha="center",
        va="bottom",
    )
    fig.legend(
        *handles,
        loc="center",
        bbox_to_anchor=(0.72, 0.205),
        fontsize=8,
        frameon=False,
        ncol=1,
    )
    fig.text(
        0.07,
        0.015,
        "How to read it. Blue is the specular-facet terrain model: the antenna solved on level ground with the local "
        "soil, each far-field direction reflected off the facet its specular point lands on, no diffraction, nothing "
        "read below the horizontal. Orange is the same antenna on an infinite 45° plane, solved in the tilted frame "
        "and read in the true one; its main lobe sits below the horizontal, off this half-disc, so the orange line is "
        "only that lobe's upper skirt. Above the horizontal "
        "a ray shallower than the slope passes over it and reaches the plain, so what the facet model draws downhill "
        "is the direct ray plus the plain's reflection from a mirror H/2 below the mast: at half a wavelength of relief "
        "that is one broad null near 20°; as the relief grows the null multiplies into the height-gain comb of a tall "
        "antenna, sliding toward the horizon, while the gain right at the horizon settles near the rotated sky's value. "
        "Hatched: uphill below the slope angle, behind the crest, quoted by no model here.",
        fontsize=7.4,
        color=INK2,
        wrap=True,
        va="bottom",
    )
    out = HERE / (
        "mike_hill_ladder_utd_2026-09-10" if utd else "mike_hill_ladder_2026-09-10"
    )
    fig.savefig(out.with_suffix(".png"), dpi=170, facecolor="white")
    fig.savefig(out.with_suffix(".pdf"), facecolor="white")
    print("wrote", out.with_suffix(".png"), "and .pdf")


if __name__ == "__main__":
    main()
