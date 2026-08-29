# Plan: extend the generic H-matrix (ACA) solver to the PEC-ground case

**Date:** 2026-06-21
**Branch:** `hmatrix-pec-ground-plan` (antenna_designer) holds this doc; implementation is a separate `pysim` branch + PR, then a submodule-pointer bump here.
**Implementation lives in:** the `pysim` submodule (`pysim/src/pysim/hmatrix.py`).
**Status:** planned, not started.
**Prereq:** done — `ArrayBlockPySim` PEC ground shipped in pysim PR #88 (submodule bumped in antenna_designer #107). This is the follow-up that doc called out.

---

## Symptom

`HMatrixPySim` — the *generic* hierarchical (ACA) solver, a binary-space-partition cluster tree over all bases, sibling of the array-aware `ArrayBlockPySim` — still falls back to the dense `BSplinePySim` path whenever ground is on:

`pysim/src/pysim/hmatrix.py:831`
```python
def _hmatrix_unsupported(self):
    """The H-matrix path is free-space, no-enrichment only for now."""
    return self.ground_z is not None or self.use_singular_enrichment  # 833
```

So a non-array design (or an array the user runs on the generic solver) under PEC ground pays the full dense `O(N²)` assembly + dense LU, losing the H-matrix speedup that free space enjoys. `ArrayBlockPySim` overrides this gate (it now supports ground); the base class does not.

---

## Why this is now small (the key insight)

PR #88 already built **every primitive this needs**. The image method adds, to each interaction, a term `real test basis × image trial basis` (trial mirrored across `z = ground_z`, tangent z-flipped `(tx, ty, −tz)`, one combined minus sign — see `BSplinePySim.compute_impedance`, `bspline.py:1382`). PR #88 added, on `HMatrixPySim`:

- `_zblock_image(I, J, k)` (`hmatrix.py:470`) — the dense image sub-block for any basis pair, full off-edge quadrature, ready to subtract from `zblock(I, J)`.
- `_offedge_block_evaluators(ctx, I, J, k, mirror_J=True)` (`hmatrix.py:658`) — the C++ off-edge assembler's `(get_row, get_col, dense)` closures with the trial cluster reflected and its tangents z-flipped, i.e. the **image** contribution for the ACA fill.

`ArrayBlockPySim._coupling_aca` already composes these into `free − image` for its coupling blocks. The H-matrix path uses the *same* near/far block machinery; it just never had the image folded in. So the work is wiring the existing helpers into `build_hmatrix`, not writing new kernel/geometry code.

The `HMatrix` container itself (`_aca.py:209`) is ground-agnostic: `matvec`/`matmat`/`to_dense`/preconditioner all bake whatever block values they are handed. Nothing there changes. The cluster-tree partition (`build_partition`) is built on the **real** geometry's basis bounding boxes — independent of ground — so it is reused verbatim.

---

## The one real question: does the image stay low-rank on far blocks?

Far blocks are admissible (well-separated) clusters compressed by ACA. Folding in the image means the ACA target becomes `Z_free[I,J] − Z_image[I,J]`, where `Z_image[I,J]` is the reaction of real cluster `I` against the **reflection** of cluster `J`. Will that stay low-rank?

For an antenna *above* a ground plane the answer is essentially yes, and here is why:

- Reflection across `z = ground_z` preserves horizontal separation and cluster diameter: `diam(image J) = diam(J)`, and the horizontal part of `dist(I, image J)` equals that of `dist(I, J)`.
- The vertical part of `dist(I, image J)` is `z_I + z_J − 2·ground_z` (both heights above the plane add) — strictly **larger** than for the real pair, never smaller.
- So if `(I, J)` is admissible (`diam ≤ η·dist`), `(I, image J)` is at least as admissible. The image block is therefore low-rank too, and folding it into the same ACA raises the combined rank only modestly (real + image content), exactly as observed for the array coupling blocks in PR #88 (max rank rose ~17→18 on bowtiearray2x4).

**Degenerate case to measure, not fear:** a *very low* antenna (height above ground ≪ horizontal cluster separation) makes `z_I + z_J − 2·ground_z` small, so some far blocks' image term approaches the rank of a near interaction. The existing rank/compression guard handles this safely:

`hmatrix.py:624`
```python
if r * (mI + nJ) >= mI * nJ:
    near_blocks.append((I, J, dense()))  # no compression → store dense
```

A block whose combined rank is too high simply falls back to dense storage — **correct, just less compressed**. So the worst case is graceful perf degradation for a near-ground antenna, never a wrong answer. We measure the compression hit; we do not need to prevent it.

(Near blocks are dense regardless, so their image term — which *can* be near-field/high-rank — is handled exactly by `_zblock_image` with no rank concern.)

---

## Implementation plan (HMatrixPySim, PEC ground)

All changes in `pysim/src/pysim/hmatrix.py`.

