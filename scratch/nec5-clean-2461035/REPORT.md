# Clean-room build 2461035 on Skylake — the gate

`nec5cl-2461035`, sha256 `8c6f7dabfff93ec3…`, 1,231,400 bytes — **verified before
any run**, and distinct by hash from all four builds already on this box (x13
`2068ae67…`, 63d0f93 `369ba4ff…`, d8e2147 `05369a2b…`, 94ad682 `3d0b05a4…`).

It supersedes 94ad682, whose gate (#1448) passed on performance and **failed on
stability**: two corpus decks segfaulted. Verdict here, item by item:

| item | verdict |
|---|---|
| 1. stability | **PASS** — 80 runs, 0 failures; corpus status identical to d8e2147 on all 3,076 decks |
| 2. correctness | **PASS** — impedance byte-identical to both baselines; field tables identical to 94ad682 |
| 3. timing and maps | **PASS** — matches 94ad682; six maps rendered |

## 1. Stability — the blocking item from #1448

20 reps per (build, thread count) on both decks. The race in 94ad682 showed 3 of
5 when it was first measured, so 20 reps at four threads is what makes a zero
mean something.

| deck | 94ad682 t1 | 94ad682 t4 | **2461035 t1** | **2461035 t4** |
|---|---|---|---|---|
| `qantenna/10-30m_vert4.nec` | 0/20 (20 SEGV) | 0/20 (20 SEGV) | **20/20** | **20/20** |
| `cebik-w4rnl/nec4-ex11.nec` | 20/20 | 2/20 (18 SEGV) | **20/20** | **20/20** |

80 runs of the new build, zero failures. 94ad682's two faults reproduce at scale
in the same batch, and the race is worse at more reps (18/20 against the 3/5
first measured), which is what a race does.

### The full corpus, same session, 3,076 decks

| build | ok | crash | error | no-impedance | ok-no-source | timeout |
|---|---:|---:|---:|---:|---:|---:|
| x13 | 2946 | 43 | 10 | 8 | 67 | 2 |
| d8e2147 | 2945 | 43 | 12 | 8 | 66 | 2 |
| 94ad682 | 2944 | **44** | 12 | 8 | 66 | 2 |
| **2461035** (4×1) | 2945 | **43** | 12 | 8 | 66 | 2 |
| **2461035** (2×4) | 2946 | 43 | 12 | 8 | 66 | 1 |
| **2461035** (8×1) | 2945 | 43 | 12 | 8 | 66 | 2 |

Every deck whose status differs, named:

- **vs d8e2147: none.** Zero status differences across the corpus.
- **vs 94ad682: one** — `qantenna/10-30m_vert4.nec` `crash` → **`ok`**. The fix.
- vs x13: two — `necpp/plane.nec` (`ok-no-source` → `error`) and
  `qantenna/airplane.nec` (`ok` → `error`). Both are **pre-existing unit-1
  differences**, which the zero-difference row against d8e2147 establishes
  directly rather than by argument.
- t1 vs t4: one — `4nec2-models/HFbeams/Bowtie.nec` `timeout` → `ok`, the deck
  #1448 already characterised as sitting on the 300 s cap.

## 2. Correctness

### Impedance rows — byte-identical

Whole ANTENNA INPUT PARAMETERS sections, not one number per deck (`gbhoyt` alone
has 500 blocks):

| comparison | verdict |
|---|---|
| 2461035 vs 94ad682, t1 and t4 | **byte-identical** |
| 2461035 vs d8e2147, t1 and t4 | **byte-identical** |

### Field tables — identical to 94ad682

The room's rule at 1e-9 (magnitudes relative to the row max, floor 1e-6 of the
table max, phases only above the floor, dB only above −80 dB), over 7.6 M rows:

| comparison | worst magnitude difference | verdict |
|---|---:|---|
| 2461035 vs 94ad682, t1 | **0.000e+00** | PASS on 9 decks |
| 2461035 vs 94ad682, t4 | **0.000e+00** | PASS on 9 decks |
| 2461035 t1 vs t4 | 1.077e-12 | PASS on 9 decks |
| 2461035 vs x13, t4 | 4.114e-06 | `fan_dipole` — **pre-existing** |

