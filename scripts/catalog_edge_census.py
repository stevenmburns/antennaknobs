"""Edges per deck and segments per edge across the catalog — momwire#1024.

WHY THIS EXISTS. momwire#1024 measured `_seg_seg_reg_geometry` at 20.3% of a
solve on one long finely-meshed wire and 0.4% on a ten-wire catalog deck. Both
functions serve the SAME-EDGE path, and a single wire at N=1201 is *one edge
with 1201 segments*, so the same-edge block is essentially the whole matrix.
The open question was whether any real catalog deck looks like that.

THE METRIC. For a deck whose edges hold n_1 .. n_E segments, the same-edge
blocks cost sum(n_e^2) while the whole fill costs (sum n_e)^2. So

    same_edge_fraction = sum(n_e^2) / (sum n_e)^2

is the share of the fill that the same-edge path serves: 1.0 for a single edge,
1/E for E equal edges. It is the quantity that predicts whether a same-edge
optimisation is visible, which "number of edges" alone does not — one long edge
among nine short ones still dominates.

Writes JSONL (one row per design x rung) and prints the summary. The rows are
the record; nothing here is scraped from a log.

    python scripts/catalog_edge_census.py --out docs/status/data/catalog-edge-census.jsonl
"""

from __future__ import annotations

import argparse
import importlib
import json
import pkgutil
import warnings
from pathlib import Path

import antennaknobs.designs as designs_pkg
from antennaknobs.engines.momwire import MomwireEngine


def _rows(rung: str, scale: int):
    for m in pkgutil.walk_packages(designs_pkg.__path__, designs_pkg.__name__ + "."):
        if m.ispkg:
            continue
        name = m.name.split("antennaknobs.designs.")[-1]
        try:
            builder = importlib.import_module(m.name).Builder
        except Exception as exc:  # noqa: BLE001 — an unimportable design is not this census's business
            yield {
                "design": name,
                "rung": rung,
                "error": f"{type(exc).__name__}: {exc}",
            }
            continue
        try:
            with warnings.catch_warnings():
                warnings.simplefilter("ignore")
                b = builder()
                eng = MomwireEngine(b)
                sim = eng._make_solver(wavelength=eng._wavelength_for(b.freq))
                per_wire = sim.n_per_edge_per_wire
        except Exception as exc:  # noqa: BLE001 — a deck that will not build is recorded, not fatal
            yield {
                "design": name,
                "rung": rung,
                "error": f"{type(exc).__name__}: {exc}",
            }
            continue
        # "Refined" here is a uniform multiplier on the counts, which is what
        # the rung means in this codebase (momwire's banked cells are the
        # nominal mesh x2 and x4) -- there is no engine-level density knob;
        # the counts come from each design's own translation.
        edges = [int(n) * scale for wire in per_wire for n in wire]
        total = sum(edges)
        yield {
            "design": name,
            "rung": rung,
            "scale": scale,
            "n_wires": len(per_wire),
            "n_edges": len(edges),
            "total_segments": total,
            "max_edge_segments": max(edges) if edges else 0,
            "edges": edges,
            # the quantity that decides whether a same-edge optimisation shows
            "same_edge_fraction": (sum(n * n for n in edges) / (total * total))
            if total
            else 0.0,
        }


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", type=Path, required=True)
    # rung -> uniform multiplier. The same-edge FRACTION is invariant under
    # this (sum (k n)^2 / (sum k n)^2 = sum n^2 / (sum n)^2), so a refined rung
    # cannot change the ranking -- it is measured to show the ABSOLUTE segment
    # counts a refined deck reaches, which is what decides whether any deck
    # gets near the N where a same-edge cost is visible.
    ap.add_argument("--rungs", default="default:1,refined:4")
    args = ap.parse_args()

    rows = []
    for spec in args.rungs.split(","):
        rung, _, mult = spec.strip().partition(":")
        rows.extend(_rows(rung, int(mult or 1)))
    args.out.parent.mkdir(parents=True, exist_ok=True)
    with args.out.open("w") as fh:
        for r in rows:
            fh.write(json.dumps(r) + "\n")

    ok = [r for r in rows if "error" not in r]
    bad = [r for r in rows if "error" in r]
    print(f"{len(ok)} decks measured, {len(bad)} could not be built\n")
    for rung in sorted({r["rung"] for r in ok}):
        sub = sorted(
            (r for r in ok if r["rung"] == rung),
            key=lambda r: -r["same_edge_fraction"],
        )
        print(f"--- rung {rung}: {len(sub)} decks ---")
        print(
            f"{'design':40s} {'wires':>5} {'edges':>5} {'segs':>6} {'max/edge':>8} {'same-edge':>9}"
        )
        for r in sub[:10]:
            print(
                f"{r['design']:40s} {r['n_wires']:5d} {r['n_edges']:5d} "
                f"{r['total_segments']:6d} {r['max_edge_segments']:8d} "
                f"{r['same_edge_fraction']:9.3f}"
            )
        one_edge = [r for r in sub if r["n_edges"] == 1]
        near = [r for r in sub if r["same_edge_fraction"] >= 0.5]
        print(
            f"\n  single-edge decks: {len(one_edge)}"
            f"  |  same-edge fraction >= 0.5: {len(near)}"
            f"  |  median fraction: "
            f"{sorted(r['same_edge_fraction'] for r in sub)[len(sub) // 2]:.3f}\n"
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
