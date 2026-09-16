# AK#1525 — razor-2p density ladder over the catalog

**Measurement only. No recommendation on the default density** — that is a product call; this is the curve. `PLAN.md` registers E1–E5 and F1–F2 and the skip rule, all before the run.

**Builds.** antennaknobs `14624ee40` (v0.79.0); momwire `a925d3709` = `v0.56.0` (v0.56.0), which is also antennaknobs' recorded pointer, so **the dev tip and the release coincide for this run**. Accelerator `_accelerators_avx2`. NEC-5 `nec5cl-3b75639` (LLNL-CODE-746721), impedances only. Provenance is the first line of `records.jsonl`.

**The metric, once.** Error is `|Z_a − Z_b|` over **all ports** as a vector. The ohm column is that numerator; the percentage is the same numerator over `|Z_b|`. The reference is **bs2 at rung 160**. This is not probe3's port-0 metric — on four-port `arrays.moxonarray` probe3 reads 9.068 Ω where this norm reads 18.0 — so probe3 supplied the *predicted* class and nothing else.

## 1. Coverage

| engine | ok | refused | skipped | other |
|---|---:|---:|---:|---:|
| `razor` | 796 | 20 | 8 | 0 |
| `bs2` | 816 | 0 | 8 | 0 |
| `nec5` | 32 | 0 | 0 | 0 |

### Skipped, with the reason recorded as rows

| design | achieved N ×21/×40/×80/×160 | growth | predicted cost | budget | reason |
|---|---|---:|---|---|---|
| `verticals.elt_whip` | 4392/4417/4471/4577 | 1.042× | 2.9 GB, 19 s | 40 GB, 1200 s | mesh does not respond to the knob |

**A skipped design is not classified.** "Cannot be laddered on this box" is the finding — it is neither converging nor not converging, and its earlier probe3 reading is withdrawn in `predicted-classes.json` with the cause.

## 2. Classes, per engine against bs2@160

Each engine under test is classified **against the reference separately**. A class is never carried from one pair to another.

**`razor`** — 206 design×ground rows: converging 155, reference unsettled 30, non-monotone 12, refused 5, not converging 2, skipped — not ladderable on this box 2

**`bs2`** — 206 design×ground rows: reference self-check 204, skipped — not ladderable on this box 2

**`nec5`** — 8 design×ground rows: converging 8

| engine | class | rows |
|---|---|---:|
| `razor` | converging | 155 |
| `razor` | reference unsettled | 30 |
| `razor` | non-monotone | 12 |
| `razor` | refused | 5 |
| `razor` | not converging | 2 |
| `razor` | skipped — not ladderable on this box | 2 |
| `bs2` | reference self-check | 204 |
| `bs2` | skipped — not ladderable on this box | 2 |
| `nec5` | converging | 8 |

Fitted order on razor-2p's **155** converging rows: median **0.90**, p10 0.82, p90 1.24.

## 3. Rows unresolved under the one-third rule

**30** rows. The reference — bs2 at rung 160 — moved between ×80 and ×160 by more than a third of the error being judged, so bs2 is not settled at that design's shipped mesh and cannot adjudicate it.

| engine | design | ground | error at ×21 (Ω) | reference moved (Ω) | ratio |
|---|---|---|---:|---:|---:|
| `razor` | `arrays.bowtie16x1` | free | 9.21 | 5.6 | 0.61 |
| `razor` | `arrays.bowtie16x1` | somm | 9.16 | 6.62 | 0.72 |
| `razor` | `arrays.bowtie4x4` | free | 5.7 | 3.32 | 0.58 |
| `razor` | `arrays.bowtie4x4` | somm | 5.86 | 3.66 | 0.63 |
| `razor` | `arrays.delta_looparray_1x4_grouped` | free | 2.34 | 0.863 | 0.37 |
| `razor` | `arrays.delta_looparray_1x4_grouped` | somm | 2.09 | 0.722 | 0.35 |
| `razor` | `broadband.t2fd` | free | 9.62 | 9.84 | 1.02 |
| `razor` | `broadband.t2fd` | somm | 9.37 | 9.7 | 1.04 |
| `razor` | `dipoles.short_dipole_loaded` | free | 9.29 | 3.25 | 0.35 |
| `razor` | `dipoles.short_dipole_loaded` | somm | 9.29 | 3.27 | 0.35 |
| `razor` | `loops.diamond_loop` | free | 0.377 | 0.275 | 0.73 |
| `razor` | `loops.diamond_loop` | somm | 0.353 | 0.225 | 0.64 |
| `razor` | `multiband.trap_dipole` | free | 0.719 | 3.67 | 5.10 |
| `razor` | `multiband.trap_dipole` | somm | 0.681 | 3.53 | 5.19 |
| `razor` | `verticals.bruce` | free | 6.46 | 8.75 | 1.35 |
| `razor` | `verticals.bruce` | somm | 6.49 | 8.25 | 1.27 |
| `razor` | `verticals.dominator` | free | 1.29 | 1.61 | 1.24 |
| `razor` | `verticals.dominator` | somm | 1.13 | 1.42 | 1.26 |
| `razor` | `wire.edz` | free | 3 | 1.4 | 0.47 |
| `razor` | `wire.edz` | somm | 3.02 | 1.42 | 0.47 |
| `razor` | `wire.expanded_lazy_h` | free | 2.43 | 1.16 | 0.48 |
| `razor` | `wire.expanded_lazy_h` | somm | 2.44 | 1.16 | 0.48 |
| `razor` | `wire.lazy_h` | free | 256 | 212 | 0.83 |
| `razor` | `wire.lazy_h` | somm | 255 | 212 | 0.83 |
| `razor` | `wire.rhombic` | free | 3.13 | 4.79 | 1.53 |
| `razor` | `wire.rhombic` | somm | 3.17 | 4.82 | 1.52 |
| `razor` | `wire.terminated_longwire` | free | 204 | 69.6 | 0.34 |
| `razor` | `wire.terminated_longwire` | somm | 4.38 | 1.54 | 0.35 |
| `razor` | `wire.vbeam` | free | 98.2 | 36.3 | 0.37 |
| `razor` | `wire.vbeam` | somm | 107 | 39.4 | 0.37 |

## 4. What 80 buys over 40

| quantity | rows | median | p10 | p90 |
|---|---:|---:|---:|---:|
| accuracy, err(80)/err(40) | 155 | 0.519 | 0.385 | 0.601 |
| cold wall, t(80)/t(40) | 155 | 2.226 | 1.199 | 3.441 |
| peak RSS, rss(80)/rss(40) | 155 | 1.254 | 1.065 | 1.896 |

| rung | Σ cold wall, razor | median cold | median warm | worst peak RSS | worst achieved N |
|---:|---:|---:|---:|---:|---:|
| ×21 | 36 s | 0.094 s | 0.001 s | 410 MB | 1376 |
| ×40 | 60 s | 0.106 s | 0.001 s | 1086 MB | 2624 |
| ×80 | 160 s | 0.205 s | 0.001 s | 3953 MB | 5216 |
| ×160 | 641 s | 0.401 s | 0.001 s | 15538 MB | 10496 |

Peak RSS is a per-process high-water mark covering both the cold and the warm solve in that worker, so it cannot be split between them.

## 5. The ×40 rung — razor-2p's declared default