`fan_dipole`'s figure against x13 is the same 4.114e-06 that d8e2147 and 94ad682
both show against x13: unit 1's Sommerfeld-flag effect, not this build's.

### The expected near-field mover, measured

The headline set cannot show it: only `gbhoyt` carries both a ground and near
fields, and `2m-sat-candidate2` and `ON6MU` have `NE`/`NH` in **free space**. So
it was measured where the room said it lives — on `qantenna/10-30m_vert4.nec`,
whose 6,300 above-floor `NH` rows are the whole population (`NE`: none above the
floor).

| comparison | rows moving | median | p90 | worst |
|---|---:|---:|---:|---:|
| 2461035 vs **x13** | **671 of 6,300 (10.7 %)** | **0.000e+00** | 3.25e-08 | 6.60e-02 |
| 2461035 vs d8e2147 | 6,300 of 6,300 (100 %) | 3.55e-05 | 3.77e-03 | 1.17e-01 |
| *control:* d8e2147 vs x13 | 6,300 of 6,300 (100 %) | 3.29e-05 | 2.59e-03 | **1.17e-01** |

**Read the control row first.** The large `NH` spread is **d8e2147's**, already
present against x13 before this build existed — same 1.17e-01 worst. 2461035
moves **back toward x13**: 5,629 of 6,300 rows are now *exactly* x13's, and the
median difference is zero. So the strict-FP field path does what it was meant to.

**One correction to the expectation.** The room described the affected rows as
points "within about a segment length of a wire". Measured against the deck's own
geometry (4 wires, segment length 0.240–0.250 m), the 671 residual movers are
**not** confined to that band:

- only **84 of 671 (13 %)** lie within one segment length, and **294** rows that
  *are* within one segment length do not move at all;
- the movers sit closer to wires than the non-movers (median **1.250 m**, 5.2
  segment lengths, against 2.975 m / 12.4 for rows that match);
- the worst are at **0.750 m = 3.12 segment lengths**.

So the effect is distance-related, as described, but the band runs to roughly
five segment lengths rather than one. Not failed on these rows, per the brief.

## 3. Timing, and the maps

Unit-2 timing matches 94ad682, as expected. Headline set, t1 → t4:

| deck | 94ad682 | **2461035** |
|---|---|---|
| `6mYagi-Onec` | 41.17 → 25.76 (1.60) | 41.09 → 25.75 (**1.60**) |
| `fan_dipole` | 3.97 → 1.89 (2.10) | 4.00 → 1.91 (**2.09**) |
| `gbhoyt` | 23.36 → 13.96 (1.67) | 23.20 → 15.70 (1.48) |
| `LP144-35-MAXFB` | 34.17 → 16.96 (2.01) | 34.27 → 15.61 (**2.20**) |
| `TRAPx2_V` (FR control) | 39.22 → 38.69 (1.01) | 38.96 → 38.75 (**1.01**) |

Six maps, every pair same-session and `timing_valid: true` on both sides:

| map | condition | comparable | median | long decks (≥ 2 s) |
|---|---|---:|---:|---|
| 2461035 vs x13 | **1 thread**, 4 workers | 1,313 | **1.552** | 86 faster, **0 slower** |
| 2461035 vs d8e2147 | **1 thread**, 4 workers | 1,319 | **1.001** | 34 faster, 31 slower |
| 2461035 t1 vs t4 | 8×1 against 2×4 | 1,459 | **1.312** | 85 faster, 9 slower |
| 94ad682 vs x13 | 1 thread, 4 workers | 1,312 | 1.554 | 85 faster, 0 slower |
| 94ad682 vs d8e2147 | 1 thread, 4 workers | 1,315 | 1.002 | 37 faster, 27 slower |
| 94ad682 t1 vs t4 | 8×1 against 2×4 | 1,466 | 1.313 | 86 faster, 5 slower |

The first four are **single-thread** comparisons — both sides ran one thread per
worker — so they measure serial speed, and the file names say `-1thread`. Only the
last two vary the thread count.

