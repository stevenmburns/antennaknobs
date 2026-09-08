# 2026-09-08 — catalog cost ladder (103 designs × 6 engines × 2 rungs)

## Goal

The push lane gates correctness on every merge but records neither wall time
nor memory, and runs one engine per design. This measures the other axis:
what every engine COSTS on every catalog design, at the design's default mesh
and one refinement rung. Closes #1235.

1,236 cells, 1,146 solved, ~1 h 30 m wall.

## Method

Haswell (8 threads, 31 GB), serially, **with nothing else on the box** — the
whole point is the timing, so a concurrent job would corrupt the measurement
rather than merely slow it. antennaknobs `1dc47b2e7a85`, momwire
`003dfcfbbe90`, ground `('finite', 13.0, 0.005)`, 12 GB cap per cell, both
SHAs recorded in the file's `_meta`.

**One cell per subprocess.** `ru_maxrss` is a high-water mark, so a shared
interpreter would report the peak of everything that ran before. The
interpreter + numpy + engine floor is about 90–100 MB and is included in every
figure.

**Warm, not cold.** Each cell solves twice and reports the second. The first
pays engine construction, mesh build and first-touch imports — a real cost,
recorded as `cold_s`, but not the per-tick cost the UI pays on a knob change.

### Two instrument bugs, found before the table existed

Both would have made this document fiction, and both are the reason to smoke-
test a bench before trusting a run of it.

- **The warm solve was a cache hit.** `MomwireEngine` memoises in
  `_solved_cache`, so the second `impedance()` on an unchanged engine is a
  dict lookup. Measured 0.19 ms against a 259 ms cold solve on
  `dipoles.invvee`/bs2 — a 1,300× "speedup" that was pure cache. The harness
  now clears the cache before the warm call, after which the warm time scales
  with mesh refinement, which a cache hit never did.
- **`mem_gb` arrived from `argv` as a string**, so `mem_gb > 0` compared `str`
  to `int` and *every* cell failed with a `TypeError` before solving.

A third bug was in a shared script rather than this one:
`bench_converge.total_nominal_segs` did `int(t[2])` on every `build_wires`
entry, which raises on a graded wire whose n_seg slot is a `GradedSegments`.
That made `verticals.buried_radial_vertical` fail on **every** engine with a
`TypeError` — six cells that looked like engine failures and were a bench bug.
Fixed here by summing the per-sub-edge `counts`.

## Coverage: what each engine serves

| engine | designs served | of 103 | refused | faults |
|---|--:|--:|--:|--:|
| bs2 | 102 | 99 % | 1 | 0 |
| bs1 | 102 | 99 % | 1 | 0 |
| sin | 97 | 94 % | 5 | **1** |
| razor-2p | 98 | 95 % | 5 | 0 |
| pynec | 100 | 97 % | 3 | 0 |
| nec5 | 98 | **95 %** | 5 | 0 |

> **The nec5 row moved after this run.** It read `77 | 75 % | 26` when the
> ladder was taken. All 26 refusals were one sentence in the wrapper — "only
> Load is served natively" — and antennaknobs#1280 gave `NEC5Engine` the
> multiport-Y + `NetworkReducer` route PyNEC has used since momwire#575, which
> lifts 21 of them. The five that still refuse are a floating port
> (`arrays.bowtie1x2_bl`, `wire.doublet_balanced_tuner`), whose second
> terminal NEC-5 cannot expose, and a distributed port (`wire.sterba_bl`,
> `wire.sterba_tl`, `wire.zepp`) — PyNEC drives every segment at V/S and reads
> the weighted current, and NEC-5's `EX` addresses knots, so the knot-weighting
> rule for that expansion has not been derived. The timing and memory rows
> below are the ladder's own and were NOT re-measured for the 21.

