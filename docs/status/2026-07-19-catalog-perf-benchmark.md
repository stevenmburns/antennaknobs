# 2026-07-19 — Full-catalog runtime + peak-RSS benchmark (across ground models)

## TL;DR

`scripts/bench_catalog.py` solves **every built-in design (91) on all four
engines** (PyNEC / Sinusoidal / BSpline d=1 / BSpline d=2) at each design's
as-shipped default mesh (`nominal_nsegs=21`), under **four ground models**
(free / pec / fast-finite / Sommerfeld). One fresh interpreter per solve for a
clean `getrusage` peak RSS, BLAS+OpenMP pinned to the physical core count
(mirrors `web/server.py`), an `RLIMIT_AS` cap so a runaway solve fails clean.

**~1456 solves, all succeed.** The main sweep guard-skipped the finite grounds
for `verticals.elt_whip` (the intentional 4392-seg W8IO stress design); a
follow-up run with the guard lifted filled in those 8 cells — see
[The elt_whip finite-ground ceiling](#the-elt_whip-finite-ground-ceiling).

Headline findings:

- **free → pec → fast-finite are all cheap and stay interactive.** Median solve
  multiplier over free space is just **1.2× (pec)** and **1.3–1.4× (fast)**.
  The reflection-coefficient finite ground is nearly free — a fine stand-in for
  quick iteration. ~80/91 designs stay under 100 ms even on the slowest engine
  (BSpline d=2) for all three of these models.
- **Sommerfeld is a cliff, and it is the whole cost story.** Median solve jumps
  to **9.4× free on PyNEC** but **45–83× free on the momwire bases**.
- **On Sommerfeld, momwire is ~13× slower than PyNEC** across all three momwire
  bases (median ~470–490 ms vs PyNEC's 36 ms). NEC's gn 2 interpolation-table
  Sommerfeld crushes momwire's dense Sommerfeld path. **PyNEC stays interactive
  on Sommerfeld (median 36 ms); momwire does not (0/91 designs under 100 ms,
  median ~490 ms, up to ~86 s on the 4392-seg stress design).**
- **PyNEC's speed lead inverts on networked/large designs** regardless of
  ground: e.g. `broadband.lpda` is the one design where PyNEC's *Sommerfeld* is
  slower than momwire's (1589 ms vs ~1200 ms) — its many wires hit PyNEC's
  multiport-Y reducer. Free-space `lpda`: PyNEC 741 ms vs Sinusoidal 72 ms.
- **Memory:** floor ~91 MB (import baseline) dominates everything except the big
  meshes. `pec` costs momwire ~30 % more memory than free (image method). The
  real memory-scaling flag is momwire's higher-order bases on a large structure:
  `elt_whip` BSpline d=2 climbs from **10.7 GB (free)** to **14.0 GB (fast)** to
  **18.5 GB (Sommerfeld)**. PyNEC stays flat at **422 MB on every ground** — ~40×
  leaner — because NEC stores one N×N matrix plus interpolation tables and
  nothing else. This is why the `--mem-gb` cap exists.

**Practical takeaway:** for the web UI, `fast`-finite ground is the sweet spot
for interactive iteration on any engine; **Sommerfeld should route to PyNEC**,
where it stays sub-100 ms for the vast majority of designs, rather than momwire's
dense path that puts every solve in the 0.5–6 s range.

## Companion files (this folder)

- [`2026-07-19-catalog-perf-benchmark.csv`](./2026-07-19-catalog-perf-benchmark.csv)
  — the full tidy dataset (364 rows: 91 designs × 4 ground models), one solve
  per engine per row. Import into any spreadsheet to sort/pivot.
- [`2026-07-19-catalog-perf-benchmark.html`](./2026-07-19-catalog-perf-benchmark.html)
  — a self-contained interactive dashboard (ground toggle, sortable table,
  family filter, latency color-coding). Open it in a browser; no dependencies.

## Method

```
python scripts/bench_catalog.py --out catalog_perf_grounds.json
```

Ground specs are identical to `profile_ground_models.py` / the web adapter
(`fast` and `somm` share `DEFAULT_GROUND = ('finite', 10.0, 0.002)` and differ
only in solve method). Each `(design, ground, engine)` runs in its own
subprocess: `OMP_WAIT_POLICY=PASSIVE`, `GOMP_SPINCOUNT=0`, BLAS/OpenMP =
physical cores, serial dispatch, 24 GB `RLIMIT_AS` per solve. Wall-clock is
`perf_counter()` around `engine.impedance()` (geometry build included, imports
excluded); peak RSS is `ru_maxrss` for the whole worker (so it **includes** the
~91 MB import baseline). The main sweep skips finite-ground solves for designs
with Σseg > 2000 (only `elt_whip`), logged not hidden; a follow-up run
(`--max-seg-finite 0 --mem-gb 27`) measured those directly and their numbers are
merged into the tables below.

Scope: default variant per design, each at its own default frequency and mesh.

## Rollup — median / max solve + peak RSS, per ground × engine

| ground | engine | n | median | max | RSS floor | RSS max |
|---|---|---|---|---|---|---|
| free | PyNEC | 91 | 3.8 ms | 3172 ms | 91 MB | 422 MB |
| free | Sinusoidal | 91 | 5.7 ms | 6471 ms | 91 MB | 1958 MB |
| free | BSpline d=1 | 91 | 9.4 ms | 22182 ms | 91 MB | 5051 MB |
| free | BSpline d=2 | 91 | 10.8 ms | 58134 ms | 91 MB | 10738 MB |
| pec | PyNEC | 91 | 4.7 ms | 3968 ms | 91 MB | 422 MB |
| pec | Sinusoidal | 91 | 6.7 ms | 8153 ms | 91 MB | 2889 MB |
| pec | BSpline d=1 | 91 | 10.8 ms | 25313 ms | 91 MB | 6457 MB |
| pec | BSpline d=2 | 91 | 13.7 ms | 67542 ms | 91 MB | 13702 MB |
| fast | PyNEC | 91 | 5.2 ms | 4386 ms | 91 MB | 422 MB |
| fast | Sinusoidal | 91 | 7.6 ms | 10796 ms | 91 MB | 3668 MB |
| fast | BSpline d=1 | 91 | 12.4 ms | 30118 ms | 91 MB | 6769 MB |
| fast | BSpline d=2 | 91 | 15.4 ms | 72653 ms | 91 MB | 14012 MB |
| somm | PyNEC | 91 | 36.0 ms | 7246 ms | 91 MB | 422 MB |
| somm | Sinusoidal | 91 | 473.8 ms | 16407 ms | 92 MB | 5665 MB |
| somm | BSpline d=1 | 91 | 481.6 ms | 38023 ms | 91 MB | 9863 MB |
| somm | BSpline d=2 | 91 | 493.3 ms | 86045 ms | 92 MB | 18504 MB |

<sub>Every max cell (all grounds) is `verticals.elt_whip`. Its finite-ground rows
come from the follow-up run; medians are unmoved by the one outlier, but the
max and RSS-max columns for `fast`/`somm` now reflect it.</sub>

### Ground-model cost multiplier (median solve ÷ free-space median)

| | PyNEC | Sinusoidal | BSpline d=1 | BSpline d=2 |
|---|---|---|---|---|
| free | 1.0× | 1.0× | 1.0× | 1.0× |
| pec | 1.2× | 1.2× | 1.2× | 1.3× |
| fast | 1.4× | 1.3× | 1.3× | 1.4× |
| **somm** | **9.4×** | **83.4×** | **51.4×** | **45.7×** |

On Sommerfeld, momwire is **~13× slower than PyNEC** (470–490 ms vs 36 ms) on
every basis.

## Sommerfeld per-design cost (slowest 15; solve ms, max peak RSS MB)

Note `broadband.lpda` — the sole design where PyNEC's Sommerfeld is the
*slowest* engine (network reducer overhead). `elt_whip` (from the follow-up run)
now tops the list.

| design | Σseg | PyNEC | Sinusoidal | BSpline d=1 | BSpline d=2 | RSS |
|---|---|---|---|---|---|---|
| `verticals.elt_whip` | 4392 | 7245.8 | 16406.9 | 38022.6 | 86045.2 | 18504 |
| `wire.terminated_longwire` | 1006 | 390.4 | 5418.9 | 5854.2 | 6157.5 | 718 |
| `wire.rhombic` | 1010 | 329.3 | 3353.1 | 3604.0 | 3811.9 | 722 |
| `arrays.bowtiearray2x4` | 1360 | 653.3 | 2256.1 | 2686.1 | 3125.1 | 674 |
| `wire.sterba` | 378 | 75.5 | 1261.4 | 1294.9 | 1323.9 | 140 |
| `broadband.lpda` | 618 | 1588.5 | 1108.6 | 1203.1 | 1290.5 | 327 |
| `wire.longwire` | 293 | 57.4 | 1226.4 | 1257.1 | 1278.8 | 122 |
| `arrays.delta_looparray_2x2` | 256 | 50.4 | 1220.0 | 1238.6 | 1252.2 | 117 |
| `wire.expanded_lazy_h` | 210 | 92.6 | 1207.4 | 1230.4 | 1231.9 | 119 |
| `arrays.bowtiearray` | 680 | 193.6 | 925.0 | 1065.2 | 1210.7 | 238 |
| `arrays.yagiarray` | 676 | 201.5 | 884.0 | 1039.7 | 1165.9 | 234 |
| `arrays.moxonarray` | 592 | 150.5 | 840.7 | 952.5 | 1061.4 | 201 |
| `arrays.delta_looparray_1x4` | 256 | 53.3 | 908.5 | 922.7 | 957.5 | 117 |
| `wire.lazy_h` | 170 | 38.6 | 883.4 | 891.1 | 897.4 | 102 |
| `wire.sterba_tl` | 99 | 281.5 | 873.8 | 881.3 | 882.5 | 98 |

### The elt_whip finite-ground ceiling

The main sweep guard-skipped `verticals.elt_whip` (4392 seg) on the finite
grounds out of caution — its free-space BSpline d=2 solve already used 10.7 GB.
A follow-up run (`--max-seg-finite 0 --mem-gb 27`) measured it directly and
**nothing hit the wall**:

| ground | PyNEC | Sinusoidal | BSpline d=1 | BSpline d=2 |
|---|---|---|---|---|
| fast | 4.4 s / 422 MB | 10.8 s / 3.7 GB | 30.1 s / 6.8 GB | 72.7 s / 14.0 GB |
| somm | 7.2 s / 422 MB | 16.4 s / 5.7 GB | 38.0 s / 9.9 GB | 86.0 s / 18.5 GB |

Takeaways: (1) it was never a machine limit — the heaviest solve (Sommerfeld
BSpline d=2) peaked at **18.5 GB**, under even the main sweep's 24 GB cap; the
`Σseg > 2000` guard tripped first. (2) The real ceiling is **momwire memory on
higher-order bases** — BSpline d=2 needs 14–18.5 GB here, which fits a 31 GB box
but would OOM a 16 GB laptop. (3) **PyNEC is flat at 422 MB on every ground**
(~40× leaner), and its Sommerfeld is only ~1.6× its fast-finite time — so for
large structures on finite ground, PyNEC is the memory-safe choice by a wide
margin.

## Free-space per-design table (baseline)

Solve times in **ms**; `RSS` is the max peak RSS across the four engines in
**MB** (≈ the 91 MB import floor for most designs). `Σseg` is the total nominal
segment count at the default mesh.

| design | Σseg | PyNEC | Sinusoidal | BSpline d=1 | BSpline d=2 | RSS |
|---|---|---|---|---|---|---|
| `arrays.bowtiearray` | 680 | 126.6 | 67.3 | 207.0 | 197.3 | 171 |
| `arrays.bowtiearray1x2` | 340 | 69.7 | 19.2 | 29.5 | 36.3 | 111 |
| `arrays.bowtiearray2x4` | 1360 | 195.4 | 298.1 | 448.4 | 530.6 | 406 |
| `arrays.delta_looparray` | 128 | 3.9 | 5.6 | 12.8 | 11.4 | 95 |
| `arrays.delta_looparray_1x4` | 256 | 11.1 | 12.4 | 20.4 | 27.1 | 103 |
| `arrays.delta_looparray_1x4_grouped` | 256 | 13.3 | 14.2 | 23.3 | 32.8 | 102 |
| `arrays.delta_looparray_2x2` | 256 | 10.8 | 12.4 | 24.1 | 31.4 | 102 |
| `arrays.delta_looparray_network` | 128 | 20.7 | 10.7 | 9.2 | 11.0 | 98 |
| `arrays.delta_looparray_with_tls` | 129 | 4.2 | 12.3 | 9.4 | 12.0 | 98 |
| `arrays.folded_invveearray` | 432 | 24.7 | 28.2 | 99.5 | 118.8 | 123 |
| `arrays.hentenna_array` | 338 | 15.6 | 18.5 | 27.3 | 35.8 | 110 |
| `arrays.hourglass_array` | 338 | 21.9 | 19.3 | 28.1 | 41.2 | 110 |
| `arrays.invveearray` | 172 | 5.4 | 7.6 | 12.4 | 15.1 | 97 |
| `arrays.lumped_coupled_pair` | 80 | 3.7 | 3.7 | 5.3 | 6.3 | 94 |
| `arrays.moxonarray` | 592 | 41.6 | 53.0 | 129.0 | 151.3 | 150 |
| `arrays.yagiarray` | 676 | 52.1 | 65.1 | 140.5 | 168.1 | 168 |
| `beams.hb9cv` | 84 | 3.5 | 4.1 | 5.7 | 6.6 | 93 |
| `beams.hexbeam` | 158 | 4.7 | 6.4 | 9.9 | 12.6 | 95 |
| `beams.moxon` | 148 | 4.4 | 5.9 | 8.9 | 10.9 | 94 |
| `beams.moxon_turnstile` | 296 | 37.1 | 19.7 | 20.8 | 26.0 | 111 |
| `beams.owa_yagi` | 158 | 4.8 | 6.2 | 9.8 | 12.8 | 96 |
| `beams.phased_driver_yagi` | 119 | 14.6 | 5.4 | 8.3 | 9.5 | 96 |
| `beams.yagi` | 169 | 5.3 | 7.0 | 19.7 | 13.3 | 96 |
| `broadband.discone` | 373 | 19.5 | 22.9 | 34.2 | 67.1 | 115 |
| `broadband.g5rv` | 127 | 4.5 | 53.9 | 8.5 | 10.7 | 96 |
| `broadband.lpda` | 618 | 741.1 | 71.8 | 134.6 | 156.8 | 172 |
| `broadband.t2fd` | 104 | 3.2 | 5.1 | 21.2 | 16.6 | 94 |
| `dipoles.dipole_turnstile` | 86 | 1.9 | 3.7 | 6.4 | 7.3 | 92 |
| `dipoles.folded_invvee` | 108 | 4.5 | 4.4 | 7.6 | 9.3 | 94 |
| `dipoles.folded_invvee_balun` | 108 | 7.1 | 12.0 | 7.4 | 9.0 | 94 |
| `dipoles.invvee` | 43 | 1.2 | 2.3 | 4.0 | 4.3 | 92 |
| `dipoles.invvee_coax_station` | 43 | 1.4 | 2.6 | 3.8 | 4.1 | 92 |
| `dipoles.koch_dipole` | 65 | 1.6 | 4.4 | 10.3 | 11.0 | 92 |
| `dipoles.ocf_dipole` | 41 | 1.1 | 2.2 | 3.9 | 4.5 | 93 |
| `dipoles.pota_invvee` | 43 | 1.1 | 2.5 | 4.9 | 5.6 | 93 |
| `dipoles.short_dipole_loaded` | 21 | 1.1 | 2.1 | 2.8 | 2.9 | 93 |
| `loops.bisquare` | 184 | 5.9 | 7.1 | 12.6 | 24.0 | 100 |
| `loops.delta_loop` | 64 | 1.5 | 3.1 | 5.0 | 5.9 | 93 |
| `loops.delta_loop_flyby` | 64 | 2.4 | 4.1 | 6.1 | 6.8 | 93 |
| `loops.delta_loop_reflected` | 64 | 2.0 | 3.8 | 5.8 | 6.6 | 94 |
| `loops.delta_loop_slanted` | 128 | 7.9 | 16.1 | 9.5 | 11.9 | 95 |
| `loops.delta_loop_topdown` | 64 | 2.2 | 3.8 | 6.1 | 6.8 | 94 |
| `loops.diamond_loop` | 85 | 1.9 | 3.5 | 6.2 | 7.3 | 93 |
| `loops.diamond_loop_turnstile` | 170 | 5.4 | 7.1 | 11.9 | 14.5 | 97 |
| `loops.horizontal_loop` | 89 | 2.1 | 3.5 | 6.5 | 7.3 | 93 |
| `loops.horizontal_loop_drone` | 85 | 2.0 | 3.7 | 6.3 | 7.2 | 93 |
| `loops.inv_delta_loop` | 64 | 1.5 | 3.1 | 5.7 | 5.7 | 93 |
| `loops.quad` | 172 | 5.8 | 7.3 | 11.3 | 14.6 | 98 |
| `loops.skyloop_lmatch` | 90 | 2.4 | 4.2 | 6.5 | 7.0 | 94 |
| `loops.triangular_skyloop` | 90 | 2.2 | 3.8 | 7.0 | 8.0 | 94 |
| `multiband.fandipole` | 421 | 23.4 | 26.4 | 118.3 | 115.0 | 121 |
| `multiband.hexbeam_5band` | 750 | 63.9 | 79.6 | 150.2 | 186.1 | 186 |
| `multiband.trap_dipole` | 64 | 1.5 | 3.8 | 5.6 | 6.1 | 93 |
| `multiband.trap_fan_dipole` | 103 | 3.2 | 6.7 | 10.1 | 10.9 | 94 |
| `multiband.twoband_fan_dipole` | 105 | 3.1 | 4.4 | 14.9 | 9.6 | 93 |
| `specialty.bowtie` | 170 | 5.3 | 6.9 | 11.4 | 14.9 | 96 |
| `specialty.helix` | 53 | 1.5 | 3.9 | 11.4 | 11.9 | 93 |
| `specialty.hentenna` | 169 | 5.3 | 7.1 | 11.0 | 13.9 | 96 |
| `specialty.hentenna_slant` | 211 | 7.4 | 8.9 | 23.8 | 19.8 | 98 |
| `specialty.hourglass` | 169 | 5.5 | 6.9 | 11.2 | 14.3 | 95 |
| `specialty.hourglass_slant` | 211 | 7.5 | 9.0 | 14.3 | 17.8 | 98 |
| `verticals.bobtail` | 151 | 4.7 | 5.9 | 10.2 | 13.4 | 96 |
| `verticals.bruce` | 189 | 6.3 | 7.8 | 12.1 | 16.1 | 96 |
| `verticals.challenger` | 29 | 1.3 | 2.4 | 4.2 | 4.4 | 94 |
| `verticals.dominator` | 32 | 1.3 | 2.5 | 4.3 | 4.5 | 92 |
| `verticals.elt_whip` | 4392 | 2977.9 | 6529.8 | 22775.1 | 61135.7 | 10739 |
| `verticals.four_square` | 164 | 5.2 | 7.2 | 11.7 | 14.0 | 96 |
| `verticals.half_square` | 86 | 1.8 | 3.5 | 5.5 | 6.8 | 93 |
| `verticals.inverted_l` | 42 | 1.1 | 2.7 | 5.5 | 5.9 | 93 |
| `verticals.inverted_l_tmatch` | 42 | 1.3 | 2.8 | 5.4 | 5.9 | 92 |
| `verticals.jpole` | 86 | 2.3 | 3.7 | 7.2 | 8.3 | 94 |
| `verticals.phased_verticals` | 86 | 1.9 | 3.6 | 6.1 | 7.0 | 93 |
| `verticals.pota_performer` | 36 | 1.2 | 2.5 | 5.7 | 6.2 | 92 |
| `verticals.raised_vertical` | 64 | 1.4 | 3.1 | 5.1 | 6.0 | 93 |
| `verticals.rectangle` | 87 | 2.7 | 4.0 | 6.3 | 7.2 | 94 |
| `verticals.right_angle_delta` | 90 | 2.0 | 3.5 | 6.4 | 8.4 | 93 |
| `verticals.tri_moxon` | 252 | 51.9 | 14.9 | 19.2 | 30.8 | 106 |
| `verticals.vertical` | 37 | 1.1 | 2.9 | 5.1 | 5.3 | 92 |
| `wire.doublet_ladder_tuner` | 43 | 1.4 | 2.7 | 3.8 | 4.1 | 92 |
| `wire.edz` | 105 | 4.6 | 4.5 | 7.1 | 11.7 | 94 |
| `wire.efhw_sloper` | 42 | 1.7 | 3.0 | 5.0 | 5.6 | 94 |
| `wire.expanded_lazy_h` | 210 | 33.2 | 16.9 | 14.0 | 18.3 | 103 |
| `wire.lazy_h` | 170 | 5.5 | 6.8 | 11.0 | 14.1 | 96 |
| `wire.longwire` | 293 | 11.0 | 13.4 | 30.6 | 42.2 | 120 |
| `wire.rhombic` | 1010 | 88.2 | 180.6 | 241.8 | 316.5 | 325 |
| `wire.sterba` | 378 | 20.2 | 21.4 | 33.9 | 48.7 | 115 |
| `wire.sterba_tl` | 99 | 17.5 | 6.0 | 10.1 | 10.2 | 94 |
| `wire.terminated_longwire` | 1006 | 83.2 | 180.4 | 417.8 | 535.3 | 562 |
| `wire.vbeam` | 169 | 5.4 | 6.7 | 12.5 | 16.8 | 101 |
| `wire.w8jk` | 106 | 3.1 | 10.7 | 7.2 | 8.9 | 94 |
| `wire.zepp` | 41 | 1.5 | 2.7 | 3.7 | 4.0 | 94 |

## Reproduce

```
python scripts/bench_catalog.py                          # all designs+grounds
python scripts/bench_catalog.py --grounds free fast somm
python scripts/bench_catalog.py --engines sin bs2 --grounds free somm
python scripts/bench_catalog.py --designs loops.quad beams.yagi
# the elt_whip finite-ground follow-up (guard lifted, higher mem cap):
python scripts/bench_catalog.py --designs verticals.elt_whip \
    --grounds fast somm --max-seg-finite 0 --mem-gb 27
```

Numbers above were taken on the development machine (BLAS=OpenMP=4, 31 GB RAM).
Absolute times drift with hardware; the *ratios* between engines and ground
models, and the shape of the tail, are the portable findings.
