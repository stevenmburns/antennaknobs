# Plan: extend the array-block fast path to the PEC-ground case

**Date:** 2026-06-20
**Branch:** `arrayblock-pec-ground-perf` (antenna_designer)
**Implementation lives in:** the `pysim` submodule (`pysim/src/pysim/`) — this doc is the handoff; the actual solver changes are a separate pysim branch/PR, then a submodule-pointer bump here.
**Status:** planned, not started.

---

## Symptom

In the web UI, on **bowtiearray2x4** with the **ArrayBlock** solver (B-spline degree 2, N=21 segments/wire, 8 feeds):

- **ground OFF (free space):** fast — the array-block accelerator (per-shape dense self-blocks, ACA low-rank coupling, per-shape block-Jacobi preconditioner, batched block GMRES) is in play.
- **ground ON (PEC):** ~2× slower — the accelerator is **not** used; it falls back to a dense solve.

Reproduced (warm timings, `impedance()` = 8-feed Y solve):

| | ground OFF | ground ON (PEC) |
|---|---|---|
| bowtiearray2x4, ArrayBlock, d=2, N=21 | ~489 ms | ~988 ms |

The gap widens with N and array size; N=21 is the floor of the effect.

Repro snippet:
```python
from antenna_designer.designs.bowtiearray2x4 import Builder
from antenna_designer.engines import PysimEngine
from pysim import ArrayBlockPySim

b = Builder()
b.nominal_nsegs = 21
eng = PysimEngine(
    b, solver=ArrayBlockPySim, solver_kwargs={"degree": 2}, ground="pec"
)  # vs ground=None
eng.impedance()
```

---

## Root cause

A single hard gate disables the accelerated path whenever ground is on:

`pysim/src/pysim/hmatrix.py`
```python
def _hmatrix_unsupported(self):  # line 757
    """The H-matrix path is free-space, no-enrichment only for now."""
    return self.ground_z is not None or self.use_singular_enrichment  # line 759


def compute_y_matrix(self):  # line 769
    if self._hmatrix_unsupported():
        return super().compute_y_matrix()  # -> BSplinePySim dense path


def compute_impedance(self):  # line 793
    if self._hmatrix_unsupported():
        return super().compute_impedance()  # -> BSplinePySim dense path
```

`ArrayBlockPySim` subclasses `HMatrixPySim`, so it inherits the gate. With ground on, both impedance and Y fall through to `BSplinePySim`, which assembles the full dense `Z` (free-space **minus** the image assembly) and does a dense LU:

`pysim/src/pysim/bspline.py:1382–1390`
```python
if self.ground_z is not None:
    # PEC image method: subtract the same-shape assembly built from J
    # integrals over image segments + (tx, ty, -tz)-modified tangent dot
    # products. The minus sign captures both the image current's horizontal
    # anti-parallel direction and the image charge's sign flip.
    J_img = self._build_J_image_blocks(geom, self.k)
    td_img = self._image_tangent_dot(geom["tangents"])
    Z = Z - self._assemble_Z(J_img, supp_seg, polys, geom, td_all=td_img)
```

None of the array-block structure runs in that branch.

---

## Why this is tractable (the key insight)

The image method adds, to every interaction, a term: real test basis × **image** trial basis (mirrored across `z = ground_z`, tangent flipped `(tx, ty, −tz)`, combined minus sign).

For a **grid array** — and bowtiearray2x4 is exactly this: 8 identical bowties that are horizontal translates of one shape (verified: one repeating element shape, elements differ only by an in-plane translation) — the real→image-of-b coupling depends on the horizontal displacement **plus the sum of the two heights**. Because every element shares the same height profile, that sum is fixed per (within-element) basis pair regardless of *which* elements a, b are. So:

> The image contribution is still a function of `(shape_a, shape_b, horizontal_displacement)` — the **same displacement key** the free-space array-block assembly already uses.

i.e. the image method does **not** break the array's translation-invariant block reuse for a grid array. It just adds an extra term to each self-block and each coupling block. (This is why the effort is ~2 days, not the ~1 week a "the image breaks the block structure" reading would imply.)

Crucially, the evaluator the image term needs already exists and is already used for ground in the dense path:

`pysim/src/pysim/bspline.py:721–735` (`_build_J_image_blocks`) calls `_seg_seg_full_moments_offedge(seg_l, seg_r, seg_l_img, seg_r_img, a, k, d, n_qp_pair)` — mirrored positions via `_image_positions` (711) and tangent flip via `_image_tangent_dot` (717). The array-block self/coupling assembly uses the same off-edge evaluator. So the per-block image term is "evaluate the same block against the mirrored trial geometry, flip the tangent dot, subtract."

