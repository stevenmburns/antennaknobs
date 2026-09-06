"""#1202 figures.

Design per the dataviz method: single-hue sequential ramps for the magnitude
heatmaps (R and X are magnitudes, not divergences from a meaningful zero --
except X, where zero IS meaningful, so X gets its zero drawn as a contour
rather than encoded as a colour break); contours in text ink so they read as
annotation over the ramp; trajectories as four categorical hues in a fixed
order with a legend and direct labels; thin marks; recessive grid.
"""

import itertools
import json
import sys
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np

HERE = Path(__file__).resolve().parent

SURFACE, INK, INK2, MUTED = "#fcfcfb", "#0b0b0b", "#52514e", "#898781"
GRID, BASE = "#e1e0d9", "#c3c2b7"
# Fixed categorical order, used identically in every figure.
HUES = ["#2a78d6", "#eb6834", "#2e8b57", "#7d5ba6"]

PRETTY = {
    "moxon": "beams.moxon (free space) — 0.08 s / solve",
    "brv12": "verticals.buried_radial_vertical, 12 radials, soil 13/0.005 — 6.4 s / solve",
}


def style(ax):
    ax.set_facecolor(SURFACE)
    for s in ("top", "right"):
        ax.spines[s].set_visible(False)
    for s in ("left", "bottom"):
        ax.spines[s].set_color(BASE)
    ax.tick_params(colors=MUTED, labelsize=8)
    ax.set_axisbelow(True)


