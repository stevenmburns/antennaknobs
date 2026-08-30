"""A-2 task 3 diagnostics: WHERE is the crossing deck's Z poisoned?

probe2 showed constraint rows are irrelevant at 1000 ohm scale, so the
defect is in the fill. Controls here:

  A. capture Z and v from the seeded solve; report the entries around the
     two coincident end bases (4 = below arm's value-1, 5 = monopole's).
  B. AMPUTATE the below arm: rows/cols 0..4 zeroed, diagonal pinned 1,
     rhs zeroed -> below current identically 0, no coupling. If the
     above/above block is clean this must reproduce the monopole-alone
     answer (71.5556 - 49.4339j) through the BURIED code path.
  C. same amputation but of the monopole (sanity: should go open).

Run: .venv/bin/python scratch/524-phase2/proto/probe3_poison.py
"""

from __future__ import annotations

import sys
from pathlib import Path

import numpy as np

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
sys.path.insert(0, str(Path(__file__).resolve().parents[3] / "momwire" / "tests"))

from momwire.bspline import BSplineSolver  # noqa: E402
from probe1_baseline import crossing_deck, seeded  # noqa: E402

MONO_ALONE = 71.5556 - 49.4339j
N_BELOW = 5  # global basis indices 0..4 live on the buried arm


def solve_mod(mod):
    """One seeded solve with Z/v edited in place just before the solve."""
    s = seeded(crossing_deck(1))
    orig = BSplineSolver._solve_with_kcl
    cap = {}

    def wrap(self, Z, v, kcl_A, overwrite=False):
        cap["Z"] = Z.copy()
        cap["v"] = np.array(v, copy=True)
        if mod is not None:
            Z, v, kcl_A = mod(Z.copy(), np.array(v, copy=True), kcl_A)
        return orig(self, Z, v, kcl_A, overwrite=False)

    BSplineSolver._solve_with_kcl = wrap
    try:
        z, _ = s.compute_impedance()
    finally:
        BSplineSolver._solve_with_kcl = orig
    return z, cap


def amputate(idx):
    def mod(Z, v, kcl_A):
        Z[idx, :] = 0.0
        Z[:, idx] = 0.0
        Z[idx, idx] = 1.0
        v[idx] = 0.0
        if kcl_A.size:
            kcl_A = kcl_A.copy()
            kcl_A[:, idx] = 0.0
            keep = np.any(kcl_A != 0.0, axis=1)
            kcl_A = kcl_A[keep]
        return Z, v, kcl_A

    return mod


def main():
    # A: capture and report the suspicious entries
    z0, cap = solve_mod(None)
    Z = cap["Z"]
    print(f"naive: Z_in = {z0:.4f}   (matrix {Z.shape})")
    print("entries around the coincident node bases (4 = below end, 5 = mono base):")
    for i in (3, 4, 5, 6):
        row = "  ".join(f"Z[{i},{j}] = {Z[i, j]:12.4e}" for j in (3, 4, 5, 6))
        print("  " + row)
    mags = np.abs(Z)
    print(
        f"|Z| stats: median {np.median(mags):.3e}, max {mags.max():.3e} "
        f"at {np.unravel_index(mags.argmax(), mags.shape)}"
    )
    print(
        f"|Z| row-max below arm rows 0..4: {[f'{mags[i].max():.2e}' for i in range(5)]}"
    )

    # B: amputate the below arm
    zb, _ = solve_mod(amputate(np.arange(N_BELOW)))
    print(
        f"\nB amputate below arm : Z_in = {zb:.4f}   "
        f"vs monopole-alone {MONO_ALONE:.4f}   "
        f"diff = {abs(zb - MONO_ALONE):.4f} ohm"
    )

    # C: amputate the monopole instead (feed dies -> expect garbage/open)
    zc, _ = solve_mod(amputate(np.arange(N_BELOW, Z.shape[0])))
    print(f"C amputate monopole  : Z_in = {zc:.4f}   (sanity, expect open-ish)")


if __name__ == "__main__":
    main()
