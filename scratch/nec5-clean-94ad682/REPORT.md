# Clean-room build 94ad682 (unit 2) on Skylake — the gate

**Unit 2 is the pattern and near-field paths made to thread.** The build is
`nec5cl-94ad682`, sha256 `3d0b05a4bf22721f…`, 1,169,880 bytes, distinct by hash
from all three builds already on this box (x13 `2068ae67…`, 63d0f93 `369ba4ff…`,
d8e2147 `05369a2b…`).

Every deck is from the translated corpus tree; every run uses `run_set.sh`'s
stdin protocol (the binaries read the deck NAME on stdin, never argv), one
process at a time.

## The headline: it scales, and it beats the calibration

Wall seconds, t1 → t4 (ratio). The clean room's expected t4 ratios are in the
last column.

| deck | x13 t4 | d8e2147 t1 → t4 | **94ad682 t1 → t4** | 94/d8 at t4 | room expected |
|---|---:|---|---|---:|---:|
| `fan_dipole` | 5.93 | 3.99 → 3.51 (1.14) | **3.97 → 1.89 (2.10)** | 1.86 | 1.83 |
| `gbhoyt` | 34.44 | 23.56 → 21.88 (1.08) | **23.36 → 13.96 (1.67)** | 1.57 | 1.10 |
| `6mYagi-Onec` | 49.56 | 41.14 → 41.33 (1.00) | **41.17 → 25.76 (1.60)** | 1.60 | 1.51 |
| `2m-sat-candidate2` | 23.00 | 16.26 → 14.91 (1.09) | **16.04 → 9.99 (1.61)** | 1.49 | — |
| `6mYagi-oneFR` | 1.21 | 1.00 → 1.01 (1.00) | **1.03 → 0.66 (1.56)** | 1.53 | — |
| `15m_20m_jumper` | 3.12 | 2.39 → 2.36 (1.01) | **2.35 → 1.63 (1.44)** | 1.45 | — |
| `ON6MU` | 6.54 | 5.11 → 5.12 (1.00) | **4.94 → 3.68 (1.34)** | 1.39 | — |
| `LP144-35-MAXFB` (fill control) | 50.28 | 34.14 → 16.74 (2.04) | 34.17 → 16.96 (**2.01**) | **0.99** | in range |
| `TRAPx2_V` (FR control) | 61.53 | 38.86 → 38.92 (1.00) | 39.22 → 38.69 (**1.01**) | 1.01 | 0.99 |
| `6mYagi-RPtoXQ` (solve only) | 0.11 | 0.08 → 0.08 (1.00) | 0.08 → 0.06 (1.33) | 1.33 | — |

Both controls behave: the fill-bound `LP144` keeps its 2.0× and does not regress
at t4 (0.99×), and `TRAPx2_V` stays at 1.01 — the deck the room predicted would
not move, because its lever is the per-frequency Sommerfeld table build rather
than the pattern.

### The 38 decks this build exists for

The AK#1433 set: the large decks d8e2147 did **not** speed up, whose t1/t4 ratio
read ~1.00 because their wall is post-solve.

| | d8e2147 | **94ad682** |
|---|---:|---:|
| median t1/t4 ratio | 0.99 | **1.42** |
| decks scaling > 1.3× | **1 of 38** | **36 of 38** |
| median wall speedup at t4 vs d8e2147 | — | **1.45×** |

The top of the list is the near-field decks, which is the right shape:
`4nec2-models/Objects/Illuminate.nec` **2.77×** and `NearFld.nec` **2.67×**
(1.01 and 1.03 under d8e2147). The two that still do not scale are `TRAPx2_V`
(1.00, predicted) and `antenna-modeling/dipole-80m-gutters.nec` (1.17).

### Unit 2 is threading, not serial vectorisation

At **one** thread 94ad682 is within 3 % of d8e2147 on all ten files —
`6mYagi-Onec` 41.14 → 41.17, `LP144` 34.14 → 34.17, `gbhoyt` 23.56 → 23.36.
Whatever vectorisation is in the build does not show on the serial path of these
decks; the entire win is in the scaling. Worth stating because the opposite
reading was available and wrong (see *the harness trap* below).

### x13 was not unthreaded on the slow decks — it was threaded and getting nothing

