# King & Smith, *Antennas in Matter* — Ch. 11, §11.5 and §11.6

**Source:** R. W. P. King and G. S. Smith, *Antennas in Matter: Fundamentals, Theory, and Applications*, Chapter 11 ("Antennas Near a Planar Interface" — running head), §11.5 "The Components of the Electromagnetic Field in Cylindrical Coordinates" and §11.6 "Subsurface Transmission in the Earth".

**Printed pages covered:** 616–635 (PDF pages 636–655 of the local scan; PRINT = PDF − 20).
**Numbered equations occur only on printed pages 616–621.** Printed pages 622–635 contain figures 11.6.1 through 11.6.11 and running prose, with no numbered equations.

**Date of transcription:** 2026-08-22
**Independent transcription copy A** (a second agent transcribed the same pages separately; no coordination).

**Status:** PRIVATE local reference. Copyrighted book. Equations captured for internal cross-checking of a solver formulation only. Not to be committed or quoted publicly. Connecting text below is my own paraphrase, not the book's prose.

---

## Conventions the section itself states

- **Time convention:** §11.5 and §11.6 as printed do **not** restate a time-dependence convention. Every exponential in the transcribed range is printed with `i` as the imaginary unit and with a **positive** sign in the exponent for outgoing/propagating factors: `e^{ik₁R₁}`, `e^{iγ₁z}`, `e^{iγ₁|z−d|}`, `e^{iγ₁(z+d)}`, `e^{i(γ₁d − γ₂z)}`, `e^{i2γ₁d}`. The convention symbol itself (e.g. `e^{−iωt}`) does not appear on these pages. [Not stated in-section — do not infer for the record.]
- **Transform variable:** λ is the radial (Sommerfeld) transform variable and the variable of integration. The text explicitly flags that this λ is *not* the wavelength; the wavelengths in the two media are written λ₁ and λ₂ = λ₀.
- **Vertical transform wavenumbers:** γ₁, γ₂ defined by (5.3).
- **Wavenumbers, stated in §11.6 (p. 619, in running text):**
  k₁² = ω²μ₀ε̃₁,  k₂² = ω²μ₀ε̃₂ = ω²μ₀ε₀ = ω²/c²,  where c = 3 × 10⁸ m/sec.
- **Media / geometry:** two half-spaces separated by a planar interface. Region 1 is z ≥ 0; region 2 is z ≤ 0. The source is a horizontal (interface-parallel) infinitesimal electric dipole of moment IΔl = 1, located **in region 1** at distance d from the boundary. In §11.6 region 1 is the lossy earth material (sea water / lake water / dry soil) in which the dipole is buried at depth d, and region 2 has ε̃₂ = ε₀ per the k₂² relation above. Both media are taken nonmagnetic in §11.6: μ₁ = μ₂ = μ₀.
- **Auxiliary quantities:** M and N are defined earlier, in (4.1) (not in this page range); P and Q are defined here in (5.8).
- **ε̃** denotes the complex (effective) permittivity; the tilde is printed on ε in (5.8), in the E₁ₓ integrand, and in the §11.6 k² relations.

---

## §11.5 — printed page 616

Cylindrical components E_ρ, E_φ, E_z are introduced in cylindrical coordinates ρ, φ, z together with transform variables λ and φ′; performing the φ′ integrations yields Bessel functions. The substitutions are:

**(5.1)** — p. 616

    x = ρ cos φ,   y = ρ sin φ,   ξ = λ cos φ′,   η = λ sin φ′.

The inverse relations follow:

**(5.2)** — p. 616

    ρ = (x² + y²)^{1/2},   φ = tan⁻¹(y/x),   λ = (ξ² + η²)^{1/2},   φ′ = tan⁻¹(η/ξ).

The vertical transform wavenumbers in the two media:

**(5.3)** — p. 616

    γ₁ = (k₁² − ξ² − η²)^{1/2} = (k₁² − λ²)^{1/2},

    γ₂ = (k₂² − ξ² − η²)^{1/2} = (k₂² − λ²)^{1/2}.

A parenthetical remark then notes that λ as a radial transform variable is Sommerfeld's conventional usage and is not to be confused with wavelength (λ₁, λ₂ = λ₀ denote the wavelengths). With (5.1), ξx + ηy = λρ cos(φ − φ′) and dξ dη = λ dφ′ dλ. The cylindrical components follow from E_ρ = E_x cos φ + E_y sin φ, E_φ = − E_x sin φ + E_y cos φ; E_z is unchanged apart from the new variables.

