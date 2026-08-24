# momwire#272 — what the coaxial rule's declined pairs cost

Measured 2026-08-24. Script: `measure_coaxial_rule.py`. Raw readings:
`readings.json`. Every deck and every nec2c printout: `decks/`.

**Status: the Δ/a question is answered. The O(h) question is NOT, and the
reason is a confound in the estimate itself — see "What could not be
separated". No engine change is proposed either way.**

## What was measured

momwire's B-spline EK extends coaxial equal-radius pairs only. NEC's per-end
gating additionally extends some cross-arm pairs at bends and K≥3 junctions.
`_bspline_kernels.py` estimates the gap at "~1 % of Z at Δ/a = 2, and O(h) in
the refinement limit — #249 §4.3".

The quantity is the **EK shift**, `δ = Z(EK on) − Z(EK off)`, taken inside each
solver, then `gap = |δ_nec − δ_mw| / |Z_nec(EK on)|`. Taking the shift is what
cancels the basis difference; a plain `|Z_mw − Z_nec|` is dominated by it.

A **straight-wire control** runs at every rung. On a straight wire every pair
is coaxial, so momwire declines nothing and the true cost is zero by
construction — whatever `gap` reads there is basis noise in the shift.

The control is load-bearing, not decoration: it reads **1.35 % at Δ/a = 2**.
Reporting a bent deck's raw gap without it would attribute that noise to the
coaxial rule.

*Method check:* at Δ/a = 6.1 the control reads a 43 % mismatch in δ, matching
the 43.2 % that `test_extended_kernel_bspline.py`'s G9 comment independently
records for the same quantity. The harness reproduces the known number.

## Leg 1 — Δ/a ∈ [2, 25], mesh fixed at 11 segments/arm

| Δ/a | straight (control) | bent | bent excess | k3 | k3 excess |
| ---: | ---: | ---: | ---: | ---: | ---: |
| 2 | 1.348 % | 2.092 % | **+0.744** | 1.317 % | −0.031 |
| 3 | 0.446 % | 0.511 % | +0.065 | 0.316 % | −0.130 |
| 4 | 0.456 % | 0.251 % | −0.205 | 0.061 % | −0.395 |
| 6 | 0.411 % | 0.181 % | −0.230 | 0.045 % | −0.366 |
| 10 | 0.377 % | 0.207 % | −0.170 | 0.059 % | −0.318 |
| 15 | 0.298 % | 0.208 % | −0.090 | 0.049 % | −0.249 |
| 25 | 0.176 % | 0.161 % | −0.015 | 0.031 % | −0.145 |

"Excess" is the deck's gap minus the control's at the same rung, in percentage
points — the part that cannot be basis noise.

**Reading.** The declined pairs are distinguishable from noise at exactly one
rung: the bent deck at Δ/a = 2, at **+0.74 pp**. At Δ/a ≥ 4 both decks read
*below* the control, which means their declined-pair contribution is smaller
than the measurement's own noise. The K=3 junction never rises above the
control anywhere in the window.

## Leg 2 — refinement at fixed radius (a = 0.00568 λ)

| n/arm | h | Δ/a | straight | bent excess | k3 excess |
| ---: | ---: | ---: | ---: | ---: | ---: |
| 5 | 0.0500 | 8.80 | 0.703 % | −0.563 | −0.559 |
| 7 | 0.0357 | 6.29 | 0.557 % | −0.384 | −0.516 |
| 11 | 0.0227 | 4.00 | 0.456 % | −0.205 | +0.062 |
| 15 | 0.0167 | 2.93 | 0.326 % | +0.074 | +0.819 |
| 21 | 0.0119 | 2.10 | 0.496 % | +0.470 | +1.333 |

## What could not be separated

**Leg 2 does not test O(h), and no sweep of this shape can.** At fixed radius,
h and Δ/a are the same motion — Δ/a *is* h/a. Refining the mesh walks Δ/a
*down* toward 2, which is where the extended kernel matters most, so the
excess grows as h shrinks. That is not the cost failing to decay under
refinement; it is the two clauses of the estimate being one axis.

Separating them needs a third variable held fixed, and the two legs disagree
enough to show a/λ is that variable: at Δ/a ≈ 2.1 leg 2 reads a bent gap of
0.97 % where leg 1 at Δ/a = 2 reads 2.09 %, the difference being a/λ (0.0057
vs 0.0114). **So the gap depends on a/λ as well as Δ/a, and #249 §4.3's
one-number estimate is under-specified.** A follow-up wanting the O(h) claim
should sweep a/λ at fixed Δ/a.

## Against the outcomes fixed on the issue

The decision fixed two meanings in advance. The measurement lands between
them, and which one fires depends on a question the decision did not settle:

- **The literal metric exceeds 1 %.** Raw gap at Δ/a = 2 is 2.09 % (bent) and
  1.32 % (k3) — the "above 1 % anywhere" branch.
- **The control shows most of that is not the coaxial rule.** The same metric
  reads 1.35 % on a geometry where the declined-pair cost is zero by
  construction. Net of control, the worst rung in the whole window is
  **+0.74 pp**, and every other rung is at or below zero — the "below 1 %
  across the usable window" branch, with the estimate vindicated.

**This is a maintainer call, not a measurement one**, and it is recorded here
undecided rather than resolved in whichever direction reads better. The
question is whether the 1 % bar was meant to apply to the raw shift residual
or to the part attributable to the declined pairs. Nothing in the issue or the
decision says, and the control was not part of the design when the bar was
set.

My recommendation, for the record and as a recommendation only: subtract the
control. A bar that a zero-declined-pairs geometry fails is not measuring what
the bar was written to measure. On that reading the estimate holds, the
coaxial rule is vindicated, and #272 closes with +0.74 pp at Δ/a = 2 as the
number — with the caveat above that a/λ is a second axis nobody has swept.
