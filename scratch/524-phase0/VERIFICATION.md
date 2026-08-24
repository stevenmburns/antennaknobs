# Page-image verification of the phase-0 integrands (2026-08-22)

Performed by the session lead directly against rendered page images (AGARD-LS-131
paper 8, archive.org DTIC_ADA135087, leaves n126–n132 = pages 8-1 … 8-7), per the
source map's fabrication-hazard warning. Images cached in the session scratchpad
(agard/n126.jpg … n140.jpg); crops taken at full 4685-px resolution where a
grouping was ambiguous at overview scale.

## Verified — safe to code from

| item | page | verdict |
| --- | --- | --- |
| e^{jωt} convention, Pocklington EFIE, C₁ = −jωμ₀/4π | 8-1/8-2 | ✔ as note §2.1/§3.10 |
| ε̃ = ε_r − jσ/ωε₀, k = k₀√ε̃ | 8-2 | ✔ |
| (3a)(3b) interface EFIE with ± = shared medium | 8-2 | ✔ |
| (4b) image reflection dyad Ī_R = x̂x̂+ŷŷ−ẑẑ | 8-2 | ✔ |
| (5a)–(5d) R components; R^H_±z = −cosφ R^V_±ρ; (5a) has k₊²V, (5b) has k_∓²V — full-res crops | 8-2/8-3 | ✔ term for term |
| (5e)(5f) U^R/V^R with exp[−γ_±\|z+z′\|] | 8-3 | ✔ — the (ρ, z+z′) collapse for ANY shared medium, incl. below/below at ± = − |
| D₁(λ), D₂(λ) with the medium-selecting ± in the subtracted static terms; γ_± = (λ²−k_±²)^½ | 8-3 | ✔ — momwire's _d12 is exactly ± = + |
| static-term-subtraction rationale sentence | 8-3 | ✔ |
| (6a)(6b) transmitted-field EFIE (source contour C_∓) | 8-3 | ✔ (note's §3.4 (6a) writes E_+^D where the page has E_±^D — trivial, direct field is in the observer's medium) |
| (7a)–(7e) T components incl. (7e) ∂²/∂ρ∂z′ | 8-3/8-4 | ✔ |
| (7f)(7g) V^T/U^T: exp[−γ_∓\|z′\| − γ_±\|z\|] over (k₋²γ₊+k₊²γ₋) and (γ₋+γ₊), factor 2 | 8-4 | ✔ — the buried-source pair, exactly as transcribed |
| reciprocity policy sentence ("only … buried source and elevated observer … through reciprocity") | 8-6 | ✔ verbatim; V₊^T(ρ,z,z′) = V₋^T(ρ,z′,z) follows term-for-term from the verified (7f) |
| (10) desingularized Ṽ₊^T incl. closed-form subtraction −[2/(k₊²+k₋²)]e^{−jk₊R_T}/R_T | 8-6 | ✔ |
| (11a)–(11e) the five interpolated surfaces (I_z^H is genuinely fifth) | 8-6 | ✔ |
| (12a)(12b)(12d)(12e) R_T→0 limits | 8-6 | ✔ |
| θ = tan⁻¹(\|z−z′\|/ρ), S = z′/R_T, C₂ = (k₋²−k₊²)/(k₊²+k₋²), C₃ = k₊²C₂/(k₊²+k₋²) | 8-7 | ✔ |
| NEC-4 interpolation region (ρ,z ≤ 2π/\|k₋\|, \|z′\| ≤ 2π/k₊) + three \|z′\| sub-regions + divided-out phase factors + 3-D linear | 8-7 | ✔ |
| 3-coordinate dependence + "3/2 power" table-cost statement | 8-5 | ✔ |

## Corrected — the note was wrong

- **(4a)**: the image-term coefficient numerator is **k_∓² − k_±²** (a
  difference), not the note's product k₊²k_±². The scan's typewriter
  overstrike is genuinely ambiguous at full magnification (leaf n127 crops
  c127_4a*.png), so the reading is pinned by three independent constraints:
  (i) a k²-dimensioned coefficient on G^I is dimensionally inconsistent;
  (ii) the reflected field must vanish identically at ε̃→1 and R_± already
  does (D₁=D₂=0), so the image coefficient must too; (iii) at ±=+ the
  difference reading gives C₂ = (k₋²−k₊²)/(k₊²+k₋²), momwire's shipped
  above/above composition. The ∓ printed on R_± is likewise overstruck;
  BOTH the coefficient sign and the R sign for ± = − are treated as
  measured quantities — the prototype resolves them against empymod and
  against momwire's ±=+ evaluation path, and the resolved signs are part of
  phase 0's findings (same pattern #545 used for its composition sign).
  BURIED-FORMULATION-SOURCES.local.md §3.2 corrected in place.
- **(12c)**: the C₂S numerator is **sinθ(1+cos²θ) − 1**, not sinθ((1+cos²θ)−1).
  Full-res crop, page 8-6. The two differ by 1/2 at θ→π/2 (the ρ→0 axis limit:
  correct form → 1/2, wrong form → 1). BURIED-FORMULATION-SOURCES.local.md §3.5
  has been corrected in place. Not load-bearing for phase 0 (direct evaluation,
  no R_T→0 interpolation seeding) but load-bearing for phase 1.

## New details worth keeping (page 8-7)

- Interpolate-the-difference (Eqs 11 minus 12) is used for |k₋R_T| < 3;
  for larger R_T the (7) components are interpolated directly because the
  subtracted term "is not attenuated by loss in the medium" and would magnify
  interpolation error.
- An earlier NEC-4 grid used (R′, θ′, x′) coordinates with
  R′ = [ρ² + (z − |k₋/k₊| z′)²]^½; the shipped one is plain (ρ, z, z′) chosen to
  join the least-squares/asymptotic regions.

## Not verified (not needed for phase 0)

Saddle-point/asymptotic eqs (13)–(14) beyond their statement, interface-crossing
(15)(16) [phase 2], Moore & Blair and Baños transcriptions [secondary — the
prototype gates against empymod numerically, not against those transcriptions],
NEC-4 Theory App. F/G closed forms [the reciprocity gate follows from (7f)
directly]. PDF cached at scratchpad nec4/NEC4TheoryMan.pdf if needed.
