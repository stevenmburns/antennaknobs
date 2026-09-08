"""Speedup S-curves as small multiples, one panel per segment-count bin,
drawn as a step function (flat run per deck, vertical riser between decks).

Same data and axes as plot_speedup_scurve.py, but each bin is its own
sorted curve on a shared log-y axis, so the size story reads without
overlaying three populations. Each panel: rank 0-100 % of ITS bin on x,
speedup on y, a dashed 1x line, and the bin's n, median and share above 1x
in the panel title.

    python plot_speedup_panels.py corpus-speedup.csv out.png [--set corpus]
"""

import argparse
import csv
import math
import statistics
import sys

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
from matplotlib.ticker import FuncFormatter, LogLocator, NullFormatter  # noqa: E402

BINS = [
    (0, 300, "under 300 segments", "#5598e7"),
    (300, 1500, "300 to 1,500 segments", "#2a78d6"),
    (1500, 10**9, "1,500 segments and up", "#104281"),
]
INK, INK2, GRID, SURF = "#1a1a19", "#6b6b68", "#e6e5e1", "#fcfcfb"


def load(path, only_set):
    rows = []
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
                continue
            if s > 0 and a > 0 and not (math.isnan(s) or math.isnan(a)):
                rows.append((n, s / a))
    return rows


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("csv")
    ap.add_argument("out")
    ap.add_argument("--set", default="corpus")
    ap.add_argument(
        "--title",
        default="NEC-5 a43 vs stock x13: speedup by deck size (4 threads, plain environment)",
    )
    a = ap.parse_args(argv)
    rows = load(a.csv, a.set)
    if not rows:
        print("no rows", file=sys.stderr)
        return 2
    ymin = min(r[1] for r in rows) / 1.3
    ymax = max(r[1] for r in rows) * 1.3
    fig, axes = plt.subplots(
        1, 3, figsize=(12.5, 4.6), dpi=150, facecolor=SURF, sharey=True
    )
    for ax, (lo, hi, label, color) in zip(axes, BINS, strict=True):
        ax.set_facecolor(SURF)
        sp = sorted(r[1] for r in rows if lo <= r[0] < hi)
        n = len(sp)
        if n == 0:
            ax.set_title(label + " (none)", color=INK, fontsize=10, loc="left")
            continue
        # A cumulative-histogram-style step: one flat run per deck (its share of
        # the bin's width) and a vertical riser to the next deck's speedup.
        # Opaque lines, no markers, so density never reads as intensity.
        edges = [100.0 * i / n for i in range(n + 1)]
        ax.stairs(sp, edges, baseline=None, color=color, lw=1.6, zorder=3)
        ax.axhline(1.0, color=INK2, lw=1.0, ls="--", zorder=2)
        above = sum(1 for v in sp if v > 1.0)
        med = statistics.median(sp)
        ax.set_title(
            f"{label}\nn = {n}, median {med:.2f}x, {100.0 * above / n:.0f} % faster on a43",
            color=INK,
            fontsize=9.5,
            loc="left",
        )
        ax.set_yscale("log")
        ax.set_ylim(ymin, ymax)
        ax.yaxis.set_major_locator(
            LogLocator(
                base=10, subs=(0.1, 0.2, 0.3, 0.5, 1.0, 2.0, 3.0, 5.0), numticks=30
            )
        )
        ax.yaxis.set_major_formatter(FuncFormatter(lambda v, _p: f"{v:g}x"))
        ax.yaxis.set_minor_formatter(NullFormatter())
        ax.set_xlim(0, 100)
        ax.grid(True, which="major", color=GRID, lw=0.8, zorder=0)
        ax.grid(True, which="minor", color=GRID, lw=0.4, zorder=0)
        for spn in ax.spines.values():
            spn.set_color(GRID)
        ax.tick_params(colors=INK2)
        ax.set_xlabel(
            "decks in this bin, sorted by speedup (percent)", color=INK, fontsize=9
        )
    axes[0].set_ylabel("speedup = stock wall / a43 wall (log)", color=INK)
    fig.suptitle(
        a.title + f"  ({len(rows)} decks)", color=INK, fontsize=11, x=0.01, ha="left"
    )
    fig.tight_layout(rect=(0, 0, 1, 0.97))
    fig.savefig(a.out, facecolor=SURF)
    print(f"{len(rows)} decks across {len(BINS)} panels -> {a.out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