---

## Implementation plan (ArrayBlock, PEC ground)

All changes in `pysim/src/pysim/`.

| # | File / function | Change | Effort |
|---|---|---|---|
| 1 | `hmatrix.py:_hmatrix_unsupported` (757) | Drop the `ground_z` clause; gate only on `use_singular_enrichment`. (Leaves enrichment on the dense fallback, where it still belongs.) | 5 min |
| 2 | `array_block.py` self-block assembly (`build_array_blocks`, ~632; `_self_block_key`, 532) | When `ground_z` is set, add the **self-image** term to each per-shape self-block: real basis × own-element image, mirrored + tangent-flipped + minus sign, via `_seg_seg_full_moments_offedge` (mirror `_build_J_image_blocks`). One block per shape still (all elements share the height profile). | ~½ day |
| 3 | `array_block.py` coupling (`_coupling_aca`, 585; coupling loop in `build_array_blocks`, ~680) | Add the real→image-of-other-element term to each coupling block. Either fold it into the same ACA target, or run a second ACA pass for the image contribution and concatenate factors. Keyed by horizontal displacement as today. | ~½–1 day |
| 4 | `_SELF_BLOCK_CACHE` key (`_self_block_key`, 532) + the coupling-block cache key | Fold `ground_z` into both keys so free-space blocks are never reused under ground (and vice-versa). | ~1 hr |
| 5 | `_BlockJacobiAugPrecond` (427) | **No structural change.** It factors whatever self-blocks it is handed, so it inherits the ground-aware self-image term automatically. KCL is unchanged — images carry no unknowns, so the augmented saddle keeps the same shape. | ~0 |
| 6 | tests (`pysim/tests/test_array_block.py`) | New cases: `ArrayBlockPySim + ground` matches `BSplinePySim + ground` for both `impedance()` and `compute_y_matrix()` to ~1e-9 on bowtiearray2x4 (and one small fixture); assert GMRES iteration count stays in the free-space range. | ~½ day |

**Total: ~1.5–2 days.**

---

## Correctness notes / subtleties

- **Sign convention:** one combined minus sign covers both the image current's anti-parallel horizontal direction and the image charge sign flip. Copy it verbatim from `bspline.py:1382–1390`; do **not** re-derive.
- **Tangent dot:** image trial tangents use `(tx, ty, −tz)` — see `_image_tangent_dot` (bspline.py:717). The self/coupling assembly must pass the image tangent-dot for the image term (the dense path passes it as `td_all=td_img`).
- **Self-image is near-field** for a low antenna — the self-block's image term can be non-trivial. That is fine: it stays per-shape, so the block-Jacobi preconditioner remains (near-)exact and one-factorisation-per-shape cheap.
- **Coupling rank** may rise slightly (real + image), so eyeball ACA `tol` and the resulting ranks; the iteration-count assertion in the test guards regressions.
- **Grid assumption:** the displacement-key reuse relies on elements being horizontal translates of a shared shape (true for the `*array*` grid designs). If a future design mixes heights/orientations per element, the image term is still correct but reuse degrades to per-pair — assembly slows, solve stays fast. Not a correctness issue; note it.

---

## Acceptance criteria

1. `ArrayBlockPySim` + PEC ground returns impedance and Y matching `BSplinePySim` + PEC ground to ≤ 1e-9 (relative) on bowtiearray2x4, d=2, N=21.
2. Web-UI warm timing for bowtiearray2x4 + PEC ground drops from ~990 ms toward the ~490 ms free-space figure (target: within ~1.5× of free space, not ~2×).
3. Block GMRES iteration count with ground on is within ~1–2 of the ground-off count.
4. Free-space results unchanged (regression guard).

---

## Follow-up (out of scope for the first PR)

- **HMatrixPySim** (the non-array hierarchical solver) shares the same gate. The same image-term idea applies, but its far-field ACA blocks (cluster tree over all bases) would each need the image contribution — more surface area than the array case. Do this **after** ArrayBlock lands, as a separate change.
- **Finite (Sommerfeld) ground** is a different beast (not a simple image) and stays on the dense PyNEC path regardless.

---

## Quick start for the next session

1. On a fresh `pysim` branch, start with step 1 (remove the gate) and add a *temporary* assertion path so `ArrayBlockPySim + ground` runs but is known-wrong, to get the test harness wired.
2. Implement steps 2–4; use the dense `BSplinePySim + ground` result as the golden reference in the test.
3. Land the pysim PR, then bump the `pysim` submodule pointer in antenna_designer (and rebuild `_accelerators` if any `.cpp` changed — for this work it likely won't, since it's all Python-level block assembly).
