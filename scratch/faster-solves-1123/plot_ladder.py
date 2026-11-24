"""Dense fill and factor against segment count from skylake/ladder.jsonl, and
the fill/factor crossover from power-law fits to the top three rungs.

usage: plot_ladder.py LADDER_JSONL OUT_PNG
"""

import json
import sys

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np

BLUE, ORANGE, AQUA, YELLOW = "#2a78d6", "#eb6834", "#1baf7a", "#eda100"
INK, MUTED, SURFACE = "#0b0b0b", "#52514e", "#fcfcfb"


def load(path):
    rows = [json.loads(line) for line in open(path)]
    out = {}
    for r in rows:
        if r["design"] != "beams.yagi":
            continue
        key = (r["engine"], r["ground"])
        d = out.setdefault(key, {})
        e = d.setdefault(r["segments"], {})
        if r["mixed_asked"]:
            m = r["mixed"]
            if m.get("refined"):
                oc = "refined"
            elif m.get("fallback"):
                oc = "fallback"
            elif m.get("declined"):
                oc = "declined"
            else:
                oc = "none"
            e["mix"], e["outcome"] = r["factor_s"], oc
        else:
            e.update(
                fill=r["fill_s"], fct=r["factor_s"], c=r["cgetrf_s"], z=r["zgetrf_s"]
            )
    return out


def fit(n, t):
    """log t = a + p log n over the top three rungs."""
    p, a = np.polyfit(np.log(n[-3:]), np.log(t[-3:]), 1)
    return a, p


def crossover(n, fill, fct):
    a1, p1 = fit(n, fill)
    a2, p2 = fit(n, fct)
    return float(np.exp((a1 - a2) / (p2 - p1))), p1, p2


def main(src, png):
    data = load(src)
    engines = ["bs2", "sinusoidal", "razor2p"]
    grounds = [("free", "free space"), ("somm", "Sommerfeld ground")]
    fig, axes = plt.subplots(
        2, 3, figsize=(13, 8), sharex=True, sharey=True, facecolor=SURFACE
    )
    report = []
    for i, (g, gname) in enumerate(grounds):
        for j, eng in enumerate(engines):
            ax = axes[i][j]
            ax.set_facecolor(SURFACE)
            d = data[(eng, g)]
            n = np.array(sorted(d))
            col = lambda k: np.array([d[s][k] for s in n])  # noqa: E731
            fill, fct, cg = col("fill"), col("fct"), col("c")
            x, p1, p2 = crossover(n, fill, fct)
            report.append((eng, g, x, p1, p2))
            ax.plot(n, fill, color=BLUE, lw=2, marker="o", ms=4, label="dense fill")
            ax.plot(
                n,
                fct,
                color=ORANGE,
                lw=2,
                marker="o",
                ms=4,
                label="factor, double (momwire)",
            )
            ax.plot(
                n,
                cg,
                color=YELLOW,
                lw=2,
                ls="--",
                label="bare cgetrf (single, no refinement)",
            )
            for s in n:
                oc = d[s]["outcome"]
                if oc == "refined":
                    ax.plot(s, d[s]["mix"], "o", color=AQUA, ms=8, mec=SURFACE, mew=1.5)
                elif oc == "fallback":
                    ax.plot(s, d[s]["mix"], "o", color=AQUA, ms=8, mfc="none", mew=2)
            # extend the fits to the crossover when it lies past the ladder
            if x > n[-1]:
                xs = np.geomspace(n[-1], x * 1.15, 20)
                for t, c in ((fill, BLUE), (fct, ORANGE)):
                    a, p = fit(n, t)
                    ax.plot(xs, np.exp(a) * xs**p, color=c, lw=1, ls=":")
            ax.axvline(x, color=MUTED, lw=1, ls="-", alpha=0.6)
            ax.annotate(
                f"crossover ≈ {x / 1000:.1f}k",
                (x * 1.06, 150),
                rotation=90,
                ha="left",
                va="top",
                fontsize=9,
                color=INK,
            )
            ax.set_xscale("log")
            ax.set_yscale("log")
            ax.set_title(f"{eng}, {gname}", fontsize=11, color=INK)
            ax.grid(True, which="major", color="#e4e3df", lw=0.6)
            for sp in ("top", "right"):
                ax.spines[sp].set_visible(False)
            if i == 1:
                ax.set_xlabel("segments", color=MUTED)
            if j == 0:
                ax.set_ylabel("seconds", color=MUTED)
    ax0 = axes[0][0]
    ax0.plot([], [], "o", color=AQUA, ms=8, label="mixed factor, refined")
    ax0.plot(
        [],
        [],
        "o",
        color=AQUA,
        ms=8,
        mfc="none",
        mew=2,
        label="mixed factor, fell back",
    )
    fig.legend(
        *ax0.get_legend_handles_labels(),
        loc="lower center",
        ncol=5,
        frameon=False,
        fontsize=9,
    )
    fig.suptitle(
        "10-element Yagi: fill and factor time against segment count\n"
        "Skylake i7-6700K, 8 threads; momwire mixed-lu-all (PR #2129); dotted = power-law extrapolation",
        fontsize=11,
        color=INK,
    )
    fig.tight_layout(rect=(0, 0.05, 1, 0.95))
    fig.savefig(png, dpi=130, facecolor=SURFACE)
    for eng, g, x, p1, p2 in report:
        print(
            f"{eng:11s} {g:5s} crossover {x:8.0f}  fill ~ n^{p1:.2f}  factor ~ n^{p2:.2f}"
        )


if __name__ == "__main__":
    main(sys.argv[1], sys.argv[2])
