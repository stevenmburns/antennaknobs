"""A-2 pre-probe: how far does the CROSSING deck get today, and what does
the geometry/junction machinery hand us once the media are seeded?

Convention check first (PLAN.md rule): e^{+jwt}, eps_t = eps_r - j sigma/(w eps0),
e^{-j k_m R}/R must DECAY with R in the lossy medium.

Questions measured here (no fill, no solve):
  1. Which refusal does the crossing deck hit at construction / at solve?
  2. With `_cached_wire_media` seeded (BELOW, ABOVE), does `_build_geometry`
     produce the bonded junction at z = 0, and what basis/dof structure
     sits on it (the K=2 junction the crossing tent replaces)?
  3. Where do the below-segment masks land (`_below_segments`), i.e. which
     rows/cols the four fill blocks would partition into.
"""

from __future__ import annotations

import sys
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[3] / "momwire" / "tests"))

from momwire import BSplineSolver, _medium_spec  # noqa: E402
from momwire._sommerfeld_transmitted import k_medium  # noqa: E402
from test_buried_serve_553 import SOIL_A, WL7  # noqa: E402

# --- convention assertion -------------------------------------------------
EPS0 = 8.8541878128e-12
_w = 2 * np.pi * 299792458.0 / WL7
eps_t = SOIL_A[0] - 1j * SOIL_A[1] / (_w * EPS0)
k_m = k_medium(eps_t, 2 * np.pi / WL7)
R = np.array([1.0, 5.0, 20.0])
decay = np.abs(np.exp(-1j * k_m * R) / R)
assert np.all(np.diff(decay) < 0), "e^{-j k_m R}/R must decay — convention flipped?"
print(f"convention OK: k_m = {k_m:.4f}, |e^-jkR/R| at 1/5/20 m = {decay}")


def crossing_deck():
    """SPEC.md deck 3 as solver kwargs: 2 m buried vertical bonded at the
    origin to a 10 m monopole, fed at the centre of monopole segment 7 of
    15 (engine `EX 4,2,7`)."""
    return dict(
        wires=[
            np.array([(0.0, 0.0, -2.0), (0.0, 0.0, 0.0)]),
            np.array([(0.0, 0.0, 0.0), (0.0, 0.0, 10.0)]),
        ],
        n_per_edge_per_wire=[[4], [15]],
        feeds=[(1, 4.3333333333, 1 + 0j)],
        wavelength=WL7,
        wire_radius=0.001,
        ground_z=0.0,
        ground_eps=SOIL_A,
        ground_model="sommerfeld",
    )


# --- 1. the refusals as shipped ------------------------------------------
kw = crossing_deck()
try:
    s = BSplineSolver(**kw)
    print("construction: ACCEPTED (no refusal at __init__)")
except ValueError as e:
    print(f"construction refusal: {str(e)[:140]!r}")
    s = None

if s is not None:
    try:
        s.compute_impedance()
        print("solve: ANSWERED (unexpected!)")
    except ValueError as e:
        print(f"solve refusal: {str(e)[:140]!r}")

# --- 2. seeded media + geometry ------------------------------------------
if s is None:
    sys.exit("cannot seed past a construction-time refusal — record and stop")

s2 = BSplineSolver(**crossing_deck())
s2._cached_wire_media = (_medium_spec.BELOW, _medium_spec.ABOVE)
geom = s2._build_geometry()
below = s2._below_segments(geom)
print(
    f"segments: {below.size} total, {int(below.sum())} below, "
    f"{int((~below).sum())} above"
)
print(f"geometry keys: {sorted(geom.keys())}")

# What dof structure sits on the bond at z=0?
for key in ("junctions", "junction_nodes", "n_dofs", "seg_offsets"):
    if key in geom:
        print(f"  geom[{key!r}] = {geom[key]}")

# --- 3. the junction DECLARED: what basis structure appears ----------------
kw3 = crossing_deck()
kw3["junctions"] = [[(0, "end"), (1, "start")]]
s3 = BSplineSolver(**kw3)
s3._cached_wire_media = (_medium_spec.BELOW, _medium_spec.ABOVE)
geom3 = s3._build_geometry()
supp_seg, polys, kcl_A, wire_knots, wire_basis_global = s3._build_basis_polynomials(
    geom3
)
n_basis = len(supp_seg)
print(f"junction declared: {n_basis} bases, kcl_A shape {np.shape(kcl_A)}")
for i, ss in enumerate(supp_seg):
    ss = np.atleast_1d(ss)
    below_supp = bool(np.any(ss < 4))
    above_supp = bool(np.any(ss >= 4))
    tag = (
        "STRADDLES"
        if (below_supp and above_supp)
        else ("below" if below_supp else "above")
    )
    if tag == "STRADDLES" or (kcl_A is not None and np.any(kcl_A[:, i] != 0)):
        print(
            f"  basis {i}: supp_seg {ss.tolist()} [{tag}]  "
            f"kcl col = {kcl_A[:, i] if kcl_A is not None else '-'}"
        )