**×40 is razor-2p's declared roster default (`default_n_per_wire=40`), not a density the web app actually reached.** Correction recorded 2026-09-16: no stock solver slot seeds razor-2p (the served seeds are bspline at 15, bspline d=1 at 20, and PyNEC), so razor-2p is only ever arrived at by swapping a slot's backend — and `useSolverSlots.ts:setSlotBackend` **deliberately preserves `nPerWire` across a swap**, overriding exactly the field the roster default would have set. The app therefore ran razor-2p at **15 or 20**, which AK#1547 fixes. Both are at or below this ladder's lowest rung, so **the figures below understate the error users actually saw**; the ×21 row in the appendix is the nearest measured point and a lower bound on it.

razor-2p's error against bs2@160 at ×40, over **155** converging rows: median **2.42 %**, p90 **7.64 %**, worst **42.5 %**.

Twelve widest at ×40:

| design | ground | Ω | relative | class | order |
|---|---|---:|---:|---|---:|
| `wire.zepp` | free | 7.15 | 42.5 % | converging | 0.98 |
| `wire.zepp` | somm | 7.14 | 42.2 % | converging | 0.98 |
| `dipoles.koch_dipole` | somm | 7.63 | 21.6 % | converging | 1.09 |
| `dipoles.koch_dipole` | free | 7.66 | 21.3 % | converging | 1.09 |
| `verticals.rectangle` | somm | 9.92 | 20.7 % | converging | 0.94 |
| `verticals.rectangle` | free | 9.64 | 20.2 % | converging | 0.92 |
| `verticals.four_square` | somm | 9.34 | 13 % | converging | 0.87 |
| `verticals.four_square` | free | 9.31 | 12.8 % | converging | 0.87 |
| `arrays.moxonarray` | free | 9.76 | 9.97 % | converging | 0.87 |
| `arrays.moxonarray` | somm | 9.8 | 9.93 % | converging | 0.87 |
| `loops.skyloop_lmatch` | free | 4.75 | 9.91 % | converging | 2.08 |
| `loops.skyloop_lmatch` | somm | 4.69 | 9.86 % | converging | 2.08 |

## 6. Predictions, scored

| prediction | bar | measured | verdict |
|---|---|---|---|
| **E1** | ≥ 90 % of the 204 classifiable rows keep probe3's predicted class | 75.5 % strict (154/204); 82.4 % excluding the 17 rows probe3 never measured | **MISS** |
| **E2a** | converging-row order median in 0.8–1.3 | 0.90 | **HIT** |
| **E2b** | `loops.skyloop_lmatch` order in 1.7–2.4 | 2.08, 2.08 | **HIT** |
| **E3** | err 0.45–0.60, wall 3.0–5.0, RSS 1.5–4.0 | err 0.519, wall 2.23, RSS 1.25 | **MISS** |
| **E4** | 10–40 rows marked reference unsettled | 30 | **HIT** |
| **E5** | exactly one knob-stiff design | 1 | **HIT** |
| **F1** | every cell bit-identical to the pre-v0.79.0 ladder except `verticals.buried_radial_vertical` | 1680 of 1680 identical, 0 movers outside | **HIT** |
| **F2** | `verticals.buried_radial_vertical` does move | 0 of its cells moved | **MISS** |

### Class changes against probe3 — **33**, each a finding

| design | ground | probe3 predicted | measured now |
|---|---|---|---|
| `arrays.bowtie16x1` | free | converging | reference unsettled |
| `arrays.bowtie4x4` | free | converging | reference unsettled |
| `arrays.delta_looparray_1x4_grouped` | free | converging | reference unsettled |
| `arrays.delta_looparray_1x4_grouped` | somm | converging | reference unsettled |
| `broadband.t2fd` | free | converging | reference unsettled |
| `broadband.t2fd` | somm | converging | reference unsettled |
| `dipoles.folded_invvee` | free | converging | non-monotone |
| `dipoles.folded_invvee` | somm | converging | non-monotone |
| `dipoles.folded_invvee_balun` | free | converging | non-monotone |
| `dipoles.folded_invvee_balun` | somm | converging | non-monotone |
| `loops.diamond_loop` | somm | unexplained | reference unsettled |
| `multiband.fandipole` | free | reference unsettled | non-monotone |
| `multiband.fandipole` | somm | reference unsettled | non-monotone |
| `multiband.trap_fan_dipole` | free | reference unsettled | non-monotone |
| `multiband.trap_fan_dipole` | somm | reference unsettled | non-monotone |
| `specialty.continuous_helix` | free | reference unsettled | converging |
| `specialty.continuous_helix` | somm | reference unsettled | converging |
| `specialty.faceted_helix` | free | unexplained | converging |
| `specialty.faceted_helix` | somm | unexplained | converging |
| `verticals.bruce` | free | not converging | reference unsettled |
| `verticals.bruce` | somm | not converging | reference unsettled |
| `wire.doublet_balanced_tuner` | free | reference unsettled | non-monotone |
| `wire.doublet_balanced_tuner` | somm | reference unsettled | non-monotone |
| `wire.edz` | free | unexplained | reference unsettled |
| `wire.edz` | somm | unexplained | reference unsettled |
| `wire.expanded_lazy_h` | free | unexplained | reference unsettled |
| `wire.expanded_lazy_h` | somm | unexplained | reference unsettled |
| `wire.lazy_h` | free | not converging | reference unsettled |
| `wire.lazy_h` | somm | not converging | reference unsettled |
| `wire.rhombic` | free | not converging | reference unsettled |
| `wire.sterba` | free | unexplained | non-monotone |
| `wire.zepp` | free | reference unsettled | converging |
| `wire.zepp` | somm | reference unsettled | converging |

probe3 ran on a 2026-09-03 build with a port-0 metric and a 1×/2×/4× sweep; this ladder is current code, an all-port norm and 21/40/80/160. A change is therefore not automatically a regression — it can be either the code moving or the metric resolving the row differently, and the appendix carries the numbers for each.

## 6. Appendix — every razor-2p row

`Ω` and `%` are against bs2@160. `N` is the achieved segment count.

