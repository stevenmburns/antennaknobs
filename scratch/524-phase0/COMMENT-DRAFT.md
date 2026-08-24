# Draft: momwire#524 phase-0 findings comment (post after G7 lands)

## Phase 0 complete: formulation prototype + oracles (the risk burn-down)

Phase 0 as scoped above is done — the standalone prototype, two independent
oracles, the limit gates, and the two measurements the phase existed to make.
Conclusions below; no product code yet (that is phase 1's stacked arc).

### The prototype and its gates

A standalone direct-evaluation script (no grids, no interpolation) computes
the transmitted (buried source → elevated observer) and in-medium
(both below) fields of buried horizontal and vertical electric dipoles, built
entirely from openly released sources (AGARD-LS-131 paper 8, archive.org
DTIC_ADA135087; NEC-4 Theory Manual UCRL-MA-109338 Pt. II, DOE
unlimited-release) with every integrand re-verified against the page images
before coding. That verification caught two transcription errors in our
working notes — a grouping in one R_T→0 limit and the image-term coefficient
reading in the reflected-field composition — both settled by the page images
plus dimensional/limit arguments and then confirmed by measurement. Process
lesson: the primaries are image-only scans; verify against pixels, not
summaries.

Gate battery (all pass, one 57 s run):

| gate | result |
| --- | --- |
| Sommerfeld identity (k_m = k_p) | 1.4e-15 |
| reciprocity V_T(b→a) vs V_T(a→b) | 0.0 (bit-identical, code-path check) |
| ε̃→1 recovers free space | 1.6e-11 |
| σ→∞ shielding, kernel cancellation asserted | monotone; |E| ratio 1.1e-5 over 5 decades of σ |
| empymod cross-check, transmitted | 3.0e-4 well-conditioned, 6.7e-3 worst — inside the oracle's own quadrature spread (median 2.9e-3, worst 1.6e-2) |
| empymod cross-check, in-medium + composition-sign scan | winner 3.2e-4 well-conditioned; runner-up composition fails at 1.5e0 (420× margin) |
| analytic vs finite-difference derivatives | 9.2e-8 |
| ± = + anchor vs momwire's shipped Sommerfeld path | kernels 0.0 over 624 λ points; four surfaces 1.4e-10 |

The composition signs for the in-medium regime are now MEASURED, not read:
total = direct + A·image + remainder, with A = +(k_p²−k_m²)/(k_p²+k_m²) and
the remainder adding; the image is the mirrored-source-and-orientation
convention momwire already uses. The sign scan is a real test — on the
in-medium line the remainder reaches 2.3× the direct field.

### The two findings that shrink phase 1 (now measured)

1. **momwire's `_d12` with swapped arguments IS the below/below kernel pair**
   — 0.0 relative difference over all SPEC soils × frequencies × the full
   integration domain, and momwire's vertical-cut γ realization agrees with
   the principal root to 8.9e-14 everywhere the contour goes. The
   (ρ, h = z+z′) collapse survives whenever source and observer share a
   medium, so the whole SommerfeldGrid architecture reuses for buried
   radials/screens. (This corrects the scoping comment above, which assumed
   the collapse was upper-medium-only.)
2. **Only below→above is 3-parameter, and it does not need 3-D tables for
   the product rung** — see the z′ measurement below.

### Measurement (a): contour behavior at large Im k₁ — benign, verified

At the target soils (loss tangent ≈ 1): zero non-convergent tails, zero
acceleration fallbacks, worst self-convergence 4.4e-9 across the full gate
run; neither Sommerfeld denominator approaches zero on the contour. Stress
cases beyond scope (self-convergence only): seawater-class ε81/σ4 (loss
tangent 127) 1.8e-6 worst; ε13/σ0.05 2.1e-8; near-lossless ε13/σ1e-4
1.9e-9 — all clean. Loss moves everything off the real axis, exactly as the
open literature predicts; the stressed direction is high loss, not the
issue's assumed high-Im-k₁ hazard, and even the extreme is 6 decades inside
tolerance. No formulation pivot needed.

### Measurement (b): z′ smoothness — the grid-architecture decision

Cubic interpolation in log|z′| against dense direct evaluation, 1e-3 target:

- raw transmitted scalars: >33 nodes over z′ ∈ [0.02, 8] m — not
  ladder-friendly (in-medium phase);
- with the single factor e^{−jk_m|z′|} divided out: **≤13–17 nodes cover the
  entire product range** (z′ to 1 m, i.e. ≤0.25 in-medium wavelengths) at
  every soil/frequency tested, scaling ≈13 nodes per quarter in-medium
  wavelength;
- the deep range (~2 λ_m) grows past 33 nodes at mid-ρ observers — the
  two-ray structure there is not removable by one phase divide.

**Decision: phase 1 tabulates below→above as (ρ, z) surfaces over a
≤17-node z′ ladder with e^{−jk_m|z′|} divided out**, covering an order of
magnitude beyond the documented radial/screen depths; deeper sources refuse
by name until rungs are added (measured cost: ~13 nodes per additional
quarter λ_m). The genuinely 3-D machinery is deferred with evidence, not
assumed away.

The interpolation-error story also hands phase 1 its H-field design rule for
free, from the public record (LLNL-TR-490316): evaluate E and H directly
rather than taking a numerical curl of an interpolated E, and interpolate
interfering branch-cut contributions separately.

### Oracle status

The three probe-deck anchors reproduce exactly (the lone-radial geometry is
pinned: a flat detached radial at constant −0.15 m depth). Convergence
ladders are smooth and monotone once rungs preserve fed-segment centering
(odd multipliers; the ×1 anchors sit ~11 Ω from converged — phase-1
tolerances must be set against ladder limits, not ×1 prints). A 23-capture
near-field matrix over buried dipoles (3 dipole types × depth ladder × 3
soils × 2 frequencies) is banked for phase-1 gates. Because the NEC family's
buried-conductor asymptotics have a documented weak spot (publicly:
LLNL-TR-490316 for NEC-4.2; corroborated in our licensed NEC-5 materials,
details in private notes), every capture was taken as an A/B pair under a
bracketing engine configuration. The spread was ZERO across every in-range
capture, and a positive control at 130 m separation (beyond the
Sommerfeld-table range) confirms the bracketing is live — so the oracle's
uncertainty band for our gate decks is negligible, and the weak regime
simply is not where these decks live.
**The engine's own near-field printout as a third check** (its printed
segment currents convolved with the prototype kernels, isolating the Green's
function): the transmitted E_x agrees THREE ways — prototype, empymod,
engine — to 0.5% magnitude / 0.2° phase across the whole 2–30 m line, every
depth, both soils tested, which is the engine's own numerical noise floor.
The transmitted E_z — the one component whose surface has no above-ground
analogue — shows a depth-independent O(1) component-selective divergence in
the engine's printout, while the prototype and empymod agree smoothly with
each other at those exact points; and the engine's printed in-medium fields
at the buried-dipole grids carry neither near-field structure nor medium
attenuation. Both observations match the publicly documented buried-conductor
near-field weakness of the NEC family (LLNL-TR-490316; corroborated in our
licensed materials, details in private notes). The shallow-depth trend is
FLAT — no degradation approaching the interface. Phase-1 rule extracted:
gate the fifth transmitted surface hardest, with empymod and the physics
gates as its oracle — not the engine; the engine's below-ground near fields
are not an oracle at any depth. (Scope note: the horizontal-dipole in-plane
grids exercise two of the five transmitted surfaces; the vertical-dipole
captures and an off-plane grid cover the rest — cheap phase-1 follow-ups,
already banked or one deck away.)

empymod (Apache-2.0, e^{+jωt} verified) is confirmed as a licence-free
second oracle with one caveat worth recording publicly: its default fast
Hankel filters are NOT oracle-grade for near-interface HF work (up to 65%
off); full quadrature (`ht='quad'`) is, with a quantified spread.

### Phase-1 scope, confirmed

Buried radials and screens, bspline-first, exactly as scoped: (1) complex-k
direct kernel in the fill path [the real remaining risk: the in-medium
thin-wire moment kernel is ours to derive]; (2) the argument-swapped
below/below remainder + its R₁→0 limits; (3) below→above z′-ladder surfaces
+ the reciprocity transpose; (4) per-segment medium assignment; (5) seam
narrowing to crossing-only. In-medium meshing rule required (segment length
against λ_m = λ₀/|n|, |n| ≈ 4.3 at the target soil — auto-mesh must learn
the lower medium or buried decks silently under-mesh). Interface crossing
stays phase 2; UM and μ_r ≠ 1 stay out of scope.

Phase-0 artifacts (scripts, captures, gate logs, measurements) are in the
repo-side scratch tree; the arc issue + unit ladder for phase 1 is next.
