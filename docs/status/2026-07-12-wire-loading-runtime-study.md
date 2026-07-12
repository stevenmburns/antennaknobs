# Wire-loading runtime study: is lossy wire cheap enough to default on?

*2026-07-12 · `scripts/bench_wire_loading.py` · i7-8550U (4 physical cores),
OMP_NUM_THREADS=4, OPENBLAS_NUM_THREADS=1 · momwire 0.10.0 (editable
checkout), antennaknobs v0.23.0.*

The question from the lossy-wire arc (momwire#131, issues #316–#318): the
distributed series wire impedance is an additive sparse Gram loading with
no kernel evaluations — if it's ~free, should real wire be the default
instead of opt-in per design?

## Method

For each design in a small→large matrix, time with a **fresh builder +
engine per call** (the web server's per-tick pattern):

- **single** — `impedance()` at the design's default freq (mean of 3),
- **swept** — one `impedance_sweep()` over 41 points, ±3 % around freq,

for `wire_type` = **ideal** (None → PEC, 0.5 mm), **bare** (`18-awg`,
conductivity only), **pvc** (`18-awg-pvc`, conductivity + insulation).
The loading entry points (`_loading_gram` build, `_apply_loading`,
HMatrix zblock's `_loading_block`) are wrapped to report
loading-attributable time and cache behaviour.

## Captured run

```
=== invvee N=21 [BSplineSolver] ===
variant |     single |          loading |      swept |          loading | csr miss
----------------------------------------------------------------------------------
ideal  |      1.7 ms |    0.00 ms  0.1% |       26 ms |    0.00 ms  0.0% |        0
bare   |      2.9 ms |    2.10 ms 72.9% |       21 ms |    2.80 ms 13.1% |        0
pvc    |      2.9 ms |    2.03 ms 68.9% |       19 ms |    2.68 ms 13.8% |        0

=== invvee N=81 [BSplineSolver] ===
ideal  |      7.4 ms |    0.00 ms  0.0% |      300 ms |    0.00 ms  0.0% |        0
bare   |     15.9 ms |   10.42 ms 65.5% |      321 ms |   12.41 ms  3.9% |        0
pvc    |     11.9 ms |    7.33 ms 61.6% |      295 ms |   12.79 ms  4.3% |        0

=== hentenna N=21 [BSplineSolver] ===
ideal  |      8.7 ms |    0.00 ms  0.0% |      284 ms |    0.00 ms  0.0% |        0
bare   |     12.1 ms |    6.91 ms 57.2% |      216 ms |   11.62 ms  5.4% |        0
pvc    |     11.3 ms |    7.61 ms 67.1% |      199 ms |   11.71 ms  5.9% |        0

=== pota_invvee N=21 [BSplineSolver] ===   (re-run after forcing wire_type)
ideal  |      1.7 ms |    0.00 ms  0.1% |       28 ms |    0.00 ms  0.0% |        0
bare   |      2.8 ms |    2.01 ms 72.2% |       22 ms |    2.66 ms 12.2% |        0
pvc    |      2.7 ms |    1.86 ms 69.9% |       15 ms |    2.72 ms 18.6% |        0

=== invvee_coax_station N=21 [BSplineSolver] ===
ideal  |      1.7 ms |    0.00 ms  0.1% |       20 ms |    0.00 ms  0.0% |        0
bare   |      2.7 ms |    1.96 ms 72.3% |       22 ms |    2.77 ms 12.9% |        0
pvc    |      3.4 ms |    2.87 ms 85.1% |       23 ms |    3.03 ms 13.4% |        0

=== rhombic N=21 [BSplineSolver] ===
ideal  |    296.8 ms |    0.00 ms  0.0% |     9271 ms |    0.12 ms  0.0% |        0
bare   |    307.4 ms |   43.89 ms 14.3% |     9478 ms |   62.67 ms  0.7% |        0
pvc    |    336.1 ms |   44.98 ms 13.4% |    10342 ms |   65.54 ms  0.6% |        0

=== rhombic N=81 [BSplineSolver] ===
ideal  |   8509.4 ms |    0.00 ms  0.0% |   268864 ms |    0.12 ms  0.0% |        0
bare   |   7909.5 ms |  146.31 ms  1.8% |   256383 ms |  212.66 ms  0.1% |        0
pvc    |   8004.4 ms |  154.53 ms  1.9% |   256261 ms |  209.75 ms  0.1% |        0

=== bowtiearray2x4 N=21 Arr [ArrayBlockSolver] ===
ideal  |     39.0 ms |    0.00 ms  0.0% |     5621 ms |    0.00 ms  0.0% |        0
bare   |     66.8 ms |   26.27 ms 39.3% |     5595 ms |   95.45 ms  1.7% |       41
pvc    |     71.1 ms |   32.85 ms 46.2% |     5604 ms |   99.65 ms  1.8% |       41

=== bowtiearray2x4 N=21 ACA [HMatrixSolver] ===
ideal  |   2165.0 ms |    0.00 ms  0.0% |    87783 ms |    0.00 ms  0.0% |        0
bare   |   2452.3 ms |  203.18 ms  8.3% |    94396 ms | 5572.43 ms  5.9% |       41
pvc    |   2356.0 ms |  200.88 ms  8.5% |    95279 ms | 5602.45 ms  5.9% |       41
```

(The first pota_invvee run showed loading time in its "ideal" row — the
design's `default_params` carry `wire_type="22-awg-pvc"`, and the script
originally only assigned non-None wire types. The script now forces the
attribute; the table above is the corrected re-run.)

## Findings

1. **Absolute cost is small everywhere.** ~2 ms per single solve on small
   designs, 45–210 ms on the biggest dense solves; per-sweep totals add
   ~3 ms (small) to ~210 ms (rhombic N=81). Against the web UI's
   ~solve+25 ms round trip, the small-design cost is invisible.
2. **The "<1 % of the fill" prediction holds at scale but not at small
   N.** The Gram *build* (`_loading_gram`) is O(N) but pure-Python-loop
   over bases/segments: ~2 ms at N=21, ~10 ms at N=81. The C++ J-block
   fill is so fast on small designs (1.7 ms total) that the loading build
   ~doubles a fresh-engine single solve (share 57–85 %). It is cached per
   solver instance, so sweeps amortise it: 4–14 % at N=21, ≤0.7 % on the
   big dense solves.
3. **Caches behave.** The gram builds once per instance. The per-ω CSR
   cache in `_loading_block` misses exactly once per frequency on the
   fast solvers (41 misses / 41-point sweep) and never within a k — no
   thrash from the H-matrix fill. The HMatrix swept path does pay ~6 % in
   `_loading_block`'s dense `L[I][:,J].toarray()` slicing across the many
   zblock calls per k — the only loading cost worth engineering down if
   it ever matters.
4. **Optional micro-opt, not urgent:** vectorising `_loading_gram`'s
   Python loops (or a C++ hoist) would push the small-solve share under
   10 %. File upstream only if per-tick latency budgets ever tighten.

## Recommendation: (b) — per-design defaults, no global flip

Perf does **not** block default-on. Product does, for now:

- **SinusoidalSolver still rejects the loading kwargs** (NEXT_ARC_PLAN
  item 4). A global default would break every sinusoidal solve and the
  matched-basis PyNEC-parity comparisons. Item 4 is a hard prerequisite
  for any global default.
- **No honest default material exists.** The implied classic wire
  (0.5 mm radius ≈ #10 bare copper) is nobody's antenna wire; picking a
  real one (e.g. 14 AWG) changes the radius too, perturbing every pinned
  test value and published docs number for a modest physical delta.
- **Ideal wire is the oracle baseline.** PEC keeps PyNEC and momwire in
  their ~0.1 Ω cross-engine agreement; that reference is worth keeping
  one click away, not buried under a default.

So: keep the global default ideal (option a's mechanism), and opt
*catalog designs* into real wire one by one where the story benefits
(option b) — `pota_invvee` already ships `22-awg-pvc`; the EFHW arc and
the wire-class designs (longwire, zepp, rhombic) are natural next. Loss
is a design decision, presented per design with the weight readout.

Revisit option (c) (global default with a "pec-ideal" catalog opt-out)
after sinusoidal loading lands, if per-design adoption proves the
numbers stable enough to re-pin tests/docs once.
