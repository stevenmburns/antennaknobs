"""The corrected Smith figure for the #518 postmortem.

Same house style, series colors and layout as figures.py's smith section
(colors follow the entities across the figure pair), with bs1/bs2 replaced
by the corrected ladder (results-corrected.json — junction list fixed, wire 6
present) and the electrostatic referee added. The point of the figure: the
NEC-2 scheme still walks the chart; the four clean engines AND the referee
now sit in ONE dot.
"""

import json
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np

HERE = Path(__file__).parent
SURFACE = "#fcfcfb"
INK, INK2, GRID = "#1a1a19", "#5f5e56", "#e8e8e6"
SERIES = {
    "nec5cl": ("#1baf7a", "NEC-5 (licensed)", "solid"),
    "razor-nec5": ("#b2379b", "momwire razor, NEC-5 quadrature", "dashed"),
    "bs2": ("#2a78d6", "momwire bs2", "solid"),
    "bs1": ("#eb6834", "momwire bs1", "solid"),
    "sin-nec2": ("#eda100", "momwire sinusoidal (NEC-2 scheme)", "solid"),
}
R = json.load(open(HERE / "results.json"))
R.update(json.load(open(HERE / "results-corrected.json")))  # bs1/bs2 fixed
KS = [1, 2, 4, 8, 16]
dense = HERE / "results-dense.json"  # ladder_dense.py: every k = 1..16
if dense.exists():
    for name, rungs in json.load(open(dense)).items():
        R.setdefault(name, {}).update(rungs)
    KS = list(range(1, 17))
LABEL_KS = {1, 2, 4, 8, 16}
V = -404675.9j
X_REFEREE = -370.5e3  # two-conductor gap capacitance, 858.7 pF at 500 Hz
Z0 = 371.0e3


def z_of(name, k):
    re, im, _ = R[name][str(k)]
    return V / complex(re, im)


def gamma(z):
    zn = z / Z0
    return (zn - 1) / (zn + 1)


fig, ax = plt.subplots(figsize=(8.6, 8.6), facecolor=SURFACE)
ax.set_facecolor(SURFACE)
ax.set_aspect("equal")
ax.axis("off")
theta = np.linspace(0, 2 * np.pi, 720)
ax.plot(np.cos(theta), np.sin(theta), color=INK2, lw=1.2)
for r in (0.2, 0.5, 1.0, 2.0, 5.0):
    c, rad = r / (1 + r), 1 / (1 + r)
    ax.plot(c + rad * np.cos(theta), rad * np.sin(theta), color=GRID, lw=0.8)
for x in (0.2, 0.5, 1.0, 2.0, 5.0):
    for sign in (1, -1):
        cx, cy, rad = 1.0, sign * 1 / x, 1 / x
        th = np.linspace(0, 2 * np.pi, 2000)
        px, py = cx + rad * np.cos(th), cy + rad * np.sin(th)
        keep = px**2 + py**2 <= 1.0000001
        ax.plot(px[keep], py[keep], color=GRID, lw=0.8)
ax.plot([-1, 1], [0, 0], color=GRID, lw=0.8)

for name, (color, label, ls) in SERIES.items():
    ks = [k for k in KS if str(k) in R.get(name, {})]
    g = [gamma(z_of(name, k)) for k in ks]
    xs, ys = [c.real for c in g], [c.imag for c in g]
    lw = 2.2 if name == "sin-nec2" else 1.6
    ax.plot(
        xs,
        ys,
        color=color,
        lw=lw,
        marker="o",
        ms=5 if name == "sin-nec2" else 3.5,
        mfc=color,
        mec=SURFACE,
        mew=0.6,
        ls=(0, (4, 3)) if ls == "dashed" else "-",
        label=label,
        zorder=5,
    )
    if name == "sin-nec2":
        for k, cx, cy in zip(ks, xs, ys):
            if k not in LABEL_KS:
                continue
            dx = -22 if cx > 0.3 else 8
            ax.annotate(
                f"{31 * k}",
                (cx, cy),
                textcoords="offset points",
                xytext=(dx, 8),
                fontsize=8.5,
                color=color,
            )

g_ref = gamma(complex(0.0, X_REFEREE))
ax.plot(
    [g_ref.real],
    [g_ref.imag],
    marker="*",
    ms=13,
    color=INK,
    mec=SURFACE,
    mew=0.6,
    ls="none",
    zorder=6,
    label="electrostatic referee (≈859 pF)",
)

# zoom lens on the clean cluster near -j1
axins = ax.inset_axes([0.64, 0.60, 0.32, 0.32])
axins.set_facecolor("#ffffff")
for name, (color, label, ls) in SERIES.items():
    if name == "sin-nec2":
        continue
    ks = [k for k in KS if str(k) in R.get(name, {})]
    g = [gamma(z_of(name, k)) for k in ks]
    axins.plot(
        [c.real for c in g],
        [c.imag for c in g],
        color=color,
        lw=1.4,
        marker="o",
        ms=3.5,
        mfc=color,
        mec="#ffffff",
        mew=0.4,
        ls=(0, (4, 3)) if ls == "dashed" else "-",
    )
axins.plot(
    [g_ref.real],
    [g_ref.imag],
    marker="*",
    ms=11,
    color=INK,
    mec="#ffffff",
    mew=0.5,
    ls="none",
    zorder=6,
)
g_all = [
    gamma(z_of(n, k))
    for n in SERIES
    if n != "sin-nec2"
    for k in KS
    if str(k) in R.get(n, {})
] + [g_ref]
cx = float(np.mean([c.real for c in g_all]))
cy = float(np.mean([c.imag for c in g_all]))
pad = 1.3 * max(
    max(abs(c.real - cx) for c in g_all), max(abs(c.imag - cy) for c in g_all)
)
axins.set_xlim(cx - pad, cx + pad)
axins.set_ylim(cy - pad, cy + pad)
axins.set_xticks([])
axins.set_yticks([])
for sp in axins.spines.values():
    sp.set_color(INK2)
ax.indicate_inset_zoom(axins, edgecolor=INK2, lw=0.8)
axins.set_title(
    "the four clean engines converge\nonto the referee's mark ★",
    fontsize=8.5,
    color=INK,
)

ax.legend(
    loc="lower left",
    frameon=False,
    fontsize=9,
    labelcolor=INK,
    bbox_to_anchor=(-0.02, -0.06),
)
ax.set_title(
    "W7EL's coupled-loop model (500 Hz) — refinement trajectories on the Smith chart (Z₀ = 371 kΩ)\n"
    "31 → 496 segments, every uniform refinement of the model's own mesh: the NEC-2 scheme\n"
    "walks the whole chart while NEC-5, momwire's solvers and an independent\n"
    "electrostatic check agree in one dot",
    color=INK,
    fontsize=10.5,
    pad=14,
)
fig.tight_layout()
fig.savefig(HERE / "coupled-loop-smith-outbound.png", dpi=160, facecolor=SURFACE)
print("corrected smith written")
