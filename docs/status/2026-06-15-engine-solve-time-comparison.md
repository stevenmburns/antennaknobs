# 2026-06-15 — engine solve-time comparison (fandipole, trap_fan_dipole)

## Goal

Measure single-call `impedance()` solve time for five MoM engines across
three segmentation levels on two representative designs, with the same
BLAS/OpenMP threading configuration the interactive UI runs under. Result
is a baseline reference for which (engine, N) combinations are viable for
live tuning vs. batch-only.

## Script

`scripts/profile_compare_engines.py` — runnable as
`.venv/bin/python scripts/profile_compare_engines.py`.

Threading setup mirrors `web/server.py` and is applied **before** any
numpy/scipy/PyNEC import (each library snapshots its env at its own
import time and ignores later changes):

```
OPENBLAS_NUM_THREADS = 1                       # avoid contention with the PyNEC/MKL pool
OMP_NUM_THREADS      = physical_core_count     # /proc/cpuinfo parse, 4 on this box
MKL_NUM_THREADS      = physical_core_count
OMP_WAIT_POLICY      = PASSIVE                 # park between OMP regions
GOMP_SPINCOUNT       = 0                       # no busy-spin barrier
```

The physical-core detector counts unique `(physical id, core id)` pairs in
`/proc/cpuinfo`, falling back to `cpu_count() // 2` (HT-assumed) on failure.

Per cell the script does one off-band warm-up call, then mean wall-clock
across each design's target bands:

- fandipole: 14.300, 18.1575, 21.383, 24.97, 28.47 MHz (warm-up 13.0)
- trap_fan_dipole: 18.1575, 21.383, 24.97, 28.47 MHz (warm-up 17.0)

Geometry/Z size is identical across band frequencies for a given
(design, N), so per-call cost is essentially N-and-solver-only and the
mean hides one-shot jitter.

## Results

Mean ms across the design's target bands, with half-spread in parens.
4 physical cores, env settings as above.

**fandipole** (5 spokes × 2 arms, all variable-length wires):

| engine | N=21          | N=41          | N=81           |
|--------|---------------|---------------|----------------|
| Tri    | 122 (±  4)    | 443 (± 18)    | 2265 (± 80)    |
| Bs1    | 106 (±  4)    | 291 (± 20)    | 1119 (± 67)    |
| Bs2    | 141 (±  5)    | 402 (± 10)    | 1367 (± 13)    |
| Sin    |  32 (±  1)    | 168 (± 21)    |  891 (± 43)    |
| PyNEC  | 114 (±  7)    | 636 (±  9)    | 4736 (± 80)    |

**trap_fan_dipole** (2 spokes × 2 arms, adaptive per-wire segmentation):

| engine | N=21         | N=41         | N=81          |
|--------|--------------|--------------|---------------|
| Tri    |  15 (±  1)   |  27 (±  2)   |  79 (±  6)    |
| Bs1    |  26 (±  1)   |  51 (±  3)   | 112 (±  2)    |
| Bs2    |  31 (±  1)   |  62 (±  2)   | 144 (±  3)    |
| Sin    |   4 (±  0)   |   7 (±  0)   |  24 (±  1)    |
| PyNEC  |   6 (±  0)   |  20 (±  0)   |  87 (±  1)    |

Reproducibility: a second back-to-back run reproduced every cell within
~5%, and the tight ±-spreads confirm the measurements are stable.

## Headlines

- **Sinusoidal is the fastest pysim basis everywhere.** ~3–4× faster
  than Tri/Bs1/Bs2 on fandipole at every N, and ~3–4× faster than the
  next-fastest pysim basis on trap_fan_dipole too.
- **PyNEC scales worst on fandipole** — 114 → 4736 ms from N=21→81
  (~42×). On the smaller trap geometry PyNEC is competitive with Sin at
  every N (6 vs 4 ms at N=21; 87 vs 24 ms at N=81).
- **Triangular flips position between designs.** Slowest on fandipole
  (2265 ms at N=81), but the *fastest* pysim basis on trap_fan_dipole
  after Sin (15 ms at N=21). The trap design pins both feed and trap
  wires to 1 segment, which plays to Tri's strengths.
- **Bs1 < Bs2 on cost.** Modest gap (e.g. 1119 vs 1367 ms at fandipole
  N=81; 112 vs 144 ms at trap N=81). Pick based on convergence quality,
  not speed.

## Why the threading config matters

Initial run (system defaults, no env config) reported numbers up to ~10×
slower with much larger run-to-run spreads. Examples:

| | no env config | UI env config |
|---|---|---|
| fandipole Sin N=21    | 326 ms (±353) | 32 ms (±1) |
| trap PyNEC N=21       |  10 ms (±  0) |  6 ms (±0) |
| trap Sin N=81         | 117 ms (± 36) | 24 ms (±1) |

