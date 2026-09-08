"""Speedup S-curve for the NEC-5 accelerated-build beta.

x: test cases sorted by speedup (rank as a percentage of the set);
y: speedup = stock wall / a43 wall, log scale; a 1x reference line;
points coloured by segment-count bin (ordinal, one hue light -> dark).

Input CSV columns: deck,segments,stock_wall_s,a43_wall_s,speedup,set
(from the Windows box's corpus-speedup.csv). Rows with a missing wall are
dropped and counted in the caption.

    python plot_speedup_scurve.py corpus-speedup.csv out.png [--set corpus]
"""

import argparse
import csv
import math
import sys

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
from matplotlib.ticker import FuncFormatter, LogLocator, NullFormatter  # noqa: E402

BINS = [
    (0, 300, "< 300 segments", "#86b6ef"),
    (300, 1500, "300 - 1,500", "#2a78d6"),
    (1500, 10**9, ">= 1,500", "#104281"),
]
INK, INK2, GRID, SURF = "#1a1a19", "#6b6b68", "#e6e5e1", "#fcfcfb"


def load(path, only_set):
    rows, dropped = [], 0
    with open(path, newline="") as fh:
        for r in csv.DictReader(fh):
            if only_set and r.get("set", "corpus") != only_set:
                continue
            try:
                s, a, n = (
                    float(r["stock_wall_s"]),
                    float(r["a43_wall_s"]),
                    int(float(r["segments"])),
                )
            except (KeyError, ValueError):
                dropped += 1
                continue
            if not (s > 0 and a > 0) or math.isnan(s) or math.isnan(a):
                dropped += 1
                continue
            rows.append((r["deck"], n, s, a, s / a))
    return rows, dropped


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("csv")
    ap.add_argument("out")
    ap.add_argument(
        "--set", default="corpus", help="set column to plot; '' for all rows"
    )
    ap.add_argument(
        "--title", default="NEC-5 a43 vs stock x13: speedup across the corpus"
    )
    a = ap.parse_args(argv)
    rows, dropped = load(a.csv, a.set)
    if not rows:
        print("no rows", file=sys.stderr)
        return 2
    rows.sort(key=lambda r: r[4])
    n = len(rows)
    xs = [100.0 * (i + 0.5) / n for i in range(n)]
    fig, ax = plt.subplots(figsize=(9, 5.2), dpi=150, facecolor=SURF)
    ax.set_facecolor(SURF)
    for lo, hi, label, color in BINS:
        pts = [(x, r[4]) for x, r in zip(xs, rows, strict=True) if lo <= r[1] < hi]
        if not pts:
            continue
        med = sorted(p[1] for p in pts)[len(pts) // 2]
        ax.scatter(
            [p[0] for p in pts],
            [p[1] for p in pts],
            s=9,
            color=color,
            edgecolors=SURF,
            linewidths=0.4,
            label=f"{label} (n={len(pts)}, median {med:.2f}x)",
            zorder=3,
        )
    ax.axhline(1.0, color=INK2, lw=1.0, ls="--", zorder=2)
    above = sum(1 for r in rows if r[4] > 1.0)
    ax.text(
        0.99,
        1.0,
        f"1x: {100.0 * above / n:.1f} % of decks faster on a43",
        color=INK2,
        fontsize=8.5,
        va="bottom",
        ha="right",
        transform=ax.get_yaxis_transform(),
    )
    ax.set_yscale("log")
    ax.yaxis.set_major_locator(
        LogLocator(base=10, subs=(0.2, 0.3, 0.5, 1.0, 2.0, 3.0, 5.0), numticks=20)
    )
    ax.yaxis.set_major_formatter(FuncFormatter(lambda v, _p: f"{v:g}x"))
    ax.yaxis.set_minor_formatter(NullFormatter())
    ax.set_xlim(0, 100)
    ax.set_xlabel("test cases, sorted by speedup (percent of set)", color=INK)
    ax.set_ylabel("speedup = stock wall / a43 wall (log)", color=INK)
    ax.set_title(
        a.title + f"  ({n} decks{', ' + str(dropped) + ' dropped' if dropped else ''})",
        color=INK,
        fontsize=11,
        loc="left",
    )
    ax.grid(True, which="major", color=GRID, lw=0.8, zorder=0)
    ax.grid(True, which="minor", color=GRID, lw=0.4, zorder=0)
    for sp in ax.spines.values():
        sp.set_color(GRID)
    ax.tick_params(colors=INK2)
    leg = ax.legend(
        loc="upper left",
        frameon=False,
        fontsize=8.5,
        title="segment count",
        title_fontsize=8.5,
    )
    for t in leg.get_texts():
        t.set_color(INK)
    leg.get_title().set_color(INK2)
    fig.tight_layout()
    fig.savefig(a.out, facecolor=SURF)
    med_all = rows[n // 2][4]
    print(
        f"{n} decks, {dropped} dropped; median speedup {med_all:.3f}x; {above} ({100 * above / n:.1f} %) above 1x; max {rows[-1][4]:.2f}x ({rows[-1][0]}, {rows[-1][1]} segs); min {rows[0][4]:.2f}x"
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
