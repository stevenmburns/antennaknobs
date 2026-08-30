"""A-2 session 8, probe 39 — WHOSE ends does the completion own?

probe38 measured the eps1 residual turning on with the first >= 3-member
below junction (0.0043 -> 0.1327 -> 0.2269 ohm for node members
2 -> 3 -> 5) and landing at the same size for the buried-hub spelling
(0.2194) where the multi-member junction has its own KCL row.

Hypothesis (probe35's cancellation, read as scope): a junction WITH a
KCL row cancels its members' dropped [f*Phi] by-parts content in the
exact solution — restoring those terms is optional in exact arithmetic
and numerically WORSE in quadrature (large mutually-cancelling additions
with independent errors). The grounded crossing node has NO KCL row, so
its ends' terms are the ones the completion genuinely owns. Candidate
rule: the ends tables keep IN-PLANE ends only.

This probe monkeypatches `_crossing_fill.axis_data` to filter the ends
table to in-plane ends and re-runs the eps1 adjudicators:

  hub-strip   - hub deck: 5 hub-tent ends dropped, node ends kept.
                Collapse to the 0.004 class = hypothesis CONFIRMED for
                the KCL side.
  fan-strip   - N-rises deck: ALL its junction ends are in-plane, so the
                filter is a no-op and the 0.2269 must REPRODUCE (control:
                the N-rises residual is a different mechanism).

Run: prlimit --as=$((8*1024*1024*1024)) .venv/bin/python \
       scratch/524-phase2/proto/probe39_ends_scope.py [hub-strip|fan-strip ...]
"""

from __future__ import annotations

import json
import sys
import time
from pathlib import Path

import numpy as np  # noqa: F401 — kept: imported for its import-time effect / to document the probe's inputs

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(Path(__file__).resolve().parents[3] / "momwire" / "tests"))

from momwire import _crossing_fill  # noqa: E402
from momwire.bspline import BSplineSolver  # noqa: E402
from test_crossing_serve_524 import fan_rise_deck, hub_deck  # noqa: E402

_TOL = 1e-9


def _install_in_plane_filter():
    orig = _crossing_fill.axis_data

    def filtered(s, geom, seg_idx):
        ax = orig(s, geom, seg_idx)
        gz = float(s.ground_z)
        kept = [e for e in ax["ends"] if abs(e[0][2] - gz) <= _TOL]
        dropped = len(ax["ends"]) - len(kept)
        if dropped:
            print(
                f"  [filter] dropped {dropped} out-of-plane end(s), kept {len(kept)}",
                flush=True,
            )
        ax["ends"] = kept
        return ax

    _crossing_fill.axis_data = filtered
    return orig


def _solve(build, tag):
    s = BSplineSolver(**build)
    t0 = time.time()
    z, _ = s.compute_impedance()
    print(f"[{tag}] Z = {z:.4f}   ({time.time() - t0:.0f}s)", flush=True)
    return z


def _truth(build):
    return {
        k: v
        for k, v in build.items()
        if k not in ("ground_z", "ground_eps", "ground_model")
    }


def run(name, deck_fn, out):
    build = deck_fn(ground_eps=(1.0, 0.0))
    z_truth = _solve(_truth(build), f"{name}-truth")
    orig = _install_in_plane_filter()
    try:
        z = _solve(build, f"{name}-stripped")
    finally:
        _crossing_fill.axis_data = orig
    diff = abs(z - z_truth)
    print(f"[{name}] |stripped - truth| = {diff:.4f} ohm", flush=True)
    out[name] = dict(
        z=f"{z:.4f}", truth=f"{z_truth:.4f}", diff_ohm=round(float(diff), 4)
    )


def main():
    fp = HERE.parent / "results" / "probe39-ends-scope.json"
    out = json.loads(fp.read_text()) if fp.exists() else {}
    decks = {"hub-strip": hub_deck, "fan-strip": fan_rise_deck}
    for name in sys.argv[1:] or ["hub-strip"]:
        run(name, decks[name], out)
        fp.write_text(json.dumps(out, indent=1))
    print(f"saved {fp}")


if __name__ == "__main__":
    main()
