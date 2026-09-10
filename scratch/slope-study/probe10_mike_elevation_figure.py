"""One page for Mike (M0AGP): polar elevation plots of a plumb quarter-wave
vertical with four radials just above the ground, standing on his plateau /
slope / plain profile, through the specular-facet terrain ground (issue
#534; probe9 ran the same profile under the buried-radial vertical).

Layout: a sketch of the profile modelled, then one conventional half-disc
elevation plot per hill (downhill to the right, uphill to the left, radius in
dBi), one line per case: flat ground, the mast at mid-slope, the mast at the
crest. The toe is not drawn because the model reproduces flat ground there
exactly (asserted below). The uphill sector below the slope angle is hatched:
the model has no diffraction, so it reports grazing cancellation where the
crest shadows the sky, and those numbers are not quoted.

Antenna: AC6LA's spelling from the second QRZ post (probe8) on flat ground —
plumb 0.956 λ/4 mast fed at its foot one inch up, four λ/4 radials one inch
above the surface, 1 mm wire. `BASE_M` is the one knob to move the radials
higher.

Far fields are cached in the session scratchpad (or `--cache DIR`) so the
layout can be iterated without re-solving.
"""

import argparse
import math
import os
import pathlib
import sys
from types import MappingProxyType, SimpleNamespace

import matplotlib

matplotlib.use("Agg")

import matplotlib.pyplot as plt  # noqa: E402
import numpy as np  # noqa: E402
from matplotlib.patches import Polygon  # noqa: E402

from antennaknobs import AntennaBuilder, Wire, WireSpec  # noqa: E402
from antennaknobs.engines.momwire import MomwireEngine  # noqa: E402
from antennaknobs.far_field import pattern_metrics  # noqa: E402

HERE = pathlib.Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
from probe4_azimuth_on_slope import gain_lookup  # noqa: E402
from probe9_mike_hillside import FREQ, LAMBDA, SOIL, mike_terrain  # noqa: E402

SLOPE_DEG = 45.0
HILLS = (40.0, 20.0)  # m of relief: about 1 λ and λ/2 at 7.1 MHz
BASE_M = 0.0254  # radials (and the feed) one inch above the ground
INK = "#1f2937"
INK2 = "#4b5563"
MUTED = "#9ca3af"
GRID = "#e5e7eb"
GROUND = "#efe6d6"
# categorical slots 1 and 2 of the validated default palette (dataviz skill);
# the flat reference is a neutral dashed line, identity carried by the dash.
C_MID = "#2a78d6"
C_CREST = "#eb6834"
C_FLAT = "#6b7280"
RMIN, RMAX = -30.0, 5.0


class PlumbVerticalSurfaceRadials(AntennaBuilder):
    """AC6LA's antenna on level ground: plumb 0.956 λ/4 mast, base `base` m
    up, four λ/4 radials at the same height along ±x and ±y, 1 mm wire."""

    default_params = MappingProxyType(
        {
            "design_freq": FREQ,
            "freq": FREQ,
            "base": BASE_M,
            "length_factor": 0.956,
            "radial_factor": 1.0,
        }
    )

    def build_wire_material(self):
        return WireSpec(radius=0.001)

    def build_wires(self):
        eps = 0.05
        h = 0.25 * LAMBDA * self.length_factor
        r = 0.25 * LAMBDA * self.radial_factor
        z0 = float(self.base)
        tups = [Wire((0, 0, z0), (0, 0, z0 + eps), ex=1 + 0j)]
        tups.append(Wire((0, 0, z0 + eps), (0, 0, z0 + eps + h)))
        for dx, dy in ((1, 0), (-1, 0), (0, 1), (0, -1)):
            tups.append(Wire((0, 0, z0), (r * dx, r * dy, z0)))
        return tups


