"""Mike's profile stretched to the easy regime: 1000 m of relief, the mast
mid-slope, 500 m (about 12 λ at 7.1 MHz) above the plain and as far below
the plateau. Two slopes, 45° and 20°. Each polar plot carries three lines:

- level ground (reference);
- the specular-facet terrain model (issue #534) with the mast mid-slope on
  the long hill — the model behind probe9/probe10, solved on level ground
  and composed per direction off the facet the specular point lands on;
  it reads nothing below the horizontal;
- the rotated-sky planar-slope solve from the slope study (probe8's
  DanAntenna, the plumb mast with radials an inch above the slope, solved
  in the tilted ground frame and read in the true frame) — the "mast ON a
  long uniform slope" case the QRZ thread discussed, which does see the
  downhill sky between the horizontal and the slope surface.

Question answered: on a slope long enough for Mike's 20 λ rule, does the
facet model reproduce the rotated-sky picture above the horizontal? The
uphill sector below the slope angle is hatched (behind the crest; the facet
model has no diffraction, the planar model has no sky there at all).

Antenna in both: plumb 0.956 λ/4 mast, four λ/4 radials an inch above the
surface, 1 mm wire (AC6LA's spelling). Far fields cache as npz.
"""

import argparse
import math
import os
import pathlib
import sys
from types import SimpleNamespace

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
from probe8_dan_antenna import DanAntenna  # noqa: E402
from probe9_mike_hillside import FREQ, LAMBDA, SOIL, mike_terrain  # noqa: E402
from probe10_mike_elevation_figure import (  # noqa: E402
    C_CREST,
    C_FLAT,
    C_MID,
    GRID,
    GROUND,
    INK,
    INK2,
    MUTED,
    PlumbVerticalSurfaceRadials,
    elevation_cut,
)

H_RELIEF = 1000.0
SLOPES = (45.0, 20.0)
F_MAST = 0.5
N_FACETS = 48  # per ramp: ~10 m facets on the 45° hill, ~57 m on the 20° one
RMIN, RMAX = -30.0, 5.0
C_FACET, C_PLANAR = C_MID, C_CREST


def _cache_ff(path, make):
    if path.exists():
        d = np.load(path, allow_pickle=False)
        return SimpleNamespace(
            rings=d["rings"], thetas=d["thetas"], phis=d["phis"]
        ), complex(d["z"])
    z, ff_full = make()
    ff = SimpleNamespace(
        rings=np.asarray(ff_full.rings),
        thetas=np.asarray(ff_full.thetas),
        phis=np.asarray(ff_full.phis),
    )
    np.savez(path, rings=ff.rings, thetas=ff.thetas, phis=ff.phis, z=np.complex128(z))
    return ff, z


def solve_level(cache):
    def make():
        e = MomwireEngine(PlumbVerticalSurfaceRadials(), ground=("finite",) + SOIL)
        return e.impedance()[0], e.far_field()

    return _cache_ff(cache / "probe10_flat.npz", make)


def solve_facet(cache, slope):
    def make():
        probe9.N_FACETS = N_FACETS
        terrain = mike_terrain(H_RELIEF, slope, F_MAST)
        e = MomwireEngine(PlumbVerticalSurfaceRadials(), ground=("terrain", terrain))
        return e.impedance()[0], e.far_field()

    return _cache_ff(
        cache / f"probe11_facet_H{H_RELIEF:.0f}_S{slope:.0f}_n{N_FACETS}.npz", make
    )


def solve_planar(cache, slope):
    def make():
        b = DanAntenna()
        b.slope_deg = slope
        e = MomwireEngine(b, ground=("finite",) + SOIL)
        return e.impedance()[0], e.far_field()

    return _cache_ff(cache / f"probe11_planar_S{slope:.0f}.npz", make)


def facet_line(ff):
    els_d, g_d = elevation_cut(ff, 0.0)
    els_u, g_u = elevation_cut(ff, 180.0)
    th = np.concatenate([els_d, 180.0 - els_u[::-1]])
    g = np.concatenate([g_d, g_u[::-1]])
    return th, g


