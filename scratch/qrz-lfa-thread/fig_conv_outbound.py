"""The clean-engine convergence panel (bydipole1 form) for Roy's model.

Feed X and max loop element vs segment count, every k = 1..16
(results-dense.json), NEC-2 scheme excluded so the good engines' convergence
is visible; the electrostatic referee is the dashed rail in the X panel.
"""

import json
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt

HERE = Path(__file__).parent
SURFACE = "#fcfcfb"
INK, INK2, GRID = "#1a1a19", "#5f5e56", "#e8e8e6"
SERIES = {
    "nec5cl": ("#1baf7a", "NEC-5 (licensed)"),
    "razor-nec5": ("#b2379b", "momwire razor, NEC-5 quadrature"),
    "bs2": ("#2a78d6", "momwire bs2"),
    "bs1": ("#eb6834", "momwire bs1"),
}
R = json.load(open(HERE / "results-dense.json"))
V = -404675.9j
X_REFEREE = -370.5


def style_ax(ax):
    ax.set_facecolor(SURFACE)
    ax.grid(True, color=GRID, lw=0.8)
    for s in ("top", "right"):
        ax.spines[s].set_visible(False)
    for s in ("left", "bottom"):
        ax.spines[s].set_color(INK2)
    ax.tick_params(colors=INK2, labelsize=9)


fig, ax0 = plt.subplots(figsize=(8.6, 5.8), facecolor=SURFACE)
axes = [ax0]

for name, (color, label) in SERIES.items():
    ks = sorted(int(k) for k in R[name])
    xs = [31 * k for k in ks]
    z = [V / complex(*R[name][str(k)][:2]) for k in ks]
    ys = [zz.imag / 1e3 for zz in z]
    axes[0].plot(
        xs,
        ys,
        color=color,
        lw=2,
        marker="o",
        ms=3.5,
        mfc=color,
        mec=SURFACE,
        mew=0.5,
        label=label,
    )
    if name in ("bs1", "bs2"):
        axes[0].annotate(
            label.split(",")[0],
            (xs[-1], ys[-1]),
            textcoords="offset points",
            xytext=(6, -3),
            fontsize=8.5,
            color=color,
        )

style_ax(axes[0])
axes[0].axhline(X_REFEREE, color=INK, lw=1.2, ls=(0, (5, 4)))
axes[0].annotate(
    "electrostatic referee: −370.5 kΩ (≈859 pF)",
    xy=(60, X_REFEREE),
    xytext=(0, 5),
    textcoords="offset points",
    fontsize=8.7,
    color=INK,
)
axes[0].set_ylabel("Feed reactance X (kΩ)", color=INK, fontsize=10)
axes[0].set_title(
    "every uniform refinement of the deck's 20 m mesh, k = 1..16; "
    "NEC-2 scheme excluded (it spans ±500 kΩ)",
    color=INK2,
    fontsize=9,
    loc="left",
    pad=8,
)

axes[0].legend(loc="lower right", frameon=False, fontsize=9, labelcolor=INK)
axes[0].set_xlim(0, 620)
axes[0].set_xlabel("Number of segments", color=INK, fontsize=10)
axes[0].annotate(
    "razor rides ON the licensed engine\n(0.006 %: the curves overprint)",
    xy=(150, -371.85),
    fontsize=8.7,
    color="#b2379b",
)
fig.suptitle(
    "W7EL's coupled-loop model (500 Hz) — feed reactance vs segment count\n"
    "NEC-5, momwire razor, bs1, bs2 and an independent electrostatic check: one limit",
    color=INK,
    fontsize=11,
)
fig.tight_layout(rect=(0, 0, 1, 0.91))
fig.savefig(HERE / "coupled-loop-convergence-outbound.png", dpi=160, facecolor=SURFACE)
print("convergence panel written")