def fig_maps(kind):
    g = json.loads((HERE / f"grid_{kind}.json").read_text())
    res = json.loads((HERE / "results.json").read_text())[kind]
    A, B = np.array(g["A"]), np.array(g["B"])
    R, X = np.array(g["R"]), np.array(g["X"])
    z0 = g["z0"]
    kx, ky = g["knobs"]

    fig, axes = plt.subplots(1, 3, figsize=(15.4, 6.4), dpi=150, facecolor=SURFACE)
    fig.subplots_adjust(left=0.052, right=0.985, top=0.79, bottom=0.28, wspace=0.30)

    for ax, M, name in ((axes[0], R, "R"), (axes[1], X, "X")):
        style(ax)
        im = ax.pcolormesh(A, B, M, cmap="Blues", shading="gouraud", rasterized=True)
        cb = fig.colorbar(im, ax=ax, pad=0.02)
        cb.ax.tick_params(colors=MUTED, labelsize=7)
        cb.outline.set_edgecolor(BASE)
        cb.set_label(f"{name}  (Ω)", color=INK2, fontsize=8)
        cR = ax.contour(A, B, R, [z0], colors=[INK], linewidths=1.6)
        cX = ax.contour(
            A, B, X, [0.0], colors=[INK2], linewidths=1.6, linestyles="dashed"
        )
        ax.clabel(cR, fmt={z0: f"R = {z0:.0f}"}, fontsize=7.5, colors=INK)
        ax.clabel(cX, fmt={0.0: "X = 0"}, fontsize=7.5, colors=INK2)
        ax.set_title(f"{name} over the knob box", color=INK, fontsize=10.5, pad=7)
        ax.set_xlabel(kx, color=INK2, fontsize=9)
        ax.set_ylabel(ky, color=INK2, fontsize=9)

    # --- panel 3: the search itself
    ax = axes[2]
    style(ax)
    ax.grid(True, color=GRID, linewidth=0.6)
    cR = ax.contour(A, B, R, [z0], colors=[INK], linewidths=1.6)
    cX = ax.contour(A, B, X, [0.0], colors=[INK2], linewidths=1.6, linestyles="dashed")
    ax.clabel(cR, fmt={z0: f"R = {z0:.0f}"}, fontsize=7.5, colors=INK)
    ax.clabel(cX, fmt={0.0: "X = 0"}, fontsize=7.5, colors=INK2)

    # The answer: where the two contours cross. Found by walking the X = 0
    # contour and interpolating where R passes R0 along it.
    tgt = None
    walk = []  # (knob0 at X = 0, knob1, R there) along the X = 0 contour
    for jj in range(len(B)):
        xr = X[jj]
        sg = np.where(np.diff(np.sign(xr)))[0]
        if not len(sg):
            continue
        k = sg[0]
        lf = A[k] - xr[k] * (A[k + 1] - A[k]) / (xr[k + 1] - xr[k])
        walk.append((lf, B[jj], float(np.interp(lf, A, R[jj]))))
    for (l0, b0, r0), (l1, b1, r1) in itertools.pairwise(walk):
        if (r0 - z0) * (r1 - z0) <= 0 and r1 != r0:
            f = (z0 - r0) / (r1 - r0)
            tgt = (l0 + f * (l1 - l0), b0 + f * (b1 - b0))
            break
    if tgt is not None:
        for a in axes:
            a.plot(
                [tgt[0]],
                [tgt[1]],
                "*",
                color=INK,
                ms=15,
                zorder=8,
                mec=SURFACE,
                mew=0.8,
            )
        axes[2].annotate(
            "the answer",
            (tgt[0], tgt[1]),
            textcoords="offset points",
            xytext=(9, -13),
            fontsize=8.5,
            color=INK,
        )

    two = res["cases"]["two_knob"]
    # Fixed set across decks so the two figures read the same way: the two
    # Nelder-Mead starts, the bare root-finder, and the seeded hybrid.
    draw = [
        ("Nelder–Mead · tuned start", two["tuned"], "Nelder-Mead", 0),
        ("Nelder–Mead · far start", two["far"], "Nelder-Mead", 1),
        ("Newton, FD Jacobian · tuned", two["tuned"], "Newton (FD Jacobian)", 2),
        ("seed + Broyden · tuned", two["tuned"], "seed + Broyden", 3),
    ]
    for label, arms, mname, h in draw:
        r = next(a for a in arms if a["method"] == mname)
        p = np.array(r["path"])
        ax.plot(
            p[:, 0], p[:, 1], "-", color=HUES[h], lw=1.0, alpha=0.9, zorder=3 + h * 0.1
        )
        ax.plot(p[:, 0], p[:, 1], ".", color=HUES[h], ms=3.4, zorder=4)
        n = r["solves"] if r["reached"] else r["used"]
        tag = f"{n} solves" if r["reached"] else f"FAILED ({r['used']})"
        ax.plot([], [], "-", color=HUES[h], lw=2.0, label=f"{label} — {tag}")
        ax.plot(
            p[0, 0], p[0, 1], "o", color=SURFACE, mec=HUES[h], mew=1.4, ms=7, zorder=5
        )

    ax.set_xlim(A.min(), A.max())
    ax.set_ylim(B.min(), B.max())
    ax.set_title("where each method actually goes", color=INK, fontsize=10.5, pad=7)
    ax.set_xlabel(kx, color=INK2, fontsize=9)
    ax.set_ylabel(ky, color=INK2, fontsize=9)
    leg = fig.legend(
        *ax.get_legend_handles_labels(),
        loc="lower center",
        bbox_to_anchor=(0.5, 0.015),
        fontsize=9.0,
        frameon=False,
        ncol=2,
        labelcolor=INK2,
        handlelength=2.4,
        columnspacing=3.0,
    )
    leg.set_zorder(9)
    fig.text(
        0.5,
        0.155,
        "★ = where R = R₀ and X = 0 cross.  ○ = each run's start.  "
        "Solve counts are DISTINCT solves to |Z − Z₀| ≤ 1 Ω.",
        color=MUTED,
        fontsize=8.6,
        ha="center",
    )

    fig.suptitle(
        "Two knobs to Z₀ is a two-component ROOT, not a minimum — "
        "the answer is where the two contours cross",
        color=INK,
        fontsize=13.5,
        x=0.052,
        ha="left",
        y=0.962,
    )
    fig.text(0.052, 0.905, PRETTY[kind], color=MUTED, fontsize=9, ha="left")
    out = HERE / f"fig1_two_knob_{kind}.png"
    fig.savefig(out, facecolor=SURFACE)
    plt.close(fig)
    print("wrote", out.name)