The big wins come from `OMP_WAIT_POLICY=PASSIVE` + `GOMP_SPINCOUNT=0`:
between OMP parallel regions the workers would otherwise busy-spin
~80 ms at every barrier on this CPU, which inflates wall-clock and adds
jitter as the spin overlaps differently with the Python serial work
between solves.

Without that pin, the numbers reflect a configuration the UI never runs
under — they're not the right baseline for "is this engine fast enough
for live tuning". The script above bakes the UI env in so future runs
stay apples-to-apples.

## Caveats

- 4-physical-core box (KBL-class). On a different core count, OMP=N
  changes the absolute numbers; cross-design and cross-engine ratios
  should hold.
- PyNEC parity coercion may bump segment counts up to the next odd
  number, slightly inflating its N relative to pysim's (small effect
  at these N values).
- Single-call `impedance()` only — no sweep, no UI overhead, no
  `run_in_threadpool` boundary. Real live-tick timing includes some
  Python/IO above these numbers.

## Follow-ups

- Verify on a different core count (e.g. CI box) that ratios hold and
  the absolute slowdown scales as expected.
- If trap_fan_dipole becomes the canonical interactive default, the
  numbers above suggest PyNEC at N=21–41 (6–22 ms) and Sin at any N up
  to 81 (4–24 ms) are both viable; fandipole at N=81 is batch-only
  territory for every engine.

## 2026-06-16 update — Bs1/Bs2 process-level basis-poly cache