def solve(ground, key, cache):
    path = cache / f"probe10_{key}.npz"
    if path.exists():
        d = np.load(path, allow_pickle=False)
        ff = SimpleNamespace(rings=d["rings"], thetas=d["thetas"], phis=d["phis"])
        z = complex(d["z"])
    else:
        e = MomwireEngine(PlumbVerticalSurfaceRadials(), ground=ground)
        z = e.impedance()[0]
        ff_full = e.far_field()
        ff = SimpleNamespace(
            rings=np.asarray(ff_full.rings),
            thetas=np.asarray(ff_full.thetas),
            phis=np.asarray(ff_full.phis),
        )
        np.savez(
            path, rings=ff.rings, thetas=ff.thetas, phis=ff.phis, z=np.complex128(z)
        )
    g = gain_lookup(ff)
    return {
        "key": key,
        "Z": z,
        "ff": ff,
        "peak": pattern_metrics(ff)["peak_gain_dbi"],
        "down3": g(3.0, 0.0),
        "down10": g(10.0, 0.0),
        "down20": g(20.0, 0.0),
        "up30": g(30.0, 180.0),
    }


def elevation_cut(ff, az_deg):
    g = gain_lookup(ff)
    els = np.arange(0.5, 90.0, 0.5)
    return els, np.array([g(el, az_deg) for el in els])


def profile_axes(ax, H):
    """Mike's drawing: plateau on the left, the slope falling to the right,
    plain on the right — so downhill is to the right, as in the polar plots
    below (az 0 on the right)."""
    run_m = H / math.tan(math.radians(SLOPE_DEG))
    # x runs downhill: plateau for x < 0, slope 0..run_m, plain beyond
    left, right = -1.45 * LAMBDA, run_m + 1.5 * LAMBDA
    ground = [
        (left, H),
        (0.0, H),
        (run_m, 0.0),
        (right, 0.0),
        (right, -15.0),
        (left, -15.0),
    ]
    ax.add_patch(Polygon(ground, closed=True, facecolor=GROUND, edgecolor=INK2, lw=1.0))
    mast = 0.956 * LAMBDA / 4
    for f, color, name in ((0.5, C_MID, "mid-slope"), (1.0, C_CREST, "crest")):
        x, z = (1.0 - f) * run_m, f * H
        ax.plot([x, x], [z, z + mast], color=color, lw=2.2, solid_capstyle="round")
        ax.plot(
            [x - 10.5, x + 10.5], [z + 0.6, z + 0.6], color=color, lw=1.2, alpha=0.8
        )
        ax.text(
            x, z + mast + 2.5, name, ha="center", va="bottom", fontsize=8.5, color=INK
        )
    ax.plot([run_m, run_m], [0, mast], color=MUTED, lw=1.4)
    ax.text(
        run_m + 3,
        mast + 1.5,
        "toe (= flat)",
        ha="left",
        va="bottom",
        fontsize=8,
        color=INK2,
    )
    xa = -0.62 * LAMBDA
    ax.annotate(
        "",
        xy=(xa, H),
        xytext=(xa, 0),
        arrowprops=dict(arrowstyle="<->", color=INK2, lw=0.9),
    )
    ax.text(
        xa - 3,
        H / 2,
        f"H = {H:.0f} m\n= {H / LAMBDA:.2g} λ",
        va="center",
        ha="right",
        fontsize=8.5,
        color=INK,
    )
    ax.text(
        run_m * 0.34,
        H * 0.18,
        f"{SLOPE_DEG:.0f}°",
        fontsize=8.5,
        color=INK,
        ha="center",
    )
    ax.text(
        right - 4, -5.0, "plain", fontsize=8.5, color=INK2, style="italic", ha="right"
    )
    ax.text(-0.5 * LAMBDA, H - 6.5, "plateau", fontsize=8.5, color=INK2, style="italic")
    ax.text(left + 4, H + mast + 4, "← uphill, az 180", fontsize=8, color=INK2)
    ax.text(
        right - 4, H + mast + 1, "downhill, az 0 →", fontsize=8, color=INK2, ha="right"
    )
    x0 = right - 8 - LAMBDA
    ax.plot([x0, x0 + LAMBDA], [-9.8, -9.8], color=INK, lw=1.2)
    ax.text(
        x0 + LAMBDA / 2,
        -10.8,
        f"λ = {LAMBDA:.1f} m",
        ha="center",
        va="top",
        fontsize=8,
        color=INK,
    )
    ax.set_xlim(left, right)
    ax.set_ylim(-15, H + mast + 10)
    ax.set_aspect("equal")
    ax.axis("off")


