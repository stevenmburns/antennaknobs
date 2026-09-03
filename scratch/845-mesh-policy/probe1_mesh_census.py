"""momwire#845 part 1a — where every razor-2p-served catalog deck sits on the
mesh axis, measured WITHOUT solving.

#845's diagnosis is that razor-2p (tent basis, NEC-5's path testing) converges
first order in the far mesh on every deck family, while bspline d2 is already
converged at the same segment count. The remedy on the table is a per-solver
`nominal_nsegs` scale in `auto_mesh`. Before any of that can be priced, two
facts have to be on the table for each deck, and neither needs a solve:

  * the segment length `auto_mesh` actually hands the deck at its shipped
    `nominal_nsegs`, expressed as the two ratios that decide whether a mesh is
    adequate — `lambda/delta` (how many segments per wavelength, the axis #845
    is first-order in) and `delta/a` (the thin-wire limit, the axis that breaks
    if a scale is applied blindly);
  * the total segment count at 1x / 2x / 4x, which is what a scale would cost
    and the only honest way to size the solve half of this probe before
    launching it.

The second is the load-bearing one for sequencing. `auto_mesh` is a DENSITY
(`nominal_nsegs` segments per quarter-wave), so a scale multiplies every
`None`-meshed wire in the catalog at once. On a deck that is already 4000
segments, 4x is 16000, and the fill is O(N^2) in memory and worse in time.
Reading Sigma-seg first tells us which decks the solve half can afford at 4x,
which is why this probe runs before probe2 rather than alongside it.

`delta/a` earns its place for the opposite reason. The thin-wire kernel wants
delta/a comfortably above ~1; refining the mesh DRIVES THIS DOWN, so the same
scale that buys razor accuracy can walk a small-radius deck into the regime
where the kernel itself is the error. A deck whose delta/a is already near the
floor at 1x cannot be given 4x, whatever the convergence table says. That makes
this census a feasibility filter on the policy, not just a description of it.

RESULTS, 2026-09-03, AK main fc0e5c68c + momwire 9eda56f, 100 non-buried decks
(93 with resolvable ratios). These stand whatever the policy turns out to be.

**lambda/delta is nearly CONSTANT across the catalog at ~83** -- 85 of the 93
decks fall in 80-90, median 83.3. That is `auto_mesh` working exactly as
designed rather than a coincidence: `nominal_nsegs=21` per quarter-wave IS
lambda/84, so on the very axis #845 is first-order in, the catalog is already
uniform. Consequence for the framing: "which decks does razor-2p mesh coarsest
relative to its class" has a much flatter answer than it sounds like. The only
outliers are `wire.sterba_tl` at 33.7 (coarsest in the catalog, 2.5x the
median segment length) and `dipoles.koch_dipole` at 104.9 (finest, its fractal
sub-segments). The spread that decides razor's error is NOT lambda/delta.

**Five decks cannot take a 4x scale -- the delta/a thin-wire floor.** Refining
drives delta/a DOWN, and these start close enough to the floor that 4x puts
them at ~2, where the thin-wire kernel itself becomes the error term:

    beams.owa_yagi            7.87 -> 1.97
    verticals.challenger      8.33 -> 2.08
    verticals.dominator       8.33 -> 2.08
    verticals.pota_performer 10.00 -> 2.50
    beams.owa_yagi_6el       10.13 -> 2.53

**Seven decks are outside `auto_mesh`'s reach entirely.** They declare no
`design_freq` and hand-assign every segment count, so the `None` path never
runs and a per-solver `nominal_nsegs` scale would silently not touch them:
`arrays.bowtiearray`, `.bowtiearray1x2`, `.bowtiearray2x4`,
`.folded_invveearray`, `.moxonarray`, `.yagiarray`, and `verticals.elt_whip`
-- the last being the catalog's largest deck at 4067 wires / 4392 segments.
A scale in `auto_mesh` therefore cannot be a catalog-wide guarantee; an
advisory at construction reaches these decks and a mesh policy does not.

**Cost of a blanket scale.** Sigma-seg 17,766 at 1x -> 35,385 at 2x -> 70,756
at 4x. Six decks exceed 2000 segments at 4x, worst `arrays.bowtie16x1` and
`arrays.bowtie4x4` at 5536 each. At the 7-16x that probe2 measures as the
equal-tolerance scale, those two become 40k-90k segments apiece, which is why
probe2's number and not this table is what decides the policy.

Run: .venv/bin/python scratch/845-mesh-policy/probe1_mesh_census.py
     .venv/bin/python scratch/845-mesh-policy/probe1_mesh_census.py --json out.json
"""

