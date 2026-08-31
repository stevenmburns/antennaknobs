"""C1-kink study, probe 2 — E3: the counterfactual C1 tie at the interface.

Production admits the slope jump (probe1 E2: the solved dI/ds ratio
tracks 1/eps-tilde — ~20:1 at soil A). This probe appends ONE extra
Lagrange row tying the below wire's end slope to the above wire's start
slope — enforcing C1 across the interface knot, the thing a single
polyline would do — and measures what it costs: the Z shift per rung
and the node-h convergence order, C0 vs C1-tied, on the crossing deck.

Run: prlimit --as=$((8*1024*1024*1024)) .venv/bin/python \
       scratch/c1-kink-study/probe2_c1_tie.py
"""

from __future__ import annotations

import json
import sys
import time
from contextlib import contextmanager
from pathlib import Path

import numpy as np
from scipy.interpolate import BSpline

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "momwire" / "tests"))

from momwire.bspline import BSplineSolver  # noqa: E402
from test_crossing_serve_524 import _GRADES, crossing_deck  # noqa: E402,F401

# A deeper node rung continuing the _GRADES pattern (probe18's walk).
G3 = dict(
    below=([-2.0, -0.5, -0.1, -0.025, -0.00625], [3, 2, 3, 2, 2]),
    above=([0.00625, 0.025, 0.1, 0.5, 10.0], [2, 2, 3, 2, 19]),
)


def deck(level):
    if level in (1, 2):
        return crossing_deck(level)
    g = G3
    below_pts = np.array([(0.0, 0.0, z) for z in g["below"][0] + [0.0]])
    above_pts = np.array([(0.0, 0.0, z) for z in [0.0] + g["above"][0]])
    b = crossing_deck(1)
    b["wires"] = [below_pts, above_pts]
    b["n_per_edge_per_wire"] = [g["below"][1], g["above"][1]]
    return b


_ORIG_BUILD = BSplineSolver._build_basis_polynomials


@contextmanager
def c1_tie():
    """Append a Lagrange row: (below wire 0 end slope) - (above wire 1
    start slope) = 0. Basis end slopes from each wire's own clamped knot
    vector via scipy's exact derivative."""

    def patched(self, geom):
        supp_seg, polys, kcl_A, wire_knots, wire_basis_global = _ORIG_BUILD(self, geom)
        d = self.degree
        row = np.zeros(kcl_A.shape[1])
        for w_idx, sign in ((0, +1.0), (1, -1.0)):
            knots = wire_knots[w_idx]
            s_eval = knots[-1] if w_idx == 0 else 0.0
            n_b = len(knots) - d - 1
            kept, local_to_global = wire_basis_global[w_idx]
            for k_entry, g_idx in zip(kept, local_to_global, strict=True):
                basis_j = k_entry[0]
                c = np.zeros(n_b)
                c[basis_j] = 1.0
                row[int(g_idx)] += sign * float(
                    BSpline(knots, c, d).derivative()(s_eval)
                )
        return supp_seg, polys, np.vstack([kcl_A, row]), wire_knots, (wire_basis_global)

    BSplineSolver._build_basis_polynomials = patched
    try:
        yield
    finally:
        BSplineSolver._build_basis_polynomials = _ORIG_BUILD


def solve(build, tag):
    s = BSplineSolver(**build)
    t0 = time.time()
    z, _ = s.compute_impedance()
    print(f"  [{tag}] Z = {z:.4f}  ({time.time() - t0:.1f}s)", flush=True)
    return z


def main():
    out = {}
    for level, hmm in ((1, 100.0), (2, 25.0), (3, 6.25)):
        z0 = solve(deck(level), f"g{level}-C0")
        with c1_tie():
            z1 = solve(deck(level), f"g{level}-C1-tied")
        d = abs(z1 - z0)
        print(
            f"  g{level} (node h ~{hmm} mm): C1 tie moves Z by {d:.4f} ohm", flush=True
        )
        out[f"g{level}"] = dict(
            h_node_mm=hmm,
            z_c0=f"{z0:.4f}",
            z_c1=f"{z1:.4f}",
            dz=round(float(d), 4),
        )
    zs0 = [complex(out[f"g{k}"]["z_c0"]) for k in (1, 2, 3)]
    zs1 = [complex(out[f"g{k}"]["z_c1"]) for k in (1, 2, 3)]
    print(
        f"  C0  rung moves: {abs(zs0[1] - zs0[0]):.4f}, {abs(zs0[2] - zs0[1]):.4f}",
        flush=True,
    )
    print(
        f"  C1t rung moves: {abs(zs1[1] - zs1[0]):.4f}, {abs(zs1[2] - zs1[1]):.4f}",
        flush=True,
    )
    (HERE / "results-probe2.json").write_text(json.dumps(out, indent=2))
    print("saved", flush=True)


if __name__ == "__main__":
    main()
