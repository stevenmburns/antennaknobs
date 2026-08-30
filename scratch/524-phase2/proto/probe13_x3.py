"""A-2: is delta* a mesh-stable node constant? The x3 test.

probe11 fit delta* = -39.3219+28.8343j at x1 (merged crossing dof, MP-B
cross blocks, lumped correction at the merged node) — circular at x1 by
construction. This probe:

  1. builds the x3 MP pieces (cached to results/probe8-blocks-x3.npz),
  2. solves mono x3 (banked cross-check: 71.4922 - 49.0045j),
  3. scores B+merged at x3 with NO correction, with delta*(x1), and
  4. fits delta*(x3) by secant against target = mono_x3 + engine_Delta_x3.

Verdict rule: if delta*(x3) ~ delta*(x1) (and Delta tracks the engine
ladder with the one constant), the crossing physics is a node-local
correction and its closed form is the production target. If it scales
with the mesh, it is a discretization artifact and the reflected-family
derivation is unavoidable.

Run (detached, ~10 min): .venv/bin/python scratch/524-phase2/proto/probe13_x3.py
"""

from __future__ import annotations

import sys
import time
from pathlib import Path

import numpy as np

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "567-phase0" / "proto"))
sys.path.insert(0, str(Path(__file__).resolve().parents[3] / "momwire" / "tests"))

from momwire.bspline import BSplineSolver  # noqa: E402
from probe1_baseline import crossing_deck, seeded  # noqa: E402
from probe8_split import ENGINE_DELTA, build_pieces, mono_deck  # noqa: E402
from probe9_sense import capture  # noqa: E402

DELTA_STAR_X1 = -39.3219 + 28.8343j
MULT = 3


def node_indices(s, geom):
    """(nb, na) at this mult: below node basis = last below basis, above
    node basis = first above basis (value-1 tents at the shared point)."""
    below = s._below_segments(geom)
    n_below_segs = int(np.count_nonzero(below))
    nb = n_below_segs  # bases 0..n_below_segs on the below arm, node last
    na = nb + 1
    return nb, na


def main():
    t0 = time.time()
    pieces = build_pieces(MULT)
    print(f"pieces ready ({time.time() - t0:.0f}s)", flush=True)
    t_ab = pieces["M"] + pieces["SW"] + pieces["SQ"]  # MP B

    s = seeded(crossing_deck(MULT))
    geom = s._build_geometry()
    below = s._below_segments(geom)
    b_seg = np.sort(np.nonzero(below)[0])
    a_seg = np.sort(np.nonzero(~below)[0])
    nb, na = node_indices(s, geom)
    print(f"x{MULT}: node bases nb={nb}, na={na}, n_basis={t_ab.shape[0]}")

    z_mono = capture(BSplineSolver(**mono_deck(MULT)))["z_in"]
    d_eng = ENGINE_DELTA[MULT]
    target = z_mono + d_eng
    print(
        f"mono x{MULT} = {z_mono:.4f} (banked 71.4922-49.0045j)   "
        f"target = {target:.4f}",
        flush=True,
    )

    def merge_hook_at(Zp):
        Zp[:, nb] += Zp[:, na]
        Zp[nb, :] += Zp[na, :]
        Zp[na, :] = 0.0
        Zp[:, na] = 0.0
        Zp[na, na] = 1.0
        return Zp

    def z_in(delta):
        def hook(Zp):
            Zp = merge_hook_at(Zp)
            Zp[nb, nb] += delta
            return Zp

        st = capture(
            seeded(crossing_deck(MULT)),
            t_ab=t_ab,
            a_seg=a_seg,
            b_seg=b_seg,
            z_hook=hook,
        )
        return st["z_in"]

    for name, delta in (
        ("B+merged, no corr", 0.0),
        ("B+merged + delta*(x1)", DELTA_STAR_X1),
    ):
        t0 = time.time()
        z = z_in(delta)
        d = z - z_mono
        print(
            f"  {name:>24}: Z_in = {z:9.4f}   Delta = {d:9.4f}   "
            f"engine = {d_eng:.4f}   dist = {abs(d - d_eng):7.3f}   "
            f"({time.time() - t0:.0f}s)",
            flush=True,
        )

    d0, d1 = DELTA_STAR_X1, DELTA_STAR_X1 * 1.3 + 5.0
    f0 = z_in(d0) - target
    f1 = z_in(d1) - target
    for it in range(12):
        if abs(f1 - f0) < 1e-12:
            break
        d2 = d1 - f1 * (d1 - d0) / (f1 - f0)
        f2 = z_in(d2) - target
        print(f"  secant {it}: delta = {d2:12.4f}   |f| = {abs(f2):.2e}", flush=True)
        d0, f0, d1, f1 = d1, f1, d2, f2
        if abs(f2) < 1e-6:
            break

    print(f"\ndelta*(x{MULT}) = {d1:.4f}   vs delta*(x1) = {DELTA_STAR_X1:.4f}")
    print(f"ratio = {d1 / DELTA_STAR_X1:.4f}")


if __name__ == "__main__":
    main()
