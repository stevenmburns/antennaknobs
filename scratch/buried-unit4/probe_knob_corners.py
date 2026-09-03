"""Buried-flow unit 4 — is the mesh the APP chooses adequate at every corner of
the knobs it exposes, or only at the default?

`verticals.buried_radial_vertical` ships one banked answer, measured at one
point in a five-dimensional knob space. The web hands a user sliders over all
of it. Nothing so far says the auto mesh is adequate anywhere but the middle,
and "adequate at the default" is exactly the kind of claim that generalises
badly: the in-medium wavelength that `auto_mesh` sizes against moves with the
SOIL, the node region moves with `depth`, and the below/below remainder cap
that refuses long radials moves with both.

So: for each corner, solve the way the app solves (auto mesh, quadrature
omitted), then refine each of the three axes independently and measure how far
the app's answer sits from the refined one.

  node       the graded rise's counts x3 -- the momwire#674 recipe, which this
             design already spells as `GradedSegments`, so refining it is
             multiplying counts rather than hand-splitting a wire (hand-splits
             mint spurious KCL rows on this deck: 8-member junctions at every
             graded vertex).
  far        `nominal_nsegs` x3.
  quadrature `n_qp_pair` forced to 64 against the auto value momwire's buried
             fill now picks for itself (momwire#760, cd356fd).

ODD MULTIPLIERS ONLY. x3, not x2, on both mesh axes. An even multiplier moves
the fed segment's centre, so the feed lands somewhere else on the wire and the
ladder measures the feed as well as the mesh -- the same axis-confusion that
made #845's headline deck non-monotone. `scratch/g1b-bs1-bs2/RESULTS.md` uses
x3/x5/x9 for this reason.

The second reading is bspline degree 1 at the auto mesh, per the underground
convention: the reference below ground is a MEASUREMENT (BLE 1937), the engine
is degree 2, and degree 1 is the same-trunk cross-check. razor and NEC-5 are
not asked underground and nothing here is gated against them.

Corners are read from the Builder's `ui_params`, not invented: n_radials 1-4,
depth 0.05-0.5 m, length_factor 0.8-1.2, radial_factor 0.3-1.5. The soil axis
is momwire's own A/B/C (13/0.005, 20/0.03, 5/0.001), consistent across three
golden files -- the WEB has no named soil presets, it exposes eps_r and sigma
as free fields, which is itself worth knowing.

A refusal is a RESULT here, not a failure: the design's docstring says long
radials over dense soil hit the below/below 2-lambda_m cap and refuse by name.
This probe records which corners refuse and why.

Run: .venv/bin/python scratch/buried-unit4/probe_knob_corners.py --json out.json
     .venv/bin/python scratch/buried-unit4/probe_knob_corners.py --only default
"""

from __future__ import annotations

import argparse
import json
import time
import traceback
import warnings
from pathlib import Path

from antennaknobs.designs.verticals.buried_radial_vertical import Builder
from antennaknobs.engines.momwire import MomwireEngine
from antennaknobs.wire_catalog import GradedSegments, as_wire

SOILS = {"A": (13.0, 0.005), "B": (20.0, 0.03), "C": (5.0, 0.001)}

# Corners of the exposed knob ranges plus the default. Read from the Builder's
# `ui_params` block; see the module docstring.
CORNERS = [
    ("default", {}, "A"),
    ("n_radials_min", {"n_radials": 1}, "A"),
    ("depth_min", {"depth": 0.05}, "A"),
    ("depth_max", {"depth": 0.5}, "A"),
    ("length_min", {"length_factor": 0.8}, "A"),
    ("length_max", {"length_factor": 1.2}, "A"),
    ("radial_min", {"radial_factor": 0.3}, "A"),
    ("radial_max", {"radial_factor": 1.5}, "A"),
    ("soil_B_dense", {}, "B"),
    ("soil_C_sparse", {}, "C"),
    # Both extremes together, on each side. The single-knob corners can each be
    # fine while their combination is not: the cap that refuses long radials is
    # a function of radial length AND the in-medium wavelength, i.e. of the
    # soil, so radial_max over soil B is a different question from either.
    (
        "worst_dense",
        {"n_radials": 4, "depth": 0.5, "length_factor": 1.2, "radial_factor": 1.5},
        "B",
    ),
    (
        "mild_sparse",
        {"n_radials": 1, "depth": 0.05, "length_factor": 0.8, "radial_factor": 0.3},
        "C",
    ),
]


def _total_segs(builder):
    total = 0
    for t in builder.build_wires():
        n = as_wire(t).n_seg
        total += sum(n.counts) if isinstance(n, GradedSegments) else int(n)
    return total


def make_builder(params, *, nseg_mult=1, node_mult=1):
    """A Builder at these knob values, optionally refined on one axis.

    `node_mult` scales the counts INSIDE each `GradedSegments` wire, which is
    how this design spells its node grading. Doing it here rather than by
    splitting wires keeps the polyline edge chain — and therefore the junction
    topology — exactly as the app builds it.
    """

    class _Corner(Builder):
        def build_wires(self):
            tups = super().build_wires()
            if node_mult == 1:
                return tups
            out = []
            for t in tups:
                w = as_wire(t)
                if isinstance(w.n_seg, GradedSegments):
                    g = w.n_seg
                    w = w._replace(
                        n_seg=GradedSegments(
                            fracs=g.fracs, counts=tuple(c * node_mult for c in g.counts)
                        )
                    )
                out.append(w)
            return out

    b = _Corner()
    for k, v in params.items():
        setattr(b, k, v)
    if nseg_mult != 1:
        b.nominal_nsegs = b.nominal_nsegs * nseg_mult
    return b


