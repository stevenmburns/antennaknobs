"""N4PC Loop (captures 0081-0084): the anti-resonance overlay.

The corpus's sharpest 'deviation' (3.8-4.3 kOhm at 14.1 MHz) is the
CAPTURE's mesh, not the seam: at 16 segs/side the licensed engine's
anti-resonance sits ~1 % high in frequency, and refining it x8 lands its
curve on top of the seam's deck-mesh curve. GD variant (the deviation is
ground-independent, which exonerates the Sommerfeld machinery).
"""

import json
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt

HERE = Path(__file__).parent
SURFACE = "#fcfcfb"
INK, INK2, GRID = "#1a1a19", "#5f5e56", "#e8e8e6"
D = json.load(open(HERE / "sweep.json"))["freq"]
SERIES = [
    ("seam", "#2a78d6", "momwire seam (bs2), 16 segs/side — the deck's own mesh", "-"),
    ("nec5cl", "#1baf7a", "NEC-5 (licensed), 16 segs/side — the capture", "-"),
    ("nec5cl-x8", "#1baf7a", "NEC-5 (licensed), 128 segs/side", (0, (4, 3))),
]

fig, axes = plt.subplots(2, 1, figsize=(8.6, 8.6), sharex=True, facecolor=SURFACE)
for ax in axes:
    ax.set_facecolor(SURFACE)
    ax.grid(True, color=GRID, lw=0.8)
    for s in ("top", "right"):
        ax.spines[s].set_visible(False)
    for s in ("left", "bottom"):
        ax.spines[s].set_color(INK2)
    ax.tick_params(colors=INK2, labelsize=9)

for name, color, label, ls in SERIES:
    rows = D[name]
    f = [r[0] for r in rows]
    for ax, col in ((axes[0], 1), (axes[1], 2)):
        ax.plot(
            f,
            [r[col] / 1e3 for r in rows],
            color=color,
            lw=2,
            ls=ls,
            marker="o",
            ms=3 if ls == "-" else 0,
            mfc=color,
            mec=SURFACE,
            mew=0.5,
            label=label,
        )

for ax, col in ((axes[0], 1), (axes[1], 2)):
    cap = [r for r in D["nec5cl"] if r[0] == 14.1][0]
    seam = [r for r in D["seam"] if r[0] == 14.1][0]
    ax.plot(
        [14.1],
        [cap[col] / 1e3],
        marker="o",
        ms=9,
        mfc="none",
        mec="#1baf7a",
        mew=1.6,
        ls="none",
        zorder=6,
    )
    ax.plot(
        [14.1],
        [seam[col] / 1e3],
        marker="o",
        ms=9,
        mfc="none",
        mec="#2a78d6",
        mew=1.6,
        ls="none",
        zorder=6,
    )

axes[0].set_ylabel("Feed R (kΩ)", color=INK, fontsize=10)
axes[0].annotate(
    "the corpus 'deviation': at 14.1 MHz the capture (○ green) reads the\n"
    "flank of ITS shifted anti-resonance; the seam (○ blue) reads the peak.\n"
    "Refine the licensed engine ×8 (dashed) and its curve lands on the seam's.",
    xy=(0.03, 0.44),
    xycoords="axes fraction",
    fontsize=8.8,
    color=INK2,
)
axes[1].set_ylabel("Feed X (kΩ)", color=INK, fontsize=10)
axes[1].set_xlabel("Frequency (MHz)", color=INK, fontsize=10)
axes[1].axhline(0.0, color=INK2, lw=0.8)
axes[1].annotate(
    "Δf_res ≈ 0.14 MHz (~1 %) at the capture's mesh:\n"
    "the resonance slope (~1.8 kΩ / 50 kHz) turns it into 3.8-4.3 kΩ of Z",
    xy=(0.03, 0.08),
    xycoords="axes fraction",
    fontsize=8.8,
    color=INK2,
)
axes[0].legend(loc="upper left", frameon=False, fontsize=8.8, labelcolor=INK)
fig.suptitle(
    "N4PC Loop (CQ Dec. 1990; captures 0081-0084) — the anti-resonance, seam vs licensed engine\n"
    "15.5 m square loop at 15.24 m, MININEC ground (the deviation is ground-independent)",
    color=INK,
    fontsize=10.5,
)
fig.tight_layout(rect=(0, 0, 1, 0.93))
fig.savefig(HERE / "n4pc-anti-resonance.png", dpi=160, facecolor=SURFACE)
print("n4pc figure written")
