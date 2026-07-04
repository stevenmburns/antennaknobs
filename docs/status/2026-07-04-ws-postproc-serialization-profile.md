# Profile: /ws phases 3 + 4 decision (post-processing skip + serialization)

Captured 2026-07-04 to decide whether phases 3 (skip stale post-processing) and
4 (serialization) of the latest-wins refactor are worth building. Phases 1+2
are merged (PR #226); 3+4 were left as "only if profiled" follow-ups.

Both targets are server-side CPU costs, so this profiles on localhost — no
fly.io deploy needed (the RTT-dependent tail-latency win is phases 1+2). Harness:
`scripts/profile_ws_postproc_serialization.py`.

## Test case + per-solver split

Worst-case design: `arrays.bowtiearray2x4` + N=21. Both solvers feed the *same*
1392-segment far-field integral (arrayblock and PyNEC both ship knot-only wire
arrays, no segment-midpoint samples), so the norm cost is ~constant across them;
only the core solve speed differs.

| metric | momwire/arrayblock | pynec (dense) |
|---|---|---|
| core solve (impedance/currents) | ~260–390 ms | ~580 ms |
| `_attach_derived_em_fields` | 0.01 ms | 0.01 ms |
| `_compute_directivity_norm` | ~425–433 ms | ~426 ms |
| total | ~700–800 ms | ~1007 ms |
| **post / total** | **52–62 %** | **42 %** |
| json.dumps → orjson.dumps | 3.4→0.27 ms (~13×) | 3.8→0.19 ms (~20×) |
| deepcopy (per cache hit) | ~1.6 ms | ~1.8 ms |
| payload | 128.6 KB | 138.2 KB |

(PyNEC on this design is ~0.6 s, not dozens of seconds — dense NEC at ~336
segments is sub-second; "dozens of seconds" needs higher N or Sommerfeld ground.)

## Headline: the directivity-norm grid is ~10–16× oversampled

`_compute_directivity_norm` (`server.py:156`) exists to produce **one scalar** —
`directivity_norm = 4π / ∫|M_perp|² dΩ`, the total-radiated-power normalizer.
Every per-direction value in its 45×90 = 4050-point grid is integrated away and
discarded; the displayed pattern is computed separately in JS (`App.tsx:5022+`,
along az/el cuts) and multiplied by this scalar.

A scalar power integral converges fast on the bowtie (reference = 180×360):

| grid | points | dB error vs ref | ms |
|---|---|---|---|
| 12×24 | 288 | −0.023 dB | 20 |
| 18×36 | 648 | −0.009 dB | 51 |
| 45×90 (current) | 4050 | −0.001 dB | 329 |

BUT the required resolution scales with **electrical size** (Nyquist for the
integral: ~2+ cells per pattern lobe, lobe count ∝ perimeter/λ). Stress test on
`loops.triangular_skyloop` (80m loop) run at harmonics:

| freq | loop size | 12×24 | 18×36 | 24×48 | 45×90 |
|---|---|---|---|---|---|
| 21 MHz (15m) | ~5.8λ | +0.001 | 0.000 | 0.000 | 0.000 |
| 28.5 MHz | ~7.9λ | −0.016 | −0.005 | −0.003 | −0.001 |
| 50 MHz | ~13.8λ | **−0.385** | −0.014 | −0.003 | −0.001 |
| 100 MHz | ~27.6λ | +0.107 | **−0.134** | −0.084 | 0.000 |

So a **fixed** coarse grid is NOT universally safe: at ~14λ, 12×24 is off
0.385 dB; at ~28λ even 18×36 is off 0.13 dB. Gain is read to ~0.1 dB, so the
grid must track the design's electrical extent. (The realistic 80m-on-15m case
is ~5.8λ and fine at 12×24 — the problem only bites at VHF harmonics / long
wires / big arrays.)

## How the norm is computed (for the optimization questions)

Fully numpy-vectorized, no Python loop over directions/segments. It materializes
the whole `(nθ, nφ, Nseg) = (45, 90, 1392) ≈ 5.6M`-element complex tensor in one
batch (doubled when ground is on — a second exp/einsum for the PEC image +
Fresnel). Cost breakdown:
- `phase = einsum("ijc,nc->ijn", rhat, mid)` — GEMM, inner dim 3.
- `expp = np.exp(1j*phase)` — elementwise complex exp over 5.6M values. **The
  bottleneck, and numpy runs it single-threaded** (no BLAS/OpenMP).
- `M = einsum("ijn,nc->ijc", expp, weighted)` — real GEMM, BLAS-able if einsum
  routes to it.

Far-field is evaluated **twice per live solve**: Python (full sphere → scalar)
and JS (cuts → plot). PyNEC has a **third** far-field path — `pynec_backend
.pattern()` via NEC `rp_card`/`get_gain` — but that's a separate on-demand
endpoint (pattern/heatmap view), not part of the live solve.

## Recommendation (dwell + adaptive, NOT a fixed coarse grid)

A fixed grid shrink is rejected — the electrical-size data above shows it aliases
for large/harmonic designs. Instead, decouple the norm from the per-solve
critical path and size the finalize grid to the design:

1. **Skip the norm on superseded solves; finalize on the settled solve.** This
   is Phase 3 specialized to the norm, and the latest-wins mailbox *already*
   provides the dwell signal: a solve is superseded iff `mailbox` is non-empty
   when it finishes. Doomed solves skip `_compute_directivity_norm` (fast churn,
   they're skip-sent anyway); the settled solve (mailbox empty = the user
   stopped = the dwell) computes it at full fidelity and renders correct. Never
   cache a norm-skipped partial result.
2. **JS carries forward the last-good norm during motion.** Pattern *shape* is
   always live (JS computes cuts from currents every frame); only the absolute-dB
   reference lags and snaps correct on settle. Small client change: reuse the
   previous `directivity_norm` when a render lacks a fresh one.
3. **Size the finalize grid to electrical extent** (`n_φ ≈ 3–4 × perimeter/λ`,
   `n_θ ≈ half`): a dipole finalizes at ~12×24 (~20 ms), a 6λ loop at ~18×36, a
   14λ structure at ~45×90+. Correct for every design, cheap for the common
   (small) case. Paid once, on the settled solve.
4. **Optionally move the norm to JS entirely.** It's display glue and JS already
   has the currents + the same |M_perp| kernel; computing it there deletes the
   server hotspot (cost → client idle CPU, no threadpool/OpenMP contention). The
   adaptive-grid + dwell logic applies equally on the JS side.
5. **C++ / OpenMP kernel: only if the norm stays server-side AND adaptive-grid +
   dwell aren't enough.** Target is the single-threaded `np.exp`; a fused OpenMP
   kernel over the direction grid would parallelize it. Try `numexpr` /
   BLAS-routed einsums first. Caveat: an all-cores kernel contends with other
   solves' threadpool + engine OpenMP under multi-user load.
6. **Phase 4 (orjson): optional.** ~13–20× faster dump but only 3.4→0.2 ms
   absolute; real argument is event-loop head-of-line blocking + 3×-cheaper
   cache-hit responses. Low-risk drop-in; adopt if hosted multi-tab concurrency
   is a priority, else defer. `deepcopy` (~1.7 ms/hit) is second-order.

Note: `orjson` was pip-installed into `.venv` for this profiling run only; it is
not in the app's runtime requirements.
