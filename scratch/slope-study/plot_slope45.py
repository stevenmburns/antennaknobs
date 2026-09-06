"""One picture for the QRZ slope thread: the level-ground elevation pattern of
the buried-radial vertical, and the same pattern with the ground tilted 45
degrees through it (mast normal to the slope). Polar, uphill-downhill plane,
gain in dBi, true elevation from the downhill horizon (right) over the
zenith to the uphill horizon (left)."""

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np

from antennaknobs.designs.verticals.buried_radial_vertical import Builder
from antennaknobs.engines.momwire import MomwireEngine

SOIL = ("finite", 13.0, 0.005)
SLOPE = 45.0
SERIES = "#2a78d6"
GROUND = "#c3c2b7"
INK = "#0b0b0b"
INK2 = "#52514e"
FLOOR = -20.0


def elevation_cut(ff):
    """gain(psi) at azimuth 0 (uphill side) and 180 (downhill side), psi 0..90."""
    rings = np.asarray(ff.rings)  # [theta 0..89 from zenith][phi 0..360]
    th = np.asarray(ff.thetas)
    psi = 90.0 - th
    j180 = int(np.argmin(np.abs(np.asarray(ff.phis) - 180.0)))
    up, dn = rings[:, 0], rings[:, j180]
    order = np.argsort(psi)
    return psi[order], up[order], dn[order]


def to_polar(elev_deg, gain):
    r = np.clip(gain, FLOOR, 0.0) - FLOOR
    return np.deg2rad(elev_deg), r


eng = MomwireEngine(Builder(), ground=SOIL)
z = eng.impedance()[0]
ff = eng.far_field()
psi, g_up, g_dn = elevation_cut(ff)

fig, axes = plt.subplots(1, 2, subplot_kw={"projection": "polar"}, figsize=(11, 5.6))
fig.patch.set_facecolor("#fcfcfb")
for ax in axes:
    ax.set_facecolor("#fcfcfb")
    ax.set_thetamin(-SLOPE)
    ax.set_thetamax(180)
    ax.set_rlim(0, -FLOOR)
    ax.set_rticks([0, 10, 20])
    ax.set_yticklabels([])
    for rv, lab in ((0.0, "−20"), (10.0, "−10"), (20.0, "0 dBi")):
        ax.text(
            np.deg2rad(88), rv - 0.6, lab, color=INK2, fontsize=7.5, ha="left", va="top"
        )
    ax.set_thetagrids(
        [0, 30, 60, 90, 120, 150, 180],
        labels=["0°", "30°", "60°", "90°", "60°", "30°", "0°"],
        color=INK2,
        fontsize=8,
    )
    ax.grid(color="#e6e5e1", linewidth=0.6)
    ax.spines["polar"].set_color("#e6e5e1")

# --- level ground: downhill side is the right half (0..90), uphill the left (90..180)
ax = axes[0]
t, r = to_polar(psi, g_dn)
ax.plot(t, r, color=SERIES, linewidth=2)
t, r = to_polar(180.0 - psi, g_up)
ax.plot(t, r, color=SERIES, linewidth=2)
ax.fill_between(
    np.deg2rad(np.linspace(-SLOPE, 0, 40)),
    0,
    -FLOOR,
    color=GROUND,
    alpha=0.35,
    linewidth=0,
)
ax.plot([0, np.pi], [-FLOOR, -FLOOR], color=INK2, linewidth=1)
ax.set_title("On level ground", color=INK, fontsize=11, pad=14)
ax.annotate(
    f"3° elevation: {np.interp(3, psi, g_dn):.1f} dBi",
    xy=to_polar(3, np.interp(3, psi, g_dn)),
    xytext=(np.deg2rad(12), 6),
    color=INK2,
    fontsize=8,
    arrowprops=dict(arrowstyle="-", color=INK2, lw=0.6),
)

# --- mast normal to a 45° slope: same pattern, the ground line rotated
ax = axes[1]
# downhill side: true elevation e = psi - SLOPE  (runs from -45 into the valley up to 45)
t, r = to_polar(psi - SLOPE, g_dn)
ax.plot(t, r, color=SERIES, linewidth=2)
# uphill side: true elevation e = psi + SLOPE, drawn from the zenith side: angle = 180 - e
t, r = to_polar(180.0 - (psi + SLOPE), g_up)
# the uphill branch continues OVER the zenith onto the downhill side
ax.plot(t, r, color=SERIES, linewidth=2)
# the hill: everything below the tilted ground line
hill = np.deg2rad(np.linspace(180 - SLOPE, 360 - SLOPE - 5, 80))
ax.fill_between(hill, 0, -FLOOR, color=GROUND, alpha=0.35, linewidth=0)
ax.plot(
    [np.deg2rad(-SLOPE), np.deg2rad(180 - SLOPE)],
    [-FLOOR, -FLOOR],
    color=INK2,
    linewidth=1,
)
ax.plot([0, np.pi], [-FLOOR, -FLOOR], color=INK2, linewidth=0.8, linestyle=(0, (3, 3)))
ax.set_title("Mast normal to a 45° slope", color=INK, fontsize=11, pad=14)
g3 = np.interp(3 + SLOPE, psi, g_dn)
ax.annotate(
    f"3° above the downhill horizon: {g3:.1f} dBi",
    xy=to_polar(3, g3),
    xytext=(np.deg2rad(50), 19.5),
    color=INK2,
    fontsize=8,
    arrowprops=dict(arrowstyle="-", color=INK2, lw=0.6),
)
ax.text(
    np.deg2rad(150),
    9,
    "uphill sky\nbehind the hill",
    color=INK2,
    fontsize=8,
    ha="center",
)
ax.text(
    np.deg2rad(-25),
    12,
    "main lobe\ninto the valley",
    color=INK2,
    fontsize=8,
    ha="center",
)
ax.text(
    np.deg2rad(-SLOPE + 4),
    -FLOOR - 1.0,
    "hill",
    color=INK2,
    fontsize=8,
    ha="left",
    va="top",
)

fig.suptitle(
    f"Quarter-wave vertical over 4 buried radials, 7.1 MHz, soil εr 13 / σ 0.005 S/m — gain in the uphill–downhill plane, Z = {z.real:.1f}{z.imag:+.1f}j Ω either way",
    color=INK,
    fontsize=9.5,
    y=0.98,
)
fig.text(
    0.5,
    0.02,
    "Grey: the ground. Dashed: the true horizon. momwire (antennaknobs.dev) — the same solve in both panels; only the ground is tilted.",
    ha="center",
    color=INK2,
    fontsize=8,
)
fig.tight_layout(rect=(0, 0.04, 1, 0.95))
out = "scratch/slope-study/slope45_elevation_cut.png"
fig.savefig(out, dpi=160)
print("wrote", out)
