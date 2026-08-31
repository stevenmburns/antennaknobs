# Thread-policy bench — OpenBLAS spin-wait, physical vs logical cores

Harness for [AK#1050](https://github.com/stevenmburns/antennaknobs/issues/1050)
and [AK#1051](https://github.com/stevenmburns/antennaknobs/issues/1051).

Run `bench_thread_policy.py` **unmodified** on every box. Two machines running
byte-identical code is the only thing that makes their rows comparable;
re-implementing it locally from a description guarantees they are not.

```
python bench_thread_policy.py --workload refl --nsegs 100,200,400 \
    --threads 4,8 --spin both --budget 8 --repeats 3 > rows.jsonl
```

Workloads: `free` (momwire dense, free space), `refl` / `somm` (momwire swept
ground, reflection-coefficient / Sommerfeld), `pynec-yagi`, `pynec-4sq`.

## What it measures, and the two traps it is built around

**Trap 1 — `min` of a few short runs measures turbo headroom, not speed.** It
selects the least-throttled sample. On a 15W i7-8550U that idiom produced a
"2 threads beats 4 by 34%" reading that vanished under a steady-state loop:
inside a single 2-thread run, iteration time degraded 60.5% as the package
clock fell 3700 → 2413 MHz. So every cell here loops for a wall-time budget
and is scored on the **median of the last half**, and every row carries its own
thermal evidence — `drift_pct` (first fifth vs last fifth) and the
**busiest-core** clock across the cell.

The clock is the busiest core deliberately. A mean over all cores conflates
"the idle cores are parked at minimum clock" with "the working cores are being
clocked down"; running 4 threads on 8 logical CPUs, the parked majority
dominates that mean and fakes a throttling signal that is not there.

**Trap 2 — the variable under test is read before Python runs.**
`OPENBLAS_THREAD_TIMEOUT` is read by each OpenBLAS copy at its own init, and
there are three copies in one process (`numpy.libs`, `scipy.libs`,
`pynec_accel.libs`) plus system libgomp. Setting it from module scope silently
does nothing — the same trap `web/server.py`'s thread-policy block documents
for its own env vars (#377). `--spin` therefore re-executes the interpreter
with the right environment, and each row records the state that was actually
in force rather than the one requested.

LU time is attributed by wrapping **both** `scipy.linalg.solve` and
`numpy.linalg.solve`: momwire's dense path calls the former
(`bspline.py:3480-3506`) and the swept path batches through the latter
(`bspline.py:3525-3558`), so wrapping one reports `fill_frac ≈ 1.0` by
construction on the path it missed. PyNEC factorizes in C via LAPACKE `zgetrf`,
invisible from Python, so pynec rows report `fill_frac: null` rather than a
number that would be wrong.

## Baseline: haswell-server (i7-4770K, 4C/8T, idle, drift <1%)

Spin off vs on, both pools at the same count. Every cell measured, none
extrapolated.

| workload | N | spin ON | spin OFF | gain |
|---|---|---|---|---|
| `free` dipole, 8 thr | 400 | 175.8 | 64.1 | **2.74×** |
| `refl` swept, 4 thr | 400 | 1195.7 | 801.0 | +49% |
| `somm` swept, 4 thr | 200 | 474.1 | 340.4 | +39% |
| `pynec-yagi`, 4 thr | 150 | 178.0 | 159.5 | +12% |

**Nothing measured on any path, engine, size or thread count was made worse by
`OPENBLAS_THREAD_TIMEOUT=1`.**

Physical (4) vs logical (8), spin off — `+` means physical won:

| workload | N | Δ | winner |
|---|---|---|---|
| `refl` | 200 / 400 | +13% / +7.2% | physical |
| `somm` | 100 / 200 | −7.2% / +3.1% | logical / marginal |
| `free` | 200–1600 | −1.9% … −7.8% | logical |
| `pynec-yagi` | 150 / 400 | −15.4% / −10.4% | logical |
| `pynec-4sq` | 120 / 300 | −14.8% / −13.2% | logical |

pynec is consistent across two unrelated decks. momwire is **path-dependent**:
the HT-contention rationale at `server.py:57-61` is a property of the
refl-coef path, not of the engine.

## Settled negative result: fill fraction does not predict the sign

The hypothesis was that the preference tracks the fill-vs-LU time fraction
rather than the ground model — attractive because it would give #1051 a policy
readable off a request instead of a hand-maintained table of ground models.
Sweeping N within each path to move the fraction continuously, then sorting
every cell by fill fraction, the sign does not partition:

```
fill 94.9%  somm N=200   LOGICAL
fill 93.0%  refl N=400   physical
fill 92.9%  somm N=100   LOGICAL
fill 92.0%  free N=1600  LOGICAL
fill 91.8%  refl N=200   physical
fill 90.5%  free N=800   LOGICAL
fill 87.1%  refl N=100   LOGICAL
```

The two physical cells are interleaved with logical cells above and below them.
There is no crossing. The deeper reason is visible in the column itself: the
fraction only spans 87–95% across a 32× range of N and three kernel paths —
every path is fill-dominated everywhere tested, so the fraction was never a
usable knob. The O(N³) LU does not overtake the fill in the measured range.

This **kills option 3 as specified** and pushes #1051 toward option 1 (fix the
rationale, keep the pin) or a per-engine option 2 written as the approximation
it is.

## Caveat on the deployed app

`fly.toml:41` is `size = 'shared-cpu-1x'` — one vCPU, so `_physical_cpu_count()`
returns 1 in production, both pools get one thread, and there is no worker pool
to spin. None of this describes the hosted server. The beneficiaries are people
running the app **locally** and the bench scripts, which is why a thermally
limited laptop is the target population and a quiet desktop is the control.

## Ordering and cooldown — not cosmetic

`--spin both` runs two child processes, because the variable is read at import.
Back to back, the second half inherits a hotter machine, which is a systematic
bias against whichever spin state runs second — and that is exactly the
comparison the issues turn on. Free on a quiet desktop, decisive on a 15 W
part.

So on a thermally limited box:

```
--cooldown 90 --spin-order on-first    # then off-first on the next workload
```

Alternating `--spin-order` across workloads makes any residual bias cancel
across the matrix instead of accumulating in one direction. (Credit where due:
this was found by driving the halves by hand on an xps13 before the flags
existed.)

## Provenance fields worth checking before trusting a comparison

- `harness.commit` / `harness.dirty` — "both boxes ran the same harness" is the
  premise of every cross-machine row here. A `dirty: true` row came from a
  locally edited script and is not comparable to anything.
- `topology.heterogeneous` — true on hybrid P/E-core parts (Alder Lake and
  later), where `psutil.cpu_count(logical=False)` returns P-cores + E-cores as
  one number over members with very different throughput. A barrier-synchronised
  OpenMP fill is gated by its slowest thread, so on such a part "physical core
  count" is not a meaningful policy input and the pin question is not the
  question these rows measure. Neither box measured so far is heterogeneous.

## `--paired` — when the noise floor swamps the effect

On a thermally limited part the dominant noise is slow clock drift. Measuring
all of thread-count A and then all of B puts minutes between the arms and lets
that drift land entirely in the difference, which is the quantity of interest.
Observed on an xps13: repeat spread 24-37% against a pin effect of 7-15%.

That is not a tuning problem, it is a resolution problem. Unpaired, resolving a
10% effect against σ≈22% needs ~39 repeats per cell — about **46 hours** for a
144-cell matrix at `--budget 15`. The pin question is simply not answerable
that way on that box. (`#1050`'s effects, +26% to 174%, sit far above the floor
and stay readable.)

`--paired` interleaves the two thread counts in short blocks so both arms see
the same thermal envelope, and reports the median of per-pair **ratios**:

```
--threads 4,8 --paired --pair-block 3 --repeats 3
```

Per-pair, not a ratio of medians: each pair is self-contained, so a pair
spanning a thermal excursion is one noisy sample rather than a shift of a whole
arm. Blocks rather than single iterations because changing a pool's thread
count is not free — OpenBLAS may respawn workers, which is itself entangled
with the spin behaviour under test.

**Validation status.** Correctness is confirmed on haswell: paired reports
+11.9 / +10.6 / +4.9% where unpaired reports +12.6% on the same cell, i.e. it
recovers the same answer. The **variance reduction is not demonstrated here and
cannot be** — a quiet desktop has almost no drift to cancel, which is the whole
point. The decisive check costs one cell on a noisy box: run it both ways and
compare `ratio_spread_pct` against the unpaired repeat spread. If pairing does
not shrink it, the noise is not drift and this mode does not help.

## Pairing is the default, and blocks are sized by time

`--paired` is **on by default** whenever `--threads` names two counts. The
unpaired failure mode is not noise, it is a confident wrong sign: on an xps13,
`free` N=200 read **+10.0% physical and was marked resolved**, because the delta
exceeded the within-arm scatter. That test is structurally blind to
between-cell drift, which is what dominates a drifting box. Paired on the same
cell: **−12.1%**, spread 3.2 points, agreeing with the desktop. `--no-paired`
restores the old arms and warns on stderr.

Block size is a *duration* (`--pair-secs`, default 1.0 s), not an iteration
count. A fixed count makes block length scale with the cell, so a setting ample
at N=400 is 156 ms at N=100 — short enough that the pool-switch overhead and
per-iteration jitter dominate. Measured on refl N=100, everything else held:

| block | ratio | spread |
|---|---|---|
| 3 iters | −3.0% | 41.9% |
| 10 iters | −2.6% | 21.5% |
| 25 iters | −3.7% | **2.4%** |

The estimate never moved; only the spread did. Time-sizing gets the tight end
automatically at every N.

## `--spin-paired`: pairing across a process boundary

`OPENBLAS_THREAD_TIMEOUT` is read at library init, so the two spin states can
never share a process — which appears to leave #1050-style comparisons stuck
with the resample-the-thermal-lottery repeat structure that produced that wrong
sign. The boundary is not the obstacle. Interleave short-lived **child
processes** instead of running two long halves:

```
--threads 4 --spin-paired --pairs 5 --block-secs 3
```

Adjacent blocks sit seconds apart in the same thermal window, so the drift is
common mode and cancels in the ratio. Cost is one interpreter start per block
(~1 s of Python + NumPy import); `--block-secs` makes that a tunable fraction
rather than a fixed tax — ~25% at the default. Validated on haswell refl N=200
thr=4: reports on 268.9 ms / off 208.1 ms, +28.2%, against 265.7 / 210.1
measured unpaired earlier.

## Reading a row

`drift_pct` is the first thing to look at. Under a few percent, read the row at
face value. Large and negative usually means warm-up leaked into the first
fifth (raise `--budget`). Large and positive on a mobile part means the cell is
reporting a thermal envelope, not a code path — check `busy_first_fifth` vs
`busy_last_fifth` and treat cross-config comparisons in that run with
suspicion.
