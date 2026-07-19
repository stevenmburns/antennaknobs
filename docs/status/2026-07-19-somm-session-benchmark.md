# 2026-07-19 — Sommerfeld session benchmark (momwire #159 measured)

## TL;DR

The momwire Sommerfeld perf work (momwire#159: PR #160 near/far grid split,
PR #162 frequency-axis grid reuse) needed a **session-shaped** measurement —
`bench_catalog.py` is deliberately cold (one fresh interpreter per solve, one
frequency per design), which captures the grid-split tail but is structurally
blind to frequency reuse, whose whole benefit lives in the second and later
solves of a session.

New harness: `scripts/bench_somm_sweep.py` — per (design, engine) one worker
runs a cold solve then a **21-point ±1.5 % band-locked sweep**, fresh
builder + engine per point (the web knob-tick pattern), reporting cold ms,
sweep total, momwire grid-fill count, and the median **warm tick** (points
that filled no grid).

Headline (90 designs, `elt_whip` guard-skipped, 12 GB caps, default ground):

- **The engine-routing recommendation inverts on sweeps.** The catalog
  status doc's takeaway was "Sommerfeld should route to PyNEC". On band
  sweeps that is no longer true at steady state: **Sinusoidal's warm tick
  (median 11.1 ms) beats PyNEC's per-tick (median ~40 ms) on 86/90
  designs; BSpline d=2 (21.6 ms) on 68/90.** PyNEC re-pays its SOMNEC
  setup on every tick; momwire now fills once per Im-ε̃ ladder rung
  (3–4 fills per ±1.5 % sweep) and every other tick is warm.
- **Cold solves: the tail collapsed** (the #160 split): catalog somm max
  6.16 s → 3.49 s (bs2), 5.42 s → 2.18 s (sin); terminated_longwire
  6.16 → 3.09 s, rhombic 3.81 → 2.50 s. Medians eased 490 → 401 ms /
  470 → 380 ms — a mix of the ≥4 λ designs' gains and run-to-run
  variance; sub-4 λ cold fills are intentionally unchanged.
- **First-sweep totals** still carry the fills: momwire median 1.7–2.0 s
  per 21-point sweep vs PyNEC's 0.83 s. Repeat sweeps and continued drags
  run at the warm-tick rate (the module cache persists per process), so
  momwire wins any session longer than roughly one sweep.

## Sweep benchmark — median over 90 designs

| engine | cold | sweep (21 pts) | fills | warm tick |
|---|---|---|---|---|
| PyNEC | 34 ms | 834 ms | – (internal, every tick) | 38.6 ms |
| Sinusoidal | 400 ms | 1672 ms | 3 | **11.1 ms** |
| BSpline d=2 | 415 ms | 1973 ms | 3 | **21.6 ms** |

Fill counts are a function of the band's fractional width (the Im-ε̃ ladder
is 1 %): ±1.5 % ⇒ 3–4 fills; a single-channel sweep lands 1–2. Expected
behavior, not noise.

Notable rows: big designs remain assembly-dominated warm (rhombic bs2 warm
tick 1.18 s at 1010 segs — the O(N²) solve, not the ground); sterba_tl,
whose 99-seg solve was 96 % grid fill in the original profiling, now warm-
ticks at 8.8 ms (sin) / 15.1 ms (bs2) vs PyNEC's 260 ms (its multiport
reducer hurts it there).

## Catalog somm slice re-run (cold, per-solve — captures #160 only)

| engine | median (was) | max (was) |
|---|---|---|
| PyNEC | 32.7 ms (35.9) | 1734 ms (1589, lpda) |
| Sinusoidal | 380 ms (470) | **2177 ms (5419)** |
| BSpline d=1 | 399 ms (481) | **2707 ms (5854)** |
| BSpline d=2 | 401 ms (490) | **3493 ms (6158)** |

All 90 designs solve; only `verticals.elt_whip` is guard-skipped. Peak RSS
unchanged in character (max 739 MB).

## Caveats

- Measured against **momwire main (post #160/#162) via the editable
  submodule**, not the pinned `momwire==0.14.0` wheel — CI and fresh clones
  will not reproduce these numbers until a momwire 0.15.0 release + pin
  bump lands.
- The warm-tick cross-over is per-process: the web backend holds one
  process, so it applies directly; CLI one-shot invocations are the cold
  column.
- Baseline numbers are `docs/status/2026-07-19-catalog-perf-benchmark.md`
  (same machine, same guards).

## Reproduce

```
python scripts/bench_somm_sweep.py --out bench_out/somm_sweep.json
python scripts/bench_catalog.py --grounds somm
```
