# antennaknobs#1525 — razor-2p density ladder over the catalog

**Measurement only. No recommendation on the default** — density is Steve's
product call; this gives him the curve. Registered 2026-09-15 before the first
ladder solve; §6 discloses what was already measured when the bars were set.

## 1. The question

The #1516 ladders (`scratch/1516-ladders`) showed that razor-2p and NEC-5 are the
*unconverged* pair at the shipped mesh on four designs, that the error is first
order in the mesh on three of them, and that at the density the app actually
serves razor-2p — `default_n_per_wire=40`, which `adapter.py` assigns straight to
`builder.nominal_nsegs` — the residual was still 8.6–20.8 %. That was four
designs. This asks the same question of all 103, and prices it.

## 2. Setup

| axis | value |
|---|---|
| antennaknobs | **PR #1532 head `3b0d942a9`** (`fix/1523-nec5-equivalent-radius`), still OPEN as of this run. This branch is cut FROM it, so the branch *is* the code the numbers came from. Chosen over `main` so any NEC-5 column carries #1523's jacket fix, per the brief. |
| momwire | submodule pointer `1ca8725`; #1532 does not move it |
| NEC-5 | `nec5cl-3b75639` |
| designs | all 103 built-ins |
| rungs | `nominal_nsegs` = **21, 40, 80, 160** (40 is the served razor density) |
| grounds | `somm` = `("finite", 13.0, 0.005)` — the app default — **and** `free` |
| threads | `OMP_NUM_THREADS = OPENBLAS_NUM_THREADS = MKL_NUM_THREADS = 4` |
| dispatch | one worker subprocess at a time, `RLIMIT_AS` **40 GB**, timeout **1200 s** |

**Engines: razor-2p AND bs2 at every rung**, not bs2 at its defaults only. That is
one deliberate extension of the brief and it is cheap (≈40 min of solve time for
the whole job, measured — see §6). The reason is D4: "error against bs2" is only a
meaningful yardstick if bs2 is not itself moving, and #1516 established that for
four designs, not 103. Running bs2's own ladder measures the yardstick instead of
assuming it. NEC-5 additionally runs at matched density on the four #1516 designs
(`loops.skyloop_lmatch`, `verticals.rectangle`, `dipoles.koch_dipole`,
`verticals.four_square`), which the brief called optional and worth having.

1,680 cells: 103 × 4 rungs × 2 grounds × 2 engines, plus 4 × 4 × 2 for NEC-5.

**A rung that breaches the memory cap or the timeout is a RECORD, not a gap** —
status `error`/`timeout` with the engine's own message, and it appears in the
tables as such. The largest cell measured so far is `arrays.bowtie16x1` at rung
160: 10,496 segments, 98.7 s, **15.5 GB** peak RSS. Memory is the ceiling here,
not cores.

## 3. Metrics

* Per cell: Z at every port, **cold and warm wall time** (two `impedance()` calls
  in the same worker; the warm one re-solves with caches hot), `solve_s`, peak
  RSS, the built segment count, status.
  *Caveat recorded with the number*: peak RSS is a per-process high-water mark, so
  the figure covers both solves and cannot be split between them.
* Error against **bs2 at rung 160** on the same design and ground, per port —
  the best available approximation to the converged answer, and the reason bs2's
  own ladder is run. Error against **bs2 at its defaults** is reported beside it,
  since that is the yardstick the brief named.
* Fitted exponent per design: least squares on `log(error)` against `log(N)` over
  the four rungs, using the **built** segment count, not the knob.
* Cost: `wall(80)/wall(40)` and `peakRSS(80)/peakRSS(40)`, per design and as
  distributions.

## 4. Predictions — registered before the first ladder solve

* **D1.** The per-design fitted exponent of razor's error is first order: **median
  in 0.8–1.3**, and **≥ 70 %** of designs with a fittable exponent fall in
  0.7–1.5.
