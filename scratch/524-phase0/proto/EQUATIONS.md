# Phase-0 prototype: the verified equation kit

Every formula here was verified against the AGARD-LS-131 paper-8 page images on
2026-08-22 (see ../VERIFICATION.md). This file is the ONLY physics source the
prototype may code from. Open literature (AGARD/NEC lineage); no licensed
material anywhere in this file.

## Conventions (momwire-identical)

e^{+jωt}. Upper medium (air) subscript `p` (= AGARD's +): k_p = ω√(μ₀ε₀), real.
Lower medium (ground) subscript `m` (= AGARD's −): k_m = k_p·√ε̃,
ε̃ = ε_r − jσ/(ωε₀), Im(ε̃) ≤ 0, Im(k_m) ≤ 0. C₁ = −jωμ₀/4π.
γ_i(λ) = (λ² − k_i²)^{1/2} with the PRINCIPAL root (Re γ ≥ 0 on the physical
sheet; realize as γ = √(−j(λ−k))·√(j(λ+k)) like momwire, or principal sqrt —
both agree on the path we integrate). Outgoing/decaying = e^{−γ|z|}.
Geometry: interface z = 0, source at (0,0,z′), observer at cylinder (ρ, φ, z);
horizontal dipole along x̂. Unit current element (I·dl = 1).
Runtime assertion: |e^{−jk_m R}| must DECAY with R (catches a flipped convention).

## Regime 1 — below → above (source z′ < 0, observer z > 0): transmitted field

The ENTIRE field above is the transmitted term (no direct/image parts):

V_T(ρ,z,z′) = 2 ∫₀^∞ e^{−γ_m|z′| − γ_p z} / (k_m²γ_p + k_p²γ_m) · J₀(λρ) λ dλ
U_T(ρ,z,z′) = 2 ∫₀^∞ e^{−γ_m|z′| − γ_p z} / (γ_m + γ_p)           · J₀(λρ) λ dλ

Cylindrical E components at the observer (AGARD 7a–7e, observation medium = +):

E_ρ^V = C₁ ∂²V_T/∂ρ∂z                       (vertical source)
E_z^V = C₁ (∂²/∂z² + k_p²) V_T
E_ρ^H = C₁ cosφ (∂²V_T/∂ρ² + U_T)           (horizontal source along x)
E_φ^H = −C₁ sinφ ((1/ρ)∂V_T/∂ρ + U_T)
E_z^H = −C₁ cosφ ∂²V_T/∂ρ∂z′

Derivatives go UNDER the integral sign analytically:
∂/∂ρ → J₀(λρ) ⇒ −λJ₁(λρ);  ∂²/∂ρ² J₀ = λ²(J₁(λρ)/(λρ) − J₀(λρ)) (use the
Bessel ODE identity; guard small λρ);  ∂/∂z → ×(−γ_p);  ∂/∂z′ → ×(+γ_m)
(z′ < 0 so |z′| = −z′ and ∂|z′|/∂z′ = −1);  (∂²/∂z² + k_p²) → ×(γ_p² + k_p²) = ×λ².
Cross-check every analytic derivative against central finite differences of the
scalar V_T/U_T integrals (gate G5).

## Regime 2 — below / below (both z, z′ < 0): direct + image + remainder

E_total = E_direct(k_m) + A_m · E_image(k_m) + s · E_remainder

- E_direct: free-space dipole field with COMPLEX k_m, source at (0,0,z′):
  standard closed form E = C₁(∇∇/k_m² + I)·(e^{−jk_m R}/R) applied to the
  dipole orientation (use the standard near+far closed form, complex k).
- E_image: same closed form, source reflected to (0,0,−z′), and the image dyad
  Ī_R = x̂x̂ + ŷŷ − ẑẑ applied (AGARD 4b: G^I = −Ī_R·G^D(r, Ī_R r′); for a
  horizontal-x̂ unit element this is the field of an x̂ element at the image
  point times (−1)·(x̂x̂ row) — work the dyad algebra carefully and unit-test it
  against the ε̃→1 limit).
- A_m = (k_p² − k_m²)/(k_p² + k_m²)   [= −C₂ in momwire's above/above language;
  (4a) at ± = −: (k_∓² − k_±²)/(k₊²+k₋²)]
- s = +1 initially ((4a)'s ∓ read at the lower sign). BOTH A_m's sign and s are
  MEASURED quantities in this phase (the scan is overstruck): gate G4/G6 pins
  them; report what survived.
- E_remainder from (5a–5f) at ± = −, i.e. exp(−γ_m|z+z′|) (note |z+z′| = |z|+|z′|):

  U_R = ∫₀^∞ D₁(λ) e^{−γ_m|z+z′|} J₀(λρ) λ dλ
  V_R = ∫₀^∞ D₂(λ) e^{−γ_m|z+z′|} J₀(λρ) λ dλ
  D₁(λ) = 2/(γ_p + γ_m) − 2k_m²/(γ_m(k_p² + k_m²))
  D₂(λ) = 2/(k_m²γ_p + k_p²γ_m) − 2/(γ_m(k_p² + k_m²))

  Components (5a–5d at ± = −, source at z′, evaluated with h = |z+z′|,
  ∂/∂z e^{−γ_m|z+z′|} = −γ_m·sign(z+z′)·e — here z+z′ < 0 so ∂/∂z → ×(+γ_m)):

  R_ρ^V = (C₁/k_m²) ∂²/∂ρ∂z [k_p² V_R]
  R_z^V = (C₁/k_m²) (∂²/∂z² + k_m²)[k_p² V_R]
  R_ρ^H = (C₁/k_m²) cosφ (∂²/∂ρ²[k_m² V_R] + k_m² U_R)
  R_φ^H = −(C₁/k_m²) sinφ ((1/ρ)∂/∂ρ[k_m² V_R] + k_m² U_R)
  R_z^H = −cosφ R_ρ^V

  ((5b)'s multiplier is k_∓² = k_p² at ± = −; (5a) carries k_+² = k_p²
  regardless — both verified at full resolution.)

## Reciprocity identity (gate G1)

V_T is symmetric under exchanging which leg carries which γ:
V_T^{below→above}(ρ, z, z′) = V_T^{above→below}(ρ, z′, z) — with the verified
(7f) both sides are literally the same integral, so implement above→below
independently (γ_p on |z′|, γ_m on |z|, source above) and check equality to
near machine precision. Any deviation is a BUG, not a tolerance.

## Numerical evaluation (open-literature recipe, Mosig & Michalski 2021)

- Head [0, a]: deform into the FIRST quadrant (e^{+jωt} ⇒ upward), half-sine or
  semi-ellipse detour, a chosen past both branch points: a ≈ 1.1·max(k_p, |k_m|).
  Detour height ρ-adaptive (shrink as ρ grows so J₀(λρ) doesn't blow up along
  the detour; J₀ grows like e^{|Im λ|ρ}). No Zenneck-pole extraction (lossy
  half-space: pole effects confined between the cuts).
- Tail [a, ∞): partition at J₀/J₁ zeros, integrate each interval (Gauss or
  adaptive), accelerate the alternating partial sums (Shanks/epsilon algorithm
  or mpmath's; scipy+numpy+mpmath are in the venv). The integrand decays like
  e^{−λ(|z|+|z′|)} (regime 1) or e^{−λ|z+z′|} (regime 2), so acceleration only
  really matters as those lengths → 0 — exactly the regime the smoothness
  measurement probes, so make the tail honest, not lucky.
- Self-convergence: every returned value carries an error estimate (compare two
  tail depths / refinement levels); the gates quote it.

## Gates (named tolerances; report every number)

G1 reciprocity: rel diff < 1e-10.
G2 ε̃→1: regime-1 field ≡ free-space transmitted... precisely: k_m→k_p makes
   V_T, U_T reduce via the Sommerfeld identity to e^{−jk_p R}/R forms; total
   below/below field must equal the free-space dipole field (A_m→0, D₁=D₂≡0);
   rel err < 1e-8 (quadrature-limited, quote actual).
G3 σ→∞ ladder (σ = 0.005, 0.05, 0.5, 5, 50, 500 S/m at 7 MHz): transmitted
   |E| at a fixed above-point must fall monotonically toward 0; assert the
   kernel-level cancellation 2/(γ_m+γ_p) → 0 explicitly at a fixed λ.
G4 empymod cross-check: point-compare regime-1 AND regime-2 fields for buried
   HED and VED (soil A, 7 MHz, depths 0.05/0.15 m) against
   ../empymod/results.json on the shared SPEC grids (../SPEC.md). If that file
   does not exist yet, structure the comparison as a standalone function and
   skip gracefully. Agreement target: rel err < 1e-3 on well-conditioned
   points; this gate also SELECTS the (A_m, s) signs — try the four
   combinations, report which one agrees and by how much, and how badly the
   others fail.
G5 analytic-vs-FD derivatives: rel diff < 1e-6 at a handful of points.
G6 ± = + anchor vs momwire: the same generalized code evaluated at ± = +
   (source AND observer above) must reproduce momwire's shipped reflected
   field. Compare D₁/D₂ at ± = + against momwire's _d12 numerically over a λ
   sweep (import momwire from the installed editable checkout; read
   src/momwire/_sommerfeld.py for the calling convention — READ ONLY, do not
   modify momwire). Rel diff < 1e-12 expected (same expressions).

## Deliverables

proto/buried_proto.py — the evaluator (V_T/U_T/U_R/V_R + field assembly, both
regimes, both dipole types) + gates runnable as `python buried_proto.py`.
proto/RESULTS.md — gate table with every named number, the resolved (A_m, s)
signs with evidence, quadrature error estimates, and any surprises.
Keep runtime minutes-scale; correctness over speed; ≤8GB.
