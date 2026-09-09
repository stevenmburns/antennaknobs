# H-matrix Sommerfeld residual census across the catalog

**A record, not a decision.** momwire#1019. Measured 2026-09-09 on momwire `7f0b631`,
Skylake box (i7-6700K, 4 physical, powersave).

## Method

Every design module under `src/antennaknobs/designs/*/*.py`, one solve each on
finite ground `(13.0, 0.005)` under `ground_model="sommerfeld"`, at the app's
default mesh (`nominal_nsegs` unset), through `scripts/bench_hmatrix_crossover.py`'s
own engine factory:

* **momwire `HMatrixSolver(degree=2)`** against **dense `BSplineSolver(degree=2)`**;
* `rel_z_vs_dense` is `|Z_h − Z_d| / |Z_d|` on the drive port;
* `resid_q` is momwire#973's sampled residual — relative to the remainder block
  **Q's own magnitude** — and is what the `somm_residual_tol = 4e-3` fallback bar
  is compared against;
* `resid_z` is momwire#1019's diagnostic: Q's *absolute* probe error over
  `max|Z_probe|` on the same entries. It gates nothing (its tolerance defaults
  to `inf`); it is published to be read.

99 designs measured, 4 skipped by refusal
(`specialty.buried_dipole`, `verticals.buried_radial_vertical`,
`verticals.elevated_buried_counterpoise`, `wire.terminated_longwire` — all
`ValueError`, buried/terminated classes the H-matrix does not serve).
Per-deck rows in the JSONL beside this file.

## Distribution of `rel_z_vs_dense`

| band | decks |
|---|--:|
| ≥ 1e-4 | 2 |
| 1e-5 … 1e-4 | 3 |
| 1e-6 … 1e-5 | 27 |
| 1e-7 … 1e-6 | 35 |
| < 1e-7 | 32 |

**32 of 99 decks read above 1e-6**, which is the accuracy momwire#977's crossover
ladder reports for every healthy cell of 101 comparisons.

## The fallback fires, and not on any of those 32

momwire#973's dense fallback fired on **2 of 99** decks, and it handled both:

| deck | N | rank | `resid_q` | `rel_z_vs_dense` |
|---|--:|--:|--:|--:|
| `dipoles.dipole_turnstile` | 82 | 82 | 1.00e+00 | 7.23e-11 |
| `loops.skyloop_lmatch` | 94 | 94 | 1.16e+00 | 4.54e-08 |

Both are gross stagnation — rank driven to N, residual of order 1 — caught and
filled dense, landing at 1e-11 and 1e-8. **That is the remedy working.**

**Among the 32 decks that read above 1e-6, the largest `resid_q` is 2.76e-03,
against a bar of 4e-3.** None of them reaches it. The bar separates
total-stagnation from everything else; it does not separate accurate from
inaccurate.

## The 32