def polar_axes(ax, slope, level, facet, planar):
    def draw(th_deg, g, color, lw, ls, label):
        g = np.asarray(g, dtype=float)
        ok = np.isfinite(g)
        g = np.clip(np.where(ok, g, RMIN), RMIN, None)
        ax.plot(
            np.radians(th_deg),
            g,
            color=color,
            lw=lw,
            ls=ls,
            label=label,
            solid_joinstyle="round",
        )

    th, g = facet_line(level)
    draw(th, g, C_FLAT, 1.5, (0, (4, 3)), "level ground")
    th, g = facet_line(facet)
    draw(
        th, g, C_FACET, 2.0, "-", f"facet model: mast mid-slope, {H_RELIEF:.0f} m hill"
    )
    ang, g = true_cut(planar, slope)
    draw(ang, g, C_PLANAR, 2.0, "-", "rotated sky: mast on the infinite planar slope")
    # behind the crest (uphill below the slope angle)
    th_s = np.radians(np.linspace(180.0 - slope, 180.0, 40))
    ax.fill_between(th_s, RMIN, RMAX, color=MUTED, alpha=0.14, hatch="///", lw=0)
    # below the horizontal downhill: real sky on a long slope, facet model blind
    th_b = np.radians(np.linspace(-slope, 0.0, 40))
    ax.fill_between(th_b, RMIN, RMAX, color=C_PLANAR, alpha=0.06, lw=0)

    ax.set_theta_zero_location("E")
    ax.set_theta_direction(1)
    ax.set_thetamin(-slope)
    ax.set_thetamax(180)
    ax.set_rlim(RMIN, RMAX)
    ax.set_rticks([-25, -20, -15, -10, -5, 0, 5])
    ax.set_yticklabels([])
    angles = (
        list(range(-int(slope), 181, 15))
        if slope % 15 == 0
        else [-int(slope), *range(0, 181, 15)]
    )
    labels = []
    for t in angles:
        if t == 90:
            labels.append("")
        elif t < 0:
            labels.append(f"−{-t}°")
        else:
            labels.append(f"{min(t, 180 - t)}°")
    ax.set_thetagrids(angles, labels=labels)
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
        np.radians(9), RMAX + 6.5, "downhill, az 0 →", fontsize=8, color=INK2, ha="left"
    )
    ax.text(
        np.radians(171),
        RMAX + 6.5,
        "← uphill, az 180",
        fontsize=8,
        color=INK2,
        ha="right",
    )


