# razor-2p, NEC-5 and momwire bs2 over the antennaknobs catalog

**Evidence, not a scoreboard.** Every built-in design solved three ways at its own default mesh and frequency, in free space and over Sommerfeld ground, and the three pairwise disagreements reported as distributions. The page states what the three engines do and do not agree about. It does not rank them.

**The builds, named because a version string does not identify a solver.** antennaknobs **main `97ca2b6b0`**, run from a study branch (`4847554b5`) that adds only this study's harness and records; momwire **0.55.0** imported from the editable submodule at `1ca872511` with a clean working tree — which is also the commit antennaknobs records as its pointer, so this run is the momwire a user installs rather than a dev tip ahead of it. The compiled accelerator actually in use was **`_accelerators_avx2`**; momwire ships more than one SIMD variant behind that module name and they are not bit-identical to each other, so the variant is recorded with the data. NEC-5 is the build `nec5cl-3b75639`, run as an executable; antennaknobs never inspects it.

**NEC-5 licensing.** NEC-5 is licensed from Lawrence Livermore National Laboratory (**LLNL-CODE-746721**). Neither its source nor any of its printouts appears here or in the committed data: the NEC-5 column is driving-point impedances and aggregates computed from them, and nothing else.

Per-design rows, and the run's own provenance record, are committed beside this page in `data/2026-09-15-catalog-razor-nec5-bs2.jsonl`. Every table below is generated from that file by `scratch/catalog-razor-nec5-bs2/status_page.py`; no number on this page is transcribed.

## The one thing to read before any table

> **The mesh reading, scoped to what was measured.** On the four designs AK#1516 refined eightfold — `loops.skyloop_lmatch`, `verticals.rectangle`, `dipoles.koch_dipole` and `verticals.four_square` — razor-2p and NEC-5 moved **18–33 % together, toward momwire bs2**, while bs2 moved **≤ 2.4 %**. On those four, a wide bs2 row is a statement about mesh density. **That is four designs, not the catalog**: for every other row the class column says what is and is not known, and the density question itself is AK#1525.

This is stated first, and again beside every table that puts bs2 next to one of the other two, because the raw numbers invite the opposite reading: bs2 is the engine that most often sits apart, and it is also the engine nearest its own mesh limit. Both are true at once.

## What this page can and cannot say