Every refusal carries a sentence except one. `dipoles.invvee_apex` on the
Sinusoidal engine raises `TypeError: SinusoidalSolver.__init__() got an
unexpected keyword argument 'node_gaps'` — antennaknobs adds `node_gaps`
whenever a design has vertex-port members and passes it to whatever solver is
configured, and `SinusoidalSolver` does not accept it. The capability is
understood elsewhere (the NEC-2 path refuses the same design with a proper
`PortAtVertex` sentence); only this path expresses it as a constructor type
error. Filed as **#1264**.

NEC-5's 26 refusals are structural rather than numerical — TL, TwoPort,
Transformer, BalancedLine and FloatingBalun branches it cannot stamp
natively — and are the reason it serves three quarters of the catalog.

## Cost at the default mesh (warm solve)

| engine | n | median s | p90 s | max s | median RSS MB | max RSS MB |
|---|--:|--:|--:|--:|--:|--:|
| sin | 97 | **0.0081** | 0.052 | 9.52 | 106 | 1510 |
| razor-2p | 98 | 0.0137 | 0.113 | 73.36 | 108 | **6170** |
| bs1 | 102 | 0.0277 | 0.167 | 39.80 | 107 | 2668 |
| pynec | 100 | 0.0343 | 0.174 | 5.43 | 101 | 433 |
| bs2 | 102 | 0.0465 | 0.244 | 97.79 | 107 | 5443 |
| nec5 | 77 | 0.3802 | 1.957 | 93.02 | 98 | 105 |

The median design is cheap on every engine — tens of milliseconds — and the
spread is four orders of magnitude. NEC-5 is the slowest by median but the
*cheapest* by memory (105 MB peak across the whole catalog), because the work
happens in an external binary whose RSS this does not capture.

## What the refinement rung costs

| engine | median time × | median RSS × |
|---|--:|--:|
| razor-2p | 3.27× | 1.14× |
| sin | 3.19× | 1.08× |
| bs1 | 2.55× | 1.07× |
| bs2 | 2.51× | 1.09× |
| nec5 | 1.52× | 1.00× |
| pynec | 1.31× | 1.01× |

Doubling `nominal_nsegs` doubles the mesh on 99 of 103 designs (median 2.00×),
so these are like-for-like. The momwire bases cost 2.5–3.3× for that doubling;
PyNEC and NEC-5 barely notice it, which says their cost is dominated by
something other than the linear solve at these sizes.

## One design dominates every cost axis

`verticals.elt_whip` is the most expensive cell in the catalog on **five of
six engines**:

| engine | warm s | peak RSS MB |
|---|--:|--:|
| bs2 | 97.79 | 5443 |
| nec5 | 93.02 | 105 |
| razor-2p | 73.36 | **6170** |
| bs1 | 39.80 | 2668 |
| sin | 9.52 | 1510 |
| pynec | 5.43 | 433 |

It is also the **one design of 103 whose refinement rung is a no-op**:
`nominal_nsegs` 21 → 42 moves the mesh only from 4,392 to 4,420 segments
(1.01×), because its segment count is set by a fixed structure rather than by
the knob. Its "refined" row is therefore a repeat measurement, not a rung, and
should not be read as a scaling data point.

razor-2p's 6.2 GB on this design is the single largest memory figure in the
catalog and the number most likely to become a MEM failure on a larger box
budget.

## Against the #927 runtime-arcs ladder — matched exactly

`scratch/runtime-arcs-ladders.jsonl` measured `arrays.bowtiearray2x4` on
momwire **0.29.0**. Its `basis` column is `bench_converge.total_nominal_segs`
and its `n_per_wire` is `nominal_nsegs` — verified, n = 9 → 304 and n = 35 →
1216, exactly the recorded basis. Same geometry, same Sommerfeld ground, same
box, same rungs, so the two are directly comparable.

**The comparison is valid because the answers agree**: Z matches to 1.8×10⁻⁶
relative on `sin` at every rung, and to 3×10⁻³ on bs2 — the bs2 drift being
the 0.45.0 quadrature split, which is expected and shrinks with basis.