The next display is the transformation to cylindrical form for E₁ρ in the range d ≤ z; the other components in other ranges follow comparably. The display begins on p. 616 **unnumbered** and its continuation on p. 617 carries the number (5.4).

**Unnumbered first step of (5.4)** — p. 616

    E_1x = − (1/4π²) ∫₀^{2π} dφ′ ∫₀^{∞} dλ λ e^{iλρ cos(φ − φ′)}

        × [ ( μ₁γ₁ (k₂² − λ² cos² φ′) + μ₂γ₂ (k₁² − λ² cos² φ′) ) / (ωMN) · e^{iγ₁d}

            + ( (k₁² − λ² cos² φ′) / (iωε̃₁γ₁) ) sin γ₁d ] e^{iγ₁z}

---

## §11.5 — printed page 617

The display continues and is numbered:

**(5.4)** — p. 617

    = − (1/4π) ∫₀^{∞} dλ λ [ ( μ₁γ₁k₂² + μ₂γ₂k₁² ) / (ωMN) · e^{iγ₁d} + ( k₁² / (iωε̃₁γ₁) ) sin γ₁d ] e^{iγ₁z}

        × ∫₀^{2π} dφ′ e^{iλρ cos(φ − φ′)}
        + (1/4π) ∫₀^{∞} dλ λ³ [ ( μ₁γ₁ + μ₂γ₂ ) / (ωMN) · e^{iγ₁d} + ( sin γ₁d ) / (iωε̃₁γ₁) ]

        × e^{iγ₁z} ∫₀^{2π} dφ′ e^{iλρ cos(φ − φ′)} cos² φ′.

A comparable expression for E₁y follows readily. The Bessel integral representation used is:

**(5.5)** — p. 617

    J_n(λρ) = (i^{−n} / 2π) ∫₀^{2π} e^{iλρ cos θ} e^{inθ} dθ

from which the two φ′ integrals evaluate:

**(5.6)** — p. 617

    (1/2π) ∫₀^{2π} e^{iλρ cos(φ − φ′)} dφ′ = J₀(λρ),

**(5.7)** — p. 617

    (1/2π) ∫₀^{2π} e^{iλρ cos(φ − φ′)} cos² φ′ dφ′ = (1/2) [ J₀(λρ) − J₂(λρ) cos 2φ ].

With (5.6), (5.7), standard Bessel differential/functional relations, and the following notation for the two interface (reflection-type) coefficients:

**(5.8)** — p. 617

    P = ( μ₁γ₂ − μ₂γ₁ ) / ( μ₁γ₂ + μ₂γ₁ ),      Q = ( ε̃₁γ₂ − ε̃₂γ₁ ) / ( ε̃₁γ₂ + ε̃₂γ₁ ),

the field components take the forms below. **For region 1, where 0 ≤ z:**

**(5.9)** — p. 617

    E_1ρ = − (ωμ₁ / 4πk₁²) cos φ ( ∫₀^{∞} { k₁² J₀(λρ) − (λ²/2)[ J₀(λρ) − J₂(λρ) ] }

        × γ₁^{−1} e^{iγ₁|z − d|} λ dλ + ∫₀^{∞} { (γ₁Q/2)[ J₀(λρ) − J₂(λρ) ]

        − (k₁²P / 2γ₁)[ J₀(λρ) + J₂(λρ) ] } e^{iγ₁(z + d)} λ dλ ),

**(5.10)** — p. 617

    E_1φ = (ωμ₁ / 4πk₁²) sin φ ( ∫₀^{∞} { k₁² J₀(λρ) − (λ²/2)[ J₀(λρ) + J₂(λρ) ] } γ₁^{−1} e^{iγ₁|z − d|} λ dλ

        + ∫₀^{∞} { (γ₁Q/2)[ J₀(λρ) + J₂(λρ) ] − (k₁²P / 2γ₁)

        × [ J₀(λρ) − J₂(λρ) ] } e^{iγ₁(z + d)} λ dλ ),

---

## §11.5 — printed page 618

**(5.11)** — p. 618

    E_1z = (iωμ₁ / 4πk₁²) cos φ ∫₀^{∞} [ ± e^{iγ₁|z − d|} + Q e^{iγ₁(z + d)} ] J₁(λρ) λ² dλ,