| design | ground | achieved N | Ω ×21/×40/×80/×160 | % ×21/×40/×80/×160 | class | order |
|---|---|---|---|---|---|---:|
| `arrays.bowtie16x1` | free | 1376/2624/5216/10496 | 9.21/7.74/5.41/4.15 | 0.502 %/0.421 %/0.294 %/0.226 % | reference unsettled | — |
| `arrays.bowtie16x1` | somm | 1376/2624/5216/10496 | 9.16/7.8/5.67/4.64 | 0.461 %/0.392 %/0.285 %/0.233 % | reference unsettled | — |
| `arrays.bowtie1x2_bl` | free | 188/352/708/1400 | 2.04/1.22/0.606/0.272 | 4.08 %/2.45 %/1.21 %/0.545 % | converging | 1.00 |
| `arrays.bowtie1x2_bl` | somm | 188/352/708/1400 | 2.03/1.22/0.604/0.272 | 4.08 %/2.45 %/1.21 %/0.544 % | converging | 1.00 |
| `arrays.bowtie4x4` | free | 1376/2624/5216/10496 | 5.7/4.41/1.76/1.42 | 0.396 %/0.306 %/0.122 %/0.0985 % | reference unsettled | — |
| `arrays.bowtie4x4` | somm | 1376/2624/5216/10496 | 5.86/4.54/1.64/1.46 | 0.391 %/0.303 %/0.11 %/0.0976 % | reference unsettled | — |
| `arrays.bowtiearray` | free | 360/704/1384/2768 | 3.6/2.52/1.2/0.419 | 0.831 %/0.583 %/0.278 %/0.0968 % | converging | 1.06 |
| `arrays.bowtiearray` | somm | 360/704/1384/2768 | 3.54/2.49/1.2/0.431 | 0.837 %/0.589 %/0.284 %/0.102 % | converging | 1.04 |
| `arrays.bowtiearray1x2` | free | 172/336/668/1336 | 2.26/1.66/0.813/0.292 | 0.857 %/0.632 %/0.309 %/0.111 % | converging | 1.00 |
| `arrays.bowtiearray1x2` | somm | 172/336/668/1336 | 2.26/1.67/0.841/0.331 | 0.879 %/0.649 %/0.326 %/0.128 % | converging | 0.95 |
| `arrays.bowtiearray2x4` | free | 720/1408/2752/5520 | 5.05/3.53/1.68/0.559 | 0.842 %/0.589 %/0.281 %/0.0933 % | converging | 1.08 |
| `arrays.bowtiearray2x4` | somm | 720/1408/2752/5520 | 4.96/3.48/1.67/0.572 | 0.847 %/0.595 %/0.286 %/0.0976 % | converging | 1.07 |
| `arrays.delta_looparray` | free | 180/344/682/1364 | 2.1/1.57/0.799/0.383 | 1.37 %/1.03 %/0.523 %/0.251 % | converging | 0.86 |
| `arrays.delta_looparray` | somm | 180/344/682/1364 | 2.04/1.54/0.792/0.387 | 1.5 %/1.13 %/0.582 %/0.284 % | converging | 0.84 |
| `arrays.delta_looparray_1x4` | free | 364/696/1386/2778 | 1.64/1.33/0.552/0.135 | 0.423 %/0.343 %/0.142 %/0.0348 % | converging | 1.24 |
| `arrays.delta_looparray_1x4` | somm | 364/696/1386/2778 | 1.47/1.25/0.549/0.173 | 0.418 %/0.354 %/0.156 %/0.0491 % | converging | 1.07 |
| `arrays.delta_looparray_1x4_grouped` | free | 364/696/1386/2778 | 2.34/1.57/0.462/0.104 | 0.412 %/0.277 %/0.0816 %/0.0184 % | reference unsettled | — |
| `arrays.delta_looparray_1x4_grouped` | somm | 364/696/1386/2778 | 2.09/1.42/0.456/0.094 | 0.402 %/0.274 %/0.0879 %/0.0181 % | reference unsettled | — |
| `arrays.delta_looparray_2x2` | free | 376/716/1434/2866 | 1.98/1.5/0.577/0.128 | 0.431 %/0.327 %/0.126 %/0.028 % | converging | 1.36 |
| `arrays.delta_looparray_2x2` | somm | 376/716/1434/2866 | 2.01/1.52/0.572/0.121 | 0.429 %/0.323 %/0.122 %/0.0258 % | converging | 1.39 |
| `arrays.delta_looparray_network` | free | 180/344/682/1364 | 0.17/0.133/0.0707/0.0366 | 0.308 %/0.24 %/0.128 %/0.0661 % | converging | 0.78 |
| `arrays.delta_looparray_network` | somm | 180/344/682/1364 | 0.0854/0.0693/0.0384/0.0208 | 0.159 %/0.129 %/0.0714 %/0.0387 % | converging | 0.72 |
| `arrays.folded_invveearray` | free | 344/648/1296/2584 | 1.96/0.436/0.248/0.076 | 0.478 %/0.106 %/0.0603 %/0.0185 % | converging | 1.53 |
| `arrays.folded_invveearray` | somm | 344/648/1296/2584 | 1.97/0.43/0.258/0.053 | 0.495 %/0.108 %/0.0647 %/0.0133 % | converging | 1.68 |
| `arrays.hentenna_array` | free | 246/472/942/1884 | 7.86/4.58/2.33/1.11 | 5.46 %/3.18 %/1.62 %/0.772 % | converging | 0.96 |
| `arrays.hentenna_array` | somm | 246/472/942/1884 | 7.87/4.58/2.33/1.11 | 5.43 %/3.16 %/1.61 %/0.769 % | converging | 0.96 |
| `arrays.hourglass_array` | free | 294/564/1122/2248 | 5.17/2.92/1.43/0.657 | 3.56 %/2.01 %/0.988 %/0.453 % | converging | 1.02 |
| `arrays.hourglass_array` | somm | 294/564/1122/2248 | 5.18/2.93/1.44/0.661 | 3.59 %/2.03 %/0.996 %/0.457 % | converging | 1.02 |
| `arrays.invveearray` | free | 172/320/640/1276 | 5.62/3.13/1.79/0.994 | 5.44 %/3.04 %/1.73 %/0.963 % | converging | 0.86 |
| `arrays.invveearray` | somm | 172/320/640/1276 | 5.65/3.15/1.8/0.998 | 5.66 %/3.16 %/1.8 %/1 % | converging | 0.86 |
| `arrays.lumped_coupled_pair` | free | 80/152/304/608 | 1.4/0.771/0.441/0.265 | 1.94 %/1.07 %/0.61 %/0.367 % | converging | 0.82 |
| `arrays.lumped_coupled_pair` | somm | 80/152/304/608 | 1.45/0.796/0.451/0.266 | 2.2 %/1.21 %/0.684 %/0.404 % | converging | 0.83 |
| `arrays.moxonarray` | free | 324/624/1232/2456 | 18.5/9.76/5.59/3.15 | 18.9 %/9.97 %/5.71 %/3.22 % | converging | 0.87 |
| `arrays.moxonarray` | somm | 324/624/1232/2456 | 18.5/9.8/5.62/3.17 | 18.8 %/9.93 %/5.69 %/3.21 % | converging | 0.87 |
| `arrays.yagiarray` | free | 660/1240/2492/4992 | 4.02/2.41/1.4/0.801 | 2.42 %/1.44 %/0.841 %/0.481 % | converging | 0.80 |
| `arrays.yagiarray` | somm | 660/1240/2492/4992 | 4.83/2.86/1.65/0.935 | 2.89 %/1.71 %/0.986 %/0.559 % | converging | 0.81 |
| `beams.hb9cv` | free | 84/162/324/646 | 8.01/4.5/2.5/1.38 | 10.6 %/5.97 %/3.32 %/1.82 % | converging | 0.86 |
| `beams.hb9cv` | somm | 84/162/324/646 | 7.86/4.41/2.46/1.35 | 10.8 %/6.05 %/3.37 %/1.85 % | converging | 0.86 |
| `beams.hexbeam` | free | 88/166/331/657 | 1.96/1.25/0.686/0.353 | 3.6 %/2.31 %/1.27 %/0.65 % | converging | 0.85 |
| `beams.hexbeam` | somm | 88/166/331/657 | 1.73/1.08/0.583/0.286 | 3.43 %/2.13 %/1.15 %/0.566 % | converging | 0.90 |
| `beams.moxon` | free | 83/156/309/617 | 6.56/3.77/2.15/1.2 | 14.1 %/8.12 %/4.63 %/2.6 % | converging | 0.84 |
| `beams.moxon` | somm | 83/156/309/617 | 6.09/3.49/1.99/1.11 | 12.9 %/7.38 %/4.21 %/2.36 % | converging | 0.84 |
| `beams.moxon_turnstile` | free | 168/318/624/1254 | 0.172/0.054/0.017/0.00492 | 0.343 %/0.108 %/0.034 %/0.00982 % | converging | 1.76 |
| `beams.moxon_turnstile` | somm | 168/318/624/1254 | 0.171/0.0542/0.0175/0.00531 | 0.341 %/0.108 %/0.0349 %/0.0106 % | converging | 1.72 |
| `beams.owa_yagi` | free | 158/300/603/1207 | 1.2/0.464/0.213/0.166 | 2.55 %/0.981 %/0.45 %/0.35 % | converging | 0.99 |
| `beams.owa_yagi` | somm | 158/300/603/1207 | 1.43/0.603/0.274/0.167 | 3.02 %/1.27 %/0.578 %/0.354 % | converging | 1.06 |
| `beams.owa_yagi_6el` | free | 235/447/892/1784 | 2.93/2.18/1.4/0.471 | 5.72 %/4.25 %/2.73 %/0.917 % | converging | 0.88 |
| `beams.owa_yagi_6el` | somm | 235/447/892/1784 | 3/2.23/1.43/0.481 | 5.83 %/4.32 %/2.77 %/0.934 % | converging | 0.88 |
| `beams.phased_driver_yagi` | free | 118/227/450/898 | 2.54/1.48/0.849/0.469 | 5.01 %/2.93 %/1.68 %/0.926 % | converging | 0.83 |
| `beams.phased_driver_yagi` | somm | 118/227/450/898 | 3.51/2.05/1.18/0.651 | 6.71 %/3.92 %/2.25 %/1.25 % | converging | 0.83 |
| `beams.yagi` | free | 157/292/589/1174 | 5/2.78/1.52/0.833 | 10 %/5.56 %/3.04 %/1.67 % | converging | 0.89 |
| `beams.yagi` | somm | 157/292/589/1174 | 4.87/2.7/1.48/0.81 | 9.66 %/5.36 %/2.93 %/1.61 % | converging | 0.89 |
| `broadband.discone` | free | 361/686/1371/2742 | 1.57/0.7/0.363/0.156 | 4.37 %/1.95 %/1.01 %/0.433 % | converging | 1.12 |
| `broadband.discone` | somm | 361/686/1371/2742 | 1.57/0.701/0.364/0.156 | 4.36 %/1.95 %/1.01 %/0.433 % | converging | 1.12 |
| `broadband.g5rv` | free | 127/240/479/960 | 5.12/2.49/1.29/0.703 | 4.03 %/1.96 %/1.02 %/0.553 % | converging | 0.98 |
| `broadband.g5rv` | somm | 127/240/479/960 | 5.17/2.52/1.31/0.711 | 4.03 %/1.97 %/1.02 %/0.554 % | converging | 0.98 |
| `broadband.lpda` | free | 618/1174/2338/4680 | 1.37/0.768/0.41/0.223 | 2.5 %/1.4 %/0.75 %/0.408 % | converging | 0.90 |
| `broadband.lpda` | somm | 618/1174/2338/4680 | 1.28/0.719/0.377/0.199 | 2.43 %/1.36 %/0.714 %/0.377 % | converging | 0.92 |
| `broadband.t2fd` | free | 104/194/388/778 | 9.62/7.32/6.44/6.98 | 0.703 %/0.535 %/0.471 %/0.51 % | reference unsettled | — |
| `broadband.t2fd` | somm | 104/194/388/778 | 9.37/7.15/6.34/6.88 | 0.694 %/0.529 %/0.469 %/0.51 % | reference unsettled | — |
| `dipoles.dipole_turnstile` | free | 82/156/306/616 | 5.21/2.88/1.62/0.899 | 5.16 %/2.85 %/1.61 %/0.891 % | converging | 0.87 |
| `dipoles.dipole_turnstile` | somm | 82/156/306/616 | 5.27/2.92/1.64/0.908 | 5.68 %/3.14 %/1.77 %/0.978 % | converging | 0.87 |
| `dipoles.folded_invvee` | free | 84/154/310/618 | 1.82/0.334/0.122/0.161 | 0.809 %/0.149 %/0.0544 %/0.0717 % | non-monotone | 1.22 |
| `dipoles.folded_invvee` | somm | 84/154/310/618 | 1.83/0.329/0.0951/0.124 | 0.918 %/0.165 %/0.0477 %/0.0622 % | non-monotone | 1.38 |
| `dipoles.folded_invvee_balun` | free | 84/154/310/618 | 0.263/0.0483/0.0177/0.0233 | 0.56 %/0.103 %/0.0377 %/0.0497 % | non-monotone | 1.22 |
| `dipoles.folded_invvee_balun` | somm | 84/154/310/618 | 0.3/0.0541/0.0156/0.0204 | 0.638 %/0.115 %/0.0332 %/0.0433 % | non-monotone | 1.38 |
| `dipoles.invvee` | free | 41/78/155/310 | 3.29/1.81/1.03/0.569 | 5.87 %/3.23 %/1.83 %/1.02 % | converging | 0.86 |
| `dipoles.invvee` | somm | 41/78/155/310 | 3.29/1.81/1.02/0.567 | 6.65 %/3.66 %/2.07 %/1.14 % | converging | 0.87 |
| `dipoles.invvee_apex` | free | 40/78/156/312 | 2.86/1.56/0.883/0.496 | 5.12 %/2.79 %/1.58 %/0.889 % | converging | 0.85 |
| `dipoles.invvee_apex` | somm | 40/78/156/312 | 2.87/1.57/0.888/0.499 | 5.81 %/3.17 %/1.8 %/1.01 % | converging | 0.85 |
| `dipoles.invvee_catenary` | free | 29/86/143/314 | 4.92/1.82/1.23/0.634 | 9.5 %/3.5 %/2.38 %/1.22 % | converging | 0.86 |
| `dipoles.invvee_catenary` | somm | 29/86/143/314 | 4.93/1.82/1.23/0.632 | 10.7 %/3.93 %/2.67 %/1.37 % | converging | 0.86 |
| `dipoles.invvee_coax_station` | free | 41/78/155/310 | 1.79/0.994/0.566/0.315 | 4.02 %/2.23 %/1.27 %/0.705 % | converging | 0.86 |
| `dipoles.invvee_coax_station` | somm | 41/78/155/310 | 1.63/0.906/0.516/0.287 | 3.72 %/2.06 %/1.18 %/0.655 % | converging | 0.85 |
| `dipoles.koch_dipole` | free | 65/98/195/358 | 11.6/7.66/3.63/1.8 | 32.2 %/21.3 %/10.1 %/5 % | converging | 1.09 |
| `dipoles.koch_dipole` | somm | 65/98/195/358 | 11.5/7.63/3.62/1.79 | 32.7 %/21.6 %/10.3 %/5.08 % | converging | 1.09 |
| `dipoles.ocf_dipole` | free | 41/78/155/310 | 11.4/6.32/3.61/2.07 | 4.97 %/2.77 %/1.58 %/0.908 % | converging | 0.84 |
| `dipoles.ocf_dipole` | somm | 41/78/155/310 | 11.7/6.53/3.71/2.11 | 5.45 %/3.03 %/1.72 %/0.981 % | converging | 0.84 |
| `dipoles.pota_invvee` | free | 41/75/150/301 | 3.31/1.87/1.02/0.568 | 6.1 %/3.44 %/1.88 %/1.05 % | converging | 0.88 |
| `dipoles.pota_invvee` | somm | 41/75/150/301 | 3.37/1.9/1.04/0.583 | 5.09 %/2.87 %/1.57 %/0.881 % | converging | 0.88 |
| `dipoles.short_dipole_loaded` | free | 21/40/80/160 | 9.29/4.55/1.03/1.34 | 51.6 %/25.3 %/5.71 %/7.43 % | reference unsettled | — |
| `dipoles.short_dipole_loaded` | somm | 21/40/80/160 | 9.29/4.55/1.02/1.35 | 54.7 %/26.8 %/6 %/7.95 % | reference unsettled | — |
| `loops.bisquare` | free | 184/352/704/1408 | 3.96/2.86/1.92/1.32 | 0.966 %/0.699 %/0.468 %/0.321 % | converging | 0.54 |
| `loops.bisquare` | somm | 184/352/704/1408 | 3.96/2.86/1.91/1.3 | 0.976 %/0.705 %/0.471 %/0.322 % | converging | 0.55 |
| `loops.delta_loop` | free | 90/173/346/691 | 1.52/1.14/0.584/0.285 | 1.27 %/0.961 %/0.49 %/0.239 % | converging | 0.84 |
| `loops.delta_loop` | somm | 90/173/346/691 | 1.5/1.13/0.582/0.287 | 1.35 %/1.02 %/0.526 %/0.259 % | converging | 0.83 |
| `loops.delta_loop_flyby` | free | 90/173/346/691 | 1.52/1.14/0.584/0.285 | 1.27 %/0.961 %/0.49 %/0.239 % | converging | 0.84 |
| `loops.delta_loop_flyby` | somm | 90/173/346/691 | 1.5/1.13/0.582/0.287 | 1.35 %/1.02 %/0.526 %/0.259 % | converging | 0.83 |
| `loops.delta_loop_reflected` | free | 90/173/346/691 | 1.52/1.14/0.584/0.285 | 1.27 %/0.961 %/0.49 %/0.239 % | converging | 0.84 |
| `loops.delta_loop_reflected` | somm | 90/173/346/691 | 1.5/1.13/0.582/0.287 | 1.35 %/1.02 %/0.526 %/0.259 % | converging | 0.83 |
| `loops.delta_loop_slanted` | free | 184/348/696/1394 | 2.32/1.73/0.889/0.44 | 1.35 %/1 %/0.516 %/0.255 % | converging | 0.84 |
| `loops.delta_loop_slanted` | somm | 184/348/696/1394 | 2.32/1.72/0.886/0.439 | 1.45 %/1.08 %/0.556 %/0.275 % | converging | 0.84 |
| `loops.delta_loop_topdown` | free | 90/173/346/691 | 1.52/1.14/0.584/0.285 | 1.27 %/0.961 %/0.49 %/0.239 % | converging | 0.84 |
| `loops.delta_loop_topdown` | somm | 90/173/346/691 | 1.5/1.13/0.582/0.287 | 1.35 %/1.02 %/0.526 %/0.259 % | converging | 0.83 |
| `loops.diamond_loop` | free | 91/172/343/684 | 0.377/0.409/0.142/0.0734 | 0.165 %/0.179 %/0.0621 %/0.0321 % | reference unsettled | — |
| `loops.diamond_loop` | somm | 91/172/343/684 | 0.353/0.403/0.148/0.0438 | 0.169 %/0.193 %/0.0711 %/0.021 % | reference unsettled | — |
| `loops.diamond_loop_turnstile` | free | 182/344/686/1376 | 2.59/1.82/0.947/0.468 | 1.69 %/1.19 %/0.618 %/0.306 % | converging | 0.86 |
| `loops.diamond_loop_turnstile` | somm | 182/344/686/1376 | 2.61/1.83/0.946/0.464 | 1.7 %/1.19 %/0.616 %/0.302 % | converging | 0.87 |
| `loops.horizontal_loop` | free | 89/168/337/675 | 2.12/1.36/0.683/0.3 | 1.7 %/1.09 %/0.547 %/0.24 % | converging | 0.97 |
| `loops.horizontal_loop` | somm | 89/168/337/675 | 2.09/1.34/0.673/0.298 | 1.69 %/1.08 %/0.544 %/0.24 % | converging | 0.97 |
| `loops.horizontal_loop_drone` | free | 85/159/318/638 | 1.31/0.92/0.553/0.31 | 0.709 %/0.499 %/0.3 %/0.168 % | converging | 0.72 |
| `loops.horizontal_loop_drone` | somm | 85/159/318/638 | 1.32/0.923/0.554/0.33 | 0.661 %/0.463 %/0.278 %/0.165 % | converging | 0.69 |
| `loops.inv_delta_loop` | free | 91/175/346/692 | 1.71/1.26/0.656/0.331 | 1.58 %/1.16 %/0.607 %/0.306 % | converging | 0.83 |
| `loops.inv_delta_loop` | somm | 91/175/346/692 | 1.73/1.26/0.651/0.323 | 1.55 %/1.13 %/0.585 %/0.291 % | converging | 0.84 |
| `loops.quad` | free | 172/332/664/1328 | 2.34/1.5/0.783/0.361 | 1.8 %/1.16 %/0.602 %/0.278 % | converging | 0.92 |
| `loops.quad` | somm | 172/332/664/1328 | 2.33/1.5/0.781/0.36 | 1.88 %/1.21 %/0.629 %/0.29 % | converging | 0.92 |
| `loops.skyloop_lmatch` | free | 90/171/339/672 | 16.1/4.75/1.11/0.25 | 33.6 %/9.91 %/2.32 %/0.521 % | converging | 2.08 |
| `loops.skyloop_lmatch` | somm | 90/171/339/672 | 15.9/4.69/1.1/0.245 | 33.5 %/9.86 %/2.31 %/0.516 % | converging | 2.08 |
| `loops.triangular_skyloop` | free | 90/171/339/672 | 0.628/0.453/0.275/0.172 | 0.553 %/0.398 %/0.242 %/0.152 % | converging | 0.65 |
| `loops.triangular_skyloop` | somm | 90/171/339/672 | 0.564/0.405/0.254/0.163 | 0.405 %/0.291 %/0.182 %/0.117 % | converging | 0.62 |
| `multiband.fandipole` | free | 295/557/1115/2237 | 2.75/0.503/0.586/1 | 5.75 %/1.05 %/1.22 %/2.09 % | non-monotone | 0.41 |
| `multiband.fandipole` | somm | 295/557/1115/2237 | 2.76/0.468/0.586/0.996 | 6.48 %/1.1 %/1.38 %/2.34 % | non-monotone | 0.40 |
| `multiband.hexbeam_5band` | free | 308/581/1165/2332 | 3.6/2.12/1.05/0.538 | 4.12 %/2.42 %/1.2 %/0.615 % | converging | 0.95 |
| `multiband.hexbeam_5band` | somm | 308/581/1165/2332 | 4.28/2.57/1.3/0.679 | 4.27 %/2.57 %/1.3 %/0.677 % | converging | 0.92 |
| `multiband.trap_dipole` | free | 64/120/240/482 | 0.719/0.494/0.891/1.93 | 0.689 %/0.473 %/0.853 %/1.85 % | reference unsettled | — |
| `multiband.trap_dipole` | somm | 64/120/240/482 | 0.681/0.482/0.86/1.86 | 0.698 %/0.494 %/0.881 %/1.9 % | reference unsettled | — |
| `multiband.trap_fan_dipole` | free | 113/211/419/829 | 2.19/2.25/1.74/1.91 | 4.03 %/4.16 %/3.21 %/3.52 % | non-monotone | 0.10 |
| `multiband.trap_fan_dipole` | somm | 113/211/419/829 | 2.19/2.26/1.75/1.91 | 4.55 %/4.7 %/3.64 %/3.98 % | non-monotone | 0.10 |
| `multiband.twoband_fan_dipole` | free | 105/179/339/673 | 5.45/2.61/0.996/0.586 | 9.49 %/4.54 %/1.73 %/1.02 % | converging | 1.22 |
| `multiband.twoband_fan_dipole` | somm | 105/179/339/673 | 5.47/2.62/0.997/0.585 | 10.7 %/5.12 %/1.95 %/1.14 % | converging | 1.23 |
| `specialty.bowtie` | free | 86/164/326/656 | 1.23/1.01/0.487/0.153 | 0.654 %/0.536 %/0.259 %/0.0814 % | converging | 1.03 |
| `specialty.bowtie` | somm | 86/164/326/656 | 1.24/1.02/0.478/0.137 | 0.608 %/0.499 %/0.234 %/0.0674 % | converging | 1.09 |
| `specialty.buried_dipole` | free | 51/95/192/381 | 3.35/0.595/0.815/3.47 | 0.173 %/0.0308 %/0.0422 %/0.18 % | not converging | — |
| `specialty.buried_dipole` | somm | 51/95/192/381 | —/—/—/— | —/—/—/— | refused | — |
| `specialty.continuous_helix` | free | 108/204/409/817 | 2.29/0.935/0.293/0.102 | 10.2 %/4.17 %/1.31 %/0.453 % | converging | 1.55 |
| `specialty.continuous_helix` | somm | 108/204/409/817 | 2.28/0.931/0.29/0.1 | 9.94 %/4.05 %/1.26 %/0.436 % | converging | 1.56 |
| `specialty.faceted_helix` | free | 117/193/418/803 | 0.61/0.63/0.225/0.0812 | 2.93 %/3.03 %/1.08 %/0.391 % | converging | 1.10 |
| `specialty.faceted_helix` | somm | 117/193/418/803 | 0.62/0.635/0.228/0.0829 | 2.9 %/2.97 %/1.07 %/0.388 % | converging | 1.10 |
| `specialty.hentenna` | free | 119/230/459/914 | 5.7/3.32/1.69/0.832 | 9.81 %/5.71 %/2.91 %/1.43 % | converging | 0.95 |
| `specialty.hentenna` | somm | 119/230/459/914 | 5.7/3.32/1.69/0.832 | 9.85 %/5.74 %/2.93 %/1.44 % | converging | 0.95 |
| `specialty.hentenna_slant` | free | 123/236/465/930 | 7.66/4.33/2.22/1.07 | 14.7 %/8.32 %/4.26 %/2.06 % | converging | 0.97 |
| `specialty.hentenna_slant` | somm | 123/236/465/930 | 7.67/4.33/2.22/1.07 | 14.9 %/8.4 %/4.31 %/2.08 % | converging | 0.97 |
| `specialty.hourglass` | free | 159/298/593/1186 | 3.2/1.85/0.937/0.449 | 5.83 %/3.38 %/1.71 %/0.82 % | converging | 0.98 |
| `specialty.hourglass` | somm | 159/298/593/1186 | 3.2/1.85/0.937/0.449 | 5.86 %/3.4 %/1.72 %/0.824 % | converging | 0.98 |
| `specialty.hourglass_slant` | free | 153/296/583/1168 | 4.31/2.4/1.22/0.583 | 7.43 %/4.14 %/2.1 %/1 % | converging | 0.99 |
| `specialty.hourglass_slant` | somm | 153/296/583/1168 | 4.31/2.4/1.22/0.582 | 7.54 %/4.2 %/2.13 %/1.02 % | converging | 0.99 |
| `verticals.bobtail` | free | 151/292/579/1160 | 1.14/0.638/0.47/0.325 | 2.35 %/1.32 %/0.969 %/0.669 % | converging | 0.60 |
| `verticals.bobtail` | somm | 151/292/579/1160 | 1.15/0.642/0.472/0.326 | 2.38 %/1.33 %/0.982 %/0.678 % | converging | 0.60 |
| `verticals.bruce` | free | 189/360/720/1440 | 6.46/3.59/2.23/3.91 | 0.533 %/0.296 %/0.184 %/0.322 % | reference unsettled | — |
| `verticals.bruce` | somm | 189/360/720/1440 | 6.49/3.6/1.91/3.58 | 0.551 %/0.306 %/0.162 %/0.304 % | reference unsettled | — |
| `verticals.buried_radial_vertical` | free | 248/453/888/1764 | 1.32/0.623/0.236/0.0328 | 1.49 %/0.703 %/0.266 %/0.037 % | converging | 1.85 |
| `verticals.buried_radial_vertical` | somm | 248/453/888/1764 | —/—/—/— | —/—/—/— | refused | — |
| `verticals.challenger` | free | 42/79/157/312 | 1.99/1.24/0.722/0.361 | 6.2 %/3.86 %/2.25 %/1.12 % | converging | 0.85 |
| `verticals.challenger` | somm | 42/79/157/312 | 1.9/1.18/0.688/0.341 | 4.4 %/2.74 %/1.6 %/0.79 % | converging | 0.85 |
| `verticals.dominator` | free | 69/130/258/518 | 1.29/0.705/0.44/0.309 | 4.19 %/2.28 %/1.43 %/1 % | reference unsettled | — |
| `verticals.dominator` | somm | 69/130/258/518 | 1.13/0.614/0.383/0.271 | 3.88 %/2.11 %/1.32 %/0.93 % | reference unsettled | — |
| `verticals.elevated_buried_counterpoise` | free | 249/459/906/1804 | 7.1e+03/7.1e+03/7.1e+03/7.1e+03 | 10.3 %/10.3 %/10.3 %/10.3 % | not converging | — |
| `verticals.elevated_buried_counterpoise` | somm | 249/459/906/1804 | —/—/—/— | —/—/—/— | refused | — |
| `verticals.elt_whip` | free | —/—/—/— | —/—/—/— | —/—/—/— | skipped — not ladderable on this box | — |
| `verticals.elt_whip` | somm | —/—/—/— | —/—/—/— | —/—/—/— | skipped — not ladderable on this box | — |
| `verticals.four_square` | free | 164/304/604/1216 | 16.3/9.31/5.16/2.82 | 22.5 %/12.8 %/7.11 %/3.89 % | converging | 0.87 |
| `verticals.four_square` | somm | 164/304/604/1216 | 16.4/9.34/5.18/2.83 | 22.7 %/13 %/7.18 %/3.93 % | converging | 0.87 |
| `verticals.half_square` | free | 86/164/327/653 | 1.4/0.606/0.387/0.238 | 2.37 %/1.03 %/0.655 %/0.403 % | converging | 0.85 |
| `verticals.half_square` | somm | 86/164/327/653 | 1.4/0.607/0.387/0.238 | 2.44 %/1.05 %/0.672 %/0.413 % | converging | 0.85 |
| `verticals.inverted_l` | free | 106/201/402/803 | 1.03/0.549/0.303/0.197 | 5.94 %/3.17 %/1.75 %/1.14 % | converging | 0.82 |
| `verticals.inverted_l` | somm | 106/201/402/803 | 1.03/0.551/0.304/0.198 | 5.92 %/3.16 %/1.75 %/1.14 % | converging | 0.82 |
| `verticals.inverted_l_tmatch` | free | 106/201/402/803 | 3.62/1.94/1.04/0.532 | 7.16 %/3.84 %/2.06 %/1.05 % | converging | 0.94 |
| `verticals.inverted_l_tmatch` | somm | 106/201/402/803 | 3.71/1.99/1.07/0.546 | 7.45 %/4 %/2.15 %/1.1 % | converging | 0.94 |
| `verticals.jpole` | free | 87/164/329/660 | 4.59/2.39/1.28/0.727 | 6.5 %/3.37 %/1.81 %/1.03 % | converging | 0.91 |
| `verticals.jpole` | somm | 87/164/329/660 | 4.62/2.4/1.29/0.732 | 6.5 %/3.38 %/1.82 %/1.03 % | converging | 0.91 |
| `verticals.phased_verticals` | free | 86/160/318/640 | 8.81/4.91/2.6/1.33 | 4.05 %/2.26 %/1.19 %/0.611 % | converging | 0.94 |
| `verticals.phased_verticals` | somm | 86/160/318/640 | 9.04/5.04/2.67/1.36 | 4.13 %/2.3 %/1.22 %/0.623 % | converging | 0.94 |
| `verticals.pota_performer` | free | 59/112/221/444 | 3.15/2/1.19/0.594 | 8.34 %/5.31 %/3.14 %/1.57 % | converging | 0.82 |
| `verticals.pota_performer` | somm | 59/112/221/444 | 3.05/1.94/1.15/0.574 | 6.7 %/4.27 %/2.53 %/1.26 % | converging | 0.82 |
| `verticals.raised_vertical` | free | 62/116/232/464 | 2.32/1.28/0.684/0.358 | 5.4 %/2.98 %/1.59 %/0.834 % | converging | 0.92 |
| `verticals.raised_vertical` | somm | 62/116/232/464 | 2.28/1.26/0.675/0.353 | 4.56 %/2.52 %/1.35 %/0.708 % | converging | 0.92 |
| `verticals.rectangle` | free | 87/165/330/661 | 15.7/9.64/4.98/2.45 | 32.9 %/20.2 %/10.4 %/5.12 % | converging | 0.92 |
| `verticals.rectangle` | somm | 87/165/330/661 | 16.4/9.92/5.06/2.47 | 34.3 %/20.7 %/10.6 %/5.16 % | converging | 0.94 |
| `verticals.right_angle_delta` | free | 90/171/342/686 | 4/2.3/1.13/0.52 | 8.16 %/4.69 %/2.31 %/1.06 % | converging | 1.01 |
| `verticals.right_angle_delta` | somm | 90/171/342/686 | 4/2.3/1.13/0.519 | 8.51 %/4.89 %/2.41 %/1.11 % | converging | 1.01 |
| `verticals.stub_matched_vertical` | free | 85/160/320/640 | 3.39/1.9/0.98/0.584 | 6.88 %/3.84 %/1.99 %/1.18 % | converging | 0.88 |
| `verticals.stub_matched_vertical` | somm | 85/160/320/640 | 2.03/1.14/0.589/0.353 | 4.55 %/2.55 %/1.32 %/0.793 % | converging | 0.87 |
| `verticals.tri_moxon` | free | 252/468/939/1869 | 5.36/3.11/1.74/0.978 | 9.59 %/5.56 %/3.11 %/1.75 % | converging | 0.85 |
| `verticals.tri_moxon` | somm | 252/468/939/1869 | 5.41/3.14/1.76/0.988 | 9.66 %/5.6 %/3.13 %/1.76 % | converging | 0.85 |
| `verticals.vertical` | free | 85/160/320/640 | 1.52/0.861/0.45/0.269 | 6.88 %/3.9 %/2.04 %/1.22 % | converging | 0.86 |
| `verticals.vertical` | somm | 85/160/320/640 | 1.49/0.842/0.439/0.264 | 4.81 %/2.72 %/1.42 %/0.853 % | converging | 0.86 |
| `wire.doublet_balanced_tuner` | free | 60/115/230/461 | 1.78/0.715/0.12/0.281 | 3.64 %/1.47 %/0.247 %/0.577 % | non-monotone | 1.07 |
| `wire.doublet_balanced_tuner` | somm | 60/115/230/461 | 1.95/0.789/0.14/0.296 | 3.74 %/1.51 %/0.268 %/0.568 % | non-monotone | 1.08 |
| `wire.doublet_ladder_tuner` | free | 55/103/203/406 | 1.12/0.513/0.215/0.0747 | 2.63 %/1.2 %/0.504 %/0.175 % | converging | 1.35 |
| `wire.doublet_ladder_tuner` | somm | 55/103/203/406 | 1.27/0.577/0.236/0.0789 | 2.48 %/1.12 %/0.461 %/0.154 % | converging | 1.39 |
| `wire.edz` | free | 105/200/399/800 | 3/1.59/0.304/0.326 | 5.76 %/3.04 %/0.583 %/0.625 % | reference unsettled | — |
| `wire.edz` | somm | 105/200/399/800 | 3.02/1.6/0.302/0.334 | 5.58 %/2.95 %/0.558 %/0.618 % | reference unsettled | — |
| `wire.efhw_sloper` | free | 42/80/160/319 | 1.58/0.737/0.357/0.194 | 3.25 %/1.52 %/0.736 %/0.401 % | converging | 1.03 |
| `wire.efhw_sloper` | somm | 42/80/160/319 | 1.47/0.692/0.349/0.205 | 2.67 %/1.26 %/0.635 %/0.373 % | converging | 0.97 |
| `wire.expanded_lazy_h` | free | 210/400/798/1600 | 2.43/1.29/0.236/0.278 | 0.89 %/0.472 %/0.0865 %/0.102 % | reference unsettled | — |
| `wire.expanded_lazy_h` | somm | 210/400/798/1600 | 2.44/1.29/0.237/0.279 | 0.89 %/0.472 %/0.0866 %/0.102 % | reference unsettled | — |
| `wire.lazy_h` | free | 170/320/638/1280 | 256/146/5.68/74.8 | 3.61 %/2.06 %/0.0801 %/1.05 % | reference unsettled | — |
| `wire.lazy_h` | somm | 170/320/638/1280 | 255/146/5.67/74.6 | 3.61 %/2.06 %/0.0801 %/1.05 % | reference unsettled | — |
| `wire.longwire` | free | 293/558/1113/2228 | 7.39/3.06/1.44/0.759 | 5.59 %/2.32 %/1.09 %/0.574 % | converging | 1.12 |
| `wire.longwire` | somm | 293/558/1113/2228 | 7.44/3.08/1.45/0.762 | 5.62 %/2.33 %/1.1 %/0.576 % | converging | 1.12 |
| `wire.rhombic` | free | 1010/1924/3846/7688 | 3.13/2.45/0.49/1.91 | 0.437 %/0.342 %/0.0684 %/0.267 % | reference unsettled | — |
| `wire.rhombic` | somm | 1010/1924/3846/7688 | 3.17/2.47/0.492/1.92 | 0.438 %/0.342 %/0.068 %/0.266 % | reference unsettled | — |
| `wire.sterba` | free | 756/1440/2880/5760 | 14.3/1.36/0.758/1.67 | 2.18 %/0.207 %/0.116 %/0.256 % | non-monotone | 1.02 |
| `wire.sterba` | somm | 756/1440/2880/5760 | 14.6/1.42/0.784/1.71 | 2.21 %/0.215 %/0.119 %/0.259 % | non-monotone | 1.02 |
| `wire.sterba_bl` | free | 420/799/1600/3200 | —/—/—/— | —/—/—/— | refused | — |
| `wire.sterba_bl` | somm | 420/799/1600/3200 | —/—/—/— | —/—/—/— | refused | — |
| `wire.sterba_tl` | free | 81/156/321/644 | 6.84/5.79/2.95/1.68 | 8.25 %/6.98 %/3.56 %/2.02 % | converging | 0.71 |
| `wire.sterba_tl` | somm | 81/156/321/644 | 6.8/6.07/2.9/1.61 | 8.56 %/7.64 %/3.65 %/2.03 % | converging | 0.73 |
| `wire.terminated_longwire` | free | 1008/1920/3840/7680 | 204/58.4/18.1/22.7 | 5.8 %/1.66 %/0.512 %/0.643 % | reference unsettled | — |
| `wire.terminated_longwire` | somm | 1008/1920/3840/7680 | 4.38/1.17/0.1/0.835 | 0.971 %/0.259 %/0.0222 %/0.185 % | reference unsettled | — |
| `wire.vbeam` | free | 169/319/638/1278 | 98.2/40.8/19.2/17.6 | 2.81 %/1.17 %/0.548 %/0.503 % | reference unsettled | — |
| `wire.vbeam` | somm | 169/319/638/1278 | 107/44.5/20.9/19 | 2.94 %/1.22 %/0.573 %/0.523 % | reference unsettled | — |
| `wire.w8jk` | free | 106/204/410/820 | 8.91/4.91/1.73/0.142 | 1.18 %/0.651 %/0.23 %/0.0188 % | converging | 1.98 |
| `wire.w8jk` | somm | 106/204/410/820 | 8.9/4.91/1.73/0.142 | 1.18 %/0.651 %/0.23 %/0.0188 % | converging | 1.97 |
| `wire.zepp` | free | 41/77/154/307 | 7.18/7.15/7.14/0.815 | 42.7 %/42.5 %/42.5 %/4.85 % | converging | 0.98 |
| `wire.zepp` | somm | 41/77/154/307 | 7.16/7.14/7.13/0.812 | 42.3 %/42.2 %/42.1 %/4.8 % | converging | 0.98 |