* It can say how far apart the three engines are on a driving-point impedance, per design, at the mesh each design ships with.
* It can say which designs an engine declines, and why, in the engine's own words.
* **It cannot say which engine is right.** No reference here is a truth oracle; the denominator in each ratio is a choice of reference and nothing more. The one adjudication on offer is the mesh-convergence one above, which is measured (AK#1516) rather than asserted.
* It cannot speak for any mesh but the default. Density is AK#1525.

## Method

103 designs × 2 ground models × 3 engines = **618** cells, 618 recorded. One worker subprocess per cell, dispatched serially, each with an address-space cap so a runaway fill fails cleanly instead of paging the machine; BLAS and OpenMP pinned to four threads. Each design is solved at its own default frequency and its shipped `nominal_nsegs`, with no per-design tuning.

Ground models are free space and the Sommerfeld-Norton finite ground `("finite", 13.0, 0.005)`, which is the application's default soil. **The reflection-coefficient ground is not on this page because NEC-5 has no such model**: its `IPERF 0` is a full Sommerfeld solution, and antennaknobs' NEC-5 engine refuses a `finite-fast` ground by name rather than silently upgrading the physics (`engines/nec5.py:_normalise_ground`). There is therefore no NEC-5 row to compare against, so the model is left off for all three engines rather than shown for two of them.

Disagreement is reported as `rel|ΔZ| = |Z_a − Z_b| / |Z_b|`, one row per design × ground × port, and only where both engines solved and returned the same number of ports. Cells where one side declined are counted as unpaired rather than dropped, so coverage is a number on the page and not a smaller denominator.

## Coverage

| engine | solved | declined | error | timeout |
|---|---:|---:|---:|---:|
| razor-2p | 201 | 5 | 0 | 0 |
| NEC-5 | 195 | 10 | 1 | 0 |
| momwire bs2 | 206 | 0 | 0 | 0 |

Where an engine declined, in its own words:

| engine | reason | cells |
|---|---|---:|
| razor-2p | no buried fill | 3 |
| razor-2p | junction ports | 2 |
| NEC-5 | a distributed (finite-gap) port | 6 |
| NEC-5 | a floating port's second terminal | 4 |
| NEC-5 | a non-reciprocal multiport Y | 1 |

## Agreement on the driving-point impedance

### razor-2p against NEC-5

| population | rows | median | p90 | p99 | max | < 0.1 % | < 2 % |
|---|---:|---:|---:|---:|---:|---:|---:|
| all | 340 | 0.0664 % | 0.283 % | 1.4 % | 2 % | 65.6 % | 99.7 % |
| free space | 172 | 0.0456 % | 0.142 % | 0.515 % | 0.655 % | 79.1 % | 100 % |
| Sommerfeld | 168 | 0.0965 % | 0.38 % | 1.86 % | 2 % | 51.8 % | 99.4 % |
| single-port designs | 148 | 0.0756 % | 0.25 % | 0.619 % | 0.655 % | 61.5 % | 100 % |
| multi-port designs | 192 | 0.0607 % | 0.29 % | 1.86 % | 2 % | 68.8 % | 99.5 % |

Unpaired: **14** design×ground cells where one side declined. Port-count mismatches: **0**.

### momwire bs2 against NEC-5

> **The mesh reading, scoped to what was measured.** On the four designs AK#1516 refined eightfold — `loops.skyloop_lmatch`, `verticals.rectangle`, `dipoles.koch_dipole` and `verticals.four_square` — razor-2p and NEC-5 moved **18–33 % together, toward momwire bs2**, while bs2 moved **≤ 2.4 %**. On those four, a wide bs2 row is a statement about mesh density. **That is four designs, not the catalog**: for every other row the class column says what is and is not known, and the density question itself is AK#1525.

| population | rows | median | p90 | p99 | max | < 0.1 % | < 2 % |
|---|---:|---:|---:|---:|---:|---:|---:|
| all | 343 | 1.55 % | 10.3 % | 49.2 % | 54.3 % | 2.92 % | 54.8 % |
| free space | 172 | 1.51 % | 9.2 % | 49.6 % | 53.6 % | 2.33 % | 54.7 % |
| Sommerfeld | 171 | 1.61 % | 10.4 % | 49.2 % | 54.3 % | 3.51 % | 55 % |
| single-port designs | 151 | 3.65 % | 11.5 % | 53.6 % | 54.3 % | 0 % | 31.8 % |
| multi-port designs | 192 | 0.774 % | 7.17 % | 22.1 % | 22.1 % | 5.21 % | 72.9 % |

Unpaired: **11** design×ground cells where one side declined. Port-count mismatches: **0**.

### momwire bs2 against razor-2p

> **The mesh reading, scoped to what was measured.** On the four designs AK#1516 refined eightfold — `loops.skyloop_lmatch`, `verticals.rectangle`, `dipoles.koch_dipole` and `verticals.four_square` — razor-2p and NEC-5 moved **18–33 % together, toward momwire bs2**, while bs2 moved **≤ 2.4 %**. On those four, a wide bs2 row is a statement about mesh density. **That is four designs, not the catalog**: for every other row the class column says what is and is not known, and the density question itself is AK#1525.

| population | rows | median | p90 | p99 | max | < 0.1 % | < 2 % |
|---|---:|---:|---:|---:|---:|---:|---:|
| all | 349 | 1.58 % | 11.5 % | 49.2 % | 54.7 % | 2.87 % | 54.4 % |
| free space | 176 | 1.59 % | 11.5 % | 49.5 % | 54 % | 2.27 % | 53.4 % |
| Sommerfeld | 173 | 1.57 % | 10.5 % | 49.2 % | 54.7 % | 3.47 % | 55.5 % |
| single-port designs | 157 | 3.75 % | 12.9 % | 54 % | 54.7 % | 0 % | 30.6 % |
| multi-port designs | 192 | 0.739 % | 7.27 % | 22.1 % | 22.1 % | 5.21 % | 74 % |

Unpaired: **5** design×ground cells where one side declined. Port-count mismatches: **0**.

### In one line

Over the whole catalog at default mesh, razor-2p and NEC-5 agree to a median **0.0664 %** and their widest single row is **2 %**. momwire bs2 sits a median **1.55 %** from NEC-5 and **1.58 %** from razor-2p, with a tail to **54.3 %**. How to read that tail is not one answer: four of its widest designs are AK#1516's mesh finding, and the single widest row of all — `dipoles.short_dipole_loaded` — is **not yet explained**, because the reference it is measured against has not settled at that design's shipped mesh either. The class column on each table below says which is which.

## The widest disagreements

> **The mesh reading, scoped to what was measured.** On the four designs AK#1516 refined eightfold — `loops.skyloop_lmatch`, `verticals.rectangle`, `dipoles.koch_dipole` and `verticals.four_square` — razor-2p and NEC-5 moved **18–33 % together, toward momwire bs2**, while bs2 moved **≤ 2.4 %**. On those four, a wide bs2 row is a statement about mesh density. **That is four designs, not the catalog**: for every other row the class column says what is and is not known, and the density question itself is AK#1525.

**`|ΔZ|` in ohms is given beside the relative figure**, because on a low-impedance or near-open design a percentage misleads: the widest row on this page is a ~7 Ω reactance difference on a driving point of about 13 Ω.

**The class column is generated, not asserted.** It comes from `scratch/845-mesh-policy/probe3_sweep.json`, a 1× / 2× / 4× mesh sweep of the catalog measured on an **older build** (2026-09-03), with #845's own resolution rule applied: a design whose *reference* moved by more than a third of the quantity being judged is marked `reference unsettled` rather than classified, because a reference that is still moving cannot adjudicate anything. probe3's metric is **port 0 alone**, so the class is a property of the design and ground, not of the individual port row beside it. **Every one of these classes will be re-measured on current code by AK#1525**, and a design that changes class there is a finding.

Where **AK#1516** covers a row it overrides probe3, because it refined that exact pair eightfold while probe3 only ever compared razor-2p against bs2. That distinction changes answers: on `verticals.four_square` over Sommerfeld the bs2-against-NEC-5 gap closes from 19.0 % to 2.7 %, while the razor-2p-against-NEC-5 gap holds at 1.78 % → 1.74 %. Only the first is a density story.

**Only a class saying the gap CLOSES explains a wide row.** `does NOT close under refinement` is a measured finding rather than an explanation — it says density is not the cause and names the issue tracking it. `reference unsettled`, `not converging`, `unexplained` and `not measured` all mean the same thing for a reader: **the disagreement on that row has no established cause yet.**

### razor-2p against NEC-5 — ten widest rows

| design | ground | port | razor-2p Z | NEC-5 Z | \|ΔZ\| Ω | rel\|ΔZ\| | class |
|---|---|---:|---|---|---:|---:|---|
| `verticals.four_square` | Sommerfeld | 0 | 25.16-34.13j | 25.51-33.37j | 0.842 | 2 % | does NOT close under refinement (AK#1526) |
| `verticals.four_square` | Sommerfeld | 2 | 27.38-4.156j | 27.69-3.737j | 0.52 | 1.86 % | does NOT close under refinement (AK#1526) |
| `verticals.four_square` | Sommerfeld | 1 | 27.38-4.156j | 27.69-3.737j | 0.52 | 1.86 % | does NOT close under refinement (AK#1526) |
| `verticals.four_square` | Sommerfeld | 3 | 25.17+31.81j | 25.43+32.33j | 0.576 | 1.4 % | does NOT close under refinement (AK#1526) |
| `verticals.dominator` | free space | 0 | 30.8+2.138j | 30.78+2.338j | 0.202 | 0.655 % | not measured (probe3 cannot speak to this pair) |
| `arrays.bowtie16x1` | Sommerfeld | 13 | 756.9-83.91j | 760.6-87.03j | 4.8 | 0.627 % | not measured (probe3 cannot speak to this pair) |
| `arrays.bowtie16x1` | Sommerfeld | 2 | 756.9-83.91j | 760.6-87.03j | 4.8 | 0.627 % | not measured (probe3 cannot speak to this pair) |
| `verticals.dominator` | Sommerfeld | 0 | 28.84+3.581j | 28.8+3.755j | 0.18 | 0.619 % | not measured (probe3 cannot speak to this pair) |
| `wire.terminated_longwire` | Sommerfeld | 0 | 448.7-22.86j | 451.3-22.3j | 2.66 | 0.59 % | not measured (probe3 cannot speak to this pair) |
| `verticals.phased_verticals` | Sommerfeld | 1 | 96.28+175.6j | 95.22+176j | 1.15 | 0.576 % | not measured (probe3 cannot speak to this pair) |

Designs in this table with **no established cause**: `arrays.bowtie16x1`, `verticals.dominator`, `verticals.four_square`, `verticals.phased_verticals`, `wire.terminated_longwire`.

### momwire bs2 against NEC-5 — ten widest rows

| design | ground | port | momwire bs2 Z | NEC-5 Z | \|ΔZ\| Ω | rel\|ΔZ\| | class |
|---|---|---:|---|---|---:|---:|---|
| `dipoles.short_dipole_loaded` | Sommerfeld | 0 | 13.79-5.974j | 13.28+1.256j | 7.25 | 54.3 % | reference unsettled |
| `dipoles.short_dipole_loaded` | free space | 0 | 13.52-4.063j | 13.02+3.097j | 7.18 | 53.6 % | reference unsettled |
| `loops.skyloop_lmatch` | free space | 0 | 47.54-6.478j | 31.49-8.296j | 16.2 | 49.6 % | closes under refinement (AK#1516) |
| `loops.skyloop_lmatch` | Sommerfeld | 0 | 47.16-6.229j | 31.34-8.048j | 15.9 | 49.2 % | mesh (probe3) |
| `verticals.rectangle` | Sommerfeld | 0 | 47.19+7.746j | 46.86-8.598j | 16.3 | 34.3 % | mesh (probe3) |
| `verticals.rectangle` | free space | 0 | 47.72+1.849j | 43.7-13.29j | 15.7 | 34.3 % | closes under refinement (AK#1516) |
| `dipoles.koch_dipole` | Sommerfeld | 0 | 35.19+1.451j | 35.52+13.43j | 12 | 31.6 % | mesh (probe3) |
| `dipoles.koch_dipole` | free space | 0 | 35.25+6.269j | 35.59+18.3j | 12 | 30.1 % | closes under refinement (AK#1516) |
| `verticals.four_square` | free space | 1 | 28.54+1.705j | 27.6-4.401j | 6.18 | 22.1 % | closes under refinement (AK#1516) |
| `verticals.four_square` | free space | 2 | 28.54+1.705j | 27.6-4.401j | 6.18 | 22.1 % | closes under refinement (AK#1516) |

Designs in this table with **no established cause**: `dipoles.short_dipole_loaded`.

### momwire bs2 against razor-2p — ten widest rows

| design | ground | port | momwire bs2 Z | razor-2p Z | \|ΔZ\| Ω | rel\|ΔZ\| | class |
|---|---|---:|---|---|---:|---:|---|
| `dipoles.short_dipole_loaded` | Sommerfeld | 0 | 13.79-5.974j | 13.28+1.31j | 7.3 | 54.7 % | reference unsettled |
| `dipoles.short_dipole_loaded` | free space | 0 | 13.52-4.063j | 13.02+3.151j | 7.23 | 54 % | reference unsettled |
| `loops.skyloop_lmatch` | free space | 0 | 47.54-6.478j | 31.52-8.284j | 16.1 | 49.5 % | closes under refinement (AK#1516) |
| `loops.skyloop_lmatch` | Sommerfeld | 0 | 47.16-6.229j | 31.34-8.161j | 15.9 | 49.2 % | mesh (probe3) |
| `verticals.rectangle` | Sommerfeld | 0 | 47.19+7.746j | 46.74-8.838j | 16.6 | 34.9 % | mesh (probe3) |
| `verticals.rectangle` | free space | 0 | 47.72+1.849j | 43.57-13.48j | 15.9 | 34.8 % | closes under refinement (AK#1516) |
| `dipoles.koch_dipole` | Sommerfeld | 0 | 35.19+1.451j | 35.52+13.47j | 12 | 31.6 % | mesh (probe3) |
| `dipoles.koch_dipole` | free space | 0 | 35.25+6.269j | 35.59+18.33j | 12.1 | 30.1 % | closes under refinement (AK#1516) |
| `verticals.four_square` | Sommerfeld | 1 | 28.29+1.894j | 27.38-4.156j | 6.12 | 22.1 % | closes under refinement (AK#1516) |
| `verticals.four_square` | Sommerfeld | 2 | 28.29+1.894j | 27.38-4.156j | 6.12 | 22.1 % | closes under refinement (AK#1516) |

Designs in this table with **no established cause**: `dipoles.short_dipole_loaded`.

## Reactance carries the disagreement

For each pair, the share of `rel|ΔZ|` attributable to the reactive part rather than the resistive one, as a median over all rows. A pair that disagrees about X and agrees about R is disagreeing about the feed region and the near field, not about radiated power.

| pair | rows | median share carried by X |
|---|---:|---:|
| razor-2p / NEC-5 | 340 | 0.966 |
| momwire bs2 / NEC-5 | 343 | 0.949 |
| momwire bs2 / razor-2p | 349 | 0.954 |

## Publication discipline

Per-design rows for all three engines are committed beside this page, including the NEC-5 impedances, because an impedance is a number this project computed and not a NEC-5 artifact. What is not committed and not quoted anywhere is any NEC-5 printout, deck output or source detail (LLNL-CODE-746721). The distinction is deliberate and it is the same one the corpus census draws.

The committed record also carries the run's provenance as its first line — both repository SHAs, both package versions, the resolved path of every compiled extension and the SIMD variant in use. A reader who has the data file does not need this page to know what produced it.

<sub>Environments — antennaknobs `4847554b55f42c71d26f9e09ebfdad6396d7dc6b`; momwire `1ca87251191c6b5bc32c9734a6275354da2e2c43` (v0.55.0), version 0.55.0, clean; accelerators `_accelerators_avx2.cpython-314-x86_64-linux-gnu.so` and `_near_interface_accel_avx2.cpython-314-x86_64-linux-gnu.so`; antennaknobs 0.78.0; Python 3.14.5; NEC-5 `nec5cl-3b75639`. Four threads, one solve at a time.</sub>
