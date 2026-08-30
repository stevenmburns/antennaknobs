"""The post figure: two convergence ladders, one per convention/engine.

Design per the dataviz method: two panels (small multiples, one Ω axis
each — R and X share units), categorical slots 1/2 (validated pair),
thin 2 px lines, 8 px markers with a surface ring, direct labels +
legend, recessive grid, converged-band annotation. Static PNG on the
light surface (forum attachment).
"""

import json
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt

HERE = Path(__file__).resolve().parent
data = json.loads((HERE / "results.json").read_text())

BLUE, ORANGE = "#2a78d6", "#eb6834"
SURFACE, INK, INK2, MUTED = "#fcfcfb", "#0b0b0b", "#52514e", "#898781"
GRID, BASE = "#e1e0d9", "#c3c2b7"

fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(12.6, 6.0), dpi=150, facecolor=SURFACE)
fig.subplots_adjust(left=0.065, right=0.975, top=0.76, bottom=0.22, wspace=0.24)


def style(ax):
    ax.set_facecolor(SURFACE)
    for s in ("top", "right"):
        ax.spines[s].set_visible(False)
    for s in ("left", "bottom"):
        ax.spines[s].set_color(BASE)
    ax.tick_params(colors=MUTED, labelsize=9)
    ax.grid(True, color=GRID, linewidth=0.7, axis="y")
    ax.set_axisbelow(True)


# --- Panel 1: momwire, connected screen, node-grading ladder -----------
# v2 rungs: every graded rung carries the graded radiator too (the axis
# the first ladder under-counted by 0.45 ohm); g2 IS the shipped default.
mw_old = complex(data["mw-ladder"]["default"]["z"])
mw2 = data["mw-ladder-v2-graded-default"]
rungs = ["g1", "g2-default", "g3"]
xt = [
    "old default\n(rise: 1 seg)",
    "graded\nh 25 mm",
    "graded\nh 6.25 mm\n(the new default)",
    "graded\nh 1.6 mm",
]
zs = [mw_old] + [complex(mw2[r]) for r in rungs]
x = range(len(zs))

for vals, color, label in (
    ([z.real for z in zs], BLUE, "R"),
    ([z.imag for z in zs], ORANGE, "X"),
):
    ax1.plot(x, vals, color=color, linewidth=2, zorder=3)
    ax1.plot(
        x,
        vals,
        "o",
        color=color,
        markersize=8,
        markeredgecolor=SURFACE,
        markeredgewidth=2,
        zorder=4,
    )
    ax1.annotate(
        label,
        (x[-1], vals[-1]),
        xytext=(8, 0),
        textcoords="offset points",
        color=INK2,
        fontsize=10,
        fontweight="bold",
        va="center",
    )

zstar = complex(mw2["g3"])
ax1.axhspan(zstar.imag - 0.10, zstar.imag + 0.10, color=ORANGE, alpha=0.12, zorder=1)
ax1.annotate(
    f"converged: {zstar.real:.2f} + j{zstar.imag:.2f} Ω  (±0.10)",
    (2.0, zstar.imag),
    xytext=(0, -22),
    textcoords="offset points",
    color=INK2,
    fontsize=9,
    ha="center",
)
ax1.annotate(
    "the old default mesh: X was\n29 Ω off converged — the\nladder is how you know",
    (0, zs[0].imag),
    xytext=(30, -52),
    textcoords="offset points",
    color=INK2,
    fontsize=9,
    va="top",
    arrowprops=dict(arrowstyle="-", color=BASE, linewidth=0.8, shrinkA=4, shrinkB=6),
)
ax1.set_xticks(list(x), xt)
ax1.set_ylim(40, 84)
ax1.set_ylabel("ohms", color=MUTED, fontsize=9)
ax1.set_title(
    "momwire — connected screen (its convention)\nnode-graded mesh ladder",
    color=INK,
    fontsize=11,
    loc="left",
)
style(ax1)

# --- Panel 2: NEC-5, detached variant, uniform density ladder ----------
n5 = data["nec5-ladder"]
ns = sorted(int(k[1:]) for k in n5)
zs5 = [complex(n5[f"N{n}"]["z"]) for n in ns]

for vals, color, label in (
    ([z.real for z in zs5], BLUE, "R"),
    ([z.imag for z in zs5], ORANGE, "X"),
):
    ax2.semilogx(ns, vals, color=color, linewidth=2, zorder=3)
    ax2.semilogx(
        ns,
        vals,
        "o",
        color=color,
        markersize=8,
        markeredgecolor=SURFACE,
        markeredgewidth=2,
        zorder=4,
    )
    ax2.annotate(
        label,
        (ns[-1], vals[-1]),
        xytext=(8, 0),
        textcoords="offset points",
        color=INK2,
        fontsize=10,
        fontweight="bold",
        va="center",
    )

zl = zs5[-1]
ax2.annotate(
    f"densest mesh: {zl.real:.2f} + j{zl.imag:.2f} Ω  (still settling, ~±0.3)",
    (ns[-1], zl.imag),
    xytext=(-6, 16),
    textcoords="offset points",
    color=INK2,
    fontsize=9,
    ha="right",
)
ax2.set_xticks(ns, [str(n) for n in ns])
ax2.minorticks_off()
ax2.set_ylim(15, 55)
ax2.set_xlabel(
    "segments per quarter-wave (our uniform mesh of its deck)", color=MUTED, fontsize=9
)
ax2.set_title(
    "NEC-5 — detached stake variant (its convention)\nuniform density ladder",
    color=INK,
    fontsize=11,
    loc="left",
)
style(ax2)

fig.suptitle(
    "Buried-radial vertical, 7.1 MHz, εr 13 / σ 0.005 soil — each engine "
    "converged on the junction convention it serves",
    color=INK,
    fontsize=13,
    x=0.065,
    ha="left",
)
fig.text(
    0.065,
    0.875,
    "The two conventions are different antennas (bonded screen vs detached "
    "stake) — the ~35 Ω between the panels is physics, not solver error.",
    color=INK2,
    fontsize=10,
)
fig.text(
    0.065,
    0.075,
    "Identity check (momwire): with the soil set to ε̃ = 1 the whole "
    "mixed-medium machinery must reproduce an independent\nfree-space "
    "solve of the same wires — agrees to 0.0098 Ω (~0.01 %).",
    color=INK2,
    fontsize=9,
    va="top",
    linespacing=1.4,
)

from matplotlib.lines import Line2D  # noqa: E402

fig.legend(
    handles=[
        Line2D(
            [],
            [],
            color=BLUE,
            linewidth=2,
            marker="o",
            markersize=7,
            markeredgecolor=SURFACE,
            label="R (resistance)",
        ),
        Line2D(
            [],
            [],
            color=ORANGE,
            linewidth=2,
            marker="o",
            markersize=7,
            markeredgecolor=SURFACE,
            label="X (reactance)",
        ),
    ],
    loc="upper right",
    bbox_to_anchor=(0.975, 0.93),
    frameon=False,
    fontsize=9,
    labelcolor=INK2,
    ncol=2,
)

out = HERE / "buried-ladders.png"
fig.savefig(out, facecolor=SURFACE)
print(out)
