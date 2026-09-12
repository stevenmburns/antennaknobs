# The large decks d8e2147 did not speed up

**Skylake 4c/8t, `--jobs 1`, OMP_NUM_THREADS and OPENBLAS_NUM_THREADS pinned to
4 (or 1) for every build compared.** Timing and counters only; no printouts, no
binaries, no source left the box. Features read from `~/nec5-timing/nec5` — the
tree the pinned-4 runs actually timed, not a later one.

84 comparable decks take ≥ 2 s under the x13 reference. 38 come in below 1.7×
against x13, 35 above 2.5×.

## The answer in one measurement

`opennec/6mYagi-Onec.nec` is 88 segments with `FR 0 41` and `RP 0 361 361` —
130,321 pattern points at each of 41 frequencies, 5.3 million pattern
evaluations on a trivial matrix. Three variants, same build, four threads:

| variant | 63d0f93 | d8e2147 |
|---|---:|---:|
| as shipped | 41.12 s | 42.00 s |
| `RP` replaced by `XQ` (41 frequencies, **solve only**) | **0.10 s** | **0.06 s** |
| `FR 0 1` (one frequency, full pattern) | 1.02 s | 1.01 s |

**The entire electromagnetic solve — 41 frequencies of fill, factor and solve —
is 0.06 s of a 42 s run: 0.14 %.** The other 99.86 % is the radiation pattern.
One frequency costs 1.01 s and 41 of them cost 42 s, so the pattern is linear in
the frequency count and nothing else in the deck matters.

d8e2147's fill *is* faster here — 0.06 s against 0.10 s, about 1.7× — and it is
invisible, because it is a sixteenth of one percent of the wall.

## Why this generalises: the slow decks do not thread at all

`perf stat`, run through `run_set.sh`'s stdin protocol (the binaries read the
deck on stdin; `perf stat <binary> <deck>` measures a run that read no deck and
exited). Full rows in `perf-rows-slow-t1-t4.csv`; every row printed the
impedance it produced, so none is a fast-because-it-failed artifact.

| deck | build | t1 | t4 | t1/t4 |
|---|---|---:|---:|---:|
| TRAPx2_V | 63d0f93 | 38.70 s | 39.21 s | 0.99× |
| TRAPx2_V | d8e2147 | 39.13 s | 38.85 s | 1.01× |
| 6mYagi-Onec | 63d0f93 | 41.07 s | 41.27 s | 1.00× |
| 6mYagi-Onec | d8e2147 | 41.37 s | 41.70 s | 0.99× |
| gbhoyt | 63d0f93 | 23.57 s | 24.21 s | 0.97× |
| gbhoyt | d8e2147 | 23.33 s | 21.73 s | 1.07× |
| **LP144-35-MAXFB** (fast control) | 63d0f93 | 33.99 s | 25.91 s | **1.31×** |
| **LP144-35-MAXFB** (fast control) | d8e2147 | 34.09 s | **16.41 s** | **2.08×** |

Four threads buy the slow decks **nothing**, under either build. The control of
similar wall scales, and scales twice as well under d8e2147 — which is the whole
four-thread story from the earlier study, reproduced on one deck.

Instruction counts say the same thing from the other side: 6mYagi-Onec executes
421.7 G instructions under 63d0f93 and 422.3 G under d8e2147, identical to three
figures. There is no different work being done, because the work that differs is
0.14 % of it.

## What splits the two sets

Best single-threshold separation of slow (< 1.7×) from fast (> 2.5×), balanced
accuracy over the 84:

| feature | threshold | balanced acc | catches | misfires on fast |
|---|---|---:|---|---|
| **`NE`/`NH` present** | ≥ 1 | **0.921** | 32 / 38 | **0 / 35** |
| total `RP` points | ≥ 1665 | 0.864 | 32 / 38 | 4 / 35 |
| `FR` steps | ≥ 20 | 0.779 | 31 / 38 | 9 / 35 |
| `GM` cards | ≥ 1 | 0.698 | 27 / 38 | 11 / 35 |
| `LD` cards | ≥ 1 | 0.652 | 30 / 38 | 17 / 35 |
| segments | ≥ 52 | 0.543 | 38 / 38 | 32 / 35 |

**No fast deck asks for a near field.** Not one of the 35.

