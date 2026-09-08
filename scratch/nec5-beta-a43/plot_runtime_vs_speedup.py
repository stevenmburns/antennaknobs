"""Where the long jobs land: stock wall time against speedup, both log.

A hexbin density (one blue hue, light -> dark = count) carries the 4,000
sub-second decks without turning overlap into intensity; every deck whose
stock solve took >= --long seconds is drawn as an opaque point on top, so a
long-running job that regresses is individually visible in the lower right.
Dashed 1x line; the count of long jobs above and below it in the title.

    python plot_runtime_vs_speedup.py corpus-speedup.csv out.png [--set corpus] [--long 2]
"""

import argparse
import csv
import math
import sys

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
from matplotlib.colors import LinearSegmentedColormap, LogNorm  # noqa: E402
from matplotlib.ticker import FuncFormatter, LogLocator, NullFormatter  # noqa: E402

RAMP = ["#cde2fb", "#9ec5f4", "#6da7ec", "#3987e5", "#256abf", "#184f95", "#0d366b"]
POINT, INK, INK2, GRID, SURF = "#0d366b", "#1a1a19", "#6b6b68", "#e6e5e1", "#fcfcfb"


def load(path, only_set):
    out = []
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
                out.append((r["deck"], n, s, s / a))
    return out


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("csv")
    ap.add_argument("out")
    ap.add_argument("--set", default="corpus")
    ap.add_argument(
        "--long",
        type=float,
        default=2.0,
        help="stock seconds above which a deck is drawn as its own point",
    )
    ap.add_argument(
        "--title", default="NEC-5 a43 vs stock x13: where the long jobs land"
    )
    a = ap.parse_args(argv)
    rows = load(a.csv, a.set)
    if not rows:
        print("no rows", file=sys.stderr)
        return 2
    xs = [r[2] for r in rows]
    ys = [r[3] for r in rows]
    longs = [r for r in rows if r[2] >= a.long]
    n_up = sum(1 for r in longs if r[3] > 1.0)
    n_down = len(longs) - n_up

    fig, ax = plt.subplots(figsize=(9.5, 5.6), dpi=150, facecolor=SURF)
    ax.set_facecolor(SURF)
    cmap = LinearSegmentedColormap.from_list("blue-seq", RAMP)
    hb = ax.hexbin(
        xs,
        ys,
        gridsize=(46, 30),
        xscale="log",
        yscale="log",
        mincnt=1,
        cmap=cmap,
        norm=LogNorm(),
        linewidths=0.2,
        edgecolors=SURF,
        zorder=2,
    )
    cb = fig.colorbar(hb, ax=ax, pad=0.01, fraction=0.04)
    cb.set_label("decks per cell", color=INK2)
    cb.ax.tick_params(colors=INK2)
    cb.outline.set_edgecolor(GRID)
    ax.scatter(
        [r[2] for r in longs],
        [r[3] for r in longs],
        s=18,
        color=POINT,
        edgecolors="none",
        zorder=4,
        label=f"stock solve >= {a.long:g} s ({len(longs)} decks: {n_up} faster, {n_down} slower on a43)",
    )
    ax.axhline(1.0, color=INK2, lw=1.0, ls="--", zorder=3)
    ax.set_xscale("log")
    ax.set_yscale("log")
    ax.xaxis.set_major_formatter(FuncFormatter(lambda v, _p: f"{v:g} s"))
    ax.yaxis.set_major_locator(
        LogLocator(base=10, subs=(0.1, 0.2, 0.3, 0.5, 1.0, 2.0, 3.0, 5.0), numticks=30)
    )
    ax.yaxis.set_major_formatter(FuncFormatter(lambda v, _p: f"{v:g}x"))
    ax.yaxis.set_minor_formatter(NullFormatter())
    ax.set_xlabel("stock x13 wall time per deck (log)", color=INK)
    ax.set_ylabel("speedup = stock wall / a43 wall (log)", color=INK)
    ax.set_title(a.title + f"  ({len(rows)} decks)", color=INK, fontsize=11, loc="left")
    ax.grid(True, which="major", color=GRID, lw=0.8, zorder=0)
    for sp in ax.spines.values():
        sp.set_color(GRID)
    ax.tick_params(colors=INK2)
    leg = ax.legend(loc="lower right", frameon=False, fontsize=8.5)
    for t in leg.get_texts():
        t.set_color(INK)
    fig.tight_layout()
    fig.savefig(a.out, facecolor=SURF)
    print(
        f"{len(rows)} decks; long (>= {a.long:g} s): {len(longs)} — {n_up} faster, {n_down} slower on a43 -> {a.out}"
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
