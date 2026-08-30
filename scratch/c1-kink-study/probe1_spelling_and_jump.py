"""C1-kink study, probe 1 — E1 (spelling parity) + E2 (the physical jump).

Ground truth from the basis code: junctions couple wires by a value-1
directional basis + one KCL row — C0 ONLY, each side's end slope free.
Within a polyline, d=2 enforces C1 at interior knots. So the spelling IS
the continuity specification: split wires + junction = C0, one polyline
= C1. The crossing serve already forces the C0 spelling at the
interface.

E1  free space, where the current IS smooth: a 12 m wire spelled as one
    polyline (C1 at the midpoint knot) vs two wires + junction (C0).
    The C0 join must cost nothing — parity per rung and no spurious
    slope jump at the join.

E2  the crossing deck over an eps-tilde ladder: the solved dI/ds just
    below vs just above the interface (current_slopes — exact in-basis
    derivative). q = -(1/jw) dI/ds must jump with the medium contrast:
    ~0 at eps=1, growing with sigma. If the solution USES the C0
    freedom, the kink is physics and the formulation is right to admit
    it.

Run: prlimit --as=$((8*1024*1024*1024)) .venv/bin/python \
       scratch/c1-kink-study/probe1_spelling_and_jump.py
"""

from __future__ import annotations

import json
import sys
import time
from pathlib import Path

import numpy as np

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "momwire" / "tests"))

from momwire.bspline import BSplineSolver  # noqa: E402
from test_crossing_serve_524 import A_WIRE, WL7, crossing_deck  # noqa: E402

FEED_ARC_1WIRE = 2.0 + 4.3333333333  # the g524_5 spelling of EX 4,1,7


def solve(build, tag):
    s = BSplineSolver(**build)
    t0 = time.time()
    z, coeffs = s.compute_impedance()
    print(f"  [{tag}] Z = {z:.4f}  ({time.time() - t0:.1f}s)", flush=True)
    return s, z, coeffs


def one_wire_free(n):
    pts = [(0.0, 0.0, z) for z in (-2.0, 0.0, 10.0)]
    return dict(
        wires=[np.array(pts)],
        n_per_edge_per_wire=[[2 * n, 10 * n]],
        feeds=[(0, FEED_ARC_1WIRE, 1 + 0j)],
        wavelength=WL7,
        wire_radius=A_WIRE,
    )


def two_wire_free(n):
    return dict(
        wires=[
            np.array([(0.0, 0.0, -2.0), (0.0, 0.0, 0.0)]),
            np.array([(0.0, 0.0, 0.0), (0.0, 0.0, 10.0)]),
        ],
        n_per_edge_per_wire=[[2 * n], [10 * n]],
        junctions=[[(0, "end"), (1, "start")]],
        feeds=[(1, 4.3333333333, 1 + 0j)],
        wavelength=WL7,
        wire_radius=A_WIRE,
    )


def junction_slopes(s, coeffs, below_idx=0, above_idx=1):
    """(dI/ds at the below wire's junction end, at the above wire's start,
    I at the junction) — per-wire in-basis derivatives, s_array pinned to
    the junction arc position on each side."""
    geom = s._build_geometry()
    arc_end = geom["per_wire"][below_idx]["arc_at_knot"][-1]
    slopes = s.current_slopes(
        coeffs,
        s_array=[
            [arc_end] if i == below_idx else [0.0] if i == above_idx else []
            for i in range(len(geom["per_wire"]))
        ],
    )
    cur = s.currents_at_knots(
        coeffs,
        s_array=[
            [arc_end] if i == below_idx else [0.0] if i == above_idx else []
            for i in range(len(geom["per_wire"]))
        ],
    )
    return (
        complex(slopes[below_idx][0]),
        complex(slopes[above_idx][0]),
        complex(cur[below_idx][0]),
    )


def run_e1(out):
    print("[E1] free space: one-polyline (C1) vs split+junction (C0)", flush=True)
    rows = {}
    for n in (1, 2, 4):
        _, z1, _ = solve(one_wire_free(n), f"n{n}-one-wire-C1")
        s2, z2, c2 = solve(two_wire_free(n), f"n{n}-split-C0")
        db, da, cur = junction_slopes(s2, c2)
        jump = abs(da - db) / max(abs(db), abs(da))
        print(
            f"  n{n}: |Z_C1 - Z_C0| = {abs(z1 - z2):.4f} ohm; "
            f"C0 rel slope jump at join = {jump:.2e}",
            flush=True,
        )
        rows[f"n{n}"] = dict(
            z_c1=f"{z1:.4f}",
            z_c0=f"{z2:.4f}",
            dz=round(float(abs(z1 - z2)), 4),
            rel_jump=float(f"{jump:.3e}"),
        )
    out["E1-free-space"] = rows


def run_e2(out):
    print("[E2] crossing deck: solved slope jump vs medium contrast", flush=True)
    rows = {}
    for tag, eps in (
        ("eps1", (1.0, 0.0)),
        ("eps13-lossless", (13.0, 0.0)),
        ("soil-A", (13.0, 0.005)),
        ("sigma-0.05", (13.0, 0.05)),
    ):
        build = crossing_deck(1, ground_eps=eps)
        s, z, coeffs = solve(build, tag)
        db, da, cur = junction_slopes(s, coeffs)
        jump = abs(da - db) / max(abs(db), abs(da), 1e-30)
        ratio = (da / db) if db != 0 else complex("nan")
        print(
            f"  {tag}: dI/ds below {db:.4e}  above {da:.4e}  "
            f"rel jump {jump:.3f}  ratio {ratio:.3f}",
            flush=True,
        )
        rows[tag] = dict(
            z=f"{z:.4f}",
            slope_below=f"{db:.6e}",
            slope_above=f"{da:.6e}",
            rel_jump=round(float(jump), 4),
            ratio=f"{ratio:.4f}",
            i_junction=f"{cur:.6e}",
        )
    out["E2-crossing-jump"] = rows


def main():
    path = HERE / "results-probe1.json"
    out = json.loads(path.read_text()) if path.exists() else {}
    run_e1(out)
    path.write_text(json.dumps(out, indent=2))
    run_e2(out)
    path.write_text(json.dumps(out, indent=2))
    print(f"saved {path}", flush=True)


if __name__ == "__main__":
    main()