`RUN TIME` is CPU summed over threads, so RUN TIME/wall is a thread count. At t4
x13 burns **3.92** CPU-seconds per wall second on `gbhoyt` and **4.00** on
`ON6MU`, for wall ratios of 1.02 and 1.00. Parallel work converting to nothing is
a sharper statement of the condition unit 2 fixes than "does not thread".

## The gates

### Impedance rows — byte-identical, which is the strict gate

Unit 2 leaves the solve alone, so every ANTENNA INPUT PARAMETERS block must
match byte for byte and any difference is a regression, not a tolerance
question. Whole sections, not one number per deck: `gbhoyt` alone has **500**
impedance blocks, `TRAPx2_V` 252, `LP144` 170, `ON6MU` 120.

| comparison | verdict |
|---|---|
| 94ad682 vs d8e2147, t1 | **PASS** — every row byte-identical |
| 94ad682 vs d8e2147, t4 | **PASS** |
| 94ad682 t1 vs t4 | **PASS** |
| 22-deck unit-1 set, 94ad682 vs d8e2147 | **PASS** |
| 22-deck unit-1 set, 94ad682 vs x13 | **PASS** |

### Field tables — the room's rule at 1e-9, on 7.6 million rows

Not byte identity: per the room's REPORT-2026-09-12, magnitudes relative to the
row maximum, a floor of 1e-6 of the table maximum, phases only above that floor,
dB gains only above −80 dB, pass at 1e-9.

| comparison | rows compared | worst magnitude diff | verdict |
|---|---:|---:|---|
| 94ad682 vs d8e2147, t1 | 7,588,769 | **5.027e-13** | PASS on 9 decks |
| 94ad682 vs d8e2147, t4 | 7,588,769 | **4.831e-13** | PASS on 9 decks |
| 94ad682 t1 vs t4 | 7,588,769 | **1.077e-12** | PASS on 9 decks |
| 94ad682 vs **x13**, t4 | 7,588,769 | 4.114e-06 | FAIL on `fan_dipole` |
| **d8e2147** vs x13, t4 | 7,588,769 | 4.114e-06 | FAIL on `fan_dipole` |

`6mYagi-Onec` alone contributes **5,343,202** rows (41 frequencies ×
130,321 pattern points). `6mYagi-RPtoXQ` carries no field table at all and is
reported as `n/a`, never as a pass.

**The `fan_dipole` failure against x13 is pre-existing and the control proves
it**: d8e2147 shows the *same* 4.114e-06 against x13, which is unit 1's
Sommerfeld-flag effect on that deck. Against d8e2147 — the comparison the room
said to use for it — `fan_dipole` reads **0.000e+00**. This is the whole reason
the room specified that baseline, and running both comparisons is what makes the
statement checkable instead of an excuse.

## THE FAILING FINDING: 94ad682 segfaults on two corpus decks

Over the full 3,076-deck corpus, at both thread counts, against both baselines:

| build | ok | crash | error | no-impedance | ok-no-source | timeout |
|---|---:|---:|---:|---:|---:|---:|
| x13 t4 | 2946 | 43 | 10 | 8 | 67 | 2 |
| d8e2147 t4 | 2946 | 43 | 12 | 8 | 66 | 1 |
| **94ad682 t1** | **2944** | **44** | 12 | 8 | 66 | 2 |
| **94ad682 t4** | **2943** | **45** | 12 | 8 | 66 | 2 |

Exactly **two** decks are `ok` under both baselines and crash under 94ad682, and
no deck newly works. Five reps per (build, thread count), so "crash" is a
property of the deck rather than of one run:

| deck | segs | cards | x13 | d8e2147 | **94ad682 t1** | **94ad682 t4** |
|---|---:|---|---|---|---|---|
| `qantenna/10-30m_vert4.nec` | 47 | NE NH RP | 10/10 ok | 10/10 ok | **5/5 SIGSEGV** | **5/5 SIGSEGV** |
| `cebik-w4rnl/nec4-ex11.nec` | 28 | NE NH RP | 10/10 ok | 10/10 ok | 5/5 ok | **3/5 SIGSEGV** |

These are two different faults, and the difference matters to whoever fixes them:

- `10-30m_vert4` is **deterministic and single-threaded** — 10 of 10 at one
  thread as well as four. Not a race.
