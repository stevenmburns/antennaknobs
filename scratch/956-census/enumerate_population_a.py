"""AK/momwire#956: enumerate the catalog's buried-conductor cases, and CLASSIFY them.

    python scratch/956-census/enumerate_population_a.py

Membership is `_has_buried_wire`'s own test -- any conductor vertex at z < 0 --
applied to every (design, VARIANT) pair the catalog declares, not to designs at
their default params. The variants are the point: `buried_radial_vertical` ships
four junction conventions and they are DIFFERENT CONDUCTORS (its own docstring
says so), so a design-level listing would report one row where the fix predicts
three different answers.

THE CLASSIFICATION IS NOT BINARY, and that matters for what momwire#1043
predicts. The brief's split was crossing versus wholly buried; the catalog has
four shapes, and the middle two are neither:

  crossing       a vertex at z == 0 with conductor BOTH above and below it --
                 the crossing junction the serve solves.
  contact+split  a vertex at z == 0 with conductor only above it, plus separate
                 buried conductor elsewhere (the stake convention).
  split          conductor above and below, nothing touching z == 0.
  wholly buried  no conductor above z == 0 at all -- no cross-medium block.

A `split` deck has no crossing node but DOES have an above x below block, which
is where the W terms live (momwire#956's probe20 and probe6 measure the fill
against the transmitted grid on NON-crossing decks). So "no crossing node" did
not predict "does not move", and lumping split in with wholly buried would have
risked reading a moving deck as a falsification -- which is why they are separate
classes here.

MEASURED, once the census ran (`BURIED-CENSUS.md`): split does NOT move either.
`elevated_buried_counterpoise` is bit-identical across all three commits, so on
that geometry the W-term change reaches only decks with a crossing junction. The
four classes are kept because that is a RESULT; collapsing them now would hide
the one deck that could have falsified it.
"""

from __future__ import annotations

import importlib
import sys
from itertools import pairwise
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "src"))

import antennaknobs.web.examples  # noqa: E402, F401 -- binds register_all before adapter imports it
from antennaknobs.cli import list_builtin_designs  # noqa: E402
from antennaknobs.geometry import flat_wires_to_polylines  # noqa: E402
from antennaknobs.web.adapter import (  # noqa: E402
    _build_builder,
    _discover_variants,
)

TOL = 0.0  # z == 0 exactly: the plane is a spelling, not a measurement (see _has_buried_wire)


def classify(polys) -> tuple[str, float, float, int]:
    zs = [z for p in polys for (_x, _y, z) in p]
    zmin, zmax = min(zs), max(zs)
    if zmin >= 0.0:
        return "not-buried", zmin, zmax, 0
    # incidence at the plane, from the SEGMENTS (a vertex alone cannot say
    # whether conductor continues up, down or both)
    above = {}
    below = {}
    for p in polys:
        for (x0, y0, z0), (x1, y1, z1) in pairwise(p):
            for (xa, ya, za), (_xb, _yb, zb) in (
                ((x0, y0, z0), (x1, y1, z1)),
                ((x1, y1, z1), (x0, y0, z0)),
            ):
                if za == TOL:
                    key = (round(xa, 12), round(ya, 12))
                    if zb > 0:
                        above[key] = above.get(key, 0) + 1
                    elif zb < 0:
                        below[key] = below.get(key, 0) + 1
    nodes_at_plane = len(set(above) | set(below))
    crossing_nodes = len(set(above) & set(below))
    if crossing_nodes:
        return "crossing", zmin, zmax, crossing_nodes
    if nodes_at_plane and zmax > 0:
        return "contact+split", zmin, zmax, nodes_at_plane
    if zmax > 0:
        return "split", zmin, zmax, 0
    return "wholly-buried", zmin, zmax, 0


def main() -> int:
    rows, failed = [], []
    for dotted in list_builtin_designs():
        cls = importlib.import_module(f"antennaknobs.designs.{dotted}").Builder
        for variant in _discover_variants(cls):
            # The app's own constructor path: variant seed overlaid with the
            # request, which is how the descriptor's has_buried_wire hint is
            # computed. A Builder does not take its params as kwargs.
            try:
                b = _build_builder(cls, {"variant": variant})
                polys = flat_wires_to_polylines(b.build_wires())["polylines"]
            except Exception as e:  # noqa: BLE001 -- a builder that will not build is reported, not skipped
                failed.append((dotted, variant, f"{type(e).__name__}: {e}"[:80]))
                continue
            kind, zmin, zmax, nodes = classify(polys)
            if kind == "not-buried":
                continue
            rows.append(
                (
                    dotted,
                    variant,
                    kind,
                    zmin,
                    zmax,
                    nodes,
                    getattr(b, "nominal_nsegs", None),
                    # `freq` is MHz on these builders, not Hz
                    float(getattr(b, "freq", 0.0)),
                )
            )
    hdr = f"{'design':40s} {'variant':10s} {'class':14s} {'zmin':>8s} {'zmax':>9s} {'nodes':>5s} {'nn':>4s} {'MHz':>7s}"
    print(hdr)
    print("-" * len(hdr))
    for d, v, k, zmin, zmax, n, nn, f in rows:
        mhz = "    --  " if f is None else f"{f:7.3f}"
        print(
            f"{d:40s} {v:10s} {k:14s} {zmin:8.4f} {zmax:9.4f} {n:5d} {str(nn):>4s} {mhz}"
        )
    print(
        f"\nPopulation A: {len(rows)} (design, variant) pairs with a conductor below z = 0"
    )
    if failed:
        print(f"builders that would not build ({len(failed)}) — reported, not skipped:")
        for d, v, e in failed:
            print(f"   {d} [{v}]: {e}")
    by = {}
    for r in rows:
        by[r[2]] = by.get(r[2], 0) + 1
    for k, n in sorted(by.items()):
        print(f"   {k:14s} {n}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