def fig_curve(kind, start="tuned"):
    c = json.loads((HERE / f"curve_{kind}.json").read_text())
    res = json.loads((HERE / "results.json").read_text())[kind]
    cur = c["curves"][start]
    v = np.array(cur["v"])
    X = np.array(cur["X"])
    kx = c["knobs"][0]

    order = ["Nelder-Mead", "secant", "bracket + Brent", "Newton (FD deriv)"]
    arms = {a["method"]: a for a in res["cases"]["one_knob"][start]}

    fig, axes = plt.subplots(
        1, 4, figsize=(15.2, 4.5), dpi=150, facecolor=SURFACE, sharey=True
    )
    fig.subplots_adjust(left=0.05, right=0.985, top=0.74, bottom=0.15, wspace=0.12)

    # the root, by dense interpolation of the curve
    s = np.where(np.diff(np.sign(X)))[0]
    root = None
    if len(s):
        i = s[0]
        root = v[i] - X[i] * (v[i + 1] - v[i]) / (X[i + 1] - X[i])

    for k, (ax, name) in enumerate(zip(axes, order, strict=True)):
        style(ax)
        ax.grid(True, color=GRID, linewidth=0.6, axis="y")
        ax.axhline(0, color=BASE, lw=1.0)
        ax.plot(v, X, "-", color=MUTED, lw=1.3, zorder=2)
        if root is not None:
            ax.axvline(root, color=INK2, lw=1.0, ls="dashed", zorder=2)
        r = arms[name]
        pts = [p[0] for p in r["path"]]
        xs = [np.interp(p, v, X) for p in pts]
        ax.plot(pts, xs, ".", color=HUES[k], ms=8, zorder=5)
        for i, (px, py) in enumerate(zip(pts, xs, strict=True), start=1):
            if i <= 12:
                ax.annotate(
                    str(i),
                    (px, py),
                    textcoords="offset points",
                    xytext=(0, 7),
                    ha="center",
                    fontsize=7,
                    color=HUES[k],
                )
        n = r["solves"] if r["reached"] else r["used"]
        tag = f"{n} solves" if r["reached"] else f"FAILED after {r['used']}"
        ax.set_title(f"{name}\n{tag}", color=HUES[k], fontsize=10, pad=6)
        ax.set_xlabel(kx, color=INK2, fontsize=9)
        if k == 0:
            ax.set_ylabel("X  (Ω)", color=INK2, fontsize=9)

    if root is not None:
        lo_y = axes[0].get_ylim()[0]
        axes[0].annotate(
            f"root: {kx} = {root:.4f}",
            (root, lo_y),
            textcoords="offset points",
            xytext=(7, 12),
            fontsize=8,
            color=INK2,
        )
    fig.suptitle(
        "One knob to X = 0 is a SCALAR root — the secant reuses its previous "
        "iterate, so it costs one solve per step",
        color=INK,
        fontsize=13,
        x=0.05,
        ha="left",
        y=0.955,
    )
    fig.text(
        0.05,
        0.865,
        f"{PRETTY[kind]}   ·   {c['knobs'][1]} fixed at "
        f"{cur['knob1']:.4f} ({start} start)   ·   numbers are solve order",
        color=MUTED,
        fontsize=9,
        ha="left",
    )
    out = HERE / f"fig2_one_knob_{kind}.png"
    fig.savefig(out, facecolor=SURFACE)
    plt.close(fig)
    print("wrote", out.name)


if __name__ == "__main__":
    for kind in sys.argv[1:] or ["moxon", "brv12"]:
        fig_maps(kind)
        fig_curve(kind)