def polar_axes(ax, rows, *, H):
    def line(ff, color, lw, ls, label):
        els_d, g_d = elevation_cut(ff, 0.0)
        els_u, g_u = elevation_cut(ff, 180.0)
        th = np.concatenate([np.radians(els_d), np.radians(180.0 - els_u[::-1])])
        g = np.concatenate([g_d, g_u[::-1]])
        g = np.clip(np.nan_to_num(g, nan=RMIN), RMIN, None)
        ax.plot(th, g, color=color, lw=lw, ls=ls, label=label, solid_joinstyle="round")

    line(rows["flat"]["ff"], C_FLAT, 1.5, (0, (4, 3)), "flat ground")
    line(rows["mid"]["ff"], C_MID, 2.0, "-", "mast at mid-slope")
    line(rows["crest"]["ff"], C_CREST, 2.0, "-", "mast at the crest")
    th_s = np.radians(np.linspace(180.0 - SLOPE_DEG, 180.0, 40))
    ax.fill_between(th_s, RMIN, RMAX, color=MUTED, alpha=0.14, hatch="///", lw=0)

    ax.set_theta_zero_location("E")
    ax.set_theta_direction(1)
    ax.set_thetamin(0)
    ax.set_thetamax(180)
    ax.set_rlim(RMIN, RMAX)
    ax.set_rticks([-25, -20, -15, -10, -5, 0, 5])
    ax.set_yticklabels([])
    angles = list(range(0, 181, 15))
    ax.set_thetagrids(
        angles, labels=[f"{min(t, 180 - t)}°" if t != 90 else "" for t in angles]
    )
    ax.tick_params(labelsize=7.5, colors=INK2, pad=2)
    ax.grid(True, color=GRID, lw=0.7)
    ax.spines["polar"].set_color(MUTED)
    for r in (-20, -10, 0):
        ax.text(
            np.radians(90),
            r,
            f" {r:+d} dBi" if r else "  0 dBi",
            fontsize=7,
            color=INK2,
            ha="left",
            va="center",
        )
    ax.text(
        np.radians(9), RMAX + 5.5, "downhill, az 0 →", fontsize=8, color=INK2, ha="left"
    )
    ax.text(
        np.radians(171),
        RMAX + 5.5,
        "← uphill, az 180",
        fontsize=8,
        color=INK2,
        ha="right",
    )


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--cache", default=os.environ.get("PROBE10_CACHE", ""))
    args = ap.parse_args()
    cache = pathlib.Path(args.cache) if args.cache else HERE / "cache"
    cache.mkdir(parents=True, exist_ok=True)

    rows = {"flat": solve(("finite",) + SOIL, "flat", cache)}
    for H in HILLS:
        for f, name in ((0.5, "mid"), (1.0, "crest")):
            rows[(H, name)] = solve(
                ("terrain", mike_terrain(H, SLOPE_DEG, f)), f"H{H:.0f}_{name}", cache
            )
    toe = solve(("terrain", mike_terrain(HILLS[0], SLOPE_DEG, 0.0)), "H40_toe", cache)
    _, g_toe = elevation_cut(toe["ff"], 0.0)
    _, g_flat = elevation_cut(rows["flat"]["ff"], 0.0)
    toe_dev = float(np.nanmax(np.abs(g_toe - g_flat)))
    print(f"toe vs flat, downhill cut: max |Δ| = {toe_dev:.2e} dB")
    for key, r in rows.items():
        print(
            f"{str(key):16s} Z {r['Z'].real:6.2f}{r['Z'].imag:+7.2f}j  peak {r['peak']:6.2f}  "
            f"down 3/10/20° {r['down3']:6.1f}/{r['down10']:6.1f}/{r['down20']:6.1f}  up 30° {r['up30']:6.1f}"
        )

    fig = plt.figure(figsize=(8.5, 11), facecolor="white")
    fig.text(
        0.07,
        0.968,
        "M0AGP's hillside: elevation patterns from the specular-facet ground",
        fontsize=12.5,
        color=INK,
        va="baseline",
    )
    fig.text(
        0.07,
        0.955,
        f"{FREQ} MHz, soil εr {SOIL[0]:.0f} / σ {SOIL[1]} S/m. Plumb quarter-wave, four radials "
        f"{BASE_M * 100:.1f} cm above the ground, standing on a {SLOPE_DEG:.0f}° slope\n"
        "between a plain below and a plateau above; the same profile, two heights of hill.",
        fontsize=8.8,
        color=INK2,
        va="top",
    )
    ax_p = fig.add_axes([0.16, 0.782, 0.68, 0.135])
    profile_axes(ax_p, HILLS[0])
    # matplotlib fits the FULL circle to the axes box (r = min(w, h) / 2) and
    # then draws the 0–180° wedge centred in it, so in a square box of side
    # 2r the half-disc spans the middle half: top at cy + r/2, baseline at
    # cy - r/2. The empty quarters overlap whatever sits above and below;
    # titles and the legend are placed by hand against the disc.
    r_in = 2.6
    w, h = 2 * r_in / 8.5, 2 * r_in / 11
    r_h = r_in / 11
    for i, (H, top) in enumerate(zip(HILLS, (0.735, 0.412), strict=True)):
        cy = top - r_h / 2
        sub = {
            "flat": rows["flat"],
            "mid": rows[(H, "mid")],
            "crest": rows[(H, "crest")],
        }
        ax = fig.add_axes([0.5 - w / 2, cy - h / 2, w, h], projection="polar")
        polar_axes(ax, sub, H=H)
        fig.text(
            0.5,
            top + 0.02,
            f"{H:.0f} m hill ({H / LAMBDA:.2g} λ) at {SLOPE_DEG:.0f}° — elevation above the horizontal",
            fontsize=9.5,
            color=INK,
            ha="center",
            va="bottom",
        )
        if i == 0:
            ax.legend(
                loc="upper center",
                bbox_to_anchor=(0.5, 0.25 - 0.06),
                fontsize=8,
                frameon=False,
                ncol=3,
            )
    z = rows["flat"]["Z"]
    fig.text(
        0.07,
        0.015,
        "How to read it. The antenna is solved on level ground with the local soil (feed impedance "
        f"{z.real:.1f}{z.imag:+.1f}j Ω in every case: the model does not see the tilt under the radials). "
        "Each far-field direction is then reflected off the facet its specular point lands on, with that "
        "facet's Fresnel coefficients and its height as extra path phase. Geometric optics only: no "
        "diffraction at the crest or the toe and no surface-wave interaction with either break, which is "
        "the regime you call hard. Hatched sector: uphill below the slope angle is behind the crest, where "
        "the model reports grazing cancellation instead of a diffracted field, so those numbers are not "
        "quoted. At the crest the slope acts as a tilted mirror of growing effective height (the low-angle "
        "gain downhill); at mid-slope the specular point for 15–35° lands on the plain below and the extra "
        "phase puts a null where level ground has its lobe. The sharp notches between 30° and 50° downhill are "
        "where the specular point steps from the slope onto the plain: a facet model is discontinuous there, "
        "and a real hill is not. At the toe the model reproduces level ground "
        f"exactly (checked: {toe_dev:.0e} dB). Facets shorter than a few wavelengths sit outside the "
        "model's comfortable regime, so the 40 m hill is the more credible of the two.",
        fontsize=7.4,
        color=INK2,
        wrap=True,
        va="bottom",
    )
    out = HERE / "mike_hillside_elevation_2026-09-10"
    fig.savefig(out.with_suffix(".png"), dpi=170, facecolor="white")
    fig.savefig(out.with_suffix(".pdf"), facecolor="white")
    print("wrote", out.with_suffix(".png"), "and .pdf")


if __name__ == "__main__":
    main()
