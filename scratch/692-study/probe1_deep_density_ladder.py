"""momwire#692 probe 1 — the deeper-deck density ladder, NEAR axes.

The #688 ladder measured far-axis coarsening (q6→4, panels G8→G4, growth
×2→×4) as ≤3e-4 Ω on every deck — but every deck was SHALLOW (0.15 m)
and the knobs shipped only behind the admissibility split (near pairs
keep dense axes unconditionally). #692 asks whether the NEAR axes can
coarsen too. This probe applies the same three knobs to the near/fine
path ONLY — scoped inside `_crossing_fill.axis_data` via a wrapper, so
the buried grid fills (`_n_qp_buried_field`'s other consumers) never
see them — on a depth ladder (0.15 / 0.5 / 1.0 m) with base and
node-graded meshes.

Knob rungs, separated per the issue (different physics):
  q4      - non-touching near segments' Gauss order 6→4 (1/R³ smoothness)
  panels  - touching segments' graded panels G8→G4, growth ×2→×4
            (the corner region's ln(a) end content)
  combo   - both (= the far knobs applied near)

Meters per deck: the ε̃=1 collapse margin (fan vs free-space truth —
truth never sees the knobs) and the soil-A Z movement vs the deck's own
baseline, plus wall time.

Run: prlimit --as=$((8*1024*1024*1024)) .venv/bin/python \
       scratch/692-study/probe1_deep_density_ladder.py [deck ...]
     decks: D015-base D015-g2 D050-base D050-g D100-base D100-g
"""

from __future__ import annotations

import json
import sys
import time
from contextlib import contextmanager
from pathlib import Path

import numpy as np

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "momwire" / "tests"))

import momwire._crossing_fill as cf  # noqa: E402
from momwire.bspline import BSplineSolver  # noqa: E402
from numpy.polynomial.legendre import leggauss  # noqa: E402
from test_crossing_serve_524 import fan_rise_deck, fan_rise_deck_graded  # noqa: E402

GX4, GW4 = leggauss(4)
_ORIG_AXIS_DATA = cf.axis_data
_ORIG_GRADED_DEFAULTS = cf._graded_u.__defaults__


@contextmanager
def near_knobs(q=None, panels=False):
    """Coarsen the NEAR/fine path of `axis_data` only. `q` shadows the
    solver's `_n_qp_buried_field` (instance attribute, non-touching
    segments); `panels=True` swaps `_graded_u`'s bound defaults to
    (growth 4.0, G4) for the touching segments. Both are applied around
    the original call and restored in finally — coarse=True calls pass
    through untouched, and nothing outside the crossing fill ever sees
    the patch."""

    def wrapper(s, geom, seg_idx, coarse=False):
        if coarse:
            return _ORIG_AXIS_DATA(s, geom, seg_idx, coarse=True)
        if q is not None:
            s._n_qp_buried_field = lambda: q
        if panels:
            cf._graded_u.__defaults__ = (4.0, GX4, GW4)
        try:
            return _ORIG_AXIS_DATA(s, geom, seg_idx, coarse=False)
        finally:
            if q is not None:
                del s.__dict__["_n_qp_buried_field"]
            cf._graded_u.__defaults__ = _ORIG_GRADED_DEFAULTS

    cf.axis_data = wrapper
    try:
        yield
    finally:
        cf.axis_data = _ORIG_AXIS_DATA


# ---------------------------------------------------------------------------
# Decks: depth ladder x mesh ladder. Node gradings follow the #674 recipe
# (matched across the interface, geometric toward the node); rise npe keeps
# the run-scale h at the base class as depth grows.
# ---------------------------------------------------------------------------