### The `FR`-steps reading is a size artifact

The medians invite it — slow decks median 40 `FR` steps against the fast set's
1 — and controlling for size kills it:

| group | n | median segments | speedup |
|---|---:|---:|---:|
| multi-`FR` | 54 | 178 | 1.49× |
| single-`FR` | 30 | 1128 | 3.17× |
| single-`FR` **and** small (< 400 seg) | 7 | — | **3.13×** |
| multi-`FR` **and** large (≥ 400 seg) | 12 | — | **2.84×** |

Small decks are fast when single-`FR`; large decks are fast with many `FR`
steps. The control deck carries 170 `FR` steps and gets 2.83×.

`NE`/`NH` survives the same control:

| | n | median seg | speedup |
|---|---:|---:|---:|
| small < 400 seg, `NE`/`NH` | 30 | 176 | 1.30× |
| small < 400 seg, no `NE` | 19 | 137 | **2.19×** |
| large ≥ 400 seg, `NE`/`NH` | 4 | 453 | 1.46× |
| large ≥ 400 seg, no `NE` | 31 | 1164 | **3.11×** |

## The six slow decks with no near field

Thresholds are the **fast set's own maxima** (11,640 `RP` points, 200 `FR`
steps), so "this deck does something no fast deck does" is a claim about the
data rather than about a cutoff chosen to fit.

| speedup | seg | deck | what explains it |
|---|---:|---|---|
| 1.19× | 88 | `opennec/6mYagi-Onec.nec` | pattern points 130,321 |
| 1.27× | 114 | `sokyrad/…/15m_20m_jumper_half_square.nec` | pattern points 65,341 |
| **1.40×** | 114 | **`qantenna/1_4l-gp_on_pole.nec`** | **neither — unexplained** |
| 1.58× | 52 | `g1ojs/Trapped/TRAPx2_V.nec` | `FR` steps 252 |
| 1.61× | 312 | `sokyrad/…/fan_dipole_80_40_20_10_6m…` | pattern points 16,471 |
| **1.63×** | 4002 | **`cebik …/ch-5/5-8a.nec`** | **neither — unexplained** |

Two are unexplained, not one. `1_4l-gp_on_pole` (5,365 `RP` points, 21 `FR`
steps, 114 segments) sits inside the fast set's range on every feature measured
here, and `5-8a` is a 4,002-segment single-frequency deck with 361 pattern
points — the shape that should be fastest of all. Both want a look; neither is
folded into the story.

## The hypotheses, one sentence each

- **(a) many `FR` steps × small N** — **killed as a general explanation** by the
  size control above, and true only of `TRAPx2_V` (252 steps, 52 segments) among
  the 84.
- **(b) free space or PEC rather than Sommerfeld** — **killed**: 71 % of slow
  decks carry no `GN` against 43 % of fast ones, an enrichment far too weak to
  separate the sets, and `GN 0` appears in both.
- **(c) `NE`/`NH` or dense `RP` dominating** — **confirmed, and it is the
  answer**: the cleanest split in the table, size-independent, and the 6mYagi
  decomposition shows the mechanism directly at 0.14 % solve / 99.86 % pattern.
- **(d) `NT`/`TL`/`LD` routing through an unparallelised path** — **killed** for
  `NT` and `TL` (median 0 in both sets) and weak for `LD` (0.652).
- **(e) `GM`/`GX` symmetry** — **not the discriminator** (0.698, misfiring on 11
  of 35 fast decks), though it rides along with the small-deck population.
- **(f) many `EX` cards / multiple RHS** — **killed**: median 1 `EX` card in
  both sets.

## What this implies for the clean room

The SIMD fill cannot show on a deck whose wall is post-solve, so the next lever
is a different routine rather than more fill work: the pattern and near-field
paths are where these 38 decks spend their time, and on the three measured they
take no benefit from four threads at all — the same 40 seconds at one thread and
at four, under both builds.

## Reproducing

- `deck_features.py` → `large-deck-features.csv` (card census joined to the
  three pinned-4 speedup CSVs; reads no printout, runs no engine).
- `~/nec5-timing/perf_slow.sh` → `perf-rows-slow-t1-t4.csv`.
- `~/nec5-timing/probe_6myagi.sh` → the three-variant table above.