def profile_axes(ax, slope):
    """Mike's drawing at 1000 m relief: plateau left, plain right, the mast
    mid-slope. Not to scale with the antenna (a λ/4 mast is 10 m)."""
    H = H_RELIEF
    run_m = H / math.tan(math.radians(slope))
    left, right = -0.35 * run_m - 200, 1.35 * run_m + 200
    ground = [
        (left, H),
        (0.0, H),
        (run_m, 0.0),
        (right, 0.0),
        (right, -250.0),
        (left, -250.0),
    ]
    ax.add_patch(Polygon(ground, closed=True, facecolor=GROUND, edgecolor=INK2, lw=1.0))
    x, z = 0.5 * run_m, 0.5 * H
    ax.plot([x, x], [z, z + 120], color=C_FACET, lw=2.4, solid_capstyle="round")
    ax.text(
        x + 40, z + 110, "mast, mid-slope", ha="left", va="top", fontsize=8.5, color=INK
    )
    xa = -0.2 * run_m - 60
    ax.annotate(
        "",
        xy=(xa, H),
        xytext=(xa, 0),
        arrowprops=dict(arrowstyle="<->", color=INK2, lw=0.9),
    )
    ax.text(
        xa - 40,
        H / 2,
        f"H = {H:.0f} m\n= {H / LAMBDA:.0f} λ",
        va="center",
        ha="right",
        fontsize=8.5,
        color=INK,
    )
    ax.text(
        run_m * 0.30, H * 0.14, f"{slope:.0f}°", fontsize=8.5, color=INK, ha="center"
    )
    ax.text(
        right - 60, -110, "plain", fontsize=8.5, color=INK2, style="italic", ha="right"
    )
    ax.text(
        -0.2 * run_m,
        H - 130,
        "plateau",
        fontsize=8.5,
        color=INK2,
        style="italic",
        ha="center",
    )
    x0 = right - 60 - 20 * LAMBDA
    ax.plot([x0, x0 + 20 * LAMBDA], [-180, -180], color=INK, lw=1.2)
    ax.text(
        x0 + 10 * LAMBDA,
        -200,
        f"20 λ = {20 * LAMBDA:.0f} m",
        ha="center",
        va="top",
        fontsize=8,
        color=INK,
    )
    ax.set_xlim(left, right)
    ax.set_ylim(-260, H + 60)
    ax.set_aspect("equal")
    ax.axis("off")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--cache", default=os.environ.get("PROBE10_CACHE", ""))
    args = ap.parse_args()
    cache = pathlib.Path(args.cache) if args.cache else HERE / "cache"
    cache.mkdir(parents=True, exist_ok=True)

    level, z_level = solve_level(cache)
    runs = {}
    for s in SLOPES:
        runs[s] = (solve_facet(cache, s), solve_planar(cache, s))
    gl = gain_lookup(level)
    print(
        f"level ground: Z {z_level:.2f}  3°/10°/20° {gl(3, 0):.1f}/{gl(10, 0):.1f}/{gl(20, 0):.1f}"
    )
    for s, ((ff_f, z_f), (ff_p, z_p)) in runs.items():
        gf = gain_lookup(ff_f)
        ang, gp = true_cut(ff_p, s)
        gpi = lambda a: float(np.interp(a, ang, gp))  # noqa: E731
        print(
            f"slope {s:.0f}°: facet Z {z_f:.2f} down 3/10/20/30° "
            f"{gf(3, 0):.1f}/{gf(10, 0):.1f}/{gf(20, 0):.1f}/{gf(30, 0):.1f} up 60° {gf(60, 180):.1f} | "
            f"planar Z {z_p:.2f} down −{s:.0f}+3/3/10/20/30° "
            f"{gpi(-s + 3):.1f}/{gpi(3):.1f}/{gpi(10):.1f}/{gpi(20):.1f}/{gpi(30):.1f} up 60° {gpi(120):.1f}"
        )

    fig = plt.figure(figsize=(8.5, 11), facecolor="white")
    fig.text(
        0.07,
        0.968,
        "M0AGP's hillside stretched to 1000 m: facet model against the rotated sky",
        fontsize=12.5,
        color=INK,
        va="baseline",
    )
    fig.text(
        0.07,
        0.955,
        f"{FREQ} MHz, soil εr {SOIL[0]:.0f} / σ {SOIL[1]} S/m. Plumb quarter-wave, four radials an inch above "
        f"the ground, mid-slope on a {H_RELIEF:.0f} m hill:\n{0.5 * H_RELIEF:.0f} m ({0.5 * H_RELIEF / LAMBDA:.0f} λ) "
        "above the plain and below the plateau — the regime where the tilted-sky method should hold.",
        fontsize=8.8,
        color=INK2,
        va="top",
    )
    ax_p = fig.add_axes([0.16, 0.835, 0.68, 0.095])
    profile_axes(ax_p, SLOPES[0])
    # matplotlib fits the full circle to the box and centres the wedge's
    # bounding box in it: for a wedge from -s to 180 the origin sits
    # r_h·(1 - sin s)/2 below the box centre, the top at origin + r_h and
    # the bottom at origin - r_h·sin s.
    r_in = 2.0
    w, h, r_h = 2 * r_in / 8.5, 2 * r_in / 11, r_in / 11
    for i, (s, top) in enumerate(zip(SLOPES, (0.79, 0.375), strict=True)):
        sin_s = math.sin(math.radians(s))
        origin = top - r_h
        cy = origin + r_h * (1 - sin_s) / 2
        ax = fig.add_axes([0.5 - w / 2, cy - h / 2, w, h], projection="polar")
        (ff_f, _), (ff_p, _) = runs[s]
        polar_axes(ax, s, level, ff_f, ff_p)
        fig.text(
            0.5,
            top + 0.02,
            f"{s:.0f}° slope, {H_RELIEF:.0f} m of relief — elevation above the true horizontal",
            fontsize=9.5,
            color=INK,
            ha="center",
            va="bottom",
        )
        if i == 0:
            fig.legend(
                *ax.get_legend_handles_labels(),
                loc="upper center",
                bbox_to_anchor=(0.5, origin - r_h * sin_s - 0.012),
                fontsize=8,
                frameon=False,
                ncol=1,
            )
    fig.text(
        0.07,
        0.015,
        "How to read it. Blue is the terrain model of the previous page with the hill made 24 λ tall and the mast "
        "half way up: solved on level ground, each direction reflected off the facet its specular point lands on; it "
        "reads nothing below the horizontal. Orange is the planar-slope solve from the QRZ thread: the same antenna on "
        "an infinite 45° (or 20°) plane, solved in the ground's frame with the mast plumb and the radials on the slope, "
        "read in the true frame, so it sees the downhill sky between the horizontal and the slope surface (tinted), "
        "where its main lobe sits. The two are not meant to agree above the horizontal, and they do not: a ray leaving "
        "the mast shallower than the slope angle passes over the slope and reaches the plain, so above the horizontal "
        "the downhill sky is the direct ray plus the plain's reflection from 1 to 10 km away, which for a mast 12 λ up "
        "is the fine height-gain comb the facet model draws (and the infinite plane, having no plain, cannot). The slope "
        "itself only feeds directions below the horizontal, which is the rotated sky's lobe. Right at the horizon the two "
        "meet: about 10 dB over level ground at 3°. Hatched: uphill below the slope angle, behind the crest, quoted by "
        "neither model. The mast in the sketch is not to scale.",
        fontsize=7.4,
        color=INK2,
        wrap=True,
        va="bottom",
    )
    out = HERE / "mike_long_hillside_2026-09-10"
    fig.savefig(out.with_suffix(".png"), dpi=170, facecolor="white")
    fig.savefig(out.with_suffix(".pdf"), facecolor="white")
    print("wrote", out.with_suffix(".png"), "and .pdf")


if __name__ == "__main__":
    main()