## 7. Reading the ladder

### razor-2p is first order, and the order is measured not assumed

155 of 204 classifiable rows converge toward bs2@160, with a fitted order of
**median 0.90** (p10 0.82, p90 1.24) against the achieved segment count. That is
first order in the mesh, which is what momwire's own `RazorFarMeshClass` advisory
declares and what AK#1516 measured on four designs. It now holds across the
catalog rather than on four cases.

`loops.skyloop_lmatch` fits **2.08** on both grounds, against AK#1516's 1.94–2.34
for the bs2−NEC-5 gap on the same design — the one design in the study whose error
falls quadratically. Predicted in advance (E2b) and hit.

### What ×40 costs in accuracy — and a correction about what was served

**Correction, 2026-09-16.** Everything below said ×40 was "the density the app
serves". It is razor-2p's *declared roster default*, and the app never reached it.
No stock slot seeds razor-2p — the served seeds are bspline at 15, bspline d=1 at
20 and PyNEC — so razor-2p is only arrived at by swapping a slot's backend, and
`useSolverSlots.ts:setSlotBackend` preserves `nPerWire` across the swap, overriding
the very field the roster default would have set. Users ran razor-2p at **15 or
20**. AK#1547 fixes that.

Both are at or below this ladder's lowest rung, so **this study never measured the
density users actually had**, and every figure here understates the real error.
The nearest measured point is ×21: median **3.64 %**, p90 **10.7 %**, worst
**54.7 %** — and since error falls with N, that is a *lower bound* on what 15 gave.
Measuring 15 and 20 properly would need two more rungs; it is not done here.

