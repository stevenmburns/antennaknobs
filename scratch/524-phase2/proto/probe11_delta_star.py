"""A-2: what NODE correction makes the merged crossing land on the engine?

With the merged crossing dof (probe10) and the MP B cross blocks, insert a
lumped complex correction delta at the merged node dof:

    Z' = merge(Z) + delta * e_nb e_nb^T

(a series impedance between the interface and the stub, in circuit terms)
and solve for the delta* that lands Z_in on the engine-implied target
z_mono + engine_Delta. Z_in is a Moebius function of delta (rank-1
update), so a secant iteration converges in a few steps.

delta* is the MEASURED size+phase of whatever the fill is missing at the
node (self-block endpoint terms / interface-corner defect). Also prints
the fill's own stub driving-point impedance for scale, and a delta scan.

Run: .venv/bin/python scratch/524-phase2/proto/probe11_delta_star.py
"""

from __future__ import annotations

import sys
from pathlib import Path

import numpy as np

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "567-phase0" / "proto"))
sys.path.insert(0, str(Path(__file__).resolve().parents[3] / "momwire" / "tests"))

from momwire.bspline import BSplineSolver  # noqa: E402
from probe1_baseline import crossing_deck, seeded  # noqa: E402
from probe8_split import build_pieces, mono_deck  # noqa: E402
from probe9_sense import capture  # noqa: E402
from probe10_merge import NB, merge_hook  # noqa: E402

ENGINE_DELTA_X1 = -2.3260 - 0.7130j


def z_in_with_delta(t_ab, a_seg, b_seg, delta):
    def hook(Zp):
        Zp = merge_hook(Zp)
        Zp[NB, NB] += delta
        return Zp

    st = capture(
        seeded(crossing_deck(1)), t_ab=t_ab, a_seg=a_seg, b_seg=b_seg, z_hook=hook
    )
    return st["z_in"]


def main():
    pieces = build_pieces(1)
    t_ab = pieces["M"] + pieces["SW"] + pieces["SQ"]  # MP B

    s = seeded(crossing_deck(1))
    geom = s._build_geometry()
    below = s._below_segments(geom)
    b_seg = np.sort(np.nonzero(below)[0])
    a_seg = np.sort(np.nonzero(~below)[0])

    z_mono = capture(BSplineSolver(**mono_deck(1)))["z_in"]
    target = z_mono + ENGINE_DELTA_X1
    print(f"mono = {z_mono:.4f}   target Z_in = {target:.4f}\n")

    # The fill's own idea of the stub: driving-point Z at the node dof of
    # the below/below block alone (delta-gap at the interface end).
    st = capture(seeded(crossing_deck(1)), t_ab=t_ab, a_seg=a_seg, b_seg=b_seg)
    Z = st["Z"]
    Zbb = Z[: NB + 1, : NB + 1]
    e = np.zeros(NB + 1, dtype=complex)
    e[NB] = 1.0
    i_node = np.linalg.solve(Zbb, e)[NB]
    print(f"fill's stub driving-point Z (below block alone) = {1.0 / i_node:.2f}")
    print("  (ground-rod estimate for 2 m, a=1 mm, soil A at 7 MHz: ~64-64j)\n")

    # Scan, then secant.
    for delta in (0.0, -100.0, -200.0 + 0j, -100 - 100j, -200 + 200j, 100 + 0j):
        z = z_in_with_delta(t_ab, a_seg, b_seg, delta)
        d = z - z_mono
        print(
            f"  delta = {delta:10.1f}: Z_in = {z:9.4f}   Delta = {d:9.4f}", flush=True
        )
    print()

    d0, d1 = -100.0 + 0j, -200.0 + 0j
    f0 = z_in_with_delta(t_ab, a_seg, b_seg, d0) - target
    f1 = z_in_with_delta(t_ab, a_seg, b_seg, d1) - target
    for it in range(12):
        if abs(f1 - f0) < 1e-12:
            break
        d2 = d1 - f1 * (d1 - d0) / (f1 - f0)
        f2 = z_in_with_delta(t_ab, a_seg, b_seg, d2) - target
        print(f"  secant {it}: delta = {d2:12.4f}   |f| = {abs(f2):.2e}", flush=True)
        d0, f0, d1, f1 = d1, f1, d2, f2
        if abs(f2) < 1e-6:
            break

    print(f"\ndelta* = {d1:.4f}")
    print(
        f"Z[nb,nb] merged (no corr) = {(Z[NB, NB] + Z[NB, NB + 1] + Z[NB + 1, NB] + Z[NB + 1, NB + 1]):.2f}"
    )
    print(f"below self entry Z[4,4] = {Z[NB, NB]:.2f}")


if __name__ == "__main__":
    main()