def _deep_fan(depth, rise_pts, rise_npe, mono_pts, mono_npe, **override):
    build = fan_rise_deck(depth=depth, **override)
    dirs = ((1, 0), (0, 1), (-1, 0), (0, -1))
    build["wires"] = [
        np.array([(5.0 * dx, 5.0 * dy, -depth)] + [(0.0, 0.0, z) for z in rise_pts])
        for dx, dy in dirs
    ] + [np.array([(0.0, 0.0, z) for z in mono_pts])]
    build["n_per_edge_per_wire"] = [[10] + list(rise_npe) for _ in dirs] + [
        list(mono_npe)
    ]
    return build


def make_deck(name, **override):
    if name == "D015-base":
        return fan_rise_deck(**override)
    if name == "D015-g2":
        return fan_rise_deck_graded("n2", **override)
    if name == "D050-base":
        return _deep_fan(0.5, [-0.5, 0.0], [7], [10.0, 0.0], [15], **override)
    if name == "D050-g":
        return _deep_fan(
            0.5,
            [-0.5, -0.05, -0.0125, 0.0],
            [6, 2, 2],
            [10.0, 0.5, 0.05, 0.0125, 0.0],
            [19, 2, 3, 2],
            **override,
        )
    if name == "D100-base":
        return _deep_fan(1.0, [-1.0, 0.0], [14], [10.0, 0.0], [15], **override)
    if name == "D100-g":
        return _deep_fan(
            1.0,
            [-1.0, -0.05, -0.0125, 0.0],
            [13, 2, 2],
            [10.0, 0.5, 0.05, 0.0125, 0.0],
            [19, 2, 3, 2],
            **override,
        )
    raise KeyError(name)


RUNGS = {
    "baseline": dict(),
    "q4": dict(q=4),
    "panels": dict(panels=True),
    "combo": dict(q=4, panels=True),
}


def _solve(build, tag):
    s = BSplineSolver(**build)
    t0 = time.time()
    z, _ = s.compute_impedance()
    dt = time.time() - t0
    print(f"  [{tag}] Z = {z:.4f}   ({dt:.1f}s)", flush=True)
    return z, dt


def run_deck(name, out):
    print(f"[{name}]", flush=True)
    truth_build = {
        k: v
        for k, v in make_deck(name, ground_eps=(1.0, 0.0)).items()
        if k not in ("ground_z", "ground_eps", "ground_model")
    }
    z_truth, _ = _solve(truth_build, "eps1-truth")
    rows = {}
    for rung, knobs in RUNGS.items():
        with near_knobs(**knobs):
            z_soil, dt_soil = _solve(make_deck(name), f"{rung}/soil")
            z_eps1, dt_eps1 = _solve(
                make_deck(name, ground_eps=(1.0, 0.0)), f"{rung}/eps1"
            )
        margin = abs(z_eps1 - z_truth)
        rows[rung] = dict(
            soil_z=f"{z_soil:.4f}",
            eps1_margin=round(float(margin), 4),
            soil_secs=round(dt_soil, 1),
        )
        if rung != "baseline":
            base = complex(rows["baseline"]["soil_z"])
            rows[rung]["soil_dz"] = round(float(abs(z_soil - base)), 4)
            rows[rung]["margin_shift"] = round(
                float(margin - rows["baseline"]["eps1_margin"]), 4
            )
            print(
                f"  -> {rung}: soil |dZ| = {rows[rung]['soil_dz']}, "
                f"eps1 margin {rows['baseline']['eps1_margin']} -> {margin:.4f}",
                flush=True,
            )
    out[name] = dict(truth=f"{z_truth:.4f}", rungs=rows)


def main():
    path = HERE / "results" / "probe1-deep-density-ladder.json"
    path.parent.mkdir(exist_ok=True)
    out = json.loads(path.read_text()) if path.exists() else {}
    for name in sys.argv[1:] or list(
        ("D015-base", "D015-g2", "D050-base", "D050-g", "D100-base", "D100-g")
    ):
        run_deck(name, out)
        path.write_text(json.dumps(out, indent=2))
    print(f"saved {path}", flush=True)


if __name__ == "__main__":
    main()