from __future__ import annotations

import argparse
import importlib.util
import json
import math
from pathlib import Path

from antennaknobs.cli import list_builtin_designs
from antennaknobs.wire_catalog import as_wire

ROOT = Path(__file__).resolve().parent.parent.parent

# bench_converge lives in scripts/, not on the package path — load it by file,
# the same way tests/test_bench_catalog.py does.
_spec = importlib.util.spec_from_file_location(
    "bench_converge", ROOT / "scripts" / "bench_converge.py"
)
cvg = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(cvg)

C_LIGHT_MHZ_M = 299.792458

# The three buried designs are out of razor-2p's served scope: RazorSolver has
# no buried fill at all (`engines/momwire.py:200`), so a mesh policy for the
# razor path has nothing to say about them. Named rather than detected because
# the detection needs a constructed solver and this probe never builds one.
BURIED = (
    "specialty.buried_dipole",
    "verticals.buried_radial_vertical",
    "verticals.elevated_buried_counterpoise",
)

# Classic idealization when a design declares no wire stock
# (`Builder.build_wire_material` returns None): PEC at 0.5 mm.
DEFAULT_RADIUS_M = 0.5e-3


def wire_radius(builder, w):
    """The radius this wire is solved at: an explicit per-wire spec wins, else
    the design's own stock, else the 0.5 mm idealization. Same precedence the
    engines use, so `delta/a` below is the ratio the kernel actually sees."""
    if w.spec is not None and getattr(w.spec, "radius", None):
        return float(w.spec.radius)
    stock = builder.build_wire_material()
    if stock is not None and getattr(stock, "radius", None):
        return float(stock.radius)
    return DEFAULT_RADIUS_M


def seg_len(w):
    """Segment length of one resolved wire, or None if its count is not a
    plain int (a `GradedSegments` wire has no single segment length; it is
    reported separately rather than averaged into a lie)."""
    p0, p1 = w.p0, w.p1
    length = math.dist(tuple(float(x) for x in p0), tuple(float(x) for x in p1))
    n = w.n_seg
    if not isinstance(n, int) or n <= 0:
        return length, None
    return length, length / n