* **D2.** `loops.skyloop_lmatch` is the known exception — its exponent lands in
  **1.7–2.4** (#1516 measured 1.94–2.34 for the bs2−NEC-5 gap on the same design).
* **D3.** What 80 buys over 40: median `err(80)/err(40)` in **0.45–0.60** (first
  order predicts 0.5). Cost: median `wall(80)/wall(40)` in **3.0–5.0** (an O(N²)
  fill with N doubling gives 4), median `peakRSS(80)/peakRSS(40)` in **1.5–4.0** —
  below 4 because a ~90 MB interpreter-plus-numpy floor dominates the small
  designs.
* **D4 (the yardstick).** bs2 at its defaults is within **2 %** of bs2 at rung 160
  on **≥ 80 %** of design×ground rows. A miss here means "error vs bs2 at
  defaults" is the wrong frame and the rung-160 column is the one to read; either
  way both are reported.
* **D5.** Fewer than **20** designs still show razor error above 2 % against
  bs2@160 at rung 160.

Misses are reported as misses, with the number that missed them.

## 5. Deliverables

* per-design error against bs2 at each rung, with the fitted exponent;
* a catalog summary of what 80 buys over 40 — accuracy, wall-time ratio, RSS ratio;
* the designs where 160 is still far off;
* **no recommendation on the default.**

## 6. Disclosure: what was measured before the bars were written

Sizing probes only, all on razor over Sommerfeld, at `3b0d942a9`:

* `wire.rhombic` rung 160: 7,688 segments, **49.6 s**, 688.0 − 219.9j
* `arrays.bowtie16x1` rung 160: 10,496 segments, **98.7 s**, 15.5 GB peak RSS,
  321.7 − 3.776j
* `verticals.elt_whip` rungs 40 and 80: 4,417 and 4,471 segments, **74.7 s** and
  **74.6 s** — this design's mesh barely responds to the knob, because its
  per-edge counts are mostly fixed. The naive projection had it at 33,462
  segments and 16.7 GB at rung 160; it is actually 4,577. That is why the job is
  affordable, and it is a fact about the catalog rather than about razor.

From the first two points, cost fits `t ≈ 8.96e-7 · N²` s, which predicts ~13 min
of razor solve time for all four rungs on one ground and ~40 min for the whole
job including bs2's ladder. **No impedance from any of these probes enters the
ladder tables** — the harness re-solves every cell. The probes set the timeout,
the memory cap and D3's cost bars, and they are the reason D3's RSS bar is a
range rather than 4.

Not measured before the bars: any error against bs2, any exponent, any rung-40
or rung-160 accuracy figure, and the whole of D1, D2, D4 and D5.

## 7. Output

Branch `scratch/1525-razor-density`, cut from `3b0d942a9`. No PR, no issue or PR
comments. NEC-5 conclusions, impedances and timings only.

* `run_density.py` — harness (driver + `--worker`)
* `records.jsonl` — one record per design × ground × rung × engine
* `report.py` — writes every table in `README.md` from the JSONL
* `hypotheses.md` — the reading, included verbatim by `report.py`
* `README.md` — the tables, the cost summary, D1–D5 scored

## 8. Amendment: dev mode (2026-09-15, before any recorded rung)

Appended, not edited in place; §4's bars stand as registered. The sweep begun at
`3b0d942a9` + momwire `1ca8725` was **stopped after 14 cells and those records
discarded** — moving momwire changes the solver, so they were the wrong
configuration, and 14 cells is cheaper to throw away than an hour.

| axis | value |
|---|---|
| antennaknobs | **`97ca2b6b0`** — main with #1532 merged. Its tree is `87602a506` , **byte-identical to the PR head `3b0d942a9`** §2 named, verified by comparing tree objects. This branch was rebased onto it. |
| momwire | **branch `main` at `227491d`**, the dev tip — **79 commits ahead** of the recorded pointer `1ca8725`. Rebuilt with `make build` (so `MOMWIRE_REQUIRE_ACCEL=1`); `momwire._accelerators` and `momwire._near_interface_accel` both resolve to the `_avx2` builds under `momwire/src/momwire/`, and `importlib.metadata` reports 0.55.0. |
| recorded pointer | still `1ca8725` in AK's tree. **`momwire` is never staged** — `git status` showing `M momwire` is the intended dev-mode state. |

### What momwire's 79 commits do to the numbers: nothing measurable here

Those commits include a real numeric-path change — `b2530ab perf(below): fill a
zone's floor and low bands in one evaluation call when both need filling
(momwire#1064 G5)` — so "79 scratch commits, probably inert" was not good enough
to assume. It was measured instead: `momwire-main-delta.jsonl` re-runs job 1's 18
cells (the three jacketed designs × free/Sommerfeld × razor/NEC-5/bs2) with the AK
tree held identical and only momwire moved.

**All 18 rows are bit-identical to the `1ca8725` records.** 0 of 6 moved for
razor, 0 of 6 for bs2, 0 of 6 for NEC-5, worst relative move 0.00000 %.

Two things that follows and one it does not:

* Job 1's result at the recorded pointer stands unchanged, and there is no
  momwire-attributable difference to report separately for it.
* The ladder's razor and bs2 columns are comparable with the catalog run at
  `b9bc3e2f0` on these designs.
* **It does NOT establish catalog-wide inertness.** All three probe designs sit
  above ground, and `b2530ab` is a *below-interface* fill change, so the geometry
  that could move it — the buried designs — is exactly what the probe does not
  cover. Any buried-design row in this ladder that disagrees with the catalog run
  is a momwire-main candidate first and a density effect second.

## 9. Re-registered 2026-09-15 — revised design, and D1–D5 superseded

Laptop-builder's revision changes the reference and adds a classification, so the
§4 bars no longer describe what is being measured. **D1–D5 are superseded, not
quietly reused**, and the reason is stated for each below. New bars are E1–E5,
registered before any rung of this configuration was solved.

### Configuration

| axis | value |
|---|---|
| antennaknobs | main `97ca2b6b0`, study branch on top |
| momwire | **dev mode**: branch `main` at `227491d`, 79 commits past the recorded pointer, rebuilt with `make build` |
| staleness guard | `verify_env.py --dev-mode` passes; the pointer check is run, **recorded as excused**, and the other six gate |
| NEC-5 | `nec5cl-3b75639`, matched density, on the four AK#1516 designs only |
| rungs | `nominal_nsegs` = **21, 40, 80, 160**, for **both** razor-2p and bs2 |
| reference | **bs2 at rung 160** |
| grounds | free and Sommerfeld `("finite", 13.0, 0.005)` |

**One stated deviation from the brief.** The brief asked for bs2 at 1× / 2× / 4×
of the shipped mesh (21 / 42 / 84) with bs2@4× as the reference. This runs both
engines on the *same* four rungs, 21 / 40 / 80 / 160, and takes **bs2@160** as the
reference. Two reasons: 40 is the served razor density and has to be a rung, and a
shared x-axis is what lets one exponent be fitted per pair without interpolating.
bs2@160 is a finer reference than bs2@4× would have been, so the reference-movement
rule below is applied against a better reference, not a worse one.

### The metric, stated once and used everywhere

Relative error is `|Z_a − Z_b| / |Z_b|` with the port impedances taken as
**vectors over all ports** — an all-port norm. **Every ohm figure in this study is
the numerator of that same expression**, `|Z_a − Z_b|` over all ports, so the ohms
and the percentage beside them are the same quantity. This is *not* probe3's
metric, which is port 0 alone: on the four-port `arrays.moxonarray` probe3 reads
9.068 Ω where this study's norm reads 18.0. probe3 is used for the **predicted
class** and for nothing else.

### Classification, keyed on the pair

Per (pair, design, ground), from this run's own data:

* **converging** — the gap shrinks monotonically across the rungs; the fitted
  order is reported with it.
* **reference unsettled** — #845's rule: the reference's own movement between the
  last two rungs exceeds **one third** of the quantity being judged. Marked
  unresolved and **not tabulated as a convergence result**.
* **not converging** — the gap at the top rung is no smaller than at ×1.
* **refused** — an engine declined; the reason is recorded.

**A class is only ever applied to the pair it was measured on.** That rule exists
because the published page got it wrong twice: a measurement of razor-against-bs2
cannot say whether razor-against-NEC-5 closes, since those two move together under
refinement, and AK#1516's records show their mutual gap is flat while both
converge. Job 2's primary comparison is razor against bs2 — the same pair probe3
measured — so the predicted classes transfer without any cross-pair inference.
Where a NEC-5 column is present, its classes are computed separately.

### Achieved mesh, not the requested knob

`nominal_nsegs` is a density and each design decides which edges follow it. Every
cell records the **achieved** segment count, and a design whose mesh does not
respond to the knob is reported as **its own finding**, not as a convergence
result: `verticals.elt_whip` goes 4392 → 4577 segments across 21 → 160, a 1.04×
refinement, so any statement about how its error behaves "under ×7.6 refinement"
is false on its face.

### Predictions

Predicted classes are committed as `predicted-classes.json` — probe3's class for
all 206 design×ground rows, computed with #845's rule. **Any row that changes
class is a finding**, reported with its design, ground and both classes.

* **E1.** ≥ **90 %** of the 206 rows keep their predicted class. probe3's
  distribution is 154 converging, 20 reference unsettled, 18 not measured, 8
  unexplained, 6 not converging; the 18 "not measured" can only improve, since
  this run covers all 103 designs.
* **E2.** On rows classed converging, the fitted exponent has median in
  **0.8–1.3**; `loops.skyloop_lmatch` lands in **1.7–2.4** (AK#1516 measured
  1.94–2.34 for the bs2−NEC-5 gap there).
* **E3.** What 80 buys over 40: median `err(80)/err(40)` in **0.45–0.60**; median
  `wall(80)/wall(40)` in **3.0–5.0**; median `peakRSS(80)/peakRSS(40)` in
  **1.5–4.0**.
* **E4.** Between **10 and 40** rows are marked *reference unsettled* — i.e. bs2
  is not settled at the shipped mesh on a real minority of the catalog, which is
  the fact that makes "bs2 as yardstick" a measured claim rather than an
  assumption. probe3 predicts 20.
* **E5.** Exactly **one** design has a mesh that fails to respond to the knob at a
  1.5× threshold over 21 → 160 (`verticals.elt_whip`).

Superseded, with reasons: **D1** and **D2** are reworded as E2 because the
reference changed from bs2-at-defaults to bs2@160. **D3** carries over unchanged
as E3. **D4** is gone: "is bs2 a usable yardstick" is no longer a prediction but
a measured output, and E4 replaces it. **D5** is gone: with a reference-movement
rule in force, "rows still above 2 % at rung 160" mixes unresolved rows with real
ones, and the classification reports it better.

**No recommendation on the default density.** Not a prediction — a constraint on
the deliverable.
