# momwire#524 phase 0 — prototype results

Direct-evaluation prototype for the transmitted (below→above) and in-medium
(below/below) fields of buried horizontal and vertical electric dipoles over a
lossy half-space. Scripts and gates only: no grids, no interpolation, no
product code.

- Evaluator + gates: `buried_proto.py` (run `python buried_proto.py`).
- empymod comparison: `gate_g4.py` (consumes `../empymod/results.json`).
- Licensed-engine NE comparison: `gate_g7.py` (consumes `../oracle/`, §6).
- Physics source: `EQUATIONS.md` only. Geometry/soils: `../SPEC.md`.
- Environment: `/home/smburns/antennas/antennaknobs/.venv` (numpy 2.5.0,
  scipy 1.18.0, empymod 2.6.0; **mpmath is NOT installed** in this venv — the
  acceleration is a hand-rolled Wynn epsilon instead).

Whole-suite runtime **182.3 s** (G7's convolution is most of it), single
process, single core, well under 1 GB.
The verbatim run is archived as `run.log` (`python buried_proto.py`, 2026-08-22).

---

## 1. Gate table

| gate | what it measures | tolerance | measured | verdict |
| --- | --- | --- | --- | --- |
| G0 (sanity) | Sommerfeld identity: at k_m = k_p, `V_T·k_p²` and `U_T` must both equal `e^{−jk_pR}/R` | 1e-9 | **1.370e-15** | PASS |
| G1 | reciprocity `V_T^{b→a}(ρ,z,z′) = V_T^{a→b}(ρ,z′,z)`, 18 (soil, freq, point) combos | 1e-10 | **0.000e+00** | PASS |
| G2 | ε̃→1 collapses regime 1 **and** regime 2 to the free-space dipole | 1e-8 | **1.580e-11** | PASS |
| G3 | σ ladder 0.005 → 500 S/m: transmitted \|E\| monotone ↓ ; kernel `2/(γ_m+γ_p)` → 0 | monotone | **monotone, ratio 1.089e-05**; kernel monotone | PASS |
| G4a | empymod time convention + axis/orientation mapping vs our complex-k closed form (homogeneous whole space) | 1e-6 | **1.460e-09**, no conjugation | PASS |
| G4b | empymod vs regime-1 transmitted field, all 17 SPEC cells (34 grids, 340 points) | 1e-3 | **3.005e-04** on well-conditioned grids (**6.664e-03** worst over all grids, every one of which has a *larger* oracle spread) | PASS |
| G4c | empymod vs regime-2 in-medium field + the (A_m, s) selection, 17 cells × 10 M-line points | 1e-3 | **3.160e-04** well-conditioned (**3.663e-03** over all); runner-up combo **1.537e+00** | PASS |
| G5 | analytic under-integral derivatives vs finite differences, both stacks, soils A and C | 1e-6 | **9.167e-08** | PASS |
| G6 | ±=+ anchor vs momwire: `D₁/D₂` over a λ sweep, and the four NEC interpolation surfaces | 1e-12 / 1e-7 | **0.000e+00** (D₁/D₂, 624 λ values) and **1.377e-10** (surfaces) | PASS |
| G7 | licensed-engine NE fields vs our kernels convolved over the engine's own printed currents (§6) | characterization, no threshold | transmitted **E_x ≤ 4.5e-04**; transmitted **E_z ≤ 1.14**; in-medium **≤ 5.6**; depth trend **flat** | see §6 |

All nine thresholded gates PASS. G7 is a characterization, not a pass/fail
test — its verdict is in §6. Every number is in the run log emitted by
`python buried_proto.py`, archived as `run.log`.

### G3 ladder (soil eps_r = 13, 7 MHz, HED at z′ = −0.05, observer (10, 0, +1))

| σ (S/m) | 0.005 | 0.05 | 0.5 | 5 | 50 | 500 |
| --- | --- | --- | --- | --- | --- | --- |
| \|E\|max | 2.3898e-01 | 8.9790e-02 | 2.4667e-02 | 5.1793e-03 | 4.5839e-04 | 2.6034e-06 |
| `2/(γ_m+γ_p)` at λ=0.5 | 2.178e+00 | 9.865e-01 | 3.568e-01 | 1.179e-01 | 3.780e-02 | 1.201e-02 |

Both columns fall monotonically; the kernel-level cancellation is explicit —
as |k_m| → ∞ the transmitted denominators are dominated by γ_m ~ |k_m| and the
whole transmitted field is extinguished, as it must be for a perfect
conductor.

---

## 2. The resolved signs — G4's load-bearing measurement

`EQUATIONS.md` marks three things as MEASURED, not transcribed: the sign of
the image coefficient `A_m`, the sign `s` on the remainder, and (implicitly)
how AGARD (4b)'s image dyad contracts. All eight combinations were scored
against the empymod oracle over every regime-2 point in the SPEC matrix
(17 cells × 10 M-line points = 170 points, HED and VED, soils A/B/C,
7 and 21 MHz, depths 0.02–0.15 m).

| image dyad | sign(A_m) | s | worst rel err (all points) | worst rel err (well-conditioned grids) |
| --- | --- | --- | --- | --- |
| **mirror** | **+1** | **+1** | **3.663e-03** | **3.160e-04** |
| mirror | −1 | +1 | 1.537e+00 | 1.375e+00 |
| literal | −1 | +1 | 1.537e+00 | 1.375e+00 |
| literal | +1 | +1 | 1.763e+00 | 1.636e+00 |
| mirror | +1 | −1 | 1.999e+00 | 1.666e+00 |
| literal | +1 | −1 | 1.999e+00 | 1.952e+00 |
| mirror | −1 | −1 | 2.000e+00 | 1.816e+00 |
| literal | −1 | −1 | 2.000e+00 | 1.816e+00 |

The verdict is not marginal: the winner is **420× better** than the
runner-up, and every loser is an O(1) failure (rel err 1.5–2.0, i.e. the
composed field is wrong by more than its own magnitude). The scan is a real
test, not a formality — on the M-line the remainder is *not* a small
correction: |E_remainder|/|E_direct| runs from 0.10 at ρ = 1 m to **2.3 at
ρ = 10 m**, so a sign error anywhere in the composition is immediately fatal.

### Resolved

```
A_m = + (k_p² − k_m²) / (k_p² + k_m²)      [ = −C₂ in momwire's ±=+ language ]
s   = +1
E_image(r) = − E^D_freespace( r − r'_img ; Ī_R · p̂ ),   r'_img = (0,0,−z′)
```

i.e. **both signs stand exactly as EQUATIONS.md writes them** — the corrected
(4a) difference reading `k_∓² − k_±²` at ± = − and the `s = +1` initial guess
are the ones that survive. Nothing in the kit had to be flipped.

### Deviation: how AGARD (4b) contracts

`EQUATIONS.md` §Regime 2 renders the image term as
`G^I = −Ī_R·G^D(r, Ī_R r′)` and then hedges ("work the dyad algebra
carefully"). Read **literally** as a left contraction — flip the z-component
of the field of an un-mirrored element sitting at the image point — that
reading is **wrong**. The prototype implements both and measures them
(`image_field(..., convention="mirror"|"literal")`):

- `literal` fails at ≥ 1.5 rel err under *every* (A_m, s) combination.
- `mirror` — mirror the source's **position and orientation** and carry one
  global minus — is what agrees, and it is the reading pinned by two
  independent constraints beyond empymod:

  1. **PEC limit — measured, no oracle involved** (`_pec_limit_probe`, printed
     in the DIAG section). At ± = + (source and observer both above), drive
     σ → ∞: C₂ → 1 and D₁ = D₂ → 0, so the entire reflected field must become
     the classical image. Observer (4, 0, 2), source z′ = +1, 7 MHz,
     ε_r = 13:

     | σ (S/m) | \|k_m\|/k_p | \|rem\|/\|img\| | source | rel err, `mirror` | rel err, `literal` |
     | --- | --- | --- | --- | --- | --- |
     | 0.005 | 4.27 | 1.59e-01 | VED | 4.910e-01 | 1.842e+00 |
     | | | 1.45e-01 | HED | 1.799e-01 | 1.842e+00 |
     | 5 | 113 | 8.00e-03 | VED | 2.830e-02 | 1.995e+00 |
     | | | 8.00e-03 | HED | 8.079e-03 | 1.995e+00 |
     | 5e3 | 3.58e3 | 2.56e-04 | VED | 9.091e-04 | 2.000e+00 |
     | | | 2.56e-04 | HED | 2.563e-04 | 2.000e+00 |
     | 5e6 | 1.13e5 | 8.11e-06 | VED | 2.876e-05 | 2.000e+00 |
     | | | 8.11e-06 | HED | 8.105e-06 | 2.000e+00 |
     | 5e9 | 3.58e6 | 2.56e-07 | VED | **9.095e-07** | **2.000e+00** |
     | | | 2.56e-07 | HED | **2.563e-07** | **2.000e+00** |

     `mirror` converges to the classical image, and its residual is exactly
     the not-quite-vanished remainder term (column 3) — identically so for the
     HED (2.563e-07 vs 2.563e-07 at σ = 5e9), 3.5× it for the VED. `literal`
     converges to **exactly 2.000** — i.e. to *minus* the correct image — for
     both orientations. There is no tolerance under which `literal` is right.

  2. **momwire ships `mirror`.** `_ground_refl.py`'s header states momwire's
     image convention verbatim: "image block assembled with mirrored tangents
     M·t = (tx, ty, −tz) and subtracted with one global minus sign", scaled by
     `image_coefficient = (ε̃−1)/(ε̃+1) = C₂`. That is `mirror` exactly.

Recommendation for phase 1: restate the (4b) line in the equation kit as
`E^I = −E^D(r − Ī_R r′ ; Ī_R p̂)` so the ambiguity cannot be re-litigated.
The dyadic identity `Ī_R·G_fs(d) = G_fs(Ī_R d)·Ī_R` is why the paper's
notation is readable both ways.

---

## 3. Quadrature health

### Contour/integrand diagnostics at the SPEC soils

Head contour: first-quadrant half-sine detour λ(t) = t + jH·sin(πt/a) over
[0, a], a = 1.1·max(k_p, |k_m|) (past both branch points), height
H = min(0.35a, 2/ρ) so the J₀ growth e^{|Im λ|ρ} is capped at e² = 7.39
everywhere. Both branch cuts run **downward** from +k_p / +k_m, so the
deformed path crosses no cut and encloses no Zenneck pole — no pole
extraction anywhere, as EQUATIONS.md prescribes.

| soil | f (MHz) | ε̃ | k_p | k_m | \|k_m\|/k_p | a | detour clearance past k_p at ρ=30 | min \|γ_m+γ_p\| / \|k\| | min \|k_m²γ_p + k_p²γ_m\| / \|k\|³ |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| A | 7 | 13.000 − 12.839j | 0.14671 | +0.58012 − 0.23818j | 4.275 | 0.6898 | 0.04130 | 1.163e+00 | 2.068e-01 |
| A | 21 | 13.000 − 4.280j | 0.44013 | +1.60771 − 0.25783j | 3.700 | 1.7911 | 0.04650 | 1.058e+00 | 1.760e-01 |
| B | 7 | 20.000 − 77.036j | 0.14671 | +1.03526 − 0.80081j | 8.921 | 1.4397 | 0.02098 | 1.060e+00 | 6.336e-02 |
| B | 21 | 20.000 − 25.679j | 0.44013 | +2.25602 − 1.10245j | 5.705 | 2.7621 | 0.03200 | 1.055e+00 | 8.159e-02 |
| C | 7 | 5.000 − 2.568j | 0.14671 | +0.33808 − 0.08174j | 2.371 | 0.3826 | 0.06225 | 1.356e+00 | 5.237e-01 |
| C | 21 | 5.000 − 0.856j | 0.44013 | +0.98773 − 0.08393j | 2.252 | 1.0904 | 0.06363 | 1.091e+00 | 3.831e-01 |

Reading: **neither Sommerfeld denominator comes near zero on the integration
path at any SPEC soil.** The normalized minima never drop below 1.05 for
(γ_m + γ_p) and 0.063 for (k_m²γ_p + k_p²γ_m). The tightest corner is soil B
at 7 MHz — the *highest-loss* soil, whose large |k_m|/k_p = 8.9 both pushes
the tail out (a = 1.44) and squeezes the detour clearance to 0.021 at ρ = 30.
Soil C — flagged in SPEC.md as "the risky high-eps/low-loss corner — contour
stressor" — is in fact the **best**-conditioned soil here on every measure
(largest denominators, largest detour clearance, smallest a). Independently,
the empymod harness reached the same conclusion from the other side (soil C is
its best-converged soil, soil B its worst). **Finding: for this direct
evaluation the stressor is high loss, not high ε_r / low loss.** That may
change in phase 1 where interpolation error, not quadrature error, dominates.

### Self-convergence

Every returned value carries a self-convergence estimate: the same integral is
evaluated a second time on a coarser machine (Gauss-16 vs Gauss-24, adaptive
rtol 1e-10 vs 1e-12, detour height factor 1.2 vs 2.0) and the max componentwise
relative difference is reported.

Over the whole gate suite:

| | |
| --- | --- |
| scalar-integral evaluations | 3879 |
| tail non-convergent (hit the 12 000-panel cap) | **0** |
| Wynn-epsilon acceleration actually needed | **0** |
| max head sub-intervals | 17 |
| max tail panels | 986 |
| **worst self-convergence estimate anywhere** | **4.430e-09** |
| … at | regime 1, soil A, 7 MHz, ρ = 10, z = 1.0, z′ = −0.05 |

The estimate is deliberately **conservative**: where an exact answer exists
(G0, the Sommerfeld identity) the realized error is 1.4e-15 while the
self-convergence estimate for the same points reads 5e-11 … 3e-9. Treat the
reported number as an upper bound roughly 5–6 decades above the truth, not as
the error. The honest statement is: the prototype's own quadrature error is
**far below** every physical discrepancy measured in this phase, including the
empymod oracle's own uncertainty (see below).

---

## 4. G4 in detail — and why "worst over all grids" is not our error

The shared oracle records its own per-grid numerical uncertainty as
`quad_ppd300_vs_primary` (empymod quad at 300 vs 600 points/decade). Our
disagreement tracks that spread almost proportionally, at roughly 0.25–0.42×,
across all 17 cells:

| cell / grid | our rel err | oracle spread | ratio |
| --- | --- | --- | --- |
| C_7MHz_HED_d0.05 T-line | 3.005e-04 | 9.3e-04 | 0.32 |
| A_7MHz_HED_d0.05 T-line | 7.894e-04 | 2.5e-03 | 0.32 |
| A_7MHz_VED_d0.05 T-line | 1.142e-03 | 3.6e-03 | 0.32 |
| A_21MHz_HED_d0.05 T-line | 4.163e-03 | 9.8e-03 | 0.42 |
| B_7MHz_HED_d0.05 T-vert | 4.136e-03 | 1.5e-02 | 0.28 |
| B_21MHz_HED_d0.05 T-line | 6.664e-03 | 1.6e-02 | 0.42 |

Our own self-convergence anywhere in the whole run is ≤ 4.4e-9 — six orders
below the disagreement. Combined with the fact that the ratio is stable while
the absolute numbers move by a factor of 20, the residual is best read as
**the oracle's quadrature error, not the prototype's**. The only transmitted
grids whose oracle spread is itself below the gate tolerance are C_7MHz
T-line at d = 0.05 / 0.15 (spread 9.3e-4 / 9.2e-4) — and those are exactly
where we agree best, 3.0e-04. Of the 170 regime-2 points, 50 sit on
well-conditioned grids; those are the ones the "well-conditioned" column of
the sign scan is computed over.

Regime 2 is even cleaner: 1e-6 … 3e-4 per point, with the error growing
smoothly with ρ exactly as the remainder's share of the total grows
(|rem|/|dir| 0.10 → 2.3 over ρ = 1 … 10 m).

### FIRST-CUT WARNING worth recording

The first cut of G4 generated its own comparison points by calling
`empymod.dipole` at library **defaults** — i.e. the DLF digital-linear-filter
Hankel transform. That produced apparent disagreements of 1.3e-3 (ρ = 2 m)
rising monotonically to **1.8e-1** (ρ = 30 m) in regime 1, and 8e-4 → 4e-2 in
regime 2 — a textbook "growing phase error" signature that would have been
easy to misdiagnose as a missing lateral-wave term or a wrong wavenumber.
It was none of those: it was the oracle. Switching to the shared harness's
`ht='quad'` (pts_per_dec 600, limit 4000, xdirect) collapsed the same numbers
to 3e-4 … 6.7e-3. The shared `empymod/SUMMARY.md` independently measures the
default DLF at 0.13 median / 0.65 max error on these grids.

**Rule for phase 1: empymod at its defaults is not an oracle in this
wave-regime problem.** Any future comparison must pin `ht='quad'` and record
the quad-vs-quad spread as the oracle's uncertainty.

---

## 5. Findings, surprises, and traps

### On the physics kit

1. **Nothing in `EQUATIONS.md` needed to be overturned.** Both measured signs
   came out as written; (7f)/(7g), (5a)–(5f), and D₁/D₂ all check out end to
   end. The one deviation is the (4b) dyad *contraction*, §2 above — an
   ambiguity the kit already flagged rather than an error.
2. **The kit is internally consistent at ε̃ → 1 analytically, not just
   numerically.** With k_m = k_p the (7f)/(7g) pair reduces to
   `V_T = G/k_p²`, `U_T = G` via the Sommerfeld identity, and substituting
   those into (7a)–(7e) reproduces the free-space dyadic dipole field term for
   term (including `∂/∂z′ = −∂/∂z` making (7e) agree with (7c)). This was
   checked on paper before any code, and G0/G2 confirm it to 1e-15/1e-11.
3. **G1 is a code-path check, not a physics check.** With the verified (7f),
   `V_T^{b→a}(ρ,z,z′)` and `V_T^{a→b}(ρ,z′,z)` are *literally the same
   integral* — the prototype's two independent assembly paths produce
   bit-identical integrands, hence a measured 0.000e+00. That is the expected
   result ("any deviation is a BUG, not a tolerance"), but it should not be
   quoted as evidence that the transmitted formulation is right; G4b is.
4. **The generalized ±-agnostic form is real.** Writing D₁/D₂ and the
   R-components in terms of a *shared* medium s and an *other* medium o
   collapses the ±=+ (momwire, both above) and ±=− (this phase, both below)
   cases into one code path. G6 confirms it: identical `D₁/D₂` at ±=+ to
   0 ulp, and all four NEC interpolation surfaces to 1.4e-10 against momwire's
   completely independent contour machinery. **One implementation can serve
   both regimes** — a phase-1 architecture datum.
5. **The remainder is not a correction term in the buried regime.** At ρ = 10
   m in soil A it is 2.3× the direct field. Any phase-1 interpolation scheme
   must carry the remainder to full relative accuracy; treating it as a small
   additive term with loose tolerance would be a mistake.

> **Highest-risk quantity in the kit** (from G7, §6): (7e),
> `E_z^H = −C₁ ∂²V_T/∂ρ∂z′`, the "genuinely fifth" surface. It is the one
> transmitted component with no above/above analogue, and it is the one the
> licensed engine departs from us on by O(1) while agreeing with us to its own
> noise floor on everything else. Phase 1 should gate it hardest and should
> not use the engine as its oracle for it.

### Numerical traps found (all fixed, all worth remembering)

6. **A Bessel-zero panel lattice must guard against zero-length panels.** With
   `next_zero(z)` computed by `floor((z−off)/lat)+1`, a `z` sitting exactly on
   the lattice can round *below* it, returning `z` itself. Two consecutive
   zero-length panels contribute exactly 0.0, which the "quiet" convergence
   test reads as **converged** — the tail silently truncates at λ ≈ 1.4 while
   the true answer needs λ ≈ 40. Measured symptom: G0 error jumped to 4.3e-02
   at ρ = 30 with `tail_converged = True` and only 12 panels. Fix: a `+1e-9`
   nudge inside the floor.
7. **A purely relative tail-convergence test cannot terminate on a
   float-noise integrand.** At ε̃ = 1 the remainder's D₁/D₂ are analytically
   zero, but the two subtracted static terms are evaluated in different
   groupings and leave ulp-level noise. `|contrib| < rtol·|total|` is then
   noise-vs-noise and never trips, so the tail burns its whole panel budget on
   values that are 1e-19 of the direct field. Measured symptom: **G2 took
   1164 s instead of 0.4 s** — same (correct) answer, 3000× the runtime, and
   it looked like a hang. Fix: short-circuit `k_s == k_o`.
   momwire's `_six_integrals` documents the identical trap — this is a
   *class* of defect in this family of integrals, not a one-off.
8. **One Gauss rule must never leap across many e-foldings of e^{−λh}.** The
   first version panelled the tail on the J₀ zero lattice alone; at ρ = 0.5,
   h = 3.15 the first panel spanned 4.5 in λ (14 e-foldings) and a Gauss-24
   rule on it was wrong by 8e-04. Fix: cap the panel length at 1.5/h as well
   as at the zero spacing. (momwire's `_tail` has the mirror-image version of
   this bug class, its geometric panel ramp.)
9. **Validating an analytic derivative needs a better stencil than the
   obvious one.** With the integrator's own accuracy at ~1e-13, a 3-point
   second difference at step `1e-4·z` is round-off limited at ~1e-5 relative —
   it *looks* like an analytic-derivative bug and is not. G5's first cut
   reported 3.6e-05 for `(∂²/∂z²+k_p²)V` purely from this. Fixes: 5-point
   second derivative, Richardson-extrapolated 4-point mixed derivative
   (the plain one is only O(h²) — worth 1e-5 at these steps), and steps scaled
   to the integrand's true variation length `L = |z| + |z′|` rather than to
   the coordinate value. After that, every analytic derivative agrees to
   ≤ 9.2e-08.
10. **`mpmath` is not in this venv**, despite the brief listing it. The
    acceleration is a hand-rolled Wynn epsilon over the tail's partial sums.
    In practice it was never needed on the SPEC geometries (see the stats
    block above) because every SPEC point has |z| + |z′| ≥ 0.12 m, giving the
    tail a genuine e^{−λh} decay; it is kept as a guard for the h → 0 limit
    that phase 1 will need.

### Not covered by phase 0

- Interface crossing (z and z′ on opposite sides *of a wire*), AGARD (15)(16).
- The R_T → 0 limits (12a)–(12e) and the desingularized Ṽ_T of (10) — not
  needed for direct evaluation, load-bearing for phase-1 interpolation seeding.
  Note `VERIFICATION.md` already corrects (12c) to
  `sinθ(1+cos²θ) − 1`; the prototype does not exercise it.
- Small-ρ / on-axis behaviour below the SPEC floor (all SPEC offsets ≥ 1 m,
  the empymod Hankel floor). The `bessel_j0_j1x` series switch handles
  λρ → 0, but no gate probes it.
- Magnetic-source (HMD/VMD) duals.

---

## 6. G7 — the licensed-engine NE comparison

Added after the six named gates, on the coordinator's follow-up. The engine's
own printed **segment currents** are convolved with the prototype's
point-dipole kernels and the result compared against the engine's own printed
**near fields** on the shared SPEC grids. Using the engine's currents removes
the current solution from the comparison entirely: whatever is left is the
Green's function.

Deck: `bhd1` — 1 m horizontal x-directed dipole, 11 segments, radius 1 mm,
fed segment 6 (`EX 4` — a 1 **A** current source; the printed input current
is exactly 1.0 + 0j A and the *voltage* is the derived quantity). Soil A /
7 MHz over the full depth ladder d ∈ {0.02, 0.05, 0.10, 0.15} m, plus the
soil-B pair at d ∈ {0.05, 0.15}. Oracle A/B workaround spread is identically
zero on every one of these captures, so the stock run is the number.

### Current-table parsing — the normalization CAUTION, confirmed

The capture agent's warning is real and this module refuses to guess around
it. The recovered scale is taken from the printed segment **length** against
the deck's own wire length / segment count, then every scaled segment centre
is required to land on the deck geometry:

| capture | recovered scale | 2π/\|k_m\| (ground) | free-space λ | centre residual |
| --- | --- | --- | --- | --- |
| bhd1 soil A / 7 MHz (all depths) | 10.01937 m | 10.01925 m | 42.827 m | 5.0e-07 m |
| bhd1 soil B / 7 MHz (both depths) | 4.80058 m | 4.80058 m | 42.827 m | 4.8e-07 m |

The table is normalized by 2π/\|k_m\| of the **containing medium** exactly as
warned — 10.02 m, not 42.83 m — and the residual is at the printed 6-figure
precision, so segment identity is unambiguous. The printed magnitude/phase
columns reproduce the printed real/imag columns to ≤ 6e-6. Convolution
discretization floor (segment midpoint rule vs 3-point Gauss along each
segment, holding the printed current constant): **5.3e-04 on the T-line**
(worst at x = 2 m, the closest point) and **1.4e-02 on the M-line** (worst at
x = 1 m, where the nearest segment centre is only 0.45 m away). Those are
floors on the comparison, not on the kernel — and they bracket the results
below usefully: the T-line E_x agreement (2e-4) sits *at or below* its own
floor, so the true kernel agreement is at least that good, while the M-line
disagreement (5.5) is 380x its floor.

### Results, per component

The T-line/T-vert grids lie at y = 0 with the source along x̂, so
φ = 0 and the two live components map one-to-one onto the equation kit:

- **E_x = E_ρ^H = C₁(∂²V_T/∂ρ² + U_T)** — (7c)
- **E_z = E_z^H = −C₁ ∂²V_T/∂ρ∂z′** — (7e)

That split turns out to be the whole story.

| depth (m) | T-line E_x | T-line E_z | T-vert E_x | M-line (all) | engine's own \|E_y\| floor |
| --- | --- | --- | --- | --- | --- |
| 0.02 | **2.640e-04** | 6.485e-01 | 5.276e-04 | 5.577e+00 | 6.347e-04 |
| 0.05 | **2.204e-04** | 6.340e-01 | 4.670e-04 | 5.491e+00 | 6.235e-04 |
| 0.10 | **1.870e-04** | 6.113e-01 | 6.030e-04 | 5.381e+00 | 6.060e-04 |
| 0.15 | **1.936e-04** | 5.899e-01 | 5.694e-04 | 5.293e+00 | 5.897e-04 |
| soil B, 0.05 | 4.476e-04 | 1.137e+00 | 1.092e-03 | 2.664e+00 | — |
| soil B, 0.15 | 4.024e-04 | 1.005e+00 | 1.090e-03 | 2.520e+00 | — |

(relative errors, per-component scale, over the whole grid; M-line is
grid-scale-normalized over all components.)

**The transmitted E_x agrees to 2e-4 over the entire 2–30 m line, at every
depth, in both soils.** That is *below the engine's own internal symmetry
floor*: the engine prints a non-zero E_y on a grid where E_y is identically
zero by symmetry, at 5.9e-04 … 6.3e-04 of grid scale. So on (7c) the
prototype and the licensed engine are in agreement to the engine's own noise.
This is an independent, third-oracle confirmation of the transmitted kernel.

E_z and the in-medium grid are a different matter.

### The shallow-depth trend: FLAT, not growing

The anticipated failure mode — agreement degrading as the source approaches
the interface — **does not appear**:

```
trend 0.15 -> 0.02 m:   T-line Ex x1.36    T-line Ez x1.10    M-line x1.05
```

Every metric is within ~1.1–1.4× across the entire ladder, and the E_z and
M-line disagreements are already O(1) at the deepest rung. The residual is
**depth-independent**. It is not an interface-proximity effect; it is a fixed,
component-selective structural difference present just as strongly at 0.15 m
as at 0.02 m. (The E_x column's ×1.36 is a rise from 1.9e-4 to 2.6e-4 —
motion entirely inside the engine's own noise floor, not a trend.)

### What the disagreement actually looks like

Point-by-point at soil A, d = 0.05 (engine ÷ empymod × the deck's net moment
Σ I·Δl = 0.05747 A·m; our convolution sits on top of empymod to ~1%):

| x (m) | \|E_x\| ratio | ∠ diff | \|E_z\| ratio | ∠ diff |
| --- | --- | --- | --- | --- |
| 2 | 0.995 | −0.01° | 1.588 | −36° |
| 6 | 0.994 | −0.19° | 0.998 | +6° |
| 10 | 1.004 | +0.16° | 0.976 | +43° |
| 14 | 1.000 | +0.02° | 0.650 | +76° |
| 18 | 0.999 | +0.03° | **0.206** | +143° |
| 22 | 0.999 | −0.01° | 0.456 | +287° |
| 26 | 0.999 | −0.03° | 0.867 | +331° |
| 30 | 1.000 | −0.06° | 0.999 | +368° |

E_x: **three-way agreement to 0.5% in magnitude and 0.2° in phase across the
whole line.** E_z: the engine's magnitude is right at x = 4–10 m and again at
x = 28–30 m, but collapses to 0.21 of ours around x = 18–20 m, while the phase
difference climbs monotonically through a full turn (+6° at x = 6 to +368° at
x = 30, ≈ 15°/m). Ours and empymod's E_z are smooth and monotone over the same
line (0.128 → 0.0032 V/m, no dip anywhere); the engine's has a pronounced
minimum at x ≈ 19 m. The residual is therefore neither a scale factor nor a
constant phase offset — but the extracted difference (engine − ours) is not a
clean single term either (its magnitude is non-monotone: 0.98, 0.11, 0.73,
1.17, 0.15 of ours at x = 2, 6, 10, 18, 30), so this note characterizes the
disagreement and deliberately does **not** assert a mechanism for it.

The in-medium M-line is worse and qualitatively different. At soil A,
d = 0.05, same normalization (engine ÷ empymod × net moment; our convolution
sits within ~1% of that reference everywhere on this grid except x = 1 m,
where its own midpoint-rule floor is 1.4e-2):

| x (m) | 1 | 2 | 4 | 6 | 8 | 10 |
| --- | --- | --- | --- | --- | --- | --- |
| \|E_x\| ratio | 0.17 | 0.32 | 0.97 | **4.06** | 10.5 | 3.14 |
| \|E_z\| ratio | **0.010** | 0.047 | 0.216 | 0.489 | 0.668 | 0.760 |

The engine's in-medium field has **no near field and no attenuation**: its
E_z at ρ = 1 m is 100× too small, and at range it decays roughly like 1/ρ
instead of carrying the ground's e^{−ρ/δ} (δ = 4.2 m). Probing it against
each piece of the composition separately — direct(k_m) alone, direct+image,
remainder alone, and free-space-with-k_p — it matches **none** of them
(the closest accidental resemblance, E_z vs the remainder term alone, breaks
down completely on E_x).

### Verdict: the residual is the engine's

Stated carefully: this phase cannot prove the engine wrong in the abstract.
What it establishes is that two independent formulations agree with each
other and disagree with the third, and that the third's numbers carry
features that are hard to reconcile with physics. The evidence:

1. **The current solution is not in question** — the comparison uses the
   engine's own printed currents.
2. **The same code path, the same kernels and the same currents produce E_x
   right to 2e-4 and E_z wrong by 0.6** on the same grid, at every depth. A
   defect on our side that spared (7c) entirely while destroying (7e) is not
   credible; G5 gates the ∂²/∂ρ∂z′ derivative that (7e) alone uses to 1.5e-10
   against finite differences, and G4b gates the assembled E_z against
   empymod to 7.9e-04 at these very points.
3. **empymod is the tie-breaker**, and it sides with the prototype: an
   independent exact layered-media code, run at converged quad, matching our
   E_z to 8e-4 on the T-line and our whole in-medium field to 3e-4 on the
   M-line (G4b/G4c).
4. **The engine's T-line E_z has structure neither independent code has.**
   Its minimum at x ≈ 19 m appears in neither the prototype's nor empymod's
   smooth monotone E_z, and a monotone 15°/m phase divergence over a line
   where E_x's phase agrees to 0.2° cannot come from a shared geometry or
   frequency error.
5. **The vanished in-medium near field is unphysical on its face.** The
   nearest source segment is 0.45 m from the ρ = 1 m observation point and
   carries 0.09 A·m; the 1/R³ near-field term cannot be 1% of its value.

**The specific finding worth carrying to phase 1:** the transmitted component
the engine departs on is exactly **(7e), E_z^H = −C₁ ∂²V_T/∂ρ∂z′** — the
∂/∂z′ derivative, which `VERIFICATION.md` already flags as "genuinely fifth"
among the (11a)–(11e) interpolated surfaces, and the only one of the five with
no above/above analogue (at ± = + it collapses to `R_z^H = −cosφ R_ρ^V`, which
is why momwire ships four surfaces and not five). Of the two components these
grids exercise, the one that *does* have an above/above analogue — (7c),
E_ρ^H, the same combination G6 anchors against momwire — agrees with the
engine to the engine's own noise floor; the genuinely-new one does not.

Phase 1 should treat the fifth surface as the highest-risk quantity in the
formulation, gate it hardest, and should NOT use the engine as its oracle for
it — empymod at converged quad is the reference there.

Scope honesty: an HED deck observed in the φ = 0 plane exercises only (7c) and
(7e). **(7b) E_ρ^V, (7a) E_z^V and (7d) E_φ^H are untested by G7.** The
`bvd1` captures (d ∈ {0.05, 0.10, 0.15}, soil A / 7 MHz) exist in
`../oracle/` and would exercise the two vertical-source components; an
off-plane NE grid would be needed for E_φ^H. Both are cheap follow-ups and
neither was in this gate's scope. Note the capture agent's warning that
`bvd1` reports a small **negative** input resistance at all three depths — the
NE fields and printed currents are still usable (G7 never touches the
drive-point impedance), but that deck deserves its own look.

Secondary: the engine's in-medium (below/below) near fields should not be
used as a phase-1 oracle at all, at any depth.
