"""Scan the contact-endpoint boundary weight w: is there ONE w that closes
the anchor, and is it a nameable physical constant? Tables built once;
each solve is ~1 s. Nelder–Mead on (Re w, Im w) after a coarse grid."""

from __future__ import annotations

import json
import sys
from pathlib import Path

import numpy as np  # noqa: F401 — kept: imported for its import-time effect / to document the probe's inputs
from scipy.optimize import minimize

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
sys.path.insert(0, str(Path(__file__).resolve().parents[3] / "momwire" / "tests"))

from mp_cross import mp_cross_block, seeded  # noqa: E402
from probe3 import ANCHORS, BUILDS, solve_with_weight  # noqa: E402


def main():
    deck = sys.argv[1] if len(sys.argv) > 1 else "contact"
    anchor = ANCHORS[deck]
    s = seeded(BUILDS[deck]())
    eps_t, *_, c2, _a_m = s._buried_medium()
    mp = mp_cross_block(s, rtol=1e-10)

    def miss(wv):
        z, _ = solve_with_weight(deck, mp, complex(wv[0], wv[1]))
        return abs(z - anchor)

    best = None
    for w0 in [0.0 + 0j, 1.0 - c2, 0.1 - 0.1j, -0.1 + 0.1j]:
        r = minimize(
            miss,
            [w0.real, w0.imag],
            method="Nelder-Mead",
            options=dict(xatol=1e-3, fatol=1e-3, maxfev=60),
        )
        if best is None or r.fun < best.fun:
            best = r
    w = complex(best.x[0], best.x[1])
    z, _ = solve_with_weight(deck, mp, w)
    print(f"deck={deck}  best w = {w:.4f}   Z = {z:.4f}   miss = {best.fun:.3f} ohm")
    print(
        f"named candidates: 1-c2 = {1 - c2:.4f}   2/(eps+1) = {2 / (eps_t + 1):.4f}   "
        f"1/eps = {1 / eps_t:.4f}   0"
    )
    res = HERE.parent / "results"
    res.mkdir(exist_ok=True)
    (res / f"wscan-{deck}.json").write_text(
        json.dumps(
            dict(deck=deck, w=str(w), z=f"{z:.4f}", miss=round(float(best.fun), 3)),
            indent=1,
        )
    )


if __name__ == "__main__":
    main()
