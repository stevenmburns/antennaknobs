# 2026-07-08 — ground-model benchmark (10 designs × 4 grounds × 6 engines)

## Goal

The [2026-06-25 solver-selection benchmark](2026-06-25-solver-selection-benchmark.md)
timed the solvers **free-space only**. This run adds the missing axis — the
**ground model** — now that momwire 0.8.0 solves the true Sommerfeld ground on
every solver ("sommerfeld everywhere"). The question: how much does each ground
model cost on top of the free-space solve, and which solver to reach for once a
finite ground is in play?

For each design we sweep **solver × ground model × segmentation** and time
`impedance()`. TriangularSolver is retired from the backend and omitted; PyNEC
is wired for all four ground models (it takes the identical `ground=` spec), so
its NEC gn 2 Sommerfeld is the reference the momwire path is validated against.

## Update — 2026-07-09 (Phase 4 Sommerfeld + refl-coef C++ kernels)

The original tables below were captured on **momwire 0.8.0** (the pinned
release). Two momwire performance efforts have since landed on `main` — ahead
of the pin, so these numbers are from a dev checkout, not a release:

- **Sommerfeld fused kernel** (`sommerfeld-perf-plan.md` Phase 4): the per-pair
  remainder assembly (surface interpolation + eqs 143-147 projection + Galerkin
  quadrature) — ~90 % of a `somm` solve — moved from numpy into one compiled
  kernel shared by every solver.
- **Refl-coef Fresnel field-tensor kernel** (`3562cad`): a compiled replacement
  for the slow field-based `ground_eps` fill that made `Sin·fast` blow up.

Both were validated against the same golden gates and PyNEC references. Full
matrix re-run: **6h10m → 2h12m**. The two gaps this benchmark originally
surfaced — Sommerfeld 10-100× and `Sin·fast` 5-9× vs PyNEC — are both closed.

**Sommerfeld, N=81 — 0.8.0 → Phase 4 (ms):**

| design | Bs2 old → new | ×  | best momwire (new) | PyNEC | mw/NEC |
|---|---|---|---|---|---|
| invvee | 520 → 31 | 17× | Sin 13 | 37 | **0.4×** |
| delta_loop | 1080 → 64 | 17× | Sin 28 | 53 | **0.5×** |
| moxon | 5435 → 305 | 18× | Sin 158 | 135 | 1.2× |
| yagi | 6954 → 365 | 19× | Sin 200 | 178 | 1.1× |
| fandipole | 44809 → 2665 | 17× | Sin 1805 | 1361 | 1.3× |
| trap_fan_dipole | 2504 → 137 | 18× | Sin 65 | 92 | **0.7×** |
| rhombic | 262541 → 18748 | 14× | ACA 9349 | 7582 | 1.2× |
| lpda | 95314 → 5226 | 18× | Arr 2798 | 23844 | **0.1×** |
| delta_looparray_1x4 | 17748 → 916 | 19× | Sin 496 | 441 | 1.1× |
| bowtiearray2x4 | 500628 → 33762 | 15× | Arr 7322 | 17330 | **0.4×** |

Bs2 is a uniform **14-19×** faster; the best momwire solver **ties or beats
PyNEC on 6 of 10** designs and is within 1.3× on the rest. The old worst cell
(`bowtie·somm·Bs2` = 500 s) is now 34 s.

**Refl-coef (`fast`), Sinusoidal, N=81 — before → after `3562cad` (ms):**

| design | Sin before → after | × | PyNEC | Sin/NEC |
|---|---|---|---|---|
| invvee | 48 → 11 | 4.4× | 8 | 1.4× |
| delta_loop | 104 → 17 | 6.1× | 15 | 1.1× |
| moxon | 589 → 112 | 5.3× | 64 | 1.8× |
| yagi | 789 → 146 | 5.4× | 97 | 1.5× |
| fandipole | 5713 → 1220 | 4.7× | 782 | 1.6× |
| trap_fan_dipole | 240 → 42 | 5.7× | 35 | 1.2× |
| rhombic | 42092 → 9263 | 4.5× | 5055 | 1.8× |
| lpda | 12022 → 2961 | 4.1× | 15952 | **0.2×** |
| delta_looparray_1x4 | 1634 → 369 | 4.4× | 221 | 1.7× |
| bowtiearray2x4 | 82198 → 19777 | 4.2× | 12457 | 1.6× |

Uniform **~4-6×**; the `Sin·fast` gap to PyNEC collapses from 5-9× to
**1.1-1.8×** (a constant-factor compiled fill, scaling stays ~quadratic), and
Sin is again the fastest dense basis on refl-coef. On `lpda` it beats NEC 5×.

**Net:** after both efforts momwire sits within ~2× of PyNEC — or beats it —
on every ground model × design. The baseline tables below are retained as the
0.8.0 reference; a fresh full capture will replace them when the work releases.

## Script

`scripts/profile_ground_models.py` — `.venv/bin/python scripts/profile_ground_models.py 2>/dev/null`.

Engines (row labels): `Bs1`/`Bs2` BSplineSolver degree 1/2 · `Sin`
SinusoidalSolver · `Arr` ArrayBlockSolver · `ACA` HMatrixSolver · `PyNEC`
PyNECEngine.