def census_one(design):
    """One deck's mesh facts at its shipped density. No solver is constructed."""
    cls = cvg.load_design(design)
    b = cls()
    nseg = b.nominal_nsegs
    design_freq = getattr(b, "design_freq", None)

    wires = [as_wire(t) for t in b.build_wires()]
    graded = sum(1 for w in wires if not isinstance(w.n_seg, int))

    deltas, ratios, lengths = [], [], []
    for w in wires:
        length, d = seg_len(w)
        lengths.append(length)
        if d is None:
            continue
        deltas.append(d)
        ratios.append(d / wire_radius(b, w))

    row = {
        "design": design,
        "nseg": nseg,
        "design_freq": None if design_freq is None else float(design_freq),
        "n_wires": len(wires),
        "graded_wires": graded,
        "span_m": max(lengths) if lengths else None,
    }

    # Sigma-seg at the three meshes the solve half would use. `total_nominal_segs`
    # re-builds the design at each density rather than scaling the 1x answer:
    # auto_mesh rounds per wire, so 2x is not exactly twice 1x.
    for mult in (1, 2, 4):
        try:
            row[f"segs_{mult}x"] = cvg.total_nominal_segs(cls, nseg * mult)
        except Exception as e:  # noqa: BLE001 — a design that will not re-mesh
            row[f"segs_{mult}x"] = None
            row.setdefault("mesh_error", f"{type(e).__name__}: {e}")

    if deltas and design_freq:
        lam = C_LIGHT_MHZ_M / float(design_freq)
        # Coarsest wire is the one that decides the deck: #845's error is
        # carried along the whole wire, so the worst segment sets the class.
        row["lam_m"] = lam
        row["delta_max_m"] = max(deltas)
        row["delta_min_m"] = min(deltas)
        row["lam_over_delta_min"] = lam / max(deltas)  # coarsest wire
        row["lam_over_delta_max"] = lam / min(deltas)  # finest wire
        row["delta_over_a_min"] = min(ratios)
        row["delta_over_a_max"] = max(ratios)
    return row


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--json", type=Path, help="also write the rows as JSON")
    ap.add_argument(
        "--sort",
        default="lam_over_delta_min",
        help="row sort key (default: coarsest-wire segments per wavelength)",
    )
    args = ap.parse_args(argv)

    designs = [d for d in list_builtin_designs() if d not in BURIED]
    print(f"# {len(designs)} razor-2p-served catalog designs (roster minus buried)")

    rows, failed = [], []
    for d in designs:
        try:
            rows.append(census_one(d))
        except Exception as e:  # noqa: BLE001 — census must not stop at one bad deck
            failed.append((d, f"{type(e).__name__}: {e}"))

    ok = [r for r in rows if r.get("lam_over_delta_min")]
    ok.sort(key=lambda r: r.get(args.sort) or 0.0)

    hdr = (
        f"{'design':44} {'N':>3} {'Wires':>5} {'lam/d':>7} {'lam/d':>7} "
        f"{'d/a':>7} {'d/a':>8} {'seg1x':>6} {'seg2x':>6} {'seg4x':>6}"
    )
    print(hdr)
    print(
        f"{'':44} {'':>3} {'':>5} {'coarse':>7} {'fine':>7} "
        f"{'min':>7} {'max':>8} {'':>6} {'':>6} {'':>6}"
    )
    print("-" * len(hdr))
    for r in ok:
        print(
            f"{r['design']:44} {r['nseg']:>3} {r['n_wires']:>5} "
            f"{r['lam_over_delta_min']:>7.1f} {r['lam_over_delta_max']:>7.1f} "
            f"{r['delta_over_a_min']:>7.1f} {r['delta_over_a_max']:>8.1f} "
            f"{r['segs_1x'] or -1:>6} {r['segs_2x'] or -1:>6} {r['segs_4x'] or -1:>6}"
        )

    no_freq = [r for r in rows if not r.get("lam_over_delta_min")]
    if no_freq:
        print(f"\n# {len(no_freq)} deck(s) with no design_freq or no plain-int mesh:")
        for r in no_freq:
            print(f"  {r['design']:44} wires={r['n_wires']} graded={r['graded_wires']}")
    if failed:
        print(f"\n# {len(failed)} deck(s) failed to build:")
        for d, err in failed:
            print(f"  {d:44} {err}")

    if ok:
        print(f"\n# Sigma-seg totals over {len(ok)} decks")
        for mult in (1, 2, 4):
            tot = sum(r[f"segs_{mult}x"] or 0 for r in ok)
            big = sum(1 for r in ok if (r[f"segs_{mult}x"] or 0) > 2000)
            print(f"  {mult}x: total {tot:>7}   decks over 2000 seg: {big}")

    if args.json:
        args.json.write_text(json.dumps(rows, indent=2))
        print(f"\nwrote {args.json}")


if __name__ == "__main__":
    main()
