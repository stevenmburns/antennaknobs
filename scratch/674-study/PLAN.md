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

## 2026-09-01 — RE-DERIVED AT CONVERGED QUADRATURE (momwire#760). Most of this study measured the wrong axis.

Every measurement above was taken at whatever `n_qp_pair` defaulted to, which
was **4**. momwire#760 then measured that on a crossing node at a lossy
interface the cross-edge quadrature error is **first order** in that knob — a
lost convergence rate, not a slow one. A mesh ladder taken at fixed quadrature
converges to the wrong limit, so the axis this study swept was never the axis
that dominated it.

The probes now take `PROBE_N_QP_PAIR` and key their output by it, so a
re-derivation cannot overwrite the record it corrects. momwire#762 tiled the
`qr` loop, so high orders run on the accelerated path and the whole re-run costs
minutes.

### probe1 — the ε̃ = 1 composition error does not exist

The study's foundational claim was "clean first order under uniform
refinement", orders 1.086 / 1.167 / 1.175.

| rung | h_node | q=8 | q=32 |
|---|---|---|---|
| s1 | 75.0 mm | 0.0544 | **0.0000** |
| s2 | 37.5 mm | 0.0224 | 0.0001 |
| s3 | 25.0 mm | 0.0121 | **0.0000** |
| s4 | 18.8 mm | 0.0073 | **0.0000** |

There is no K>2 composition error at ε̃ = 1. The ladder was measuring
quadrature. momwire#760 guessed this case "may well be clean, since the
near-singular transmitted kernel is exactly what ε̃ = 1 removes" — the
conclusion is right and the reasoning is not: ε̃ = 1 removes the *lossy*
transmitted kernel, but four rises meeting at a point still make the cross-edge
pairs near-singular geometrically, which is why q=4 saw an error here at all.

### probe2 — no arm dominates

| `n_qp_pair` | mono-only | rise-only |
|---|---|---|
| 4 | 0.0171 | **0.2214** ← the ATTRIBUTION above |
| 8 | 0.0007 | 0.0540 |
| 16 | 0.0003 | 0.0082 |
| 32 | 0.0002 | **0.0001** |

The 13× asymmetry the attribution rests on is 0.5× at converged quadrature.
Withdrawn in momwire#774, including from the user-visible `CoarseCrossingNode`
warning that quoted it.

### probe3 — the dominant MESH axis inverts

Soil-A fan, split lane. `|base − n3|` is what node grading buys; `|n2 − n2-far2|`
is what doubling the far mesh buys.

| `n_qp_pair` | base | n3 | node grading | far-mesh ×2 | Richardson p |
|---|---|---|---|---|---|
| 4 | 143.9327−26.2135j | 142.1918−36.4770j | **10.4101** | 0.0215 | 3.361 |
| 8 | 142.1384−36.2122j | 141.3995−40.6478j | 4.4967 | 0.0968 | 4.144 |
| 16 | 141.3093−40.9316j | 141.0606−42.4745j | 1.5628 | 0.1182 | 2.521 |
| 32 | 140.9938−42.7580j | 140.9548−43.0580j | 0.3025 | 0.1227 | 0.193 |
| 64 | 140.9123−43.2310j | 140.9371−43.1568j | **0.0782** | **0.1224** | 0.825 |

- "The 7.48 Ω probe38 move was ALL node class" — no. At q=64 the whole
  base→graded move is **0.078 Ω**.
- "Far-mesh doubling worth 0.022 Ω" — that was itself a q=4 artifact. The real
  figure is **~0.12 Ω, stable at every order**, and it overtakes node grading
  between q=16 and q=32. The far mesh is the dominant mesh axis, not the node.
- The Richardson orders (3.4 at q=4) are not a convergence rate; they wander
  (3.36 → 4.14 → 2.52 → 0.19 → 0.83) because the quantity being extrapolated
  was mostly quadrature error. At q=64 the rungs move ~0.001 Ω — the ladder is
  converged at n1 and there is no order left to fit.
- The q=64 n2 rung, **140.9366−43.1577j**, agrees with `FAN_SOIL_A_N2` as
  re-banked by momwire#758 (140.9358−43.1622j) to 0.005 Ω. The anchor is right;
  it was the study around it that was not.

### What survives

The grading itself. At the shipped default of 8 it is worth ~4.5 Ω on the
soil-A fan, so `fan_rise_deck_graded`, `_FAN_GRADES` and both G-674 gates stay
exactly as they are. What does not survive is the *reason* — this was never a
mesh convergence class — and the claim that the node mesh is where the error
lives.