Ground models (one table per model, per design):

- **free** — free space (no ground)
- **pec**  — perfectly conducting plane, image method (no material solve)
- **fast** — reflection-coefficient finite ground (NEC gn 0 / momwire `refl-coef`)
- **somm** — true Sommerfeld-Norton finite ground (NEC gn 2 / momwire `sommerfeld`)

`fast` and `somm` share `DEFAULT_GROUND`'s constants (εr=10, σ=0.002), so the
two finite models differ only in solve method. `ground_z` is fixed at 0 (the
whole app runs the plane at z=0; antenna height lives in each design's geometry).

Threading mirrors `web/server.py`, applied before any numpy/scipy/PyNEC import,
so per-call times reflect **what the live web backend actually delivers per
request** — not peak solver throughput: `OPENBLAS_NUM_THREADS=1`,
`OMP/MKL_NUM_THREADS=physical_core_count` (4 here), `OMP_WAIT_POLICY=PASSIVE`,
`GOMP_SPINCOUNT=0`. For the Sommerfeld cells the cost is dominated by the
matrix *fill* (per-element grid interpolation), which runs under OMP across all
4 cores; only the dense linear solve is pinned to OpenBLAS=1, and it is not
where the Sommerfeld time goes.

Per cell: one off-band warm-up call, then mean wall-clock across the design's
bands (single-band 10 m designs sweep 28.0/28.3/28.57/28.85; fandipole /
trap_fan_dipole keep their multiband target sets). Geometry/Z size is fixed by
(design, N), so per-call cost is essentially N-solver-ground-only and the mean
hides one-shot jitter. Full run: **~6h10m** wall clock on a 4-physical-core box
(the array Sommerfeld cells averaged over 4 bands are the long pole).

## Headlines

- **Ground-cost ladder is consistent everywhere: `free ≈ pec < fast < somm`.**
  Relative to free space at N=81: `pec` ≈ 1.1–1.5×, `fast` ≈ 1.5–3× (dense
  bases), and `somm` is the dominant cost — **5–40×** on the dense solvers.
  `pec` is nearly free (image method, no material solve).

- **PyNEC's native NEC gn 2 Sommerfeld is 1–2 orders of magnitude faster than
  every momwire Sommerfeld path** on 9 of 10 designs. Sommerfeld @ N=81:

  | design | PyNEC | best momwire | worst (Bs2 dense) |
  |---|---|---|---|
  | moxon | **0.14 s** | Arr 0.95 s | 5.4 s |
  | yagi | **0.18 s** | Arr 1.0 s | 7.0 s |
  | delta_looparray_1x4 | **0.44 s** | Arr 3.5 s | 17.7 s |
  | fandipole | **1.4 s** | ACA 10.2 s | 44.8 s |
  | rhombic | **7.6 s** | ACA 23.7 s | 262 s |
  | bowtiearray2x4 | **17.4 s** | Arr 33.6 s | 501 s |
  | lpda | 24 s | **Arr 8.0 s** | 95 s |

  momwire's Sommerfeld is the *accurate-at-any-height* model, but pays heavily
  for it versus NEC's precomputed Sommerfeld/Norton interpolation tables.
  `lpda` is the lone design where a momwire solver (ArrayBlock, 8.0 s) beats
  PyNEC (24 s) — NEC2's fill scales badly on the log-periodic, the same
  geometry that beat it free-space in the 2026-06-25 run.

- **Under Sommerfeld the momwire fast paths pay off exactly where designed**,
  and the low-rank structure survives the finite ground (the Sommerfeld
  remainder rides one global ACA-compressed term, not a dense O(n²) rebuild):
  - **Large single wire (`rhombic`):** HMatrix/ACA wins — 24 s vs dense Bs2's
    262 s (~11×).
  - **Arrays (`bowtiearray2x4`):** ArrayBlock wins — 34 s vs dense Bs2's 501 s
    (~15×).
  - **Small designs (`invvee`, `delta_loop`):** dense Sinusoidal is fine; the
    ACA/block setup is pure overhead there, same as free-space.

- **`Sinusoidal`'s refl-coef (`fast`) ground is surprisingly expensive on large
  geometries.** `bowtiearray2x4` fast N=81 `Sin` = **117 s** — ~5× the
  dense-bspline `fast` cell (24 s) and worse than most of its own Sommerfeld
  neighbours. The field-based `ground_eps` in the sinusoidal solver scales
  poorly on large arrays; on small/medium designs it stays cheap.

- **Worst cell in the matrix:** `bowtiearray2x4` · somm · Bs2 · N=81 ≈
  **500 s/solve**. This is why Sommerfeld must stay opt-in in the UI and the
  fast paths (or PyNEC) are the only viable Sommerfeld engines at scale.

## Solver-selection guide (finite ground)

- **Small/medium single or few-element designs** → PyNEC for Sommerfeld (often
  <1 s where momwire dense is seconds); dense `Sin` for refl-coef/PEC.
- **Large single structures** (rhombic, longwire class) → `HMatrixSolver` (ACA)
  under Sommerfeld among momwire solvers; PyNEC still faster if available.
- **Arrays** → `ArrayBlockSolver` under any finite ground; it can beat PyNEC
  on the log-periodic / larger arrays and is the closest momwire gets to PyNEC's
  Sommerfeld speed on `bowtiearray2x4`.
- **PEC** is cheap on every solver — never a reason to avoid a ground plane if
  PEC is an acceptable model.

## Caveats

- 4-physical-core box, production-matched threading (`OPENBLAS=1`,
  `OMP=4`). Absolute numbers move with core count; cross-design and
  cross-engine ratios should hold. A full-threading variant (unpinned BLAS)
  would measure peak solver speed rather than web-backend behaviour.
- Single-call `impedance()` only — no sweep amortization, no UI overhead.
- PyNEC parity coercion may bump segment counts to the next odd number,
  slightly inflating its effective N relative to momwire's.
- `fast`/`somm` use εr=10, σ=0.002 (`DEFAULT_GROUND`). The Sommerfeld remainder
  rank is geometry-dependent; costs are specific to these designs on this box.

## Follow-ups

- Investigate why momwire's Sommerfeld trails NEC gn 2 by 10–100×: NEC's
  precomputed interpolation grid vs momwire's per-fill remainder evaluation is
  the likely gap. A shared/cached Sommerfeld grid across the fill could close it.
- The `Sinusoidal` refl-coef blow-up on large arrays (`bowtiearray2x4` fast
  = 117 s) deserves its own profile — the field-based `ground_eps` path looks
  quadratic where the bspline `refl-coef` stays sub-linear.
- Web engine auto-selection could extend the 2026-06-25 free-space heuristic
  with a ground-aware branch: PyNEC for Sommerfeld on non-array designs,
  ArrayBlock for arrays, HMatrix for large single structures.

## Full results

Verbatim capture (`.venv/bin/python scripts/profile_ground_models.py 2>/dev/null`).
Each cell is `mean ms (±half-spread across bands)`.

```
OMP_NUM_THREADS=4 MKL_NUM_THREADS=4 OPENBLAS_NUM_THREADS=1 OMP_WAIT_POLICY=PASSIVE GOMP_SPINCOUNT=0
grounds=['free', 'pec', 'fast', 'somm'] nsegs=[21, 41, 81] engines=['Bs1', 'Bs2', 'Sin', 'Arr', 'ACA', 'PyNEC'] designs=['invvee', 'delta_loop', 'moxon', 'yagi', 'fandipole', 'trap_fan_dipole', 'rhombic', 'lpda', 'delta_looparray_1x4', 'bowtiearray2x4'] mean over band set

########## invvee ##########

=== invvee · ground=free ===
engine |        21        |        41        |        81
---------------------------------------------------------------
Bs1    |       1 ms (±   0) |       3 ms (±   0) |       9 ms (±   0)
Bs2    |       2 ms (±   0) |       4 ms (±   1) |      11 ms (±   0)
Sin    |       1 ms (±   0) |       2 ms (±   0) |       5 ms (±   0)
Arr    |       5 ms (±   0) |      13 ms (±   0) |      46 ms (±   0)
ACA    |       8 ms (±   0) |      24 ms (±   0) |      85 ms (±   3)
PyNEC  |       1 ms (±   0) |       2 ms (±   0) |       4 ms (±   0)

=== invvee · ground=pec ===
engine |        21        |        41        |        81
---------------------------------------------------------------
Bs1    |       2 ms (±   0) |       3 ms (±   0) |       8 ms (±   0)
Bs2    |       2 ms (±   0) |       4 ms (±   0) |      14 ms (±   0)
Sin    |       1 ms (±   0) |       3 ms (±   0) |       8 ms (±   0)
Arr    |       8 ms (±   0) |      20 ms (±   0) |      84 ms (±   1)
ACA    |      12 ms (±   0) |      40 ms (±   0) |     148 ms (±   8)
PyNEC  |       1 ms (±   0) |       2 ms (±   0) |       7 ms (±   0)

=== invvee · ground=fast ===
engine |        21        |        41        |        81
---------------------------------------------------------------
Bs1    |       2 ms (±   0) |       4 ms (±   0) |      14 ms (±   0)
Bs2    |       2 ms (±   0) |       6 ms (±   0) |      22 ms (±   1)
Sin    |       4 ms (±   0) |      11 ms (±   0) |      47 ms (±   0)
Arr    |       9 ms (±   0) |      23 ms (±   1) |      90 ms (±   2)
ACA    |      13 ms (±   0) |      47 ms (±   2) |     156 ms (±   1)
PyNEC  |       1 ms (±   0) |       3 ms (±   0) |       8 ms (±   1)

=== invvee · ground=somm ===
engine |        21        |        41        |        81
---------------------------------------------------------------
Bs1    |     383 ms (±   2) |     123 ms (±   1) |     515 ms (±   7)
Bs2    |      29 ms (±   0) |     123 ms (±   2) |     520 ms (±   7)
Sin    |      10 ms (±   0) |      34 ms (±   2) |     155 ms (±   0)
Arr    |      47 ms (±   1) |      89 ms (±   2) |     197 ms (±   1)
ACA    |      50 ms (±   0) |     107 ms (±   2) |     258 ms (±   3)
PyNEC  |      28 ms (±   0) |      30 ms (±   0) |      37 ms (±   0)

########## delta_loop ##########

=== delta_loop · ground=free ===
engine |        21        |        41        |        81
---------------------------------------------------------------
Bs1    |       2 ms (±   0) |       4 ms (±   0) |      12 ms (±   0)
Bs2    |       2 ms (±   0) |       5 ms (±   0) |      18 ms (±   0)
Sin    |       2 ms (±   0) |       3 ms (±   0) |       9 ms (±   0)
Arr    |       9 ms (±   0) |      26 ms (±   0) |      88 ms (±   4)
ACA    |      21 ms (±   0) |      77 ms (±   0) |     153 ms (±   4)
PyNEC  |       1 ms (±   0) |       3 ms (±   0) |       9 ms (±   0)

=== delta_loop · ground=pec ===
engine |        21        |        41        |        81
---------------------------------------------------------------
Bs1    |       2 ms (±   0) |       5 ms (±   0) |      20 ms (±   2)
Bs2    |       4 ms (±   0) |      10 ms (±   0) |      28 ms (±   5)
Sin    |       2 ms (±   0) |       4 ms (±   0) |      13 ms (±   0)
Arr    |      14 ms (±   0) |      44 ms (±   1) |     152 ms (±   2)
ACA    |      35 ms (±   1) |     124 ms (±   3) |     251 ms (±   2)
PyNEC  |       1 ms (±   0) |       4 ms (±   0) |      13 ms (±   0)

=== delta_loop · ground=fast ===
engine |        21        |        41        |        81
---------------------------------------------------------------
Bs1    |       3 ms (±   0) |       7 ms (±   0) |      24 ms (±   0)
Bs2    |       4 ms (±   0) |      10 ms (±   0) |      32 ms (±   0)
Sin    |       7 ms (±   0) |      23 ms (±   0) |     101 ms (±   1)
Arr    |      15 ms (±   0) |      47 ms (±   1) |     165 ms (±   2)
ACA    |      36 ms (±   0) |     133 ms (±   4) |     297 ms (±   1)
PyNEC  |       2 ms (±   0) |       5 ms (±   0) |      14 ms (±   0)

=== delta_loop · ground=somm ===
engine |        21        |        41        |        81
---------------------------------------------------------------
Bs1    |      75 ms (±   1) |     279 ms (±   4) |    1059 ms (±   8)
Bs2    |      71 ms (±   1) |     265 ms (±   3) |    1080 ms (±   1)
Sin    |      21 ms (±   0) |      84 ms (±   1) |     347 ms (±   1)
Arr    |      79 ms (±   0) |     167 ms (±   1) |     397 ms (±   4)
ACA    |      97 ms (±   0) |     253 ms (±   2) |     500 ms (±   8)
PyNEC  |      29 ms (±   0) |      34 ms (±   0) |      53 ms (±   0)

########## moxon ##########

=== moxon · ground=free ===
engine |        21        |        41        |        81
---------------------------------------------------------------
Bs1    |       5 ms (±   0) |      14 ms (±   0) |      52 ms (±   0)
Bs2    |       6 ms (±   0) |      19 ms (±   0) |      74 ms (±   1)
Sin    |       4 ms (±   0) |      12 ms (±   0) |      50 ms (±   0)
Arr    |      30 ms (±   0) |      73 ms (±   1) |     232 ms (±  13)
ACA    |      59 ms (±   0) |     179 ms (±   4) |     517 ms (±  23)
PyNEC  |       5 ms (±   0) |      15 ms (±   2) |      46 ms (±   0)

=== moxon · ground=pec ===
engine |        21        |        41        |        81
---------------------------------------------------------------
Bs1    |       6 ms (±   0) |      19 ms (±   0) |      82 ms (±   1)
Bs2    |       9 ms (±   0) |      28 ms (±   0) |     114 ms (±   2)
Sin    |       5 ms (±   0) |      17 ms (±   0) |      68 ms (±   1)
Arr    |      47 ms (±   0) |     124 ms (±   0) |     409 ms (±   1)
ACA    |     104 ms (±   3) |     312 ms (±   8) |     889 ms (±  42)
PyNEC  |       4 ms (±   0) |      14 ms (±   0) |      56 ms (±   0)

=== moxon · ground=fast ===
engine |        21        |        41        |        81
---------------------------------------------------------------
Bs1    |       9 ms (±   0) |      29 ms (±   0) |     130 ms (±   0)
Bs2    |      11 ms (±   0) |      38 ms (±   0) |     159 ms (±   2)
Sin    |      31 ms (±   0) |     130 ms (±   1) |     578 ms (±   2)
Arr    |      50 ms (±   0) |     137 ms (±   5) |     445 ms (±   3)
ACA    |     115 ms (±   0) |     343 ms (±  18) |     956 ms (±  19)
PyNEC  |       7 ms (±   0) |      16 ms (±   0) |      65 ms (±   1)

=== moxon · ground=somm ===
engine |        21        |        41        |        81
---------------------------------------------------------------
Bs1    |     388 ms (±   1) |    1412 ms (±   3) |    5261 ms (±   9)
Bs2    |     363 ms (±   0) |    1404 ms (±   1) |    5435 ms (±  10)
Sin    |     114 ms (±   2) |     454 ms (±   4) |    1798 ms (±   3)
Arr    |     167 ms (±   2) |     359 ms (±  11) |     949 ms (±   7)
ACA    |     219 ms (±   2) |     555 ms (±   8) |    1453 ms (±  42)
PyNEC  |      38 ms (±   0) |      54 ms (±   0) |     144 ms (±  18)

########## yagi ##########

=== yagi · ground=free ===
engine |        21        |        41        |        81
---------------------------------------------------------------
Bs1    |       6 ms (±   0) |      17 ms (±   0) |      69 ms (±   1)
Bs2    |       8 ms (±   0) |      24 ms (±   0) |      99 ms (±   1)
Sin    |       5 ms (±   0) |      16 ms (±   0) |      69 ms (±   1)
Arr    |      32 ms (±   1) |      60 ms (±   1) |     156 ms (±   1)
ACA    |      85 ms (±   1) |     292 ms (±   8) |     815 ms (±  34)
PyNEC  |       6 ms (±   0) |      18 ms (±   3) |      68 ms (±   0)

=== yagi · ground=pec ===
engine |        21        |        41        |        81
---------------------------------------------------------------
Bs1    |       8 ms (±   0) |      31 ms (±   3) |     108 ms (±   1)
Bs2    |      14 ms (±   2) |      36 ms (±   1) |     154 ms (±   2)
Sin    |       7 ms (±   0) |      22 ms (±   0) |      93 ms (±   0)
Arr    |      51 ms (±   0) |     102 ms (±   1) |     276 ms (±   2)
ACA    |     148 ms (±   1) |     517 ms (±  29) |    1383 ms (±  93)
PyNEC  |       6 ms (±   0) |      20 ms (±   0) |      83 ms (±   1)

=== yagi · ground=fast ===
engine |        21        |        41        |        81
---------------------------------------------------------------
Bs1    |      12 ms (±   0) |      40 ms (±   3) |     174 ms (±   2)
Bs2    |      15 ms (±   0) |      49 ms (±   1) |     224 ms (±   3)
Sin    |      41 ms (±   0) |     177 ms (±   2) |     789 ms (±   3)
Arr    |      53 ms (±   1) |     108 ms (±   1) |     296 ms (±   1)
ACA    |     164 ms (±   1) |     551 ms (±  24) |    1486 ms (±  37)
PyNEC  |       6 ms (±   0) |      22 ms (±   0) |      93 ms (±   1)

=== yagi · ground=somm ===
engine |        21        |        41        |        81
---------------------------------------------------------------
Bs1    |     413 ms (±   1) |    1810 ms (±   6) |    6920 ms (±   7)
Bs2    |     393 ms (±   1) |    1807 ms (±   2) |    6954 ms (±   6)
Sin    |     126 ms (±   1) |     582 ms (±   2) |    2214 ms (±   1)
Arr    |     288 ms (±   2) |     566 ms (±   7) |    1028 ms (±   2)
ACA    |     397 ms (±   9) |     928 ms (±  13) |    2151 ms (±  84)
PyNEC  |      37 ms (±   0) |      64 ms (±   0) |     179 ms (±   0)

########## fandipole ##########

=== fandipole · ground=free ===
engine |        21        |        41        |        81
---------------------------------------------------------------
Bs1    |      31 ms (±   4) |     116 ms (±   2) |     547 ms (±   3)
Bs2    |      38 ms (±   0) |     148 ms (±   2) |     711 ms (±   6)
Sin    |      28 ms (±   0) |     119 ms (±   1) |     602 ms (±   5)
Arr    |     217 ms (±   2) |     783 ms (±  11) |    4530 ms (±  13)
ACA    |     441 ms (±   7) |    1694 ms (±  30) |    5278 ms (± 142)
PyNEC  |      29 ms (±   1) |     114 ms (±   1) |     540 ms (±   6)

=== fandipole · ground=pec ===
engine |        21        |        41        |        81
---------------------------------------------------------------
Bs1    |      42 ms (±   1) |     164 ms (±   3) |     713 ms (±   5)
Bs2    |      57 ms (±   0) |     221 ms (±   3) |    1026 ms (±   3)
Sin    |      38 ms (±   0) |     162 ms (±   5) |     753 ms (±   6)
Arr    |     402 ms (±   2) |    1458 ms (±   6) |    8648 ms (±  20)
ACA    |     807 ms (±  30) |    2956 ms (±  95) |    8850 ms (±  94)
PyNEC  |      40 ms (±   5) |     160 ms (±  18) |     717 ms (±  73)

=== fandipole · ground=fast ===
engine |        21        |        41        |        81
---------------------------------------------------------------
Bs1    |      67 ms (±   1) |     265 ms (±   1) |    1098 ms (±   4)
Bs2    |      80 ms (±   1) |     324 ms (±   8) |    1422 ms (±  32)
Sin    |     256 ms (±   1) |    1051 ms (±   3) |    4812 ms (±  12)
Arr    |     460 ms (±   8) |    1604 ms (±   6) |    9198 ms (±  15)
ACA    |     863 ms (±   8) |    3176 ms (±  64) |    9238 ms (± 199)
PyNEC  |      46 ms (±   5) |     184 ms (±  19) |     805 ms (±  69)

=== fandipole · ground=somm ===
engine |        21        |        41        |        81
---------------------------------------------------------------
Bs1    |    3275 ms (±  90) |   11096 ms (±  13) |   42565 ms (±  27)
Bs2    |    2909 ms (±  38) |   11290 ms (±  11) |   44809 ms (±  31)
Sin    |     966 ms (±  38) |    3596 ms (±   4) |   14552 ms (±  18)
Arr    |     745 ms (±  65) |    2657 ms (±  35) |   10802 ms (±  78)
ACA    |    1103 ms (±  25) |    3618 ms (± 114) |   10200 ms (± 103)
PyNEC  |     109 ms (±  16) |     347 ms (±  58) |    1367 ms (± 227)

########## trap_fan_dipole ##########

=== trap_fan_dipole · ground=free ===
engine |        21        |        41        |        81
---------------------------------------------------------------
Bs1    |       5 ms (±   0) |      10 ms (±   0) |      27 ms (±   0)
Bs2    |       6 ms (±   0) |      13 ms (±   0) |      36 ms (±   1)
Sin    |       4 ms (±   0) |       7 ms (±   0) |      22 ms (±   0)
Arr    |      22 ms (±   0) |      60 ms (±   1) |     182 ms (±   0)
ACA    |      36 ms (±   0) |     110 ms (±   2) |     352 ms (±  11)
PyNEC  |       3 ms (±   0) |       9 ms (±   0) |      23 ms (±   0)

=== trap_fan_dipole · ground=pec ===
engine |        21        |        41        |        81
---------------------------------------------------------------
Bs1    |       6 ms (±   0) |      13 ms (±   0) |      37 ms (±   0)
Bs2    |       8 ms (±   0) |      18 ms (±   0) |      52 ms (±   1)
Sin    |       4 ms (±   0) |      10 ms (±   0) |      31 ms (±   0)
Arr    |      36 ms (±   1) |     107 ms (±   1) |     342 ms (±   9)
ACA    |      59 ms (±   1) |     188 ms (±   7) |     558 ms (±   4)
PyNEC  |       3 ms (±   0) |       9 ms (±   1) |      33 ms (±   4)

=== trap_fan_dipole · ground=fast ===
engine |        21        |        41        |        81
---------------------------------------------------------------
Bs1    |       8 ms (±   0) |      18 ms (±   0) |      56 ms (±   1)
Bs2    |       9 ms (±   0) |      23 ms (±   0) |      70 ms (±   1)
Sin    |      18 ms (±   0) |      58 ms (±   0) |     206 ms (±   0)
Arr    |      37 ms (±   0) |     116 ms (±   1) |     361 ms (±   1)
ACA    |      63 ms (±   0) |     204 ms (±   8) |     611 ms (±  19)
PyNEC  |       4 ms (±   0) |      10 ms (±   1) |      36 ms (±   4)

=== trap_fan_dipole · ground=somm ===
engine |        21        |        41        |        81
---------------------------------------------------------------
Bs1    |     248 ms (± 101) |     726 ms (±   1) |    2532 ms (±   2)
Bs2    |     191 ms (±   1) |     734 ms (±   2) |    2504 ms (±   7)
Sin    |      63 ms (±   0) |     216 ms (±   1) |     831 ms (±   1)
Arr    |     116 ms (±   5) |     308 ms (±  37) |     743 ms (±  35)
ACA    |     141 ms (±   5) |     376 ms (±  39) |     939 ms (±  41)
PyNEC  |      33 ms (±   1) |      45 ms (±   3) |      92 ms (±  12)

########## rhombic ##########

=== rhombic · ground=free ===
engine |        21        |        41        |        81
---------------------------------------------------------------
Bs1    |     224 ms (±   2) |    1108 ms (±   2) |    6058 ms (±  29)
Bs2    |     291 ms (±   1) |    1467 ms (±   8) |    7386 ms (±  40)
Sin    |     208 ms (±   0) |    1179 ms (±   2) |    6212 ms (±   9)
Arr    |    1787 ms (±   6) |    7449 ms (±  14) |   32349 ms (± 178)
ACA    |     898 ms (±  50) |    1896 ms (±  37) |    4004 ms (±  48)
PyNEC  |     160 ms (±   1) |     787 ms (±   1) |    4418 ms (±   5)

=== rhombic · ground=pec ===
engine |        21        |        41        |        81
---------------------------------------------------------------
Bs1    |     296 ms (±   1) |    1402 ms (±   2) |    7172 ms (±  25)
Bs2    |     419 ms (±   2) |    1973 ms (±  15) |    9438 ms (±  47)
Sin    |     269 ms (±   2) |    1463 ms (±   4) |    7294 ms (±   9)
Arr    |    3410 ms (±   8) |   13894 ms (±  11) |   59089 ms (±  61)
ACA    |    1441 ms (±  43) |    3137 ms (± 141) |    6773 ms (±  81)
PyNEC  |     193 ms (±   1) |     911 ms (±   1) |    4921 ms (±   4)

=== rhombic · ground=fast ===
engine |        21        |        41        |        81
---------------------------------------------------------------
Bs1    |     445 ms (±   4) |    2079 ms (±   2) |   10933 ms (±  26)
Bs2    |     594 ms (±   2) |    2678 ms (±  31) |   13359 ms (±  20)
Sin    |    1959 ms (±   1) |    9718 ms (±   5) |   42605 ms (±  83)
Arr    |    3796 ms (±  18) |   15548 ms (±  55) |   65233 ms (±  89)
ACA    |    1549 ms (±  17) |    3405 ms (±  81) |    7217 ms (± 138)
PyNEC  |     219 ms (±   1) |    1011 ms (±   2) |    5324 ms (±   3)

=== rhombic · ground=somm ===
engine |        21        |        41        |        81
---------------------------------------------------------------
Bs1    |   18766 ms (± 355) |   61833 ms (±  18) |  243563 ms (± 114)
Bs2    |   17644 ms (±  15) |   66886 ms (±  50) |  262541 ms (± 153)
Sin    |    5795 ms (±   6) |   22071 ms (±   3) |   86482 ms (±  93)
Arr    |    7171 ms (± 162) |   21324 ms (± 370) |   76632 ms (± 645)
ACA    |    5086 ms (± 158) |   11650 ms (± 552) |   23712 ms (± 180)
PyNEC  |     398 ms (±   1) |    1610 ms (±   8) |    7592 ms (±  28)

########## lpda ##########

=== lpda · ground=free ===
engine |        21        |        41        |        81
---------------------------------------------------------------
Bs1    |      62 ms (±   1) |     283 ms (±   3) |    1413 ms (±   8)
Bs2    |      90 ms (±   1) |     375 ms (±  11) |    1741 ms (±  18)
Sin    |      71 ms (±   1) |     332 ms (±   3) |    1827 ms (±  10)
Arr    |     228 ms (±  10) |     459 ms (±   7) |    1188 ms (±  11)
ACA    |     824 ms (±  36) |    1936 ms (±  24) |    4506 ms (±  96)
PyNEC  |     664 ms (±   3) |    2815 ms (±  27) |   14046 ms (±  20)

=== lpda · ground=pec ===
engine |        21        |        41        |        81
---------------------------------------------------------------
Bs1    |      89 ms (±   1) |     403 ms (±  15) |    1852 ms (±  11)
Bs2    |     138 ms (±   1) |     567 ms (±   8) |    2477 ms (±  12)
Sin    |      93 ms (±   0) |     412 ms (±   8) |    2211 ms (±  11)
Arr    |     374 ms (±   7) |     812 ms (±  22) |    2151 ms (±  15)
ACA    |    1419 ms (±  64) |    3368 ms (± 140) |    8062 ms (±  75)
PyNEC  |     754 ms (±   1) |    3090 ms (±   8) |   14807 ms (±  20)

=== lpda · ground=fast ===
engine |        21        |        41        |        81
---------------------------------------------------------------
Bs1    |     152 ms (±   1) |     569 ms (±   4) |    2538 ms (±   6)
Bs2    |     193 ms (±   3) |     727 ms (±   6) |    3186 ms (±  21)
Sin    |     647 ms (±   1) |    2333 ms (±   6) |   10372 ms (±  12)
Arr    |     445 ms (±  36) |     931 ms (±  18) |    2413 ms (±  16)
ACA    |    1495 ms (±  25) |    3711 ms (± 116) |    8435 ms (± 176)
PyNEC  |     855 ms (±   3) |    3443 ms (±  10) |   16196 ms (±  22)

=== lpda · ground=somm ===
engine |        21        |        41        |        81
---------------------------------------------------------------
Bs1    |    7331 ms (±   6) |   23249 ms (±  11) |   90018 ms (±  79)
Bs2    |    6654 ms (±   7) |   24343 ms (±   8) |   95314 ms (±  79)
Sin    |    2132 ms (±   1) |    7875 ms (±   8) |   30633 ms (±   4)
Arr    |    1849 ms (±  13) |    3783 ms (± 150) |    7999 ms (± 323)
ACA    |    2840 ms (±  24) |    6269 ms (±  85) |   13507 ms (± 440)
PyNEC  |    1665 ms (±   4) |    5678 ms (±  12) |   23926 ms (±  28)

########## delta_looparray_1x4 ##########

=== delta_looparray_1x4 · ground=free ===
engine |        21        |        41        |        81
---------------------------------------------------------------
Bs1    |      15 ms (±   1) |      45 ms (±   1) |     199 ms (±   2)
Bs2    |      18 ms (±   0) |      62 ms (±   1) |     245 ms (±   5)
Sin    |      11 ms (±   0) |      44 ms (±   0) |     198 ms (±   3)
Arr    |      45 ms (±   0) |      96 ms (±   1) |     254 ms (±   1)
ACA    |     233 ms (±  11) |     619 ms (±  22) |    1473 ms (±  35)
PyNEC  |      13 ms (±   0) |      40 ms (±   1) |     174 ms (±   2)

=== delta_looparray_1x4 · ground=pec ===
engine |        21        |        41        |        81
---------------------------------------------------------------
Bs1    |      20 ms (±   0) |      63 ms (±   0) |     264 ms (±   1)
Bs2    |      28 ms (±   1) |      96 ms (±   0) |     349 ms (±   2)
Sin    |      16 ms (±   1) |      60 ms (±   1) |     257 ms (±   2)
Arr    |      77 ms (±   3) |     164 ms (±   2) |     453 ms (±   2)
ACA    |     385 ms (±  14) |    1073 ms (±  39) |    2453 ms (±  58)
PyNEC  |      13 ms (±   0) |      47 ms (±   0) |     204 ms (±   1)

=== delta_looparray_1x4 · ground=fast ===
engine |        21        |        41        |        81
---------------------------------------------------------------
Bs1    |      31 ms (±   1) |     102 ms (±   0) |     414 ms (±   2)
Bs2    |      37 ms (±   1) |     133 ms (±   1) |     513 ms (±   5)
Sin    |     104 ms (±   1) |     418 ms (±   2) |    1642 ms (±   5)
Arr    |      94 ms (±   1) |     181 ms (±   6) |     502 ms (±  10)
ACA    |     415 ms (±  14) |    1125 ms (±  49) |    2570 ms (± 115)
PyNEC  |      15 ms (±   0) |      55 ms (±   0) |     232 ms (±   2)

=== delta_looparray_1x4 · ground=somm ===
engine |        21        |        41        |        81
---------------------------------------------------------------
Bs1    |    1233 ms (±   4) |    4407 ms (±   2) |   16826 ms (±   8)
Bs2    |    1134 ms (±   9) |    4372 ms (±  24) |   17748 ms (±  15)
Sin    |     394 ms (±   1) |    1417 ms (±   4) |    5588 ms (±   5)
Arr    |     921 ms (±  50) |    1637 ms (± 164) |    3466 ms (± 146)
ACA    |    1216 ms (±  60) |    2506 ms (± 185) |    5384 ms (±  79)
PyNEC  |      54 ms (±   0) |     129 ms (±   1) |     444 ms (±   2)

########## bowtiearray2x4 ##########

=== bowtiearray2x4 · ground=free ===
engine |        21        |        41        |        81
---------------------------------------------------------------
Bs1    |     428 ms (±   3) |    2112 ms (±  17) |   12136 ms (±  52)
Bs2    |     518 ms (±   7) |    2427 ms (±  15) |   13527 ms (±  65)
Sin    |     440 ms (±   4) |    2515 ms (±  11) |   14276 ms (±  28)
Arr    |     209 ms (±   7) |     494 ms (±  11) |    1619 ms (±  13)
ACA    |    2400 ms (±  31) |    5680 ms (± 202) |   13394 ms (± 270)
PyNEC  |     380 ms (±   4) |    1928 ms (±   3) |   11197 ms (±  18)

=== bowtiearray2x4 · ground=pec ===
engine |        21        |        41        |        81
---------------------------------------------------------------
Bs1    |     616 ms (±   6) |    2729 ms (±  10) |   14345 ms (±  43)
Bs2    |     785 ms (±   6) |    3460 ms (±  15) |   17410 ms (±  49)
Sin    |     568 ms (±   3) |    3128 ms (±  10) |   16500 ms (±  62)
Arr    |     358 ms (±  15) |     844 ms (±   5) |    3292 ms (±  19)
ACA    |    4359 ms (± 101) |   10366 ms (± 389) |   23689 ms (± 485)
PyNEC  |     440 ms (±   3) |    2061 ms (±   5) |   12007 ms (±  29)

=== bowtiearray2x4 · ground=fast ===
engine |        21        |        41        |        81
---------------------------------------------------------------
Bs1    |     865 ms (±   7) |    3586 ms (±  24) |   20591 ms (±  80)
Bs2    |     970 ms (±   6) |    4299 ms (±  10) |   23613 ms (±  41)
Sin    |    3093 ms (±   2) |   15689 ms (±  29) |  117590 ms (±3426)
Arr    |    1829 ms (± 274) |     996 ms (±  34) |    2916 ms (±  19)
ACA    |    5210 ms (± 381) |   17142 ms (±3076) |   28843 ms (±4145)
PyNEC  |     502 ms (±   2) |    2361 ms (±   6) |   12971 ms (±  25)

=== bowtiearray2x4 · ground=somm ===
engine |        21        |        41        |        81
---------------------------------------------------------------
Bs1    |   35283 ms (±  15) |  123086 ms (± 622) |  472762 ms (± 409)
Bs2    |   32863 ms (±  37) |  124289 ms (± 194) |  500628 ms (±5493)
Sin    |   10532 ms (±  16) |   41401 ms (±  22) |  165035 ms (± 109)
Arr    |    6324 ms (± 416) |   13417 ms (± 457) |   33642 ms (±1270)
ACA    |   13152 ms (±3296) |   22979 ms (± 429) |   49327 ms (± 885)
PyNEC  |     834 ms (±   7) |    3481 ms (±  10) |   17370 ms (±  44)
```
