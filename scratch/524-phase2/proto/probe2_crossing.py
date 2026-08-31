"""A-2 task 3: the crossing CONDITION as Lagrange rows — first spellings.

The K=2 junction at z = 0 is grounded, so production drops its KCL row and
each arm continues into its own image. Here the two crossing rows are
appended to whatever constraint matrix the solve already carries, by
wrapping `_solve_with_kcl`:

  row V (continuity):  I(0+) - I(0-) = 0
  row S (slope jump):  I'(0+) - r * I'(0-) = 0,   r = eps~_+ / eps~_-

AGARD (15)-(16) / NEC-4 (3-45). Both wires run t-hat = +z so dI/dl = dI/dz
on each side. Coefficients are read off the basis polynomials at the node:
value/derivative of every basis wing touching the two node segments.

Spellings:
  S0  no rows            (= probe1 baseline)
  S1  V only             (continuity, derivative free)
  S2  V + S with AGARD r (the physics)
  S3  V + S with r = 1   (naive C1 contrast)

The contact-image fiction is NOT touched here — that is the next spelling
axis; this probe measures what the constraint rows alone buy.

Run: .venv/bin/python scratch/524-phase2/proto/probe2_crossing.py [mult]
"""

from __future__ import annotations

import json
import sys
import time
from pathlib import Path

import numpy as np

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
sys.path.insert(0, str(Path(__file__).resolve().parents[3] / "momwire" / "tests"))

from momwire import _medium_spec  # noqa: E402,F401
from momwire.bspline import BSplineSolver  # noqa: E402
from probe1_baseline import LADDER, crossing_deck, seeded  # noqa: E402


def node_rows(s, geom):
    """(row_V, above_deriv, below_deriv) coefficient vectors at the node.

    The node is the shared point: END of wire 0's last segment (global
    segment n0-1, u_local = h), START of wire 1's first segment (global
    segment n0, u_local = 0).
    """
    supp_seg, polys, _kcl, _wk, _wbg = s._build_basis_polynomials(geom)
    n_basis = supp_seg.shape[0]
    n0 = int(geom["seg_offsets"][1])  # wire 0 segment count
    seg_below, seg_above = n0 - 1, n0
    h_below = float(geom["h_per_seg"][seg_below])

    val_above = np.zeros(n_basis)
    val_below = np.zeros(n_basis)
    der_above = np.zeros(n_basis)
    der_below = np.zeros(n_basis)
    for m in range(n_basis):
        for wing in range(supp_seg.shape[1]):
            a = polys[m, wing]
            if not np.any(a):
                continue  # zero-padded wing
            seg = int(supp_seg[m, wing])
            if seg == seg_above:
                # node at u_local = 0
                val_above[m] += a[0]
                der_above[m] += a[1]
            elif seg == seg_below:
                # node at u_local = h
                u = h_below
                val_below[m] += sum(a[p] * u**p for p in range(len(a)))
                der_below[m] += sum(p * a[p] * u ** (p - 1) for p in range(1, len(a)))
    row_v = val_above - val_below
    return row_v, der_above, der_below


def solve_spelling(mult, rows):
    s = seeded(crossing_deck(mult))
    orig = BSplineSolver._solve_with_kcl

    def wrap(self, Z, v, kcl_A, overwrite=False):
        if rows:
            add = np.stack(rows)
            kcl_A = np.vstack([kcl_A.astype(add.dtype), add])
        return orig(self, Z, v, kcl_A, overwrite=overwrite)

    BSplineSolver._solve_with_kcl = wrap
    try:
        t0 = time.time()
        z, _ = s.compute_impedance()
        secs = time.time() - t0
    finally:
        BSplineSolver._solve_with_kcl = orig
    return z, secs


def main():
    mult = int(sys.argv[1]) if len(sys.argv) > 1 else 1
    ref = LADDER.get(mult)

    s = seeded(crossing_deck(mult))
    geom = s._build_geometry()
    row_v, der_a, der_b = node_rows(s, geom)
    eps_t, *_rest = s._buried_medium()
    r_agard = 1.0 / eps_t  # eps~_+ / eps~_- with eps~_+ = 1 (air)
    print(f"eps_t = {eps_t:.4f}, r = eps~+/eps~- = {r_agard:.6f}")
    nz = np.nonzero(row_v)[0]
    print(
        f"row V nonzeros: {dict(zip(nz.tolist(), row_v[nz].round(4).tolist(), strict=True))}"
    )

    spellings = {
        "S1_V_only": [row_v],
        "S2_V_plus_AGARD": [row_v, der_a - r_agard * der_b],
        "S3_V_plus_r1": [row_v, der_a - 1.0 * der_b],
    }
    out = {}
    for name, rows in spellings.items():
        z, secs = solve_spelling(mult, rows)
        miss = abs(z - ref) if ref else float("nan")
        out[name] = dict(z=f"{z:.4f}", miss_ohm=round(float(miss), 3))
        print(
            f"  {name:>16}: Z = {z:9.4f}   engine(x{mult}) = {ref:.4f}   "
            f"miss = {miss:8.3f} ohm   ({secs:.0f}s)"
        )

    res = HERE.parent / "results"
    res.mkdir(exist_ok=True)
    (res / f"probe2-x{mult}.json").write_text(json.dumps(out, indent=1))


if __name__ == "__main__":
    main()