| engine | basis | 0.29.0 s | today s | Δ | 0.29.0 MB | today MB | Δ |
|---|--:|--:|--:|--:|--:|--:|--:|
| bs2 | 304 | 0.5187 | 0.1629 | **−69 %** | 116 | 134 | +16 % |
| bs2 | 1216 | 1.7700 | 1.6993 | −4 % | 372 | 406 | +9 % |
| bs2 | 3968 | 17.180 | 16.987 | −1 % | 682 | 766 | +12 % |
| bs2 | 8320 | 92.654 | 78.141 | −16 % | 2310 | 2592 | +12 % |
| sin | 304 | 0.4660 | 0.0428 | **−91 %** | 108 | 122 | +13 % |
| sin | 1216 | 1.2340 | 0.5256 | **−57 %** | 316 | 364 | +15 % |
| sin | 3968 | 15.787 | 6.744 | **−57 %** | 681 | 741 | +9 % |
| sin | 8320 | 172.58 | 39.542 | **−77 %** | 1516 | 1639 | +8 % |

### Every cost that moved more than 20 %

- **`sin` wall time, at every rung: −57 % to −91 %.** The sinusoidal basis is
  between 2.3× and 11× faster than it was at 0.29.0, and the gain is largest
  at the large end (−77 % at basis 8320), which is where it matters.
- **`bs2` wall time at small basis: −69 %** (304). The gain disappears by
  basis 1216 and returns only weakly at 8320 (−16 %), so this is fixed
  overhead removed rather than the solve itself getting faster.
- **Nothing moved more than 20 % on memory, in either direction.** Every rung
  is 8–16 % heavier than at 0.29.0 — consistent, modest, and worth noting as a
  slow drift rather than a regression.

## Findings filed

- **#1264** — the Sinusoidal engine raises a `TypeError` instead of refusing
  on a `PortAtVertex` design.
- A "cost" column for the design tab list is a separate issue and deliberately
  not built here; this run is the data that would populate it.

## Caveats

- One box, one ground, one refinement rung. Costs under `pec` or free space
  are not measured and will differ.
- `peak_rss_mb` includes the ~90–100 MB interpreter floor.
- NEC-5's RSS measures the Python side only; its solver is an external binary.
- `verticals.elt_whip`'s refined row is a repeat, not a rung (above).

## Addendum — the two accelerators against dense bs2

`HMatrixSolver` and `ArrayBlockSolver` were left out of the run above. They are
`BSplineSolver` **subclasses at the same degree**, so they are measured against
bs2 rather than against each other: same basis, same mesh, same expected
answer, only the matrix representation differs. 412 further cells, same box,
same rungs, same warm-solve discipline with the cache cleared, one process per
cell. The ladder JSONL now holds all eight engines (1,648 cells).

### The verdict is one-sided

| | cells | faster than bs2 | same | slower | lighter | heavier | faster **and** lighter |
|---|--:|--:|--:|--:|--:|--:|--:|
| hmatrix | 196 | **0** | 0 | 196 | 24 | 16 | **0** |
| arrayblock | 196 | **54** | 0 | 142 | 34 | 16 | **27** |

**H-matrix never wins.** Not "usually slower" — zero cells faster than dense
d=2, on every design and both rungs. It is lighter on memory in 24 cells, but
never lighter *and* faster. On this catalog there is no design for which it is
the right choice.

**ArrayBlock wins on 54 of 196**, and half of those (27) are also lighter.

### Where ArrayBlock wins, and why it is not "arrays"

The wins look like a namespace at first — 36 of 54 are `arrays.*` — but the
other 18 give the rule away:

| ×faster | design | rung | segments | bs2 → arrayblock |
|--:|---|---|--:|---|
| 45.4 | `arrays.bowtie16x1` | refined | 2752 | 8.268 s → 0.182 s |
| 40.4 | `arrays.bowtie4x4` | refined | 2752 | 8.014 s → 0.198 s |
| 36.7 | `arrays.bowtiearray2x4` | refined | 1456 | 2.413 s → 0.066 s |
| 27.9 | `arrays.delta_looparray_2x2` | refined | 754 | 0.962 s → 0.035 s |
| 23.2 | `arrays.yagiarray` | refined | 1312 | 1.923 s → 0.083 s |
| 17.1 | `wire.lazy_h` | refined | 336 | 0.214 s → 0.013 s |
| 16.8 | `wire.expanded_lazy_h` | refined | 420 | 0.303 s → 0.018 s |
| 16.6 | `wire.sterba_bl` | refined | 839 | 0.933 s → 0.056 s |
| 14.2 | `verticals.four_square` | refined | 320 | 0.195 s → 0.014 s |
| 13.5 | `beams.yagi` | refined | 308 | 0.182 s → 0.013 s |
| 12.7 | `wire.w8jk` | refined | 216 | 0.116 s → 0.009 s |
| 10.1 | `verticals.phased_verticals` | refined | 168 | 0.079 s → 0.008 s |

Lazy-H, Sterba curtains, four-square, phased verticals, W8JK, Yagis. The
predictor is **repeated translated elements**, not the design's namespace —
which is what ArrayBlock exploits, so the result is the one its name promises,
spread across four namespaces.

Two secondary patterns:

- **Every design that wins, wins harder at the refined rung** (e.g.
  `bowtie16x1` 24.9× → 45.4×). The block structure pays off as the dense matrix
  grows, so the advantage widens exactly where dense hurts most.
- **Memory follows time but more weakly.** `bowtie4x4` refined drops 540 MB →
  265 MB, but `bowtie16x1` refined goes *up*, 540 MB → 613 MB, while still being
  45× faster. Speed and footprint are not the same trade here.

### Where dense bs2 is simply better

The other 142 arrayblock cells and all 196 hmatrix cells. Anything without
repeated structure — single dipoles, verticals, loops, fans — pays the
accelerator's setup cost for nothing.

Sharpest case: **`verticals.elt_whip` times out past 600 s on both
accelerators**, where dense bs2 solves it in 98 s. On the catalog's single most
expensive design, both accelerators are more than 6× worse before being killed.

### Refusals (all properly worded)

Both accelerators refuse the same four designs, with a sentence each:
`specialty.buried_dipole`, `verticals.buried_radial_vertical`,
`verticals.elevated_buried_counterpoise` — "cannot solve this design's buried
geometry", correct, neither has buried fill — and `wire.terminated_longwire`
on the below/below domain limit. Plus the `elt_whip` timeouts above.

### The catch: they do not always agree with bs2 — momwire#971

Same basis and same mesh should mean the same answer. **15 cells across 5
designs disagree with dense bs2 by more than 1e-3 relative**, worst 7.4 %:

| relative ΔZ | engine | rung | design | accelerator | dense bs2 |
|--:|---|---|---|--:|--:|
| **7.4e-2** | arrayblock | refined | `arrays.folded_invveearray` | 214.054 + 1.134j | 199.312 + 0.120j |
| 3.7e-2 | hmatrix | refined | `arrays.folded_invveearray` | 206.508 − 1.572j | 199.312 + 0.120j |
| 1.4e-2 | arrayblock | refined | `arrays.moxonarray` | 38.653 − 27.141j | 39.241 − 26.831j |
| 7.1e-3 | arrayblock | refined | `wire.sterba_bl` | 680.425 + 406.999j | 674.831 + 407.463j |

Two things make this more than a tolerance: the disagreement **grows with
refinement** (folded_invveearray 1.5e-2 default → 7.4e-2 refined), which a rank
truncation should not do; and both accelerators move on the same designs in
*different directions*. The affected designs are all repeated-element — the
same family where the accelerators win — so the speedup and the discrepancy sit
on the same decks. Filed as **momwire#971**.

### Recommendation

ArrayBlock is worth offering **only** on repeated-element geometry, and only
once #971 is settled: a 45× speedup on `bowtie16x1` is real, but
`folded_invveearray` is in the same winning set and is the worst impedance
disagreement in the run. H-matrix has no case on this catalog at present.
