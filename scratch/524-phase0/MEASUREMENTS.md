# Phase-0 measurements (session lead)

## (c) momwire `_d12` at ± = − ≡ the below/below kernel — CONFIRMED

`d12_pm_minus_check.py`, 2026-08-22. The argument-swapped call
`_d12(lam, k_air, k_ground)` reproduces an independently coded
D₁/D₂(± = −) pair with **0.0 relative difference** (the expressions coincide
term for term — the d2 denominator k₋²γ₊ + k₊²γ₋ is symmetric under the swap,
the d1/d2 subtracted terms swap correctly) over: soils A/B/C × {7, 21} MHz ×
(real λ axis to 8·max k + a first-quadrant detour). Additionally momwire's
vertical-cut `_gamma` realization agrees with the principal square root to
**8.9e-14 worst-case** on that domain — the two branch-cut conventions
coincide on the physical sheet everywhere the contour goes.

Consequence (the phase-1 shrink, now measured, not just read): below/below
keeps the (ρ, h = z+z′) collapse and the whole SommerfeldGrid architecture;
the kernel change is an argument swap. What below/below still needs is the
complex-k₋ direct kernel in the fill path, the ± = − R₁→0 limits, in-medium
meshing, and per-segment medium assignment.

## (a) contour behavior at large Im k₁ — CONFIRMED BENIGN, far past the target

`zprime_smoothness.py::run_contour_stress` + the prototype's whole-run health
counters. At the SPEC soils: zero non-convergent tails, zero acceleration
needed, worst self-convergence 4.4e-9 anywhere in the 799-integral gate run;
neither Sommerfeld denominator approaches zero on the contour
(min |γ_m+γ_p|/|k| ≥ 1.05, min |k_m²γ_p+k_p²γ_m|/|k|³ ≥ 0.063). Stress cases
beyond SPEC (self-convergence only, no oracle claims): seawater-class
ε81/σ4 (loss tangent 127, |k_m|/k_p = 101) worst 1.8e-6; wet-clay ε13/σ0.05
2.1e-8; near-lossless ε13/σ1e-4 1.9e-9 — all with zero tail failures.
Verdict: loss pushes everything off the real axis exactly as the open
literature says; the SPEC expectation that soil C (low-loss) is the stressor
was WRONG — high loss (soil B, and beyond) is what squeezes the contour, and
even the seawater extreme stays 6 decades inside tolerance. No pivot needed;
the direct-evaluation machinery is sound across the whole capability range.

## (b) below→above z′-smoothness — MEASURED; architecture decided

`zprime_smoothness.py` + the product-range/spherical-flatten follow-up.
Metric: cubic interpolation in log|z′| from N log-spaced nodes, max rel error
vs direct evaluation at 61 dense points, threshold 1e-3, at four (ρ, z)
observers, V_T and U_T.

- RAW quantities are NOT ladder-friendly: >33 nodes over z′ ∈ [0.02, 8] m at
  every soil (in-medium phase e^{−jk_m|z′|} wiggles through the range).
- Dividing out e^{−jk_m|z′|} (NEC-4's sub-region-2 trick, single factor):
  - product range [0.02, 1] m: N ≤ 13 (A/7 MHz, 0.10 λ_m), ≤ 13 (B/7 MHz,
    0.20 λ_m), ≤ 17 (A/21 MHz, 0.25 λ_m) — everywhere, both scalars.
  - deep range [0.02, 8] m (~2 λ_m): grows to >33 at mid-ρ observers; the
    two-ray (λ₁/λ₂ saddle) structure is not removable by one phase divide.
  - a spherical-phase divide e^{−jk_m√(ρ²+z′²)} is no better in the product
    range and also fails deep — no reason to prefer it.
- Node count scales with the z′-range measured in in-medium wavelengths
  (≈13 nodes per ¼ λ_m at 1e-3, cubic).

DECISION for phase 1: tabulate the below→above family as **(ρ, z) surfaces
over a z′ ladder** (≤ ~17 log-spaced nodes) with e^{−jk_m|z′|} divided out,
covering the buried-radial/screen product regime (|z′| ≲ 0.25 λ_m ≈ 2.7 m at
soil A / 7 MHz — an order of magnitude past the documented 15 cm workflow).
Depths beyond the ladder refuse by name (honest), extendable by adding rungs
at the measured ~13-per-¼λ_m rate. The genuinely 3-D machinery (NEC-4's
sub-regions + least-squares + asymptotics) is NOT needed for the phase-1
product rung — that is the measurement phase 0 existed to make.
