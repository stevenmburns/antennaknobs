# momwire#674 — the K>2 node's convergence-rate study

Arc opened 2026-08-27 (session 12). Issue:
https://github.com/stevenmburns/momwire/issues/674 — the fan widening
(#524 phase 2 session 8) measured the complete composition's ε̃=1
residual as a node-mesh CONVERGENCE class past K=2. This study owes:

1. a clean grading study of the K>2 node (uniform self-similar ladder +
   probe18-style per-arm node grading),
2. a Richardson-class trend to a converged fan answer,
3. only then a banked soil-A fan anchor with a mesh envelope in the
   session-7 pattern.

## Inherited numbers (records, not gates)

- ε̃=1 |fan − truth|: N=1 0.0043 Ω, N=2 0.1327, N=4 0.2269 (probe38,
  base mesh [10,2]×4 + [15]); grading rungs 0.2269 → 0.1487 ([14,4]/[22])
  → 0.1060 ([20,6]/[30]) — roughly first order, but the old rungs mix
  refinement ratios (run ×1.4/×1.43 vs rise ×2/×1.5) so no clean fit.
- Hub spelling ε̃=1 residual 0.2194; hub ends cancel TO THE DIGIT
  (probe39) — ends tables exonerated. Sign classes excluded by magnitude
  (−1000j / ~1e5 class).
- soil-A fan 143.9327−26.2135j base, 142.6822−33.5867j node-graded —
  7.48 Ω mesh move, the class amplified ~30× by the lossy transmitted
  kernels. Hub 140.9839−43.6025j (different structure, never gated
  against the fan).
- Correctness gates today: ε̃=1 collapses g524_7/g524_8 at envelope 0.30.

## The deck (from momwire/tests/test_crossing_serve_524.py)

`fan_rise_deck(n_radials=4, depth=0.15)`: 4 radials, each a 2-edge
polyline (5 m run at z=−0.15, then a 0.15 m rise to (0,0,0)), all N
rises geometrically coincident; monopole 10→0 fed at arclength 4.3333
(EX 4,1,7 — NEVER improvise 10−4.333). Junction = K=5 crossing node at
the interface point (0,0,0). Base npe [10,2]×4 + [15].

## Probes

- probe1_eps1_uniform_ladder.py — self-similar rungs s∈{1,2,3,4}:
  npe [10s,2s]×4 + [15s]. Order fit + Richardson check on |fan−truth|.
- (planned) probe2 node-graded ladder; probe3 term identification;
  probe4 soil-A extrapolation + envelope.

## Session log

- 2026-08-27 s12, probe1 DONE — the self-similar ladder s∈{1,2,3,4}
  (h_node 75/37.5/25/18.8 mm): |fan−truth| = 0.2269 / 0.1069 / 0.0666 /
  0.0475 Ω; adjacent-pair orders p = 1.086 / 1.167 / 1.175 — the class
  is FIRST ORDER, cleanly. Richardson on fan and truth Z separately
  (both rung pairs): |fan* − truth*| = 0.0004 Ω — the residual trends
  to ZERO, no floor. (The absolute Z still moves rung-to-rung — the
  free-space junction deck's own convergence — but fan and truth share
  it; the composition error is the diff and it dies.) Fan solves 2.4 →
  17.1 s across the ladder. results/probe1-eps1-uniform-ladder.json.
- 2026-08-27 s12, probe2 DONE — per-arm node grading (probe18 style,
  matched across the interface, far mesh at base): n1/n2/n3 (h_node
  25/6.25/1.56 mm) residual 0.0036/0.0001/0.0000 Ω, order ~2.6 vs
  h_node, every fan solve ~2.5 s. **ATTRIBUTION: rise-only grading
  leaves 0.2214 (unchanged from base 0.2269); mono-only drops to
  0.0171** — the slow term is the ABOVE-ARM'S NODE TENT: the monopole's
  interface-adjacent segment (667 mm at base, ∝1/s on the uniform
  ladder) controls the class at first order. N-scaling with mono graded
  (N=1/2/4 → 0.0006/0.0097/0.0171): the dominant term needs BOTH the
  coarse above tent AND the bundle (N≥2); the secondary term is the
  rise-side coincident-pair content, also node-local, killed by grading
  the rise side too. **#692-caveat check: FORCE_DENSE vs split on the
  graded n2 mm-deck differ by ~2e-4 Ω** — the split holds at the
  measurement floor; banked soil digits should use FORCE_DENSE.
  results/probe2-node-graded-ladder.json.
- 2026-08-27 s12, probe3 DONE + BANKED — soil-A fan on the graded
  rungs, BOTH lanes (dense and split agree ≤5e-4): base 143.9327−26.2135j
  (probe38 record reproduced) → n1 142.2912−35.8545j → **n2
  142.1922−36.4711j** → n3 142.1918−36.4770j. n2→n3 movement 0.0059 Ω,
  observed order 3.4, Richardson Z* 142.1918−36.4771j; far-mesh
  doubling (n2-far2) worth 0.022 Ω. The 7.48 Ω probe38 move was ALL
  node class. results/probe3-soil-ladder.json.
- SHIPPED as momwire PR #693 (branch 674-fan-convergence-study):
  `fan_rise_deck_graded` + `_FAN_GRADES` (n2/n3) + `FAN_SOIL_A_N2` +
  G-674-1 (graded ε̃=1 collapse ≤ 0.005) + G-674-2 (soil-A fan anchor
  ≤ 0.05), module/g524_7 docstrings updated. Measurement bank posted as
  the second #674 comment. Closes #674 on merge.
