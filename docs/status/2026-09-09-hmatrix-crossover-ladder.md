# 2026-09-09 — H-matrix crossover ladder (206 cells, momwire#977)

## Goal

Find where `HMatrixSolver` actually beats `BSplineSolver` on real catalog
geometry, after [momwire#979](https://github.com/stevenmburns/momwire/issues/979)
changed the Sommerfeld remainder — and say so per (class, degree, ground,
`aca_tol`) rather than as one number. Answers momwire#977.

Measured on the Skylake box (i7-6700K, 4 physical cores, powersave). **Trust
the ratios, not the absolute seconds** — the dense/hmatrix ratio is the
portable quantity and even it moved between this box and Laptop-control's on
the same commit.

Data: `2026-09-09-hmatrix-crossover-ladder.jsonl`, 206 rows, momwire at
`16699bf`. Harness: `scripts/bench_hmatrix_crossover.py`.

## Headline

**The H-matrix wins 3 of 101 comparable cells.** All three are
`wire.rhombic` at ~8,000 bases on finite ground, far fraction 0.980:

| cell | ratio (hmatrix/dense) | relZ |
|---|--:|--:|
| rhombic n=8,074 d=1 finite, default tol | **0.78×** | 1.8e-06 |
| rhombic n=8,078 d=2 finite, default tol | **0.90×** | 6.9e-07 |
| rhombic n=8,074 d=1 finite, `aca_tol=1e-8` | **0.98×** | 4.9e-07 |

Everywhere else it is slower, by 1.6× to 38×. It is *correct* nearly
everywhere — relZ against dense at the same degree sits at 1e-6 or below in
every healthy cell — so this is a cost result, not an accuracy one.

**On ground-coupled compact loops it has no case at all, and will not acquire
one by meshing harder.** `loops.skyloop_lmatch` is the only class whose ratio
gets *worse* with size: 4.2× at 93 bases to 16.4× at 270. Its far fraction is
0.687 at the top rung and **0.000** at the bottom — at 93 bases nothing is
admissible, so the "H-matrix" is a dense matrix carrying the cluster tree's
overhead. That is the class to stop offering it for.

## Crossover by (class, degree, ground, `aca_tol`)

Ratio of warm hmatrix wall to warm dense wall, by basis count. Below 1.00 the
H-matrix is winning.

| class | d | ground | tol | far_frac | ratio by n |
|---|--:|---|---|--:|---|
| wire.rhombic | 1 | finite | def | 0.980 | 1014:4.73 2022:2.94 3030:2.54 4042:1.59 6058:1.22 **8074:0.78** |
| wire.rhombic | 2 | finite | def | 0.980 | 1014:4.88 2026:3.53 3034:2.72 4042:1.85 6058:1.36 **8078:0.90** |
| wire.rhombic | 1 | finite | 1e-8 | 0.980 | 1014:5.53 2022:3.54 3030:2.89 4042:1.96 6058:1.82 **8074:0.98** |
| wire.rhombic | 2 | finite | 1e-8 | 0.980 | 1014:6.21 2026:3.88 3034:3.15 4042:2.30 6058:1.60 8078:1.03 |
| wire.rhombic | 1 | free | def | 0.980 | 1014:7.93 2022:5.71 3030:5.56 4042:3.50 6058:2.40 8074:1.42 |
| wire.rhombic | 2 | free | def | 0.980 | 1014:7.17 2026:7.62 3034:5.96 4042:4.00 6058:2.70 8078:1.71 |
| broadband.lpda | 1 | finite | def | 0.976 | 618:10.58 1222:6.78 1828:4.41 2456:3.36 3686:2.38 4896:1.58 |
| broadband.lpda | 2 | finite | def | 0.976 | 618:8.15 1242:5.98 1848:4.56 2456:3.55 3686:2.36 4916:1.81 |
| broadband.lpda | 1 | finite | 1e-8 | 0.976 | 618:13.98 1222:8.02 1828:5.51 2456:4.01 3686:2.80 4896:2.06 |
| broadband.lpda | 2 | finite | 1e-8 | 0.976 | 618:9.61 1242:6.89 1848:5.29 2456:4.04 3686:2.65 4916:2.02 |
| broadband.lpda | 1 | free | def | 0.976 | 618:15.57 1222:13.27 1828:9.35 2456:8.29 3686:5.66 4896:3.66 |
| broadband.lpda | 2 | free | def | 0.976 | 618:10.13 1242:9.96 1848:9.36 2456:7.57 3686:5.18 4916:4.03 |
| loops.skyloop_lmatch | 1 | finite | def | 0.687 | 93:5.96 183:8.85 270:14.53 357:11.26 |
| loops.skyloop_lmatch | 2 | finite | def | 0.687 | 94:4.46 184:7.77 271:11.61 358:8.93 |
| loops.skyloop_lmatch | 1 | finite | 1e-8 | 0.687 | 93:16.51 183:26.77 270:38.08 357:21.90 |
| loops.skyloop_lmatch | 2 | finite | 1e-8 | 0.687 | 94:11.63 184:17.46 271:14.85 358:11.19 |
| loops.skyloop_lmatch | 1 | free | def | 0.687 | 93:4.21 183:8.72 270:16.42 357:13.98 |
| loops.skyloop_lmatch | 2 | free | def | 0.687 | 94:3.48 184:6.56 271:10.90 358:9.25 |
| verticals.elt_whip | — | — | — | — | **dense both arms — see below, the ratios are not comparisons** |

Three readings:

- **Size is necessary but not sufficient.** rhombic and lpda both fall
  monotonically with n and both sit at far fraction ≈0.98, but at ~4,900 bases
  lpda is still 1.58× and rhombic at 4,042 is 1.59×. The crossover is around
  **6,000–8,000 bases** for this shape of geometry, and lpda's ladder simply
  stops below it.
- **Finite ground helps the H-matrix, and it is not subtle** — rhombic d=1 at
  8,074 is 0.78× on finite ground and 1.42× on free. Finite ground adds work to
  *both* arms, but the dense arm pays it densely. The best case for compression
  is the expensive-kernel case.
- **`aca_tol` is a cost knob here, not an accuracy knob.** Tightening the
  default to 1e-8 moves the winning rhombic cell from 0.78× to 0.98× — it gives
  up the entire win — while relZ improves from 1.8e-06 to 4.9e-07 in a
  comparison whose reference is itself only good to ~1e-6. On this evidence
  #974's default is in the right place and tightening it globally would be paid
  for at every rung.

## `verticals.elt_whip` is refused the H-matrix, and its rows are not comparisons

`HMatrixSolver` declines its own fast path on this deck through
[momwire#972](https://github.com/stevenmburns/momwire/issues/972)'s
fragmentation guard: `_prefers_dense_for_fragmentation()` is True at
**11,758 far blocks for 8,401 bases, ratio 1.40**, and it raises
`HMatrixFragmented`. So the "hmatrix" arm solves **dense**, both arms of the
comparison run the same code, and:

- the ratios (1.03–1.07) measure harness overhead, not compression;
- **relZ is exactly 0.0** in every elt_whip cell — dense against dense;
- the `somm_rank` / `somm_residual` / `somm_fallback` columns for those rows
  are **`_hmatrix_stats` numbers**. That helper builds a *second* solver and
  calls `build_hmatrix()` after the timed solve, which bypasses the
  fragmentation decision. Measured on this box: **34.5 s for the real solve,
  with zero calls to `_zblock_sommerfeld_remainder`, against 268 s for the
  forced build.** No user path reaches the second number.

This is the guard working. It is recorded here because the columns are in the
banked JSONL and would otherwise read as ordinary results.

### Harness note — an ignored warning became a phantom regression

Worth writing down, because the failure was mine and it is reusable.

The ladder's one timeout row (`elt_whip` d=2 finite, >600 s) was initially read
as a momwire scaling regression against #979, and nearly filed as one: a
Sommerfeld fallback quietly filling 4.5 GB. Three things were wrong.

1. **The invisible warning — and it is worse than "suppressed".** The harness
   wraps its solve in `simplefilter("ignore")` for tidy output, and
   `HMatrixFragmented` is the *only* signal that a deck was refused the
   H-matrix. But removing that `ignore` would not have helped: `impedance()`
   is decorated `@_captures_advisories`, which runs the call inside its own
   `catch_warnings(record=True)` and **absorbs every momwire-origin warning by
   module root** into `eng.advisories`, re-emitting only non-momwire ones.
   `HMatrixFragmented` lives in `momwire.hmatrix`, so it is absorbed.

   Measured: `catch_warnings(record=True)` with `simplefilter("always")`
   wrapped around construction *and* the solve records **zero** warnings, while
   the same deck's solver returns `_prefers_dense_for_fragmentation() is True`
   and raises `HMatrixFragmented` when asked directly. An outer warnings
   handler is the wrong instrument for this channel by construction; the
   advisory is only ever readable from `eng.advisories`.
2. **The timeout row lost its own configuration.** `worker_main` sets
   `aca_tol` in the `out.update(...)` *after* the solve, so a row written by
   the parent on timeout carries the parent's context only — and `aca_tol`
   reads `null`, which is also what the default-tol cells record. The timing
   out cell was `aca_tol=1e-8`; the default-tol cell beside it **completed at
   79.3 s**, and a confirmation run reproduced it at 81.7 s. The "79 s versus
   timeout" pair was two different tolerances.
3. **The memory was the dense solve.** Peak 4.93 GB traced / 5.45 GB RSS at
   `somm_rank=187/12,405`, residual 3.73e-05, **fallback False**. No fallback
   fired on any elt_whip cell at either tolerance. 12,405² × 16 B = 2.46 GB is
   the matrix the fragmentation guard deliberately chose, plus factorisation
   workspace.

What the 1e-8 tolerance does buy on this deck is **rank**: at d=1 the global
remainder needs rank **2,064 of 8,401** at 1e-8 against **192** at the default,
inside a build the solve never performs.

Two fixes worth having, neither filed yet:

- A **queryable flag** for the fragmentation refusal, alongside
  `_last_somm_fallback`, so a refusal is legible after the fact instead of only
  as a warning a caller may have suppressed.
- The harness should **record `eng.advisories` — the property, never an outer
  `catch_warnings`** — into every row, and assert the two arms actually differ
  before reporting a ratio. A relZ of identically 0.0 is not a strong pass; it
  is the tell that nothing was compared.

## The #984 residual window

Checked against this ladder for
[momwire#987](https://github.com/stevenmburns/momwire/pull/987)'s move of
`somm_residual_tol` from 1e-2 to 4e-3. Of 101 H-matrix cells, 67 carry a
Sommerfeld residual and 9 fall back. Excluding the three elt_whip cells, whose
health verdict is unfalsifiable for the reason above, **54 are healthy** (no
fallback and relZ < 1e-5):

| band | probe residual |
|---|---|
| healthy, 54 cells | 6.14e-07 … **2.483e-04** (max: lpda 4,896 d=1) |
| the #984 miss | **9.745e-03** (skyloop 93 d=1, relZ 1.26e-03, no fallback) |
| fell back, 9 cells | 6.143e-02, then 1.132 … 1.205 |

**Zero healthy cells in (2.5e-3, 9.74e-3)**, so 4e-3 sits in the gap with 16×
margin below and 2.4× above. Caveat kept deliberately: this band tops out an
order lower than the 1.66e-03 worst-healthy catalog figure cited in
`DEFAULT_SOMM_RESIDUAL_TOL`'s comment, and these two datasets should be read
together rather than one replacing the other.

Two properties of the probe worth not forgetting:

- **Every fallback in 206 cells is `skyloop_lmatch`.** rhombic, lpda and
  elt_whip never trip it at either tolerance.
- **The residual is not monotone in `aca_tol`.** skyloop 271 d=2 goes 1.187 at
  1e-6 to 6.143e-02 at 1e-8 — an order below the other eight fallbacks — and
  still falls back, correctly. The probe *value* is a pivot-path artefact; only
  its *verdict* means anything, so no constant should be calibrated against it.

## Method

- **Warm timing.** Each cell solves once, clears `_solved_cache` (the
  momwire#1235 trap — a second `impedance()` on an unchanged engine is a dict
  lookup, not a solve), then solves again under `tracemalloc`. The reported
  wall is the second solve.
- **Memory by `tracemalloc` peak, not `ru_maxrss`** — a forked child inherits
  its parent's high-water mark.
- **Each cell is a capped subprocess** and a timeout is recorded as a *result*,
  not an exception, so a cell that cannot finish still appears in the ladder.
- **`--aca-tol` overrides the default in place** rather than swapping momwire
  commits, which isolates #974's change exactly; a SHA swap would also carry
  #883/#975/#976.
- A third engine, `hmatrix-nocompress` (`aca_eta=1e-9`), is the check-the-check
  arm: it forces every block near, so it must reproduce dense to round-off.

## What this does not cover

- **Four classes.** rhombic, lpda, elt_whip, skyloop — not the catalog.
- **One box.** Crossover ratios were already shown to differ between machines
  on an identical commit; the *ordering* of classes is the portable part.
- **No rung above ~8,000 bases** except elt_whip, which is refused. The rhombic
  win is measured at the top of its ladder, so how far below 1.0 it goes is
  unmeasured.
- **Free ground has no `aca_tol=1e-8` arm** — that sweep was finite-only.