| # | Site | Change | Effort |
|---|---|---|---|
| 1 | `_hmatrix_unsupported` (831) | Drop the `ground_z` clause; gate only on `use_singular_enrichment`. (Enrichment + ground stays unsupported — same as the array path; the constructor still raises for enrichment+ground.) | 5 min |
| 2 | **Refactor** — extract a shared `_offedge_aca_evaluators(ctx, I, J, k, use_accel)` on `HMatrixPySim` that returns `(get_row, get_col, dense)` for the **off-edge** block, folding `free − image` when `ground_z` is set (numpy `_zblock_image` rows/cols or C++ `mirror_J=True`). This is exactly today's `ArrayBlockPySim._coupling_aca` body; move it up to the base class. | ~2 hr |
| 3 | `build_hmatrix` near loop (592) | When `ground_z` is set, `D = zblock(I, J) − _zblock_image(I, J)`. | ~½ hr |
| 4 | `build_hmatrix` far loop (605) | Use the shared evaluator from #2 for `get_row/get_col/dense`, so far blocks and the dense fallback both carry the image. | ~½ hr |
| 5 | `ArrayBlockPySim._coupling_aca` | Rewrite to call the shared base helper from #2 (DRY; no behaviour change — guard with the existing array tests). | ~½ hr |
| 6 | preconditioner (`_near_sparse` 779, `_make_preconditioner` 799, `precond_extra`) | **No change.** They reconstruct from the near blocks and the far `U@V`, which now include the image automatically — same as the array block-Jacobi inherited it. | 0 |
| 7 | tests (`pysim/tests/test_hmatrix.py`) | New ground cases (see below). | ~½ day |

**Total: ~1 day.**

No `.cpp` changes (the mirrored-input C++ path landed in #88). No module operator cache for `HMatrixPySim` (unlike `ArrayBlockPySim`), so no cache-key edits; the `_hm_partition` and per-k same-edge caches are ground-independent and reused as-is.

---

## Correctness notes / subtleties

- **Sign / tangent convention:** reuse `_zblock_image` and `mirror_J=True` verbatim — they already encode the combined minus sign and the `(tx, ty, −tz)` tangent flip. Do not re-derive.
- **Near blocks are exact:** `_zblock_image` is full off-edge quadrature (the mirror always separates image from real), matching `_build_J_image_blocks`. The same-edge analytic path applies only to the *free-space* near block (`zblock(..., same_edge=True)`); the image term never uses it.
- **Symmetry:** `Z = Z_free − Z_image` is complex-symmetric under PEC ground (both terms are: reflection preserves `|r_m − mirror(r_n)|` and the flipped tangent dot is symmetric). The H-matrix path does not currently exploit `Z_ab = Z_ba^T` between far blocks (unlike the array coupling cache), so no symmetry bookkeeping is needed here.
- **Refactor risk:** moving the image-folding into a shared base method must not change the free-space array path. The array P3/P4 tests (coupling reuse, Toeplitz, phase/spacing sweeps) are the regression guard; run them.

---

## Tests (mirror the existing free-space `test_hmatrix.py` structure, with `ground_z` set)

1. `HMatrixPySim + ground` matches `BSplinePySim + ground` for `compute_impedance` and `compute_y_matrix` (dipole + a junction geometry) to the existing ACA bar (~1e-4 rel; `to_dense`/matvec to ~1e-4) — mirrors `test_compute_impedance_matches_dense_dipole` / `test_compute_y_matrix_matches_dense_junction`.
2. `H.to_dense()` under ground matches the dense PEC `Z` (`_assemble_Z` free minus image) — mirrors `test_hmatrix_to_dense_reconstruction`.
3. Iteration count under ground within ~1–2 of free space (the near-field preconditioner inherits the image).
4. **Compression measurement:** assert the grounded H-matrix still compresses storage vs dense for a normal-height antenna; add a *low-antenna* case and assert it stays correct (compression may drop — log it, don't over-assert).
5. Free-space regression: existing `test_hmatrix.py` and `test_array_block.py` unchanged.

---

## Acceptance criteria

1. `HMatrixPySim + PEC ground` matches `BSplinePySim + PEC ground` impedance and Y to the same accuracy the free-space H-matrix path matches dense free space (~1e-4 relative).
2. For a normal-height antenna, the grounded H-matrix solve is materially faster than the dense PEC path (warm), and storage still compresses vs dense.
3. GMRES iteration count with ground on is within ~1–2 of ground-off.
4. Free-space H-matrix and array-block results unchanged (regression guard; the shared-evaluator refactor is transparent).

---

## Out of scope / follow-up

- **Finite (Sommerfeld) ground** is not a simple image and stays on the dense PyNEC path regardless — same as for the array case.
- **Enrichment + ground** remains unsupported (the constructor raises); the image reaction for enrichment bases is a separate piece of work.
- **Symmetry reuse between far blocks** (`Z_ab = Z_ba^T`) is a possible later micro-optimisation for the H-matrix fill; not needed for correctness or the headline speedup.

---

## Quick start for the next session

1. Fresh `pysim` branch off `main` (which now has #88).
2. Step 1 (gate) + step 2 (extract `_offedge_aca_evaluators`), then rewire `ArrayBlockPySim._coupling_aca` (step 5) and run the array tests — that proves the refactor is transparent before touching the H-matrix.
3. Steps 3–4 (near/far image fold in `build_hmatrix`), with the dense `BSplinePySim + ground` result as the golden reference.
4. Tests; measure compression on a normal-height and a low antenna.
5. Land the pysim PR, bump the submodule pointer here. No `_accelerators` rebuild expected (all Python-level assembly).