**(5.12)** — p. 618

    B_1ρ = − (μ₁ / 4π) sin φ ( ± ∫₀^{∞} J₀(λρ) e^{iγ₁|z − d|} λ dλ + ∫₀^{∞} { (Q/2)[ J₀(λρ) + J₂(λρ) ]

        − (P/2)[ J₀(λρ) − J₂(λρ) ] } e^{iγ₁(z + d)} λ dλ ),

**(5.13)** — p. 618

    B_1φ = − (μ₁ / 4π) cos φ ( ± ∫₀^{∞} J₀(λρ) e^{iγ₁|z − d|} λ dλ + ∫₀^{∞} { (Q/2)[ J₀(λρ) − J₂(λρ) ]

        − (P/2)[ J₀(λρ) + J₂(λρ) ] } e^{iγ₁(z + d)} λ dλ ),

**(5.14)** — p. 618

    B_1z = (iμ₁ / 4π) sin φ ∫₀^{∞} [ e^{iγ₁|z − d|} − P e^{iγ₁(z + d)} ] γ₁^{−1} J₁(λρ) λ² dλ.

*(Transcriber's note, not an emendation: (5.14) is printed with no ± on the first exponential, unlike (5.11)–(5.13).)*

Sign rule stated immediately after (5.14): where two signs appear, the upper sign applies for the range d < z and the lower sign for 0 ≤ z ≤ d.

**For region 2, where z ≤ 0:**

**(5.15)** — p. 618

    E_2ρ = − (1/4π) cos φ ∫₀^{∞} dλ λ { (ωμ₁μ₂ / M)[ J₀(λρ) + J₂(λρ) ] + (γ₁γ₂ / ωN)[ J₀(λρ)

        − J₂(λρ) ] } e^{i(γ₁d − γ₂z)},

**(5.16)** — p. 618

    E_2φ = (1/4π) sin φ ∫₀^{∞} dλ λ { (ωμ₁μ₂ / M)[ J₀(λρ) − J₂(λρ) ] + (γ₁γ₂ / ωN)[ J₀(λρ)

        + J₂(λρ) ] } e^{i(γ₁d − γ₂z)},

**(5.17)** — p. 618

    E_2z = − (i / 2π) cos φ ∫₀^{∞} dλ λ² (γ₁ / ωN) J₁(λρ) e^{i(γ₁d − γ₂z)},

**(5.18)** — p. 618

    B_2ρ = (μ₂ / 4π) sin φ ∫₀^{∞} dλ λ { (μ₁γ₂ / M)[ J₀(λρ) − J₂(λρ) ] + (ε̃₂γ₁ / N)[ J₀(λρ)

        + J₂(λρ) ] } e^{i(γ₁d − γ₂z)},

**(5.19)** — p. 618

    B_2φ = (μ₂ / 4π) cos φ ∫₀^{∞} dλ λ { (μ₁γ₂ / M)[ J₀(λρ) + J₂(λρ) ] + (ε̃₂γ₁ / N)[ J₀(λρ)

        − J₂(λρ) ] } e^{i(γ₁d − γ₂z)},

---

## §11.5 — printed page 619

**(5.20)** — p. 619

    B_2z = (iμ₂ / 2π) sin φ ∫₀^{∞} dλ λ² (μ₁ / M) J₁(λρ) e^{i(γ₁d − γ₂z)}.

Closing remark of §11.5: M and N are defined in (4.1), P and Q in (5.8); this completes the cylindrical-coordinate specification of the field in both half-spaces for a horizontal electric dipole of moment IΔl = 1 located in region 1 at distance d from the boundary. The λ integrations remain and are described as complicated.

---

## §11.6 "Subsurface Transmission in the Earth" — printed page 619

Setup paraphrase: the subsurface-communication problem applies the general two-half-space formulas for an infinitesimal electric dipole parallel to the interface. The transmitting dipole oscillates at frequency f at depth d in a homogeneous isotropic half-space having the properties of some part of the earth's surface (sea water, lake water, or dry soil). The field is studied over wide ranges of radial distance ρ and frequency f to identify which component attenuates least and in which direction. For that purpose the observation point is placed at the same depth as the transmitter, i.e. z = d — so both source and observer are in region 1 (the earth material).

Specializations stated inline on p. 619 (nonmagnetic media, μ₁ = μ₂ = μ₀):

    in (4.1):  M = μ₀(γ₂ + γ₁)
    in (5.8):  P = (γ₂ − γ₁) / (γ₂ + γ₁)
    k₁² = ω²μ₀ε̃₁,  k₂² = ω²μ₀ε̃₂ = ω²μ₀ε₀ = ω²/c²,   c = 3 × 10⁸ m/sec
    in (4.1):  N = (k₁²γ₂ + k₂²γ₁) / ω²μ₀
    in (5.8):  Q = (k₁²γ₂ − k₂²γ₁) / (k₁²γ₂ + k₂²γ₁)

From (5.9) through (5.11), the components of the electric field in the earth are:

**(6.1)** — p. 619

    E_1ρ = − (ωμ₀ / 4πk₁²) cos φ ( ∫₀^{∞} { k₁² J₀(λρ) − (λ²/2)[ J₀(λρ) − J₂(λρ) ] } γ₁^{−1} λ dλ

        + ∫₀^{∞} { [ γ₁ (k₁²γ₂ − k₂²γ₁) ] / [ 2 (k₁²γ₂ + k₂²γ₁) ] · [ J₀(λρ) − J₂(λρ) ]

        − [ k₁²(γ₂ − γ₁) ] / [ 2γ₁(γ₂ + γ₁) ] · [ J₀(λρ) + J₂(λρ) ] } e^{i2γ₁d} λ dλ ),

---

## §11.6 — printed page 620

**(6.2)** — p. 620

    E_1φ = (ωμ₀ / 4πk₁²) sin φ ( ∫₀^{∞} { k₁² J₀(λρ) − (λ²/2)[ J₀(λρ) + J₂(λρ) ] } γ₁^{−1} λ dλ

        + ∫₀^{∞} { [ γ₁ (k₁²γ₂ − k₂²γ₁) ] / [ 2 (k₁²γ₂ + k₂²γ₁) ] · [ J₀(λρ) + J₂(λρ) ]

        − [ k₁²(γ₂ − γ₁) ] / [ 2γ₁(γ₂ + γ₁) ] · [ J₀(λρ) − J₂(λρ) ] } e^{i2γ₁d} λ dλ ),

**(6.3)** — p. 620

    E_1z = (iωμ₀ / 4πk₁²) cos φ ∫₀^{∞} [ ± 1 + ( (k₁²γ₂ − k₂²γ₁) / (k₁²γ₂ + k₂²γ₁) ) e^{i2γ₁d} ] J₁(λρ) λ² dλ.

These are the components per unit dipole moment, IΔl = 1. In (6.3) the upper sign is for d < z, the lower sign for 0 ≤ z ≤ d.

The text then notes that the same formulas follow from a Hertz-potential formulation attributable to Baños (footnote 3), who first computed the Hertz-potential components and thence the field. For a unit electric moment (IΔl = 1):

**(6.4)** — p. 620

    E_1ρ = (iωμ₀ / 4πk₁²) cos φ ( ∂²F/∂ρ² + k₁² G ),

**(6.5)** — p. 620

    E_1φ = − (iωμ₀ / 4πk₁²) sin φ ( (1/ρ) ∂F/∂ρ + k₁² G ),

**(6.6)** — p. 620

    E_1z = (iωμ₀ / 4πk₁²) cos φ · ∂²H / (∂ρ ∂z),

where

**(6.7)** — p. 620

    F = e^{ik₁R₁}/R₁ − e^{ik₁R₂}/R₂ + k₁² V₁₁,

**(6.8)** — p. 620

    G = e^{ik₁R₁}/R₁ − e^{ik₁R₂}/R₂ + U₁₁,

**(6.9)** — p. 620

    H = e^{ik₁R₁}/R₁ + e^{ik₁R₂}/R₂ − k₂² V₁₁,

and R₁ = [ρ² + (z − d)²]^{1/2}, R₂ = [ρ² + (z + d)²]^{1/2}. The functions U₁₁ and V₁₁ are the integrals:

**(6.10)** — p. 620

    U₁₁ = 2i ∫₀^{∞} (γ₂ + γ₁)^{−1} e^{iγ₁(z + d)} J₀(λρ) λ dλ,

---

## §11.6 — printed page 621

**(6.11)** — p. 621

    V₁₁ = 2i ∫₀^{∞} (k₁²γ₂ + k₂²γ₁)^{−1} e^{iγ₁(z + d)} J₀(λρ) λ dλ.

The Bessel derivative identity used in reducing (6.4)–(6.6):

**(6.12)** — p. 621

    (∂²/∂ρ²) J₀(λρ) = − λ (∂/∂ρ) J₁(λρ) = − (λ²/2) [ J₀(λρ) − J₂(λρ) ].

Carrying out the indicated differentiation and rearranging, (6.4)–(6.6) reproduce (6.1)–(6.3) exactly. The value of the (6.4)–(6.6) form is that the field splits into three parts: the direct dipole contribution (e^{ik₁R₁}/R₁), the contribution of a fictitious ideal image in a perfectly conducting region 2 (−e^{ik₁R₂}/R₂), and corrections accounting for region 2 not actually being a perfect conductor — the latter carried by the complex integrals U₁₁ and V₁₁ with their constant factors.

---

## §11.6 — printed pages 621–635 (no numbered equations)

Remaining §11.6 material is descriptive/numerical and contains no further numbered equations. Summary of what is there, for orientation only:

- **p. 621:** closed-form analytical integration over λ has not been achieved; approximate procedures including saddle-point integration have limited ranges of applicability. Parameter ranges of interest: ρ from 1 m to 1000 km; f from 1 to 10⁹ Hz; real effective relative permittivities ε_er from 2 to 81; real effective conductivities σ_e from 10⁻⁸ to 10 Si/m. Numerical evaluation faces two problems: (a) a sharp peak at the branch points (integrand examples in fig. 11.6.1, f = 0.1 MHz, ρ = 20 km, for dry earth σ_e1 = 4 × 10⁻⁵ Si/m and ε_er1 = 4; sea water σ_e1 = 4 Si/m and ε_er1 = 80; lake water σ_e1 = 4 × 10⁻³ Si/m and ε_er1 = 80) — handled by Romberg integration along the real axis; and (b) Bessel-function oscillation (fig. 11.6.2).
- **p. 622:** figures 11.6.1 and 11.6.2.
- **p. 623:** the non-Bessel part of each integrand was approximated by a degree-16 polynomial via the Remez method, and the product of the Remez polynomial with the Bessel function was integrated directly, avoiding numerical integration of oscillatory functions; maximum approximation error known, so integration error is bounded. Quantities computed are the normalized components at their respective maxima in φ: E_ρ = E_1ρ(φ = 0°), E_φ = E_1φ(φ = 90°), E_z = E_1z(φ = 0°); computed for sea water (σ_e1 = 4 Si/m, ε_er1 = 80), lake water (σ_e1 = 4 × 10⁻³ Si/m, ε_er1 = 80), dry earth (σ_e1 = 4 × 10⁻⁵ Si/m, ε_er1 = 4), ρ from 1 m to 50 km, f from 10 to 10⁸ Hz (footnote 4), with transmitter and observation point at the same depth z = d = 0.15 m (also 1.5 m mentioned).
- **pp. 623–626:** subsection "Electric Field in Three Media at Specific Frequencies"; loss tangent p_e1 = σ_e1/ωε_e1 quoted as ≈ 9,000 (sea water), 9 (lake water), 1.8 (dry earth) at f = 0.1 MHz, and 90 / 0.09 / 0.018 at f = 10 MHz. Figures 11.6.3a (p. 624) and 11.6.3b (p. 626) give |E_ρ|, |E_φ|, |E_z| vs ρ at f = 10⁵ Hz and f = 10⁷ Hz, z = d = 0.15 m. Conclusion: E_ρ is the most useful component over the whole distance range in all three media at both frequencies.
- **pp. 626–635:** subsection "Radial Electric Field E_ρ as a Function of Distance and Frequency" (tabulated in Appendix B, tables B.1/B.2/B.3, d = z = 0.15 m, ε_er1 from 2 to 80, σ_e1 from 4 × 10⁻⁶ to 4 Si/m); figures 11.6.4 and 11.6.5 (|E_ρ| vs ρ with f as parameter, water and earth), 11.6.6 and 11.6.7 (|E_ρ| vs f with ρ as parameter), 11.6.8 and 11.6.9 (contours of constant |E_ρ| in the ρ–f plane, with λ₂ = c/f axis, c = 3 × 10⁸ m/sec); then subsection "Transverse Electric Field E_φ in Lake Water" with figure 11.6.10 (p. 635) and figure 11.6.11 (referenced on p. 635).

---

## Legibility notes

- No characters in the numbered equations of pp. 616–621 were illegible in the 300 dpi render; no [UNREADABLE] markers were required.
- (5.14) as printed carries no ± on the leading exponential term, in contrast with (5.11)–(5.13); transcribed as printed.
- The imaginary unit is printed as italic `i` throughout (not `j`).
- The complex permittivity is printed with a tilde, `ε̃₁` / `ε̃₂`, in (5.8), in the unnumbered p. 616 display, in (5.4), and in the p. 619 k² relations.
