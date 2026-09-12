"""momwire#956 derivation, probe 3: cross-check probe2's patches against probe1's
saved blocks by substituting constant blocks into the solve (probe3_cross_block's
`solve_with`), and measure how sensitive Z is to each departure.

Blocks (all from probe1_blocks.npz, the shipped mesh of the #956 deck):
  shipped                       gate: must reproduce 75.8482+40.4523j
  fixW  = shipped - dW          dW = (s_w1 - s_w1_fix) + (s_w2 - s_w2_fix) + (SW - SW_fix)
  fixC  = shipped + (C_all - C_in)
  fixWC = both
plus the patched-path blocks from probe2 for the same settings (must equal).
"""

import os
import sys

os.environ.setdefault("MOMWIRE_CROSSING_FORCE_DENSE", "1")
for _v in ("OMP_NUM_THREADS", "OPENBLAS_NUM_THREADS", "MKL_NUM_THREADS"):
    os.environ.setdefault(_v, "4")

import warnings  # noqa: E402
from pathlib import Path  # noqa: E402

import numpy as np  # noqa: E402

warnings.filterwarnings("ignore")
HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent / "956-oracle"))
sys.path.insert(0, str(HERE))

import probe2_impedance as P2  # noqa: E402  (installs the patches on import)
from momwire import _crossing_fill as CF  # noqa: E402
from probe3_cross_block import build, parts, solve_with, solver_of  # noqa: E402


def rel(x, y):
    return float(np.abs(x - y).max() / max(np.abs(y).max(), 1e-300))


def main():
    d = np.load(HERE / "probe1_blocks.npz")
    shipped = d["shipped"]
    dW = (
        (d["s_w1"] - d["s_w1_fix"])
        + (d["s_w2"] - d["s_w2_fix"])
        + (d["SW"] - d["SW_fix"])
    )
    dC = d["C_all"] - d["C_in"]
    print(
        f"|dW| max {np.abs(dW).max():.4e} at {np.unravel_index(np.abs(dW).argmax(), dW.shape)}; nonzero entries {np.count_nonzero(np.abs(dW) > 0)}"
    )
    print(
        f"|dC| max {np.abs(dC).max():.4e} at {np.unravel_index(np.abs(dC).argmax(), dC.shape)}; nonzero entries {np.count_nonzero(np.abs(dC) > 0)}"
    )
    nz = np.argwhere(np.abs(dC) > 0)
    print(
        "  dC entries:", [(int(m), int(n), f"{abs(dC[m, n]):.3e}") for m, n in nz[:12]]
    )

    b = build()
    s = solver_of(b)
    geom, supp_seg, polys, a_idx, b_idx = parts(s)
    ctx = s._crossing_context(geom, supp_seg, polys)
    A = CF.axis_data(ctx, a_idx)
    B = CF.axis_data(ctx, b_idx)

    # the patched path's blocks, for the same settings
    for label, w, c, ref in (
        ("shipped", False, False, shipped),
        ("fixW", True, False, shipped - dW),
        ("fixC", False, True, shipped + dC),
        ("fixWC", True, True, shipped - dW + dC),
    ):
        P2.FIX["W"], P2.FIX["C"] = w, c
        blk = CF.cross_complete_block_split(ctx, a_idx, b_idx, A, B)
        P2.FIX["W"], P2.FIX["C"] = False, False
        print(f"patched path {label:8s} vs npz block: {rel(blk, ref):.3e}")

    for label, blk in (
        ("shipped", shipped),
        ("fixW", shipped - dW),
        ("fixC", shipped + dC),
        ("fixWC", shipped - dW + dC),
    ):
        z, n = solve_with(solver_of(b), block=blk)
        print(
            f"solve with {label:8s} block: Z = {z.real:9.4f}{z.imag:+9.4f}j  (patch calls {n})"
        )
        sys.stdout.flush()

    # sensitivity: which part of dW drives the move? on-axis rows only vs the rest
    rows, cols = d["rows"], d["cols"]
    m_vv = np.zeros_like(dW, bool)
    m_vv[np.ix_(rows, cols)] = True
    z, _ = solve_with(solver_of(b), block=shipped - np.where(m_vv, dW, 0))
    print(
        f"solve with dW removed on the pure VV block only: Z = {z.real:9.4f}{z.imag:+9.4f}j"
    )
    z, _ = solve_with(solver_of(b), block=shipped - np.where(~m_vv, dW, 0))
    print(
        f"solve with dW removed everywhere ELSE:          Z = {z.real:9.4f}{z.imag:+9.4f}j"
    )
    # split dW by column (below basis): print per-column effect for the VV columns
    for n in cols:
        dcol = np.zeros_like(dW)
        dcol[:, n] = dW[:, n]
        z, _ = solve_with(solver_of(b), block=shipped - dcol)
        print(
            f"   remove dW on column {n}: |dW col| {np.abs(dW[:, n]).max():.3e}  Z = {z.real:9.4f}{z.imag:+9.4f}j"
        )
        sys.stdout.flush()


if __name__ == "__main__":
    main()
