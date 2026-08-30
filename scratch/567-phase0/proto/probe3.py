"""Probe 3/4 of FORMULATION.md §8: full solves against the two engine anchors.

The cross block is swapped for the MP prototype by intercepting the two
cross-medium `_field_galerkin_block` calls inside `_compute_Z_operator_buried`
(detected by their obs/src index sets); everything else — both direct blocks,
both images, the two same-medium remainders — is the production fill.

The boundary weight w parameterizes the contact-endpoint spelling of §7:
  w = 1        spelling A (field form's implicit endpoint charge)
  w = 0        spelling B (endpoint charge deleted)
  w = 1 − C₂   spelling C (transmitted fraction 2/(ε̃+1) of it survives)

Run: .venv/bin/python scratch/567-phase0/proto/probe3.py [contact|fan] [w ...]
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

from mp_cross import mp_cross_block, seeded  # noqa: E402
from momwire import BSplineSolver  # noqa: E402
from test_buried_serve_553 import contact_deck, fan_deck  # noqa: E402

ANCHORS = {"contact": 92.130 - 70.141j, "fan": 89.985 - 71.401j}
BUILDS = {"contact": contact_deck, "fan": fan_deck}


def solve_with_weight(deck, mp, w):
    """One full solve with cross block = main + w·bnd_test (t_ba = ᵀ)."""
    s = seeded(BUILDS[deck]())
    geom = s._build_geometry()
    below = s._below_segments(geom)
    b_idx = np.sort(np.nonzero(below)[0])
    a_idx = np.sort(np.nonzero(~below)[0])
    t_ab = mp["main"] + w * mp["bnd_test"]
    t_ba = t_ab.T

    orig = BSplineSolver._field_galerkin_block

    def wrap(self, supp_seg, polys, proj_fn, obs_idx, src_idx, *rest):
        o = np.sort(np.asarray(obs_idx))
        sr = np.sort(np.asarray(src_idx))
        if np.array_equal(o, a_idx) and np.array_equal(sr, b_idx):
            return t_ab.copy()
        if np.array_equal(o, b_idx) and np.array_equal(sr, a_idx):
            return t_ba.copy()
        return orig(self, supp_seg, polys, proj_fn, obs_idx, src_idx, *rest)

    BSplineSolver._field_galerkin_block = wrap
    try:
        t0 = time.time()
        z, _ = s.compute_impedance()
        secs = time.time() - t0
    finally:
        BSplineSolver._field_galerkin_block = orig
    return z, secs


def main():
    deck = sys.argv[1] if len(sys.argv) > 1 else "contact"
    anchor = ANCHORS[deck]
    s = seeded(BUILDS[deck]())
    eps_t, *_, c2, _a_m = s._buried_medium()
    weights = {
        "A_keep(1)": 1.0 + 0j,
        "B_drop(0)": 0.0 + 0j,
        "C_transmit(1-c2)": 1.0 - c2,
    }
    if len(sys.argv) > 2:
        weights = {f"w={v}": complex(v) for v in sys.argv[2:]}

    print(f"deck={deck}  anchor={anchor}  eps_t={eps_t:.4f}  1-c2={1.0 - c2:.4f}")
    t0 = time.time()
    mp = mp_cross_block(s, rtol=1e-10)
    print(
        f"MP block built in {time.time() - t0:.0f}s; "
        f"|bnd_test|/|main| = {np.max(np.abs(mp['bnd_test'])) / np.max(np.abs(mp['main'])):.3f}"
    )

    out = {}
    for name, w in weights.items():
        z, secs = solve_with_weight(deck, mp, w)
        miss = abs(z - anchor)
        out[name] = dict(
            w=str(w), z=f"{z:.4f}", miss_ohm=round(float(miss), 3), secs=round(secs, 1)
        )
        print(f"  {name:>18}: Z = {z:9.4f}   miss = {miss:7.3f} ohm   ({secs:.0f}s)")

    res = HERE.parent / "results"
    res.mkdir(exist_ok=True)
    (res / f"probe3-{deck}.json").write_text(json.dumps(out, indent=1))


if __name__ == "__main__":
    main()