## 2026-09-01 — probe4: first-order sensitivity, and why adaptive order is unsafe here

Built to settle unit 4's design question before any rule gets written: is the
q=8 cross-edge error carried by a few pairs (build adaptive order) or spread
across the class (build singularity subtraction)?

### The estimator

The fill error is a pure perturbation of Z at fixed dimension, so with `Z c = v`
and `I = v^T c`, `dZ_in = u^T dZ u` exactly to first order, `u = c / I`. No
adjoint solve: the Galerkin fill is complex-symmetric (measured asymmetry
1e-13, the momwire#249 §4.1 gate keeps it so) and `compute_impedance` reads the
port current with the SAME vector that drives the RHS (`bspline.py:5148`, and
`v == port_vectors[0]` is exactly True). A KCL block, where a deck has one,
leaves the augmented matrix symmetric and is annihilated by the perturbation.

Validated on three decks against the real q=8 -> q=32 move:

| deck / case | move | `u^T dZ u` | residual | corrected vs reference |
|---|---|---|---|---|
| fan base | 6.6451 | 6.6834 | 0.0404 (0.61 %) | 140.9743−42.7934j vs 140.9938−42.7580j |
| fan n2 | 2.4513 | 2.4566 | 0.0062 (0.25 %) | 140.9502−43.0636j vs 140.9543−43.0589j |
| brv base | 2.8179 | 2.8144 | 0.0045 (0.16 %) | 75.8497+40.7619j vs 75.8525+40.7584j |

So the correction is worth 165x (fan) to 627x (brv) on the quadrature axis for
one extra fill and NO extra solve. The brv 2.818 Ω is the ~2.8 Ω reactive floor
of #760/#1068; first order removes all but 0.0045 of it.

### Where dZ lives

Entirely on pairs whose supports touch: on the fan, `max|dZ|` is 1.007e+03 there
and 4.9e-06 everywhere else (L1 8826.647 vs 2.4e-05). The knob does not move far
pairs at all. **A segment-pair attribution shows a spurious tail to 5 m** — an
artifact of splitting a touching ENTRY across its own 2 m-long support, not a
real far contribution. Judge locality on entries, not on attributed blocks.

### The finding: partial refinement is catastrophic

Within the touching class the L1 mass overstates the signed move by 1321x (fan),
2756x (fan n2), 5282x (brv). That cancellation is BETWEEN pairs, so refining a
subset breaks it. Ranked by the first-order weight, corrected exactly, and
re-SOLVED (not extrapolated):

| top k pairs | fan base `vs_coarse` | fan n2 | brv |
|---|---|---|---|
| 1 | 11.5x worse | 35.1x | 0.6x |
| 4 | **238.7x worse** | 575.1x | **37554x worse** |
| 32 | 215.4x | 508.8x | 10757x |
| 128 | 0.001x | 16.6x | 221.5x |
| all touching | exact | exact | exact |

Correcting the top 4 pairs on brv returns −24848+17294j. The curve is a cliff,
not a slope: nothing is gained until roughly a third of the class is corrected,
then it snaps to exact.

**Consequence for unit 4.** A rule that refines a geometric or sensitivity-
selected SUBSET of the near-singular class trades a ~6 Ω error for a ~1000 Ω one.
Adaptive order is not merely lower-value than #760 assumed, it is unsafe unless
the refinement unit is the whole touching class — at which point it is just the
existing global knob. The family that survives is singularity subtraction (or a
Duffy-type transformation): a better RULE applied uniformly across the class,
which preserves the cancellation instead of breaking it.

What the sensitivity analysis is for here is therefore the ERROR BAR, not the
selector — a per-deck number for the quadrature axis, which is what "a user
should not have to know" actually needs.

### Cost note

Raising q is nearly free on the fan (1.9 s at q=8, 1.8 s at q=32) but not on brv
(10.6 s -> 37.5 s, 3.5x). The estimator needs the same fine fill on the touching
class that the fine answer does, so it is not cheaper than q=32 — its value is
that it QUANTIFIES the residual rather than merely moving it.

### Limits

Quadrature axis only. It says nothing about the ~0.12 Ω far-mesh error of the
2026-09-01 re-derivation above, and the two must never be summed into one bar.
Single-feed decks only (probe4 refuses otherwise). `RazorSolver` is razor-blade
tested, hence Petrov-Galerkin and NOT symmetric — the free adjoint does not
transfer to it.