| deck | N | rank | `resid_q` | `resid_z` | fallback | `rel_z_vs_dense` |
|---|--:|--:|--:|--:|:--:|--:|
| `multiband.twoband_fan_dipole` | 111 | 11 | 1.56e-03 | 9.83e-10 | no | **3.28e-04** |
| `arrays.folded_invveearray` | 360 | 40 | 1.77e-04 | 2.61e-10 | no | **1.15e-04** |
| `beams.owa_yagi` | 158 | 12 | 2.76e-03 | 8.35e-09 | no | **9.06e-05** |
| `multiband.trap_fan_dipole` | 119 | 16 | 1.24e-03 | 2.06e-09 | no | **5.46e-05** |
| `arrays.hourglass_array` | 306 | 35 | 8.45e-05 | 1.11e-10 | no | **1.65e-05** |
| `arrays.yagiarray` | 660 | 65 | 4.11e-04 | 7.36e-10 | no | **8.91e-06** |
| `beams.owa_yagi_6el` | 236 | 7 | 2.54e-03 | 1.43e-09 | no | **7.62e-06** |
| `wire.sterba` | 761 | 63 | 1.04e-04 | 1.18e-10 | no | **7.19e-06** |
| `arrays.hentenna_array` | 258 | 39 | 2.94e-05 | 3.04e-11 | no | **6.06e-06** |
| `loops.diamond_loop_turnstile` | 190 | 43 | 1.68e-04 | 2.85e-10 | no | **4.68e-06** |
| `arrays.delta_looparray_1x4` | 380 | 37 | 7.19e-05 | 1.09e-10 | no | **4.64e-06** |
| `arrays.moxonarray` | 324 | 44 | 1.74e-03 | 2.88e-09 | no | **3.89e-06** |
| `loops.horizontal_loop_drone` | 89 | 18 | 3.03e-05 | 4.82e-11 | no | **3.58e-06** |
| `arrays.bowtie4x4` | 1440 | 330 | 1.47e-05 | 1.63e-11 | no | **3.15e-06** |
| `loops.horizontal_loop` | 93 | 17 | 1.46e-04 | 2.33e-10 | no | **2.72e-06** |
| `wire.doublet_ladder_tuner` | 55 | 13 | 4.20e-05 | 1.16e-10 | no | **2.42e-06** |
| `arrays.invveearray` | 172 | 24 | 2.43e-03 | 3.98e-09 | no | **2.38e-06** |
| `arrays.bowtie16x1` | 1440 | 251 | 1.45e-05 | 1.33e-11 | no | **1.92e-06** |
| `arrays.delta_looparray_1x4_grouped` | 380 | 69 | 4.29e-05 | 5.86e-11 | no | **1.66e-06** |
| `loops.inv_delta_loop` | 95 | 27 | 5.13e-05 | 1.21e-10 | no | **1.58e-06** |
| `loops.diamond_loop` | 95 | 17 | 2.81e-05 | 3.44e-11 | no | **1.53e-06** |
| `arrays.delta_looparray` | 188 | 26 | 1.06e-04 | 1.55e-10 | no | **1.53e-06** |
| `loops.delta_loop` | 94 | 27 | 9.06e-05 | 1.05e-10 | no | **1.45e-06** |
| `loops.delta_loop_reflected` | 94 | 27 | 9.06e-05 | 1.05e-10 | no | **1.45e-06** |
| `loops.delta_loop_flyby` | 94 | 27 | 9.06e-05 | 1.05e-10 | no | **1.45e-06** |
| `loops.delta_loop_topdown` | 94 | 27 | 9.06e-05 | 1.05e-10 | no | **1.45e-06** |
| `multiband.fandipole` | 307 | 30 | 3.94e-05 | 6.50e-11 | no | **1.34e-06** |
| `wire.lazy_h` | 170 | 16 | 2.84e-05 | 2.54e-11 | no | **1.32e-06** |
| `arrays.bowtiearray2x4` | 752 | 137 | 7.64e-05 | 7.80e-11 | no | **1.27e-06** |
| `wire.longwire` | 293 | 33 | 1.86e-05 | 2.35e-11 | no | **1.08e-06** |
| `broadband.lpda` | 618 | 42 | 1.81e-05 | 1.64e-11 | no | **1.04e-06** |
| `verticals.four_square` | 164 | 23 | 4.71e-05 | 1.60e-11 | no | **1.01e-06** |

## What the numbers say, and what they do not

`resid_z` does **not** discriminate either, which is why it ships as a diagnostic
rather than a second bar. The worst decks here sit at 2.6e-10 … 8.4e-09, and a
*healthy* rung measured separately (`skyloop_lmatch` at nseg 7, `rel_z` 2.0e-07)
sits at 2.15e-09 — inside that range. The map from an entrywise operator error to
the solved impedance is the conditioning of the deck, and it varies by orders
across the catalog.

The affected decks are **not** the compact ground-coupled class: fan dipoles,
Yagis, arrays, above-ground, with low ACA rank (11, 12, 16, 35, 40, 65). So a
partition change aimed at the compact class (momwire#973) does not address them.

**Whether 1e-6 is the right line has not been decided, and this document does not
decide it.** 3.28e-04 — the worst reading — is 0.03 % of an impedance: small in
engineering terms, and ~300× the figure the lane's own ladder reports. The
H-matrix lane is **opt-in**: `src/antennaknobs/web/adapter.py:2404` reads
`model = req.get("momwire_model", "bspline")`, with bspline the default and the
fallback for unknown or retired model names, so no default-path user meets any of
this.

## Reproducing

The script is in the momwire#1019 session's scratch rather than committed; it
walks the design modules, calls `bench_converge.load_design`, and writes the
JSONL beside this file per row as it goes. That last detail is deliberate: the
first attempt at this census was piped through `tail`, which silently discarded
74 of the 99 rows and produced two wrong summary sentences before anyone noticed.