def solve(
    params,
    soil_key,
    *,
    degree=2,
    nseg_mult=1,
    node_mult=1,
    n_qp_pair=None,
    swept_mem_mb=None,
):
    """One impedance the way the app asks for it, with one axis optionally
    refined. Returns (z, seconds, total_segs) or raises.

    `swept_mem_mb` is raised only for REFINED points, never for the app's own
    answer. momwire routes buried decks through the dense moment tensor and
    refuses past a 256 MB budget rather than truncating the medium; that is a
    resource guard, not physics, so lifting it for a ladder rung is legitimate
    where lifting it for the measured answer would not be.
    """
    from momwire import BSplineSolver

    kwargs = {"degree": degree}
    if n_qp_pair is not None:
        kwargs["n_qp_pair"] = n_qp_pair
    if swept_mem_mb is not None:
        kwargs["swept_mem_mb"] = swept_mem_mb
    b = make_builder(params, nseg_mult=nseg_mult, node_mult=node_mult)
    eps_r, sigma = SOILS[soil_key]
    t0 = time.perf_counter()
    eng = MomwireEngine(
        b,
        solver=BSplineSolver,
        solver_kwargs=kwargs,
        ground=("finite", eps_r, sigma),
        ground_z=0.0,
    )
    z = eng.impedance()[0]
    return complex(z), time.perf_counter() - t0, _total_segs(b)


def run_corner(name, params, soil_key, *, node_mult, far_mult, q_hi):
    """The app's answer plus one refinement per axis, and the degree pair."""
    row = {"corner": name, "params": dict(params), "soil": soil_key, "axes": {}}
    caught = []

    def attempt(label, **kw):
        try:
            with warnings.catch_warnings(record=True) as rec:
                warnings.simplefilter("always")
                z, secs, segs = solve(params, soil_key, **kw)
            fired = sorted({type(w.message).__name__ for w in rec})
            caught.extend(f"{label}:{n}" for n in fired)
            print(
                f"    {label:12} {secs:7.2f} s  segs={segs:>5}  Z = {z:.4f}", flush=True
            )
            return {"z": [z.real, z.imag], "s": secs, "segs": segs, "warnings": fired}
        except Exception as e:  # noqa: BLE001 — a refusal is a RESULT here
            print(
                f"    {label:12} REFUSED/ERROR: {type(e).__name__}: {str(e)[:90]}",
                flush=True,
            )
            return {
                "error": f"{type(e).__name__}: {e}",
                "trace_tail": traceback.format_exc()[-400:],
            }

    row["axes"]["auto"] = attempt("auto")
    row["axes"]["bs1"] = attempt("bs1", degree=1)
    row["axes"]["node"] = attempt(f"node x{node_mult}", node_mult=node_mult)
    # The far rung is the one that outgrows the dense-tensor budget on the
    # bigger decks, so it gets the raised budget; the app's answer never does.
    row["axes"]["far"] = attempt(
        f"far x{far_mult}", nseg_mult=far_mult, swept_mem_mb=4096
    )
    row["axes"]["quad"] = attempt(f"n_qp={q_hi}", n_qp_pair=q_hi)
    row["warnings_seen"] = sorted(set(caught))

    def z_of(k):
        a = row["axes"].get(k, {})
        return None if a.get("error") or "z" not in a else complex(*a["z"])

    auto = z_of("auto")
    row["deltas"] = {
        k: (None if (auto is None or z_of(k) is None) else abs(auto - z_of(k)))
        for k in ("node", "far", "quad", "bs1")
    }
    return row


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--json", type=Path)
    ap.add_argument("--only", action="append", help="corner name(s) to run")
    ap.add_argument("--node-mult", type=int, default=3)
    ap.add_argument("--far-mult", type=int, default=3)
    ap.add_argument("--q-hi", type=int, default=64)
    args = ap.parse_args(argv)

    for m in (args.node_mult, args.far_mult):
        if m % 2 == 0:
            ap.error(f"multiplier {m} is even; odd only (it would move the feed)")

    corners = [c for c in CORNERS if not args.only or c[0] in args.only]
    print(
        f"# {len(corners)} corner(s); node x{args.node_mult}, far x{args.far_mult}, n_qp {args.q_hi}"
    )

    rows, t0 = [], time.perf_counter()
    for name, params, soil in corners:
        print(f"\n=== {name}  {params or '(defaults)'}  soil {soil} ===", flush=True)
        rows.append(
            run_corner(
                name,
                params,
                soil,
                node_mult=args.node_mult,
                far_mult=args.far_mult,
                q_hi=args.q_hi,
            )
        )
        if args.json:
            args.json.write_text(json.dumps(rows, indent=2))
    print(f"\ntotal {time.perf_counter() - t0:.0f} s")

    hdr = f"{'corner':16} {'soil':4} {'Z(auto)':>22} {'d_node':>8} {'d_far':>8} {'d_quad':>8} {'d_bs1':>8}"
    print("\n" + hdr)
    print("-" * len(hdr))
    for r in rows:
        a = r["axes"]["auto"]
        z = "REFUSED" if a.get("error") else f"{complex(*a['z']):.4f}"
        d = r["deltas"]
        cells = "".join(
            f"{'     n/a' if d[k] is None else f'{d[k]:8.3f}'} "
            for k in ("node", "far", "quad", "bs1")
        )
        print(f"{r['corner']:16} {r['soil']:4} {z:>22} {cells}")
        if r["warnings_seen"]:
            print(f"{'':16} warnings: {', '.join(r['warnings_seen'])}")

    if args.json:
        args.json.write_text(json.dumps(rows, indent=2))
        print(f"\nwrote {args.json}")


if __name__ == "__main__":
    main()
