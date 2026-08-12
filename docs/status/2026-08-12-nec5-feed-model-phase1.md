# 2026-08-12 — NEC-5 feed-model control study (#872 phase 1)

## Goal

De-confound the feed model before any convergence or census comparison
(#872 phase 1): NEC-5 places sources at segment ENDS (knots) while the
NEC-2 lineage and momwire feed segment CENTERS. Quantify the systematic,
decide the correction recipe, and pin the dialect facts as tests.

Instrument: `scripts/bench_nec5_feed_model.py` (sections A/B/C below) on a
straight L = 5.2 m wire, free space, 27 MHz, fed at L/4 — an asymmetric
point where dZ/ds ≠ 0 so position errors are visible. Artifact:
`scratch/nec5-feed-model-phase1.json`. Dialect pins:
`tests/test_nec5_engine.py::test_live_ex_sources_live_at_knots`.

## A. The dialect trap, measured (NS = 8 wire)

| card | Z | meaning |
|---|---|---|
| `EX 0 1 2 2` | 103.350 −126.380j | end 2 of seg 2 = knot 0.250L |
| `EX 0 1 3 1` | 103.350 −126.380j | **bit-identical** — same knot, other spelling |
| `EX 0 1 -3 0` | 103.350 −126.380j | **bit-identical** — negative-I3 spelling |
| `EX 0 1 3 0` | 69.130 −77.870j | vanilla NEC-2 card, reinterpreted |
| `EX 0 1 3 2` | 69.130 −77.870j | **bit-identical to the row above** = end 2 of seg 3 |
| nec2c `EX 0 1 3 0` | 89.279 −64.056j | center of seg 3 (0.3125L) |

NEC-5 is backward compatible with NEC-2 decks **in syntax only**: a
vanilla `EX 0 tag seg 0` runs unwarned with the source moved half a
segment (segment center → end 2). The manual says so quietly (EX card,
p. 47: sources exist at "a segment end or patch edge" — there is no
center option); the identity triple proves there is no hidden center DOF.
On this coarse mesh the shift is worth ~34 Ω in R.

**Census-pipeline immunity (verified 2026-08-12, follow-up to this
study):** the trap bites RAW decks fed to the binary, not the translated
census lane. `wire_tuples` isolates an off-center fed segment on its own
1-segment wire, and `NEC5Engine`'s even-parity coercion makes that
segment's center a knot — so the emitted `EX` lands at exactly the NEC-2
delta-gap position (off-center case: isolated wire, 1→2 segments;
middle-of-odd-wire case: whole wire, N→N+1). Pinned by the
`test_corpus_*_feed_lands_on_exact_gap_position` tests. Census
comparisons therefore carry no feed-POSITION offset; their residual
NEC-5 systematic is the knot-source feed-MODEL march of section B alone
— which also means the corpus splits (e.g. the 2m yagi family) are
feed-model/formulation, not position. The cost of exactness is a local
mesh perturbation only: the fed segment becomes two half-length segments
(a 2:1 neighbor-length ratio at the source).

## B. Ladder decomposition at feed = L/4

Aligned = NS 4k, fed knot pinned exactly at L/4 every rung. Walking =
NS 4k+2, deck-natural knot drifting toward L/4 (the fixed-parity-deck
situation).

| pitch | NEC-5 aligned | NEC-5 walking | walking−aligned |
|---|---|---|---|
| L/8 | 103.350 −126.380j | 138.930 −161.060j | 49.7 Ω |
| L/16 | 109.560 −101.150j | 127.140 −118.450j | 24.7 Ω |
| L/32 | 111.640 −92.196j | 120.340 −100.640j | 12.1 Ω |
| L/64 | 112.410 −88.385j | 116.740 −92.524j | 6.0 Ω |
| L/128 | 112.750 −86.464j | 114.900 −88.506j | 3.0 Ω |

Two separately measurable O(Δ) terms, both with the halving-step
signature that was previously read as slow solver convergence:

1. **Feed-position walk** (walking − aligned): halves per rung, vanishes
   by construction when the knot is pinned. This is the mechanism behind
   the O(1/N) drift observed in the hentenna/contact ladders — a moving
   feed masquerading as formulation convergence.
2. **Knot-source model march** (the aligned ladder's own drift):
   Richardson order 0.99, extrapolating to **Z∞ ≈ 113.09 −84.53j** —
   which agrees with nec2c's own aligned-bridge series (113.6 −84.1j at
   L/128, still descending) to <1 Ω in both parts.

Reference solves on the identical aligned geometry (1-segment bridge, gap
centered at L/4):

| engine | L/128 value | note |
|---|---|---|
| nec2c | 113.620 −84.056j | agrees with NEC-5's Z∞ |
| bs2 | 113.394 −84.126j | agrees (regenerated — see finding below) |
| bs1 | 112.973 −84.733j | converges to the same place from below |
| sing | 113.504 −84.082j | ditto from above |

**Flagged finding — the ~15 Ω X "formulation split", resolved twice.**
The first run of this study read every momwire basis (and pynec) at
X ≈ −99 on the bridge geometry, against −84 from nec2c and NEC-5's
extrapolated limit. Same-day controls established the −84 side was
right (single-wire off-center feeds agree across all engines to <1 Ω;
single-wire feeds at seg 52/53 of NS=208 bracket exactly L/4 with an
agreed mean ≈ **113.4 −84j**, bs2 itself included at 113.346−83.998j),
and the split was blamed on the 1-segment colinear bridge feed idiom —
filed as momwire#300 with a "feed-local basis never enriches" mechanism.

**momwire#300 dissolved under the momwire-level repro (2026-08-12): the
split was a study-instrument radius mismatch, not a solver defect.**
`make_momwire`'s builder declared no wire material, so the momwire and
pynec reference rows solved the adapter-default **0.5 mm** wire while
every hand deck (nec2c, NEC-5) specified the study's **1 mm** — and at
an off-center feed the radius moves X while barely touching R, exactly
the observed signature. Driving `BSplineSolver` directly at a
*consistent* radius, the single-wire and 3-wire-bridge spellings agree
at any radius (1 mm: 113.42−83.89j vs 113.26−83.94j at pitch L/256;
0.5 mm: 112.30−99.13j vs 112.16−99.15j — the second pair reproducing
the "anomalous" −99 exactly). The bridge idiom is exonerated on the
issue's own open questions too: enriching the bridge to 3–9 segments
moves X < 0.1 Ω, and a 16×-pitch 1-segment bridge costs only +0.22 Ω.
The identity is now pinned as a momwire regression test; the momwire
reference rows above and the JSON artifact are regenerated at the
correct radius, restoring three-way agreement (bs2/bs1/sing all → ≈
113.4 −84j, matching nec2c's series and NEC-5's Z∞).

Census immunity holds trivially: the census lane translates each deck's
own GW radius per wire, so no census row ever mixed radii — the mismatch
was confined to this study's first-run reference rows.

## C. Correction-recipe verdict

Candidate: census decks feed segment centers = always midway between two
knots, so correct a fixed-mesh NEC-5 read as the mean of the two
adjacent-knot solves. Measured against nec2c's true center feed:

| NS | raw knot error | knot-mean error |
|---|---|---|
| 10 | 29.0 Ω | 38.6 Ω |
| 18 | 17.2 Ω | 16.3 Ω |
| 34 | 9.6 Ω | 7.8 Ω |
| 130 | 2.9 Ω | 2.6 Ω |

**Rejected as the primary recipe**: knot-averaging repairs the position
term (R lands within ~1 Ω) but the X error is dominated by the intrinsic
knot-source march, which averaging cannot touch — at coarse mesh the mean
is *worse* than the raw read.

**The adopted recipe** (feeds #872 phases 2–5):

1. Never compare walking-knot ladders. Author NEC-5 ladders so the fed
   knot lands on the same physical point every rung (NS divisible by the
   feed fraction; `NEC5Engine`'s even-parity center feed already does
   this for center-fed designs).
2. Census-grade NEC-5 numbers are **Richardson-extrapolated aligned
   pairs** (order ≈ 1, so a (NS, 2NS) pair suffices: Z∞ ≈ 2·Z(2NS) −
   Z(NS)), not single-mesh reads — confirming the issue's phase-2
   hypothesis with the mechanism now understood.
3. Single-mesh knot-averaging is recorded as measured-and-rejected.

## Instrumentation added

- `NEC5Engine.run_deck(deck)` — raw-deck escape hatch (rides the capture
  cache) for knot-placed sources; ladder studies author deck text
  directly.
- `scripts/bench_nec5_feed_model.py` — sections A/B/C, JSON artifact.
- Live dialect pins in `test_nec5_engine.py` (knot identity ×3 and the
  NEC-2-card reinterpretation) plus a stub-binary `run_deck` test.
