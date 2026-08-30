# The C1-kink study — Steve's continuity hypothesis, quantified

2026-08-28 session 12. Steve's idea: bs2 enforces C1 at knots; at the
soil-air interface the physics wants a charge (dI/ds) jump; do we have a
way to specify C0-not-C1, and is C1-over-the-kink a slow-convergence
source?

## Ground truth (code)

`_build_basis_polynomials`: each WIRE gets its own clamped B-spline;
junctions couple wires via a value-1 directional basis per member + one
KCL Lagrange row — **C0 only, slopes free on each side**. Within a
polyline, d=2 gives C1 at interior knots. So the SPELLING is the
continuity specification (split+junction = C0; one polyline = C1), and
the crossing serve's mandatory split-at-interface IS the C0 spelling.
AK's geometry walk merges degree-2 continuations into one polyline
(C1); spec changes / ≥3-member junctions / end-ports force C0
boundaries.

## Results (probe1 = E1+E2, probe2 = E3; JSONs beside)

- **E1 free space** (smooth physics): split-C0 vs one-polyline-C1 —
  |ΔZ| 0.002 → 0.0000 with refinement, and the C0 join's slope jump
  self-converges to zero (1.4e-2 → 1.2e-3 → 1.1e-4, ~2nd order). The
  C0 join costs NOTHING where the current is smooth.
- **E2 crossing deck** (the physics): solved dI/ds ratio (above/below)
  at the interface **tracks 1/ε̃**: 1.000 at ε̃=1; |0.096−0.020j| vs
  1/13 at εr13 lossless; |0.043+0.013j| vs 1/|13−12.7j| at soil-A;
  ~0.005 vs 1/127 at σ=0.05. The charge jump is the full medium
  contrast — ~20:1 at soil-A, ~100:1 at σ=0.05.
- **E3 counterfactual C1 tie** (one extra Lagrange row tying end
  slopes): Z biased **~15 Ω** (138.77−102.99 → ~143.6−117.2) and rung
  movement degraded **~400×** (0.002/0.0015 → 1.25/0.60 across
  g1→g2→g3) — first-order crawl, the exact signature of a smooth basis
  fighting a physical kink.

## Verdict

The hypothesis's physics is right and now measured; the formulation was
already careful (the mandatory interface split = C0). The #674 node
class is NOT this (it exists at ε̃=1, no kink — it's bundle/near-field
quadrature, fixed by grading). The 15 Ω / 400× numbers are what any
mesh-through-the-interface smooth-basis treatment would suffer.

## probe3 — the thought-identical spellings on the CATALOG deck (Steve's
## follow-up: "there is a difference on formulations I thought were the
## same — measure it")

Wire inventory (N21 defaults): 4 runs [13] + 4 graded rises [2,2,2]
(C1 interior knots) + gap⌒radiator one polyline [1,2,2,2,2,2,15] (C1 at
the 0.05 knot); junctions = hub 8-member (C0) + node 5-member (C0).

- **X1 hub bend — THE difference**: run+rise separate wires with an
  8-member hub junction (C0 bend, the AK catalog spelling) vs one
  polyline per radial (C1 bend, the momwire fan_rise_deck spelling):
  **0.2139 Ω apart at N21, 0.1129 at N42** — halves per density
  doubling ⇒ first-order DISCRETIZATION difference, same limit (both
  extrapolate to ≈75.88+47.57j within ~0.01). The shipped hub-C0 is
  the closer spelling at equal density (err ≈0.09 vs ≈0.16 at N21);
  N21 stays inside its ±0.10 envelope vs the common limit — verified,
  not assumed. NOTE: momwire's fan adjudication deck and the AK catalog
  use OPPOSITE bend spellings; adjudications comparing them must count
  this 0.1–0.2 Ω class.
- **X2 rise split (C0 panels + bundle shared-point junctions)**:
  0.0027 Ω vs the shipped graded knots — the spurious-junction topology
  alarm was measured SMALL; the graded spelling's argument is
  cleanliness, not accuracy.
- **X3 mono split at 0.05 (=2f)**: over soil REFUSED (above-side
  interior OTHER junction, outside the crossing serve's scope) — C1
  there is mandatory-by-scope. Steve flagged 2f as "not forced C1" —
  actually the WALK'S silent degree-2 merge makes it C1 today (builder
  wrote separate wires; the walk chains them). Free-space measurement
  of C0-vs-C1 at 2f: **4e-4 Ω, flat with density** — immaterial,
  physics-consistent (no medium change at 2f; the feed's structure is
  at f, mid-segment).

## probe3b — Steve's even/odd trick unlocks the soil measurement

The X3 scope wall dissolved by reformulation: bs2 feeds at any
arclength, so the mono can be ONE wire with the mesh honoring f — even
count between 0 and 2f puts the feed ON a knot, odd puts it
mid-segment — no authored break at 2f, no above junction, SERVED over
soil. Measured on the catalog deck (everything else shipped): M1
shipped gap-idiom 75.8581+47.4818j; M2 feed-on-knot 75.8582+47.4948j
(0.013); M3 odd/mid-middle 75.8699+47.4932j (0.016). **Feed-region
spelling class ON SOIL ≈ 0.015 Ω** — inside every envelope; and
feed-exactly-on-a-knot solves fine. Note: the eps-gap idiom is a
card-engine inheritance momwire never needed — the single-wire feed
spelling is served and matches the momwire adjudication decks.

## The continuity map, all measured (the deliverable)

node/interface C0 = mandatory physics (15 Ω / 400× if tied) · hub C0
vs C1-bend = 0.1–0.2 Ω first-order discretization class, same limit,
C0 closer — AND the momwire fan adjudication deck (bend-C1) vs the AK
catalog (hub-C0) sit on OPPOSITE sides · 2f C1 (silent walk merge) =
4e-4 · graded interior C1 vs split = 3e-3.

## Candidate follow-ups (not yet built)

- momwire gate: pin the soil-A interface slope-ratio class through
  production (|ratio| ≪ 1, e.g. < 0.1) — catches accidental future
  slope-tying, a measured 15 Ω defect class, ~1.4 s.
- Crossing-serve docstring: the WHY of the mandatory split, with E2/E3
  numbers.
- Community-post sequel material.
