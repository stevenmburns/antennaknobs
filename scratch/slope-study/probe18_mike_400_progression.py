"""Three generations of the hillside model on one page, for the 400 m hill,
mast 200 m above the plain: (1) the tilted sloper -- the antenna on an
infinite 45 degree plane, solved in the tilted frame and read in the true one
(the "rotated sky"); (2) the specular facet model of the 10 Sep pages --
each direction reflected once off the facet its specular point lands on,
horizontal mirrors, no shadowing; (3) the diffracted model of the 11 Sep
pages -- every path, tilted mirrors, shadowing, UTD wedge diffraction at the
crest and the toe. Level ground dashed for scale. Same antenna, soil and
frequency as every Mike page; all four far fields from probe12's cache.
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

from probe5_invvee_on_slope import true_cut  # noqa: E402
from probe9_mike_hillside import FREQ, LAMBDA, SOIL  # noqa: E402
from probe10_mike_elevation_figure import C_FLAT, GRID, INK, INK2, MUTED  # noqa: E402
from probe11_mike_long_hillside import RMAX, RMIN, facet_line, solve_level, solve_planar  # noqa: E402
from probe12_mike_hill_ladder import SLOPE, solve_facet  # noqa: E402

H = 400.0
C_PLANAR, C_SPEC, C_UTD = "#9333ea", "#d97706", "#2563eb"
LINES = (  # key, colour, width, style, label
    ("level", C_FLAT, 1.1, (0, (2, 2)), "level ground, for scale"),
    (
        "planar",
        C_PLANAR,
        1.4,
        (0, (6, 2)),
        "1. tilted sloper: infinite 45° plane, rotated sky",
    ),
    (
        "spec",
        C_SPEC,
        1.5,
        (0, (4, 2)),
        "2. specular facets: one horizontal-mirror reflection per direction",
    ),
    ("utd", C_UTD, 2.0, "-", "3. shadowing, tilted mirrors and wedge diffraction"),
)


def clipped(g):
    g = np.asarray(g, float)
    return np.clip(np.where(np.isfinite(g), g, RMIN), RMIN, None)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--cache", default=os.environ.get("PROBE10_CACHE", ""))
    args = ap.parse_args()
    cache = pathlib.Path(args.cache) if args.cache else HERE / "cache"

    level, _ = solve_level(cache)
    planar, _ = solve_planar(cache, SLOPE)
    spec, z_spec = solve_facet(cache, H, diffraction=False)
    utd, z_utd = solve_facet(cache, H, diffraction=True)
    cuts = {
        "level": facet_line(level),
        "planar": true_cut(planar, SLOPE),
        "spec": facet_line(spec),
        "utd": facet_line(utd),
    }
    cuts = {k: (np.asarray(t, float), clipped(g)) for k, (t, g) in cuts.items()}

    print(
        f"H = {H:.0f} m ({H / LAMBDA:.1f} λ), mast {H / 2:.0f} m above the plain; Z facet {z_spec:.3f} / {z_utd:.3f}"
    )
    print(
        f"{'elev':>5s} | "
        + " ".join(f"{'dn ' + k:>9s}" for k, *_ in LINES)
        + " | "
        + " ".join(f"{'up ' + k:>9s}" for k, *_ in LINES)
    )
    for e in (3, 10, 20, 30, 45, 60, 75):
        dn = " ".join(f"{np.interp(e, *cuts[k]):9.1f}" for k, *_ in LINES)
        up = " ".join(f"{np.interp(180 - e, *cuts[k]):9.1f}" for k, *_ in LINES)
        print(f"{e:5d} | {dn} | {up}")

    fig = plt.figure(figsize=(8.5, 11), facecolor="white")
    fig.text(
        0.07,
        0.965,
        f"M0AGP's hill at H = {H:.0f} m ({H / LAMBDA:.1f} λ), mast {H / 2:.0f} m above the plain: "
        "three generations of the model",
        fontsize=12,
        color=INK,
        va="baseline",
    )
    fig.text(
        0.07,
        0.950,
        f"{FREQ} MHz, soil εr {SOIL[0]:.0f} / σ {SOIL[1]} S/m, plumb quarter-wave with four radials an inch up, "
        f"mid-slope on the {SLOPE:.0f}° hill.\nElevation above the true horizontal; downhill toward the plain, "
        "uphill toward the crest and the plateau.",
        fontsize=8.6,
        color=INK2,
        va="top",
    )

    ax = fig.add_axes([0.14, 0.585, 0.72, 0.34], projection="polar")
    for k, c, lw, ls, label in LINES:
        t, g = cuts[k]
        keep = t >= 0
        ax.plot(
            np.radians(t[keep]),
            g[keep],
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
        angles, labels=[f"{min(a, 180 - a)}°" if a != 90 else "" for a in angles]
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
        loc="lower center", bbox_to_anchor=(0.5, -0.06), fontsize=7.5, frameon=False
    )

    for i, (title, is_up) in enumerate(
        (
            ("downhill (toward the plain)", False),
            ("uphill (toward the crest and plateau)", True),
        )
    ):
        axl = fig.add_axes([0.10 + i * 0.45, 0.16, 0.38, 0.35])
        for k, c, lw, ls, label in LINES:
            t, g = cuts[k]
            sel = (t >= 90) if is_up else ((t >= 0) & (t <= 90))
            el = (180 - t[sel]) if is_up else t[sel]
            o = np.argsort(el)
            axl.plot(el[o], g[sel][o], color=c, lw=lw, ls=ls, label=label.split(":")[0])
        if is_up:
            axl.axvspan(0, SLOPE, color=MUTED, alpha=0.12, lw=0)
            axl.text(
                SLOPE / 2,
                RMAX - 2.5,
                "behind the crest",
                fontsize=7,
                color=INK2,
                ha="center",
            )
        axl.set_title(title, fontsize=8.5, color=INK, loc="left", pad=4)
        axl.set_xlim(0, 90)
        axl.set_ylim(RMIN, RMAX)
        axl.set_xticks(range(0, 91, 15))
        axl.set_xlabel(
            "elevation above the true horizontal, °", fontsize=7.5, color=INK2
        )
        axl.tick_params(labelsize=7, colors=INK2)
        axl.grid(True, color=GRID, lw=0.6)
        for sp in axl.spines.values():
            sp.set_color(MUTED)
        if i == 0:
            axl.set_ylabel("dBi", fontsize=8, color=INK2)
            axl.legend(fontsize=7, frameon=False, loc="lower left")
        else:
            axl.set_yticklabels([])

    fig.text(
        0.1,
        0.10,
        "1. The sloper only knows the ground is tilted: the whole sky is rotated. The plain and the plateau do not exist, so there is\n"
        "   no comb downhill, and the uphill sky below the slope angle lies under the plane's own horizon and is simply absent.\n"
        "2. The facets know where the plain is, so the height-gain comb appears downhill, but each direction gets one reflection\n"
        "   off a horizontal mirror and the uphill sky is answered straight through the hill (shaded).\n"
        "3. Every path is summed: the hill shadows the uphill sky below its crest line, the slope acts as a tilted mirror and throws\n"
        "   a lobe high uphill, and the crest and the toe diffract, filling the zenith null. The comb keeps its period and phase.",
        fontsize=7.5,
        color=INK2,
        va="top",
    )
    out = HERE / "mike_400m_progression_2026-09-11"
    fig.savefig(out.with_suffix(".png"), dpi=170, facecolor="white")
    fig.savefig(out.with_suffix(".pdf"), facecolor="white")
    print("wrote", out.with_suffix(".png"), "and .pdf")


if __name__ == "__main__":
    main()
