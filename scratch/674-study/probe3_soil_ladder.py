"""momwire#674 probe 3 — the soil-A fan ladder under matched node grading.

probe2's verdict: the K>2 composition error is node-local, dominated by
the above tent's interface-adjacent h, and matched per-arm geometric
grading restores ~2.6-order convergence at ε̃ = 1. At soil A the lossy
transmitted kernels amplify the same class ~30× (the 7.48 Ω base→graded
move of probe38). This probe runs the soil-A fan on the SAME graded
rungs so the anchor converges, plus a far-mesh doubling on the n2 rung
(at soil the absolute answer also owns the far mesh — at ε̃ = 1 it
cancelled in the diff).

The convergence here is self-referential (no free-space truth at soil):
rung-to-rung movement + a Richardson trend vs h_node.

Run: prlimit --as=$((8*1024*1024*1024)) [env MOMWIRE_CROSSING_FORCE_DENSE=1] \
       .venv/bin/python scratch/674-study/probe3_soil_ladder.py [case ...]
     cases: base n1 n2 n3 n2-far2   (results keyed by case and by
     dense/split according to the env var)
"""

from __future__ import annotations

import itertools
import json
import math
import os
import sys
import time
from pathlib import Path

import numpy as np

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "momwire" / "tests"))

from momwire.bspline import BSplineSolver  # noqa: E402
from probe2_node_graded_ladder import MONO_GRADES, RISE_GRADES, H_NODE_MM  # noqa: E402,F401
from test_crossing_serve_524 import fan_rise_deck  # noqa: E402

# momwire#760: this study was run at whatever `n_qp_pair` defaulted to, which
# was 4 — and on a crossing node at a lossy interface the cross-edge error is
# FIRST ORDER in that knob, so a mesh ladder taken at fixed quadrature
# converges to the wrong limit. The order is now an explicit axis rather than
# an inherited default. momwire#762 tiled the qr loop, so high orders run on
# the accelerated path and this is affordable.
N_QP_PAIR = int(os.environ.get("PROBE_N_QP_PAIR", "0"))


def _with_nqp(build):
    if N_QP_PAIR:
        build = dict(build, n_qp_pair=N_QP_PAIR)
    return build


DEPTH = 0.15
LANE = "dense" if os.environ.get("MOMWIRE_CROSSING_FORCE_DENSE") else "split"


def _graded_soil_build(rise_rung=None, mono_rung=None, far_mult=1):
    build = fan_rise_deck()  # soil A, sommerfeld — the deck's own default
    dirs = ((1, 0), (0, 1), (-1, 0), (0, -1))
    wires, npe = [], []
    if rise_rung is None:
        rise_pts, rise_npe = ([-0.15, 0.0], [2])
    else:
        rise_pts, rise_npe = RISE_GRADES[rise_rung]
    for dx, dy in dirs:
        pts = [(5.0 * dx, 5.0 * dy, -DEPTH)] + [(0.0, 0.0, z) for z in rise_pts]
        wires.append(np.array(pts))
        npe.append([10 * far_mult] + list(rise_npe))
    if mono_rung is None:
        mono_pts, mono_npe = ([10.0, 0.0], [15 * far_mult])
    else:
        mono_pts, mono_npe = MONO_GRADES[mono_rung]
        mono_npe = [mono_npe[0] * far_mult] + list(mono_npe[1:])
    wires.append(np.array([(0.0, 0.0, z) for z in mono_pts]))
    npe.append(list(mono_npe))
    build["wires"] = wires
    build["n_per_edge_per_wire"] = npe
    return build


CASES = {
    "base": dict(),
    "n1": dict(rise_rung="n1", mono_rung="n1"),
    "n2": dict(rise_rung="n2", mono_rung="n2"),
    "n3": dict(rise_rung="n3", mono_rung="n3"),
    "n2-far2": dict(rise_rung="n2", mono_rung="n2", far_mult=2),
}


def run_case(name, out):
    s = BSplineSolver(**_with_nqp(_graded_soil_build(**CASES[name])))
    t0 = time.time()
    z, _ = s.compute_impedance()
    dt = time.time() - t0
    print(f"[{name}/{LANE}] Z = {z:.4f}   ({dt:.1f}s)", flush=True)
    out.setdefault(LANE, {})[name] = dict(z=f"{z:.4f}", secs=round(dt, 1))


def trend(out):
    lane = out.get(LANE, {})
    rungs = [r for r in ("n1", "n2", "n3") if r in lane]
    print(f"\n[trend/{LANE}] rung-to-rung movement:", flush=True)
    for r1, r2 in itertools.pairwise(rungs):
        z1, z2 = complex(lane[r1]["z"]), complex(lane[r2]["z"])
        print(f"  {r1}->{r2}: |dZ| = {abs(z2 - z1):.4f} ohm", flush=True)
    if len(rungs) == 3:
        z1, z2, z3 = (complex(lane[r]["z"]) for r in rungs)
        # observed order from the three-rung ratio (h steps x4)
        num, den = abs(z2 - z1), abs(z3 - z2)
        if den > 0:
            p = math.log(num / den) / math.log(4.0)
            z_star = z3 + (z3 - z2) / (4.0**p - 1)
            print(
                f"  observed order p = {p:.3f}; Richardson Z* = {z_star:.4f}",
                flush=True,
            )
            out[f"richardson_{LANE}"] = dict(p=round(p, 3), z_star=f"{z_star:.4f}")


def main():
    # Keyed by quadrature order so a re-derivation never overwrites the record
    # it is correcting (momwire#760).
    _suffix = f"-q{N_QP_PAIR}" if N_QP_PAIR else ""
    path = HERE / "results" / f"probe3-soil-ladder{_suffix}.json"
    path.parent.mkdir(exist_ok=True)
    out = json.loads(path.read_text()) if path.exists() else {}
    for name in sys.argv[1:] or ["base", "n1", "n2", "n3", "n2-far2"]:
        run_case(name, out)
        path.write_text(json.dumps(out, indent=2))
    trend(out)
    path.write_text(json.dumps(out, indent=2))
    print(f"saved {path}", flush=True)


if __name__ == "__main__":
    main()
