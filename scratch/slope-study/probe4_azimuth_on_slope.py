"""An azimuth plot at a fixed TRUE elevation for a vertical normal to a
slope: rotate each true-frame direction into the ground frame, read the
untilted far field there, and mark directions that fall below the tilted
ground as behind the hill. True azimuth 0 = downhill; ground-frame azimuth
180 = downhill (the convention the other probes use)."""

import math
import sys

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np

from antennaknobs.engines.momwire import MomwireEngine

from probe3_downhill_radials import SOIL, sector_builder

SERIES = ("#2a78d6", "#eb6834")
INK, INK2 = "#0b0b0b", "#52514e"
FLOOR = -25.0


def true_to_ground(az_true_deg, elev_true_deg, slope_deg):
    """(elev_ground, az_ground) for a true-frame direction; elev_ground < 0
    means the direction is inside the hill."""
    a, e, s = map(math.radians, (az_true_deg, elev_true_deg, slope_deg))
    x, y, z = math.cos(e) * math.cos(a), math.cos(e) * math.sin(a), math.sin(e)
    xg = x * math.cos(s) - z * math.sin(s)  # rotate about y by -slope
    zg = x * math.sin(s) + z * math.cos(s)
    return math.degrees(math.asin(zg)), (
        math.degrees(math.atan2(y, xg)) + 180.0
    ) % 360.0


def gain_lookup(ff):
    rings = np.asarray(ff.rings)
    elev = 90.0 - np.asarray(ff.thetas)
    order = np.argsort(elev)
    elev, rings = elev[order], rings[order]
    phis = np.asarray(ff.phis)

    def g(elev_deg, az_deg):
        if elev_deg < 0.0:
            return float("nan")
        i = int(np.clip(np.searchsorted(elev, elev_deg) - 1, 0, len(elev) - 2))
        j = int(np.clip(np.searchsorted(phis, az_deg) - 1, 0, len(phis) - 2))
        ft = (elev_deg - elev[i]) / (elev[i + 1] - elev[i])
        fp = (az_deg - phis[j]) / (phis[j + 1] - phis[j])
        return float(
            rings[i, j] * (1 - ft) * (1 - fp)
            + rings[i + 1, j] * ft * (1 - fp)
            + rings[i, j + 1] * (1 - ft) * fp
            + rings[i + 1, j + 1] * ft * fp
        )

    return g


def azimuth_ring(ff, elev_true, slope, step=1.0):
    g = gain_lookup(ff)
    az = np.arange(0.0, 360.0 + step, step)
    out = []
    for a in az:
        eg, ag = true_to_ground(a, elev_true, slope)
        out.append(g(eg, ag))
    return az, np.asarray(out)


if __name__ == "__main__":
    slope = float(sys.argv[1]) if len(sys.argv) > 1 else 45.0
    elev = float(sys.argv[2]) if len(sys.argv) > 2 else 3.0
    cases = [
        ((4, 360.0), "4 radials, full circle"),
        ((4, 180.0), "4 radials, downhill half"),
    ]
    rings = []
    for (n, sec), name in cases:
        e = MomwireEngine(sector_builder(n, sec)(), ground=SOIL)
        e.impedance()
        az, g = azimuth_ring(e.far_field(), elev, slope)
        rings.append((name, az, g))
    print(
        f"true elevation {elev:g} deg, slope {slope:g} deg (0 = downhill); dBi, '--' = behind the hill"
    )
    print("  az   " + "  ".join(f"{name:>26s}" for name, _, _ in rings))
    for k in range(0, 361, 15):
        vals = "  ".join(
            f"{('--' if math.isnan(g[k]) else f'{g[k]:.2f}'):>26s}" for _, _, g in rings
        )
        print(f"{k:4d}   {vals}")

    fig, ax = plt.subplots(subplot_kw={"projection": "polar"}, figsize=(6.4, 6.4))
    fig.patch.set_facecolor("#fcfcfb")
    ax.set_facecolor("#fcfcfb")
    ax.set_theta_zero_location("E")
    ax.set_theta_direction(1)
    for (name, az, g), c in zip(rings, SERIES, strict=True):
        r = np.clip(g, FLOOR, 0.0) - FLOOR
        r = np.where(np.isnan(g), np.nan, r)
        ax.plot(np.deg2rad(az), r, color=c, linewidth=2, label=name)
    ax.set_rlim(0, -FLOOR)
    ax.set_rticks([0, 5, 15, 25])
    ax.set_yticklabels(["", "−20", "−10", "0 dBi"], color=INK2, fontsize=8)
    ax.set_rlabel_position(135)
    ax.set_thetagrids(
        range(0, 360, 30),
        labels=[
            "downhill" if d == 0 else ("uphill" if d == 180 else f"{d}°")
            for d in range(0, 360, 30)
        ],
        color=INK2,
        fontsize=8,
    )
    ax.grid(color="#e6e5e1", linewidth=0.6)
    ax.spines["polar"].set_color("#e6e5e1")
    ax.text(np.deg2rad(180), 6, "behind\nthe hill", color=INK2, fontsize=8, ha="center")
    ax.legend(
        loc="lower center",
        bbox_to_anchor=(0.5, -0.14),
        ncol=2,
        frameon=False,
        fontsize=8,
    )
    ax.set_title(
        f"Azimuth at {elev:g}° true elevation, mast normal to a {slope:g}° slope\nresonant vertical, 7.1 MHz, soil εr 13 / σ 0.005",
        color=INK,
        fontsize=10,
        pad=18,
    )
    out = f"scratch/slope-study/azimuth_{int(elev)}deg_slope{int(slope)}.png"
    fig.tight_layout()
    fig.savefig(out, dpi=160)
    print("wrote", out)