`pysim/src/pysim/bspline.py` gained a bounded process-level cache for
`_build_geometry` and `_build_basis_polynomials` (pysim PR #80, parent
PR #77). Both functions are pure in their geometry inputs and don't
depend on `k`/wavelength, so caching across solver instances is safe.
The existing instance-level cache only helped `compute_impedance_swept`'s
internal k-loop; the engine wrapper creates a fresh `BSplinePySim` per
`impedance()` call, so for interactive band sweeps the instance cache
was dead.

cProfile attribution at fandipole N=81 said `_build_basis_polynomials`
was 38% of the call and dominated by ~5000 tiny numpy dispatches per
solve (linspace, vander, BSpline.__init__/__call__, small
`numpy.linalg.solve`). Promoting the existing memoization to module
level turns a band-sweep of N freqs into 1 cold call + (N−1) hot calls
for that stage.

### Post-cache results (same script, same env, same day)

**fandipole** (5 spokes × 2 arms):

| engine | N=21          | N=41          | N=81           |
|--------|---------------|---------------|----------------|
| Tri    | 131 (± 10)    | 463 (± 26)    | 2313 (± 64)    |
| Bs1    |  43 (±  4)    | 168 (± 19)    |  796 (± 62)    |
| Bs2    |  61 (±  4)    | 234 (± 20)    | 1054 (± 30)    |
| Sin    |  29 (±  2)    | 135 (±  4)    |  922 (± 49)    |
| PyNEC  | 131 (± 13)    | 702 (± 16)    | 4943 (± 29)    |

**trap_fan_dipole** (2 spokes × 2 arms, adaptive seg):

| engine | N=21         | N=41         | N=81          |
|--------|--------------|--------------|---------------|
| Tri    |  17 (±  2)   |  27 (±  1)   |  85 (±  3)    |
| Bs1    |  11 (±  1)   |  17 (±  1)   |  46 (±  2)    |
| Bs2    |  11 (±  0)   |  22 (±  0)   |  66 (±  1)    |
| Sin    |   4 (±  0)   |   8 (±  1)   |  24 (±  1)    |
| PyNEC  |   6 (±  0)   |  21 (±  1)   |  87 (±  3)    |

### Speedup vs pre-cache

| design / engine | N=21 | N=41 | N=81 |
|---|---|---|---|
| fandipole Bs1 | 106 → 43 (**2.5×**) | 291 → 168 (**1.7×**) | 1119 → 796 (**1.4×**) |
| fandipole Bs2 | 141 → 61 (**2.3×**) | 402 → 234 (**1.7×**) | 1367 → 1054 (**1.3×**) |
| trap Bs1      |  26 → 11 (**2.4×**) |  51 → 17 (**3.0×**) |  112 → 46 (**2.4×**) |
| trap Bs2      |  31 → 11 (**2.8×**) |  62 → 22 (**2.8×**) |  144 → 66 (**2.2×**) |

Tri / Sin / PyNEC unchanged (different code paths). Bit-identical
impedance values across cached / cache-hit / cache-cleared passes on
6 (builder, N, degree) cases; all 104 pysim tests and all 103 relevant
parent tests pass.

### Where the time still goes (Bs2 N=81 cProfile)

The cache eliminates the *amortized* basis-poly cost on solves 2..N of
a sweep, but the cold-call cost is unchanged. Per-band the picture is
roughly: ~400 ms LU solve, ~600 ms basis-poly (cold) / ~0 ms (hot),
~270 ms full-moments C kernel, ~160 ms reg-moments, ~100 ms Z assemble.

## 2026-06-16 — vectorize `_build_basis_polynomials` inner loop

The cold-call basis-poly build was ~5000 numpy dispatches per solve
(linspace + vander + small `np.linalg.solve` + per-basis BSpline
construction + per-wing BSpline eval). Two observations enable a clean
vectorization:

1. The Vandermonde on uniform `[0, 1/d, ..., 1] · h_seg` factors as
   `Vmat = V_unit @ diag(1, h, h², ..., h^d)`. `V_unit_inv` is a fixed
   matrix per degree (closed-form: `[[1,0],[-1,1]]` for d=1;
   `[[1,0,0],[-3,4,-1],[2,-4,2]]` for d=2). Polynomial coefficients are
   then `(V_unit_inv @ vals) / h^p` — pure matmul + column scaling, no
   `scipy.linalg.solve` needed.
2. `BSpline.design_matrix(eval_pts, knots, d)` returns the values of
   every basis function at every eval point in one sparse call. Per
   wire we now build one set of (d+1) uniform sample points per segment
   and call `design_matrix` once, instead of constructing N_basis
   `BSpline` objects and calling each ~3 times.

The inner per-basis loop now reduces to: pick the basis's wing-segment
range (`max(0, j-d) .. min(N, j+1)`), slice into the precomputed
`poly_per_seg[wing_segs, :, j]`, and write into `polys_m`. No
`linspace`, `vander`, `BSpline.__init__`, or `BSpline.__call__` in the
hot loop at all.

### Cold-call speedup (cache cleared each call, mean of 3 reps)

| case            | cache only | + vectorize | speedup |
|-----------------|-----------:|------------:|--------:|
| fan Bs2 N=21    |  142 ms    |   62 ms     | **2.3×** |
| fan Bs2 N=41    |  401 ms    |  234 ms     | **1.7×** |
| fan Bs2 N=81    | 1420 ms    | 1036 ms     | **1.4×** |
| fan Bs1 N=81    | 1112 ms    |  785 ms     | **1.4×** |
| trap Bs2 N=21   |   38 ms    |   16 ms     | **2.4×** |
| trap Bs2 N=41   |   66 ms    |   29 ms     | **2.3×** |
| trap Bs2 N=81   |  152 ms    |   73 ms     | **2.1×** |

The benchmark script (`profile_compare_engines.py`) does a warm-up call
per cell, so its measured numbers don't change — the warm-up populates
the cache and all measured solves take the hot path. The vectorization
matters whenever the geometry just changed (UI tweaking a length,
loading a new design, optimizer step that bumps `nominal_nsegs`); for
those cold solves, the basis-poly stage is now ~3× faster.

Numerical change: results differ from the pre-vectorization path by
~1e-9 (rounding noise from constant matmul vs `scipy.linalg.solve` —
different float ops, same answer). All 104 pysim tests and 103
relevant parent tests pass; bit-identical impedance across
cached / cache-cleared passes confirms determinism.

## Note: `_solve_with_kcl` LU-factor reuse — not an opportunity

Earlier analysis suggested LU-factor reuse inside `_solve_with_kcl`
(the two `scipy.linalg.solve` calls per invocation). That was a
misread of the cProfile. The two solves use *different* matrices:

```python
sol = scipy.linalg.solve(Z, rhs)  # Z is (n_b, n_b)
lam = scipy.linalg.solve(kcl_A @ X, kcl_A @ w)  # (n_c, n_c) Schur
```

For fandipole (`n_c = 1`, single apex K-wire junction) the second
solve is a 1×1 system taking microseconds; the 400 ms attributed to
`scipy.linalg._batched_linalg._solve (ncalls=2)` is essentially all
the first call's LU+back-sub. The function is already structured
optimally (one LU on Z, batched back-substitution on `(1+n_c)` RHS,
then a small Schur step). The remaining LU cost on Z is irreducible
without an algorithmic change — Z is k-dependent, so factorization
can't be reused across band frequencies either.

That leaves the LU solve as the floor at fandipole N=81 (~400 ms /
1036 ms total cold, ~400 / ~700 ms hot). Further improvement would
need either a different numerical method (iterative GMRES with a
geometry-based preconditioner, low-rank ACA on the off-diagonal
blocks) or a faster LAPACK path (float32 preview mode, or pushing
the solve into the C accelerator with the same threading config the
moment kernels already use).
