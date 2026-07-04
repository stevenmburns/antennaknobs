# Plan: directivity-norm rework + remaining /ws follow-ups

Status: **superseded (2026-07-04).** Moves 1–3 shipped (superseded-skip +
adaptive grid + GL quadrature, PRs through #230), then the whole approach was
replaced by a change of algorithm on the `gain-norm-input-power` branch: the
live norm is now the O(1) input-power identity `η₀k²/(8π·P_in)` (the displayed
gain algebraically equals the old `(4π/∮|M_perp|²dΩ)·efficiency`, so the
integral cancelled out of the product), and the pattern integral survives only
as the dwell-triggered `/norm_check` power-balance diagnostic, computed in
closed form (spherical-Bessel pair sum — exact, no grid) on the PEC web paths.
The superseded-skip and JS norm carry-forward from move 1 were removed again
along with the hotspot they worked around. Kept below for the profiling
background.

## Background — what the profiling established

- `_compute_directivity_norm` (`web/server.py:156`) is a **~430 ms fixed tax on
  every heavy solve**, solver-independent (momwire/arrayblock and dense PyNEC
  both feed the same 1392-segment far-field integral), 42–62 % of a heavy solve.
- It computes a 45×90 far-field **only to extract one scalar** — the
  radiated-power normalizer `directivity_norm = 4π/∫|M_perp|² dΩ`. The displayed
  pattern is computed separately in JS (`App.tsx:5022+`, az/el cuts) and scaled
  by this scalar. So far-field is evaluated twice per live solve; PyNEC has a
  third path (NEC `rp_card` in the on-demand pattern endpoint) but not per-solve.
- **A fixed coarse grid is NOT universally safe.** Required resolution scales
  with electrical size (Nyquist-for-integral: ~2+ cells per pattern lobe, lobe
  count ∝ perimeter/λ). On an 80m `triangular_skyloop` at harmonics, 12×24 holds
  <0.001 dB at ~5.8λ but is off **0.385 dB at ~13.8λ**; ~28λ needs ~45×90. Gain
  is read to ~0.1 dB, so the grid must track the design's electrical extent.

## Design — decouple the norm from the per-solve critical path

Three independent, composable moves. Do them in order; each stands alone.

### 1. Skip the norm on superseded solves; finalize on the settled solve

This is the plan's "phase 3" specialized to the norm — and the latest-wins
mailbox already provides the dwell signal for free. In the `/ws` solver loop
(`web/server.py`, the mailbox handler from PR #226), a solve is superseded iff
`mailbox` is non-empty when it finishes.

- Thread a `superseded: Callable[[], bool]` (closure over `bool(mailbox)`, safe
  to read from the worker thread) into the solve path. Between the core solve
  and `_compute_directivity_norm`, if `superseded()` → skip the norm entirely and
  return (the result is skip-sent anyway, so its norm would be wasted).
- The settled solve (mailbox empty = user stopped = the dwell) computes the norm
  at full/adaptive fidelity and renders correct.
- **Do NOT cache a norm-skipped partial result** — only fully post-processed
  results may enter `_SOLVE_CACHE`. Gate the cache insert on "norm present".

### 2. JS carries forward the last-good norm during motion

Pattern *shape* is always live (JS computes cuts from the currents every frame);
only the absolute-dB reference should lag and snap correct on settle.

- In `App.tsx`, when a rendered result lacks a fresh `directivity_norm` (norm
  skipped upstream), reuse the previous good value instead of the current
  fallback branch (`App.tsx:5186`). Track `lastGoodNorm` in a ref.
- Net UX: during a drag the shape updates live, absolute dBi labels are slightly
  stale (a few tenths at most — the norm is a smooth scalar), and snap exact when
  the user stops. Matches the "we see the shape change, absolute value settles"
  intent.

### 3. Size the finalize grid to electrical extent (+ Gauss–Legendre in θ)

Replace the fixed 45×90 with a grid sized to the design, so the settled value is
correct for every design and cheap for the common (small) case.

- **Adaptive sizing:** compute the structure's max extent in wavelengths
  `D_λ` (bounding-box diagonal / λ_meas) and set the band limit `L ≈ ceil(2π·D_λ)`.
  Then `n_θ ≈ L + a_pad`, `n_φ ≈ 2L + b_pad` (small pads for safety). Clamp to a
  sane floor (e.g. 12×24) and ceiling. A dipole finalizes at ~12×24 (~20 ms), a
  6λ loop at ~18×36, a 14λ structure at ~45×90+.
- **Quadrature:** switch the θ rule from midpoint-rectangle to **Gauss–Legendre
  in u = cos θ** (nodes/weights from `np.polynomial.legendre.leggauss`; the
  weight absorbs the sin θ Jacobian). Keep φ uniform — it is periodic, so the
  rectangle rule is already spectrally accurate. Measured on the 13.8λ skyloop:
  above the resolution floor GL is ~10–70× more accurate per θ-point (e.g. at
  n_θ=20, uniform 0.0069 dB vs GL 0.0001 dB), saving ~30–50 % of θ points at a
  tight tolerance. It does NOT lower the floor (~L θ points) — that is set by the
  band-limit, not the quadrature. Low-risk, isolated change to the two node/weight
  lines.
- **Optional further step — Lebedev quadrature:** a true 2-D spherical rule that
  integrates spherical harmonics to a given degree with ~30–50 % fewer points
  than the product Gauss×uniform rule. Needs tabulated node sets (hardcode a few
  degrees or a small dep). Only if the norm is still a bottleneck after GL +
  adaptive + dwell. Investigate; likely not worth the complexity.
- **Re-check the ground-on path:** it runs a *second* exp/einsum for the PEC
  image + Fresnel (`server.py:216-253`), so it is ~2× the free-space cost and its
  convergence should be re-measured (the reflected term is smooth, so quadrature
  applies equally — expect similar behavior).

### Alternative to 1+3: move the norm to JS entirely

The norm is display glue, the display is JS, and JS already receives the currents
*and* computes the same |M_perp| kernel. Computing the scalar in JS deletes
`_compute_directivity_norm` from the server outright — cost moves to the client's
idle, per-user CPU (no threadpool/OpenMP contention, scales per-user for free).
The adaptive-grid + GL-quadrature + dwell logic all port to the JS side. Bigger
change (reimplement the sphere integral + ground image in TS, keep it consistent
with the existing cut renderer) but architecturally cleanest. Weigh against 1–3
once those are in.

## Lower-priority / optional

- **Phase 4 (orjson serialization):** ~13–20× faster dump but only 3.4→0.2 ms
  absolute; real argument is event-loop head-of-line blocking + 3×-cheaper
  cache-hit responses (5.3→1.8 ms). Low-risk drop-in for the `/ws` send path
  (add `orjson` to the `web` extra). Adopt only if hosted multi-tab concurrency
  is a priority. `deepcopy` (~1.7 ms/hit) is second-order.
- **Generic Phase 3 (skip ALL post-processing when superseded):** mostly
  subsumed — `_attach_derived_em_fields` is free (0.01 ms), so the norm skip
  (move 1) captures ~all of it. No separate work needed.
- **C++/OpenMP kernel for the norm:** only if it stays server-side AND
  adaptive-grid + GL + dwell are not enough. Target is the single-threaded
  `np.exp` over the direction×segment tensor. Try `numexpr` / BLAS-routed
  einsums first. Caveat: an all-cores kernel contends with other solves'
  threadpool + engine OpenMP under multi-user load.
- **rAF-hidden-tab deferral (carried over from PR #226):** the rAF send-throttle
  pauses while a tab is backgrounded, so a background-opened tab defers its
  solves until focused (self-heals on refocus). Left as-is deliberately. Fix only
  if background-tab load proves a common entry path: `document.hidden` →
  `setTimeout` fallback, or a `visibilitychange` flush.

## Verification

- The harness `scripts/profile_ws_postproc_serialization.py` already measures
  per-solver cost + grid convergence (bowtie + skyloop harmonics). Extend it to
  compare uniform vs Gauss–Legendre θ and to exercise the adaptive sizing.
- Add a unit test for the adaptive grid sizer (extent → L → n_θ/n_φ) and an
  accuracy regression: for a spread of designs incl. the 13.8λ skyloop, assert
  the adaptive norm is within ~0.05 dB of a fine reference.
- Re-measure the ground-on path convergence before shipping the adaptive grid.
- End-to-end: scrub a heavy design (bowtiearray2x4) and confirm shape stays live
  while absolute dBi snaps correct on settle; confirm no norm-skipped result
  enters the cache.

## Suggested sequencing

1. Moves 1 + 2 together (server norm-skip on superseded + JS carry-forward) —
   smallest change, reuses the merged mailbox, gives the fast-churn/settle
   behavior immediately. One PR.
2. Move 3 (adaptive grid + Gauss–Legendre θ, ground-on re-check, tests) — the
   correctness-preserving speedup for the settled solve. One PR.
3. Re-profile; decide whether the JS-side move, orjson, or an OpenMP kernel is
   still warranted. Likely none are, after 1–3.