At `default_n_per_wire=40` razor-2p sits a
**median 2.42 %** from bs2@160 over its 155 converging rows, p90 **7.64 %**, worst
**42.5 %**. Doubling to 80 removes about half of that: the median
`err(80)/err(40)` is **0.519**, which is what first order predicts and is the one
E3 component that landed inside its bar.

**No recommendation follows from this page.** Density is a product call; the curve
is here and the cost is below.

### What doubling density costs, and why my cost bars missed

E3's wall and RSS bars missed, and the reason is that **I set them from the two
biggest designs and then scored them on a median over a population of small
ones.** Split by size, the model is fine:

| population | rows | median wall ×80/×40 | median RSS ×80/×40 |
|---|---:|---:|---:|
| achieved N at ×80 **< 2000** | 183 | **2.22** | **1.25** |
| achieved N at ×80 **≥ 2000** | 16 | **3.99** | **3.20** |

The registered bars were 3.0–5.0 and 1.5–4.0. The large designs land inside both;
the small ones do not, because a ~90 MB interpreter-and-numpy floor and a fixed
per-solve setup dominate anything with a few hundred segments. The O(N²) fill only
governs once N is big enough to matter.

The practical form of that, which is the useful half: **doubling the
density is cheaper than the asymptotic model suggests for most of the catalog.**
Median cold solve goes 0.106 s at ×40 to 0.205 s at ×80; the catalog total goes
60 s to 160 s; the worst single solve goes 5.4 s to 20.3 s. The ×160 rung costs
641 s in total and 102 s on its worst design.