- `nec4-ex11` fails **only at four threads, and only sometimes** (3 of 5), which
  is the signature of a race.

Both decks are tiny and both carry **`NE` and `NH`** — the near-field path this
unit rewrote. Nothing here says anything about the build's internals: these are
exit codes and deck cards, observed from outside.

`4nec2-models/HFbeams/Bowtie.nec` also reads `ok → timeout` against d8e2147, and
that one is **not** a regression: at one thread it exceeds the 300 s cap under
d8e2147 as well (measured, 2 reps, `rc=124` both), so its status is decided by
whether four threads bring it under the cap.

**Verdict on the gate as a whole: the performance claim passes and the stability
gate fails.** Every timing and table result above stands; two decks that used to
solve now segfault, one of them deterministically at one thread, and that is a
blocking finding rather than a tolerance question.

## Two bugs in my own gate, both of which reported a green that was not there

Recorded because either would have shipped a false pass.

**The RP column layout.** An RP row is 12 whitespace fields of which one — the
polarization `SENSE` word (`LINEAR`/`RIGHT`/`LEFT`) — is not a number, so the
numeric width is **11**. The first version required 12 and indexed the
magnitudes at 8 and 10, which are the *phase* columns. Every pattern row was
rejected: `6mYagi-Onec` reported **40 rows compared out of 5.3 million**, and
the verdict was PASS. The script now carries an explicit `WIDTH` table and prints
an **unread-lines** count per deck, so a layout that does not match is a number
on the report rather than silence.

**The floor gated phases but not magnitudes.** With the layout fixed, the gate
went red: 215 cells on `15m_20m_jumper`, worst **4.9e-04**. Every one was a
`theta = 90°` row over lossy ground where NEC-5 prints its −999.99 dB floor and
both field components sit near **1e-16 V** against a table maximum of
**3.4e-03** — that is **1.4e-14 of the table maximum**, eight orders of
magnitude below the 1e-6 floor. Comparing such a row relative to its *own*
near-zero maximum manufactures the failure. Reading the room's rule as "below the
floor, do not compare" is what reproduces the room's own figures; with it that
deck reads 0.000e+00 across 196,026 rows with 816 rows excluded as below floor.

## The harness trap, which cost an hour of runs

The first timing harness wrote

```bash
OMP_NUM_THREADS=$nt printf 'model.nec\nmodel.out\n\n' | "$exe"
```

A variable assignment prefixes **one** command, and in a pipeline that is the
**left-hand** one — so the thread settings went to `printf` and the binary
inherited the shell's environment. The t1 and t4 passes ran the same
configuration and **every ratio came out 1.00**, across all three builds and all
eleven decks. The conclusion that invited — "x13 gets nothing from four threads,
and unit 2's threading has not landed" — was one message from being reported.

`export VAR=…; printf … | "$exe"` is the fix. `thread_env_gate.sh` is the proof
it took, and it is the check to run before trusting any ratio from a new harness:

```
threads 1: wall 4.02 s, RUN TIME 4.011, thread count 1.00
threads 4: wall 1.94 s, RUN TIME 6.181, thread count 3.18
```

It also explains the void numbers rather than merely discarding them: with the
prefix lost, OpenMP defaulted to all **8 logical** CPUs on 4 physical cores, and
that oversubscription is markedly worse than a pinned 4 — `gbhoyt` 56.3 s unset
against 34.4 s at four threads under x13.

## Provenance

- decks: `~/nec5-timing/decks-unit2` (the eight the room named, plus the three
  6mYagi spellings), built by `make_unit2_decks.sh` from the translated tree.
  The one-frequency spelling is `FR 0 1 0 0 50 0` — NFRQ → 1 and DELFRQ → 0,
  **keeping FMHZ = 50**; zeroing the frequency field instead writes a 0 MHz deck
  that runs and means nothing.
- binaries: by sha256, listed above. No binary left this box; nothing about the
  build's internals is recorded here — timings, printouts and counters only.
- runs: `run_unit2.sh` (headline set), `run_rest.sh` (corpus checks, the 38
  decks, the unit-1 set), `run_slow38.sh`, `run_unit1_regression.sh`.
- gates: `gate_compare.sh` drives `compare_impedance.py` and `compare_tables.py`.