At one thread per worker the two unit-2 builds are **indistinguishable from
d8e2147** (median 1.001 and 1.002, p10 0.983/0.986) — the whole of unit 2 is in
the threading column, where the corpus median is 1.31 and the long decks are 85
of 94 faster.

## The cross-session drift, and an audit of what rested on it

**This box's absolute wall times are not comparable across sessions.** The same
d8e2147 corpus pass — 4 jobs × 1 thread, same tool, same tree — read **852 s on
2026-09-10 and 1,135 s today**, a 33 % difference with no code involved.

That drift produced a wrong result before it was caught. Built on the 09-10
reports, the 94ad682 map read **median 0.945 with p10 0.586** — "unit 2 is 5 %
slower than unit 1, and much worse in the tail". Two independent checks refuted
it: a serialised 7-rep best-of probe put the two builds at **0.998, 0.992, 1.006,
0.992** on four decks, and the same-session map now reads **1.002**. The
regression was the box, not the build.

### Which published comparisons were cross-session

| where | cross-session? | does its conclusion survive? |
|---|---|---|
| #1448's 94ad682 t1/t4 ratios (headline set, 38 decks) | **no** — both passes in one session, one process at a time | yes, unaffected |
| #1448's 94ad682-vs-d8e2147 at t4 (headline set) | **no** — same session | yes |
| #1448's corpus mover list (statuses, impedances at 1e-9) | n/a — statuses and impedances, not walls | yes |
| the first 94ad682-vs-x13 / vs-d8e2147 **maps** (never published) | **yes** | **no — discarded and rebuilt same-session** |
| `scratch/nec5-clean-d8e2147/speedup-*-t4.csv` (on main) | **within one session** for each pair | **yes** |
| #1433's "d8e2147 gives 2.08× on LP144" and the 38-deck set | **no** — one session, serialised | yes |

### A claim I made about those files, withdrawn

An earlier draft of this report said the committed `speedup-*-t4.csv` files ran
**4 workers × 1 thread** and were therefore serial-speed maps under a four-thread
name. **That is wrong**, and the check that settles it is four decks:

| deck | `check-x13-t4.jsonl` | this box, serialised at 4 threads, today |
|---|---:|---:|
| `gbhoyt` | 34.69 | 34.44 |
| `LP144-35-MAXFB` | 50.05 | 50.28 |
| `TRAPx2_V` | 61.48 | 61.53 |
| `6mYagi-Onec` | 49.38 | 49.56 |

Those walls are a serialised four-thread run, which is exactly what
`scratch/nec5-clean-d8e2147/README.md` says on its fourth line: **`--jobs 1`,
`OMP_NUM_THREADS=4`**. The reasoning that produced the wrong claim was about the
tool's `--jobs 4` DEFAULT, which pins each worker to one thread unless the caller
exported a count — true of the pass *I* ran in #1448, not of those.

So the published files are the better measurement of the two, their name is
accurate, and nothing there needs correcting. What needed correcting was in this
PR: the baselines here ran `--jobs 4` with `OMP_NUM_THREADS=1`, so the four
build-vs-build maps are **single-thread** comparisons and were carrying `-t4`
names. They are renamed `-1thread`.

## Provenance

- Binaries by sha256, verified before use; nothing about any build's internals is
  recorded here. Timings, statuses, exit codes, printout comparisons and deck
  cards only.
- Corpus passes: `jobs × threads` is 4, 8 and 8 against 8 CPUs, so the tool
  reports `timing_valid: true` on every pass used for a ratio. The first t4 pass
  in #1448 was 4 × 4 = 16 on 8 and is not used for any timing claim.
- Runs: `run_all.sh`, `stability.sh`; their output is `run-log.txt` and the
  comparison verdicts are `field-tables.txt`. Comparisons reuse #1448's
  `compare_impedance.py` and `compare_tables.py` unchanged. (#1448's own verdict
  log never landed: `.gitignore` carries `*.log`, so the `cp` into the branch was
  silently dropped. It is added here as `gate-verdicts.txt`.)
- PNGs are gitignored; the CSVs they are drawn from are committed.