### 30 rows cannot be adjudicated, and that is the yardstick's own result

Under #845's one-third rule, **30 razor rows are `reference unsettled`**: bs2
itself moved between ×80 and ×160 by more than a third of the error being judged,
so bs2 at rung 160 cannot arbitrate those designs. E4 predicted 10–40 and hit.
This is the answer to "is bs2 a usable yardstick" — **mostly, with 30 named
exceptions** — and it is a measured output rather than the assumption the original
D4 would have made.

12 further rows are `non-monotone`: the error does not fall cleanly across the four
rungs. 5 are refusals (razor has no buried fill), 2 are `not converging`, and 2 are
the skipped design.

### E1 missed, and most of the change is the metric, not the code

**33 rows changed class** against probe3's prediction (75.5 % strict agreement,
82.4 % excluding the 17 rows probe3 never measured; the bar was 90 %). Before
reading those as regressions, note what changed between the two measurements:

* probe3 used **port 0 alone**; this ladder uses an **all-port norm**. On a
  multi-port design those differ by up to the square root of the port count.
* probe3's reference was **bs2 at 4× (84 segments)**; this ladder's is **bs2 at
  160**, and the one-third rule is applied against that finer reference. A finer
  reference with a smaller own-movement changes which rows trip the rule.
* probe3 swept **1× / 2× / 4×**; this ladder is **21 / 40 / 80 / 160**.
* probe3 ran on a **2026-09-03** build.

