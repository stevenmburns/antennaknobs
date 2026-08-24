# momwire#272 — what the coaxial rule's declined pairs cost

Measured 2026-08-24. Script: `measure_coaxial_rule.py`. Raw readings:
`readings.json`. Every deck and every nec2c printout: `decks/`.

**Status: RESOLVED. The declined pairs cost at most 0.27 % of Z anywhere in
the window, and the estimate's O(h) clause is wrong — the cost is set by wire
radius and does not improve under refinement. No engine change is warranted.
See "The answer" below; the nec2c legs that follow are how it was reached and
why they could not settle it alone.**

## The answer

Script: `bracket_in_basis.py`. Raw: `bracket.json`.

The cross-solver measurement below has a noise floor as large as the effect,
so it cannot settle a 1 % question on its own. Removing the floor means never
leaving momwire: force `_ek_axis_groups` to a single label and the EK extends
**every** pair — strictly more than NEC's per-end gating does — then diff
against the shipped coaxial-only gate. Same solver, same mesh, same
quadrature; only the gate moves. That bounds what the declined pairs can cost.

**The straight-wire control reads exactly 0.00000 % at every rung.** Nothing
is declined on a straight wire, so there is nothing for the swap to change.
The metric has no noise floor at all — by construction, and confirmed to
every printed digit.

| Δ/a | a/λ | bent | k3 |
| ---: | ---: | ---: | ---: |
| 2 | 0.01136 | **0.273 %** | 0.207 % |
| 3 | 0.00758 | 0.138 % | 0.108 % |
| 4 | 0.00568 | 0.082 % | 0.069 % |
| 6 | 0.00379 | 0.039 % | 0.040 % |
| 10 | 0.00227 | 0.017 % | 0.026 % |
| 25 | 0.00091 | 0.004 % | 0.007 % |

**Below 1 % everywhere, by a factor of four at the worst rung**, and that is an
upper bound on a strictly-more-generous rule than NEC's. The estimate's
first clause is vindicated with room to spare.

### The O(h) clause is wrong

Refining at **fixed** radius — the only sweep in which h moves and a/λ does
not — the bound is flat, not decaying:

| n/arm | h | Δ/a | bent | k3 |
| ---: | ---: | ---: | ---: | ---: |
| 5 | 0.0500 | 8.80 | 0.0812 % | 0.1209 % |
| 11 | 0.0227 | 4.00 | 0.0823 % | 0.1295 % |
| 21 | 0.0119 | 2.10 | 0.0910 % | 0.1265 % |
| 31 | 0.0081 | 1.42 | 0.0867 % | 0.1525 % |

Six-fold refinement moves it by a few percent of itself. Against that, the
radius sweep moves it 60-fold. **The cost is O(a), not O(h)**: it is set by how
fat the wire is, not by how finely it is meshed, and you cannot refine it
away. Practically this does not matter — it is small at any radius a
thin-wire code is valid for — but `_bspline_kernels.py`'s "O(h) in the
refinement limit" and #249 §4.3 both name the wrong variable and should be
corrected to say so.

### Against the outcomes fixed on the issue

**Below 1 % across the usable window — the estimate holds and the coaxial rule
is vindicated**, which is the branch the decision pre-assigned to that result.
The bar question raised by the nec2c legs below turns out not to need
settling: 0.27 % is under 1 % on any reading.

The caveat that survives is the bound's slack — extending *every* pair also
extends far pairs NEC never touches. That makes the true cost lower than
0.27 %, not higher, so it cannot flip the verdict.

## How it was reached — the nec2c legs

The two legs below are the measurement #272 literally specifies. They are
kept because they are what showed the method needed replacing: their control
reads 1.35 % where the true answer is 0, which is the whole reason the
in-basis bracket exists.

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

## What the nec2c legs could not separate

At fixed radius, h and Δ/a are one motion — Δ/a *is* h/a — so leg 2 walks Δ/a
down toward 2 as it refines, and the excess grows rather than decays. The legs
also disagree at equal Δ/a (0.97 % vs 2.09 %), which is what first showed a/λ
to be a second axis. The in-basis bracket answers both by having no noise to
confound: its leg B holds a/λ fixed while h moves, which is the sweep the O(h)
claim is actually about, and it is flat there.

## A defect this measurement found in its own first draft

`BSplineSolver` does **not** infer junctions. Three arms sharing a coordinate
with no `junctions=` argument are three electrically disconnected wires, and
the first K=3 run reported momwire's EK shift as 15× nec2c's — an artefact of
that, not a kernel gap. `RazorSolver` and `HarringtonSolver` detect the same
geometry automatically; `PulseSolver` has no junction concept at all. That
inconsistency is filed separately.
