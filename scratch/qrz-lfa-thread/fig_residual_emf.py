"""The mechanism figure for the QRZ follow-up: two panels, house style.

Top: the measured spurious loop EMF per ampere of loop current (k=1 mesh) —
the NEC-2-class sinusoidal scheme rides an f^-1 rail at ~2e5 V/A @ 500 Hz;
the Harrington pulse row reads machine zero (its loop sum telescopes).
Bottom: what that does to the solve — loop/source current ratio vs
frequency (k=4 mesh): the clean point-matched lanes sit flat at 0.46 down
to 5 Hz while the NEC-2 scheme explodes.

Data: results-residual-emf.json (per_amp, sin_fsweep_k4) and
results-pulse.json (fsweep). Palette validated (dataviz six checks) against
the house surface: sin #cf3f4f, harrington #7a5bd6, pulse #0f9bb8.
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
C_SIN, C_HAR, C_PUL = "#cf3f4f", "#7a5bd6", "#0f9bb8"

RE = json.load(open(HERE / "results-residual-emf.json"))
RP = json.load(open(HERE / "results-pulse.json"))


def style_ax(ax):
    ax.set_facecolor(SURFACE)
    ax.grid(True, color=GRID, lw=0.8, which="major")
    for s in ("top", "right"):
        ax.spines[s].set_visible(False)
    for s in ("left", "bottom"):
        ax.spines[s].set_color(INK2)
    ax.tick_params(colors=INK2, labelsize=9)


fig, (axA, axB) = plt.subplots(
    2, 1, figsize=(8.6, 8.4), facecolor=SURFACE, height_ratios=[1, 1]
)

# ---- panel A: spurious EMF per ampere -------------------------------------
pa = RE["per_amp"]
f = np.array(pa["ladder_mhz"]) * 1e6
e_sin = np.abs([complex(a, b) for a, b in pa["sin_V_per_A"]])
e_har = np.abs([complex(a, b) for a, b in pa["harrington_V_per_A"]])

axA.loglog(
    f,
    e_sin,
    color=C_SIN,
    lw=2,
    marker="o",
    ms=4.5,
    mfc=C_SIN,
    mec=SURFACE,
    mew=0.6,
    label="NEC-2-class sinusoidal scheme",
)
axA.loglog(
    f,
    e_har,
    color=C_HAR,
    lw=2,
    marker="o",
    ms=4.5,
    mfc=C_HAR,
    mec=SURFACE,
    mew=0.6,
    label="Harrington pulse row (point-matched)",
)

# the f^-1 guide, offset below the sin curve so it reads as a slope guide
guide = 0.08 * e_sin[2] * (500.0 / f)
axA.loglog(f, guide, color=INK, lw=1.1, ls=(0, (5, 4)))
axA.annotate(
    "f$^{-1}$: the electrostatic-error law\n(measured slope $-$1.007)",
    xy=(f[3], guide[3]),
    xytext=(6, -30),
    textcoords="offset points",
    fontsize=8.7,
    color=INK,
)

axA.annotate(
    "~2×10$^5$ V per ampere at 500 Hz",
    xy=(500, e_sin[2]),
    xytext=(-4, 11),
    textcoords="offset points",
    fontsize=8.7,
    color=C_SIN,
)
axA.annotate(
    "machine zero: the loop sum telescopes,\nerror cancels term by term",
    xy=(f[1], e_har[1]),
    xytext=(6, 12),
    textcoords="offset points",
    fontsize=8.7,
    color=C_HAR,
)

style_ax(axA)
axA.set_ylim(1e-9, 3e7)
axA.set_ylabel(
    "loop circulation of grad φ  (V per A of loop current)", color=INK, fontsize=9.5
)
axA.set_title(
    "the same functional, two discretizations: Σ over the loop's equations,\n"
    "applied to one fixed clean current (k = 1 mesh) — must be zero in the continuum",
    color=INK2,
    fontsize=9,
    loc="left",
    pad=8,
)
axA.legend(loc="center left", frameon=False, fontsize=9, labelcolor=INK)

# ---- panel B: loop/source ratio vs frequency ------------------------------
sinf = RE["sin_fsweep_k4"]
fB = np.array([float(m) for m in sinf]) * 1e6
order = np.argsort(fB)
fB = fB[order]
r_sin = np.array([sinf[m] for m in sinf])[order]

pulf = RP["pulse"]["fsweep"]
harf = RP["harrington"]["fsweep"]
fP = np.array([float(m) for m in pulf]) * 1e6
oP = np.argsort(fP)
fP = fP[oP]
r_pul = np.array([pulf[m] for m in pulf])[oP]
r_har = np.array([harf[m] for m in harf])[oP]

axB.loglog(
    fB,
    r_sin,
    color=C_SIN,
    lw=2,
    marker="o",
    ms=4.5,
    mfc=C_SIN,
    mec=SURFACE,
    mew=0.6,
    label="NEC-2-class sinusoidal scheme",
)
axB.loglog(
    fP,
    r_har,
    color=C_HAR,
    lw=2,
    marker="o",
    ms=4.5,
    mfc=C_HAR,
    mec=SURFACE,
    mew=0.6,
    label="Harrington pulse row",
)
axB.loglog(
    fP,
    r_pul,
    color=C_PUL,
    lw=2,
    marker="o",
    ms=4.5,
    mfc=C_PUL,
    mec=SURFACE,
    mew=0.6,
    label="plain pulse row",
)

axB.annotate(
    "39,291 at 5 Hz",
    xy=(fB[0], r_sin[0]),
    xytext=(8, -2),
    textcoords="offset points",
    fontsize=8.7,
    color=C_SIN,
)
axB.annotate(
    "the clean lanes: flat at 0.46 to 5 Hz\n(overprinting curves)",
    xy=(fP[1], r_pul[1]),
    xytext=(0, -26),
    textcoords="offset points",
    fontsize=8.7,
    color=INK2,
)

style_ax(axB)
axB.set_ylim(0.02, 3e5)
axB.set_xlabel("frequency (Hz)", color=INK, fontsize=10)
axB.set_ylabel("max loop current / source current", color=INK, fontsize=9.5)
axB.set_title(
    "what the residual does to the solve: loop/source current ratio (k = 4 mesh)",
    color=INK2,
    fontsize=9,
    loc="left",
    pad=8,
)
axB.legend(loc="upper right", frameon=False, fontsize=9, labelcolor=INK)

fig.suptitle(
    "W7EL's coupled-loop model — the loop pathology's mechanism, measured\n"
    "a spurious EMF in the scalar-potential loop integral,\n"
    "cancelled by construction in the clean schemes",
    color=INK,
    fontsize=11,
)
fig.tight_layout(rect=(0, 0, 1, 0.905))
fig.savefig(HERE / "residual-emf-mechanism.png", dpi=160, facecolor=SURFACE)
print("mechanism figure written")
