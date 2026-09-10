# Blocked ACA row sampling across the catalog: b = 1 against b = 8

**Evidence, not a recommendation.** momwire#1028, which came out of momwire#981's
batching step (closed negative on cost). Measured 2026-09-10 on momwire
`94a14ad` plus the opt-in branch `perf/981-blocked-aca` (`3fc1f4b`), Skylake box.

## Method

Identical to the b = 1 census in `2026-09-09-hmatrix-catalog-residual-census.md`
— 99 designs, finite ground `(13.0, 0.005)`, app-default mesh, momwire
`HMatrixSolver(degree=2)` against dense `BSplineSolver(degree=2)`,
`rel_z_vs_dense = |Z_h − Z_d| / |Z_d|` on the drive port — with one change: the
Sommerfeld remainder's ACA fetches **8 rows per call** instead of 1. Per-deck
rows in `2026-09-10-hmatrix-catalog-residual-census-b8.jsonl`.

## Headline

**32 decks above 1e-6 → 26.** Seven came under, one crossed above.

## The tail improves by two orders

| deck | b = 1 | b = 8 | rank |
|---|--:|--:|---|
| `multiband.twoband_fan_dipole` | 3.28e-04 | 1.39e-06 | 11 → 16 |
| `beams.owa_yagi` | 9.06e-05 | 6.65e-07 | 12 → 15 |
| `multiband.trap_fan_dipole` | 5.46e-05 | 5.23e-07 | 16 → 22 |

The three worst decks in the catalog improve 236×, 136× and 104×, and in each
case the **rank goes up** — the b = 1 factorization was stopping early.

## The middle gets worse

19 decks are more than 2× worse (counting only those above 1e-8, so this
is not float noise):

| deck | b = 1 | b = 8 | factor |
|---|--:|--:|--:|
| `verticals.challenger` | 3.50e-09 | 5.29e-08 | 15.1× |
| `verticals.bruce` | 3.43e-08 | 4.86e-07 | 14.2× |
| `beams.moxon` | 1.29e-07 | 9.57e-07 | 7.4× |
| `verticals.bobtail` | 4.56e-08 | 3.25e-07 | 7.1× |
| `beams.hb9cv` | 9.95e-08 | 6.45e-07 | 6.5× |
| `arrays.delta_looparray_2x2` | 2.69e-07 | 1.31e-06 | 4.9× |
| `verticals.dominator` | 4.47e-08 | 2.04e-07 | 4.6× |
| `wire.sterba_tl` | 6.65e-08 | 3.02e-07 | 4.5× |
| `arrays.bowtie1x2_bl` | 3.89e-08 | 1.23e-07 | 3.2× |
| `arrays.delta_looparray` | 1.53e-06 | 4.22e-06 | 2.8× |
| `specialty.hentenna_slant` | 3.99e-08 | 1.03e-07 | 2.6× |
| `loops.bisquare` | 1.63e-07 | 4.11e-07 | 2.5× |
| `loops.skyloop_lmatch` | 4.54e-08 | 1.13e-07 | 2.5× |
| `wire.edz` | 8.47e-08 | 2.02e-07 | 2.4× |
| `wire.expanded_lazy_h` | 4.45e-08 | 1.03e-07 | 2.3× |
| `wire.w8jk` | 5.61e-08 | 1.27e-07 | 2.3× |
| `verticals.raised_vertical` | 4.77e-08 | 1.07e-07 | 2.2× |
| `dipoles.invvee` | 5.46e-08 | 1.17e-07 | 2.1× |
| `verticals.right_angle_delta` | 8.27e-08 | 1.70e-07 | 2.1× |

`arrays.delta_looparray_2x2` is the one that crosses 1e-6.

## The fallback set changes rather than shrinks

    b = 1:  dipoles.dipole_turnstile, loops.skyloop_lmatch
    b = 8:  dipoles.dipole_turnstile, beams.yagi, wire.vbeam

`loops.skyloop_lmatch` stops stagnating — rank 94 = N and residual 1.16 become
rank 34 and 2.14e-05, which is the observation momwire#1028 was filed on. But
`beams.yagi` and `wire.vbeam` start. **A block is not immune to trapping; it
traps differently.**

## What this is

Better tail, worse middle, six fewer decks over the line, and — per momwire#981's
own ladder — slower on every deck at every block size tried. **It is a different
trade, not a better point.** Which decks matter is a judgement this census does
not make.