The largest single group of changes — 8 rows moving `converging` →
`reference unsettled` — is what a stricter, differently-scaled application of the
one-third rule produces, not a code regression. Four rows moved the other way
(`reference unsettled` / `unexplained` → `converging`), and the helices in
particular now resolve. **I am not claiming which cause applies to which row**:
the appendix carries the achieved counts, ohms and percentages for all of them,
and separating metric from code would need probe3 re-run on current code with this
metric, which is a different job.

### F2 missed: a design's source changing is not its answer changing

F1 held exactly — all 1,680 cells are bit-identical to the pre-v0.79.0 ladder —
which confirms the reading that momwire's six commits touch only the EZNEC
printout shell and nothing on the solver path.

F2 predicted `verticals.buried_radial_vertical` would move, because v0.79.0
changed 21 lines of that design. **It did not move at all.** The change gives the
mast and feed-gap wires an explicit bare spec so they stop inheriting a jacket
from `build_wire_material()` — but at this design's *default* parameters
`wire_type` is `None` and `build_wire_material()` returns `None`, so there was no
jacket to inherit and the change is a no-op. It bites only the `-pvc` variants,
which the catalog does not solve at defaults.

The lesson is narrow and worth keeping: **"this design's source changed" does not
imply "this design's default answer changed."** A variant-only change moves
nothing at catalog defaults, and F2 was a guess dressed as an inference.

## 8. Reproducing

```
NEC5_EXE=<nec5cl-3b75639> python scratch/1525-razor-density/run_density.py \
  --out scratch/1525-razor-density/records.jsonl
python scratch/1525-razor-density/report.py > scratch/1525-razor-density/README.md
```

1,680 cells in 3,746 s. The staleness guard runs first and aborts before the first
cell if a gating check fails; its output is the records file's first line. The
NEC-5 binary is licensed (LLNL-CODE-746721), lives outside this repo and is run as
an executable; nothing here carries its source or printouts.

