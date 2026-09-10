"""Issue #1373: the diffraction model on M0AGP's 40 m, 45° hill as polar
elevation plots — one half-disc per mast position (mid-slope, crest),
downhill to the right, uphill to the left, the #534 specular path dashed
and `Terrain(diffraction=True)` solid. Same solves as probe13."""

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
from probe9_mike_hillside import mike_terrain  # noqa: E402
from probe10_mike_elevation_figure import (  # noqa: E402
    C_CREST,
    C_MID,
    GRID,
    INK,
    INK2,
    MUTED,
    PlumbVerticalSurfaceRadials,
)

probe9.N_FACETS = 12
RMIN, RMAX = -30.0, 5.0
SLOPE = 45.0


def half_disc(ff):
    g = gain_lookup(ff)
    els = np.arange(1.0, 90.0, 1.0)
    d = np.array([g(e, 0.0) for e in els])
    u = np.array([g(e, 180.0) for e in els])
    th = np.concatenate([els, 180.0 - els[::-1]])
    gain = np.concatenate([d, u[::-1]])
    return np.radians(th), np.clip(np.nan_to_num(gain, nan=RMIN), RMIN, None)


def polar(ax, ff_spec, ff_utd, color, title):
    th, g = half_disc(ff_spec)
    ax.plot(th, g, color=MUTED, lw=1.6, ls=(0, (4, 3)), label="specular only (#534)")
    th, g = half_disc(ff_utd)
    ax.plot(
        th,
        g,
        color=color,
        lw=2.1,
        label="shadowing + tilted mirrors + diffraction (#1373)",
    )
    th_s = np.radians(np.linspace(180.0 - SLOPE, 180.0, 40))
    ax.fill_between(th_s, RMIN, RMAX, color=MUTED, alpha=0.12, hatch="///", lw=0)
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
    ax.text(np.radians(9), RMAX + 6.5, "downhill →", fontsize=8, color=INK2, ha="left")
    ax.text(np.radians(171), RMAX + 6.5, "← uphill", fontsize=8, color=INK2, ha="right")
    ax.set_title(title, fontsize=10, color=INK, pad=14)


def main():
    fig = plt.figure(figsize=(11, 6.2), facecolor="white")
    for i, (f, name, color) in enumerate(
        ((0.5, "mast mid-slope", C_MID), (1.0, "mast at the crest", C_CREST))
    ):
        t = mike_terrain(40.0, SLOPE, f)
        spec = MomwireEngine(
            PlumbVerticalSurfaceRadials(), ground=("terrain", t)
        ).far_field()
        utd = MomwireEngine(
            PlumbVerticalSurfaceRadials(),
            ground=("terrain", Terrain(sectors=t.sectors, diffraction=True)),
        ).far_field()
        ax = fig.add_axes([0.03 + 0.49 * i, 0.08, 0.46, 0.8], projection="polar")
        polar(ax, spec, utd, color, f"{name}, 40 m hill at {SLOPE:.0f}°, 7.1 MHz")
        if i == 0:
            ax.legend(
                loc="upper center",
                bbox_to_anchor=(1.05, 0.02),
                fontsize=8,
                frameon=False,
                ncol=2,
            )
    fig.text(
        0.5,
        0.965,
        "Hatched: uphill below the slope angle, behind the crest — now a shadowed, diffracted field instead of an artefact",
        fontsize=8.5,
        color=INK2,
        ha="center",
    )
    out = HERE / "diffraction_polar_2026-09-10.png"
    fig.savefig(out, dpi=150, bbox_inches="tight")
    print("wrote", out)


if __name__ == "__main__":
    main()
