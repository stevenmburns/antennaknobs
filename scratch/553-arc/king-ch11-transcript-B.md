# King & Smith, *Antennas in Matter* — Ch. 11, §11.5 and §11.6

**Source:** R. W. P. King and G. S. Smith, *Antennas in Matter: Fundamentals, Theory, and Applications*, Chapter 11 "Antennas Near a Planar Interface", §11.5 "The Components of the Electromagnetic Field in Cylindrical Coordinates" and §11.6 "Subsurface Transmission in the Earth".
**Scan:** `/home/smburns/antennas/references/king-smith-antennas-in-matter.pdf`, PDF pages 636–655 = printed pages 616–635 (offset: PRINT = PDF − 20).
**Date transcribed:** 2026-08-22.
**Independent transcription copy B.** (Produced without reference to any other transcript.)

**PRIVATE — copyrighted material. Local scratch reference only; never commit, never quote publicly.**

---

## Transcription notes on the scan

- The imaginary unit is printed as an italic **i** throughout (e.g. `i^{-n}` in (5.5), `iωε̃₁γ₁` in (5.4), `2i∫` in (6.10), `e^{ik₁R₁}` in (6.7)). At the 300-dpi rendering the exponent italic *i* is unambiguous; all exponentials are transcribed as `e^{i...}`.
- **Time convention:** these two sections do **not** restate the time-dependence convention. What is printed here: the outgoing spherical wave from the source is written `e^{ik₁R₁}/R₁` (6.7)–(6.9), and the vertical propagation factors are `e^{iγ₁z}`, `e^{iγ₁|z−d|}`, `e^{iγ₁(z+d)}`, `e^{i(γ₁d − γ₂z)}`. (Any e^{∓iωt} attribution would be my inference, not text on these pages, so it is not asserted here.)
- **Wavenumbers, as stated in these sections:**
  - γ₁ and γ₂ are defined by (5.3) below.
  - §11.5 note on λ: "The use of the symbol λ for the radial transform variable is conventional since it was introduced by Sommerfeld. As a variable of integration, it need not be confused with the no less conventional use of λ for the wavelength. This is not a problem here because the wavelengths in the two media are designated by λ₁ and λ₂ = λ₀."
  - §11.6 (p. 619 prose): μ₁ = μ₂ = μ₀ (nonmagnetic); k₁² = ω²μ₀ε̃₁, k₂² = ω²μ₀ε̃₂ = ω²μ₀ε₀ = ω²/c², where c = 3 × 10⁸ m/sec.
- Upper limits of the λ-integrals are printed ∞ (they render as a small "∝"-like glyph at low resolution; verified at 300 dpi).
- ε̃ denotes the tilde-accented (complex/effective) permittivity as printed.

---

## §11.5 The Components of the Electromagnetic Field in Cylindrical Coordinates

### p. 616

Opening prose: it is more convenient to express the field in terms of its cylindrical components E_ρ, E_φ, E_z in the cylindrical coordinates ρ, φ, z and the transform variables λ and φ′; integration over φ′ then yields Bessel functions. "Let"

```
x = ρ cos φ,   y = ρ sin φ,   ξ = λ cos φ′,   η = λ sin φ′.                    (5.1)
```
— printed p. 616

"It follows that"

```
ρ = (x² + y²)^{1/2},   φ = tan⁻¹(y/x),   λ = (ξ² + η²)^{1/2},   φ′ = tan⁻¹(η/ξ).
                                                                                (5.2)
```
— printed p. 616

"Also,"

```
γ₁ = (k₁² − ξ² − η²)^{1/2} = (k₁² − λ²)^{1/2},
γ₂ = (k₂² − ξ² − η²)^{1/2} = (k₂² − λ²)^{1/2}.                                  (5.3)
```
— printed p. 616

Parenthetical prose (transcribed in full because it fixes the λ notation): "(The use of the symbol λ for the radial transform variable is conventional since it was introduced by Sommerfeld. As a variable of integration, it need not be confused with the no less conventional use of λ for the wavelength. This is not a problem here because the wavelengths in the two media are designated by λ₁ and λ₂ = λ₀.) With (5.1), ξx + ηy = λρ cos (φ − φ′) and dξ dη = λ dφ′ dλ. The cylindrical components of the field are given by E_ρ = E_x cos φ + E_y sin φ, E_φ = − E_x sin φ + E_y cos φ; the component E_z is changed only by the introduction of the new variables."

Then: "The following transformation to cylindrical form is for E_{1ρ} in the range d ≤ z. The other components in the other ranges are obtained in a comparable manner. Thus, as a first step," — the following **unnumbered** display begins on p. 616 and is completed as (5.4) on p. 617:

```
                1    2π      ∞
E_1x  =  −  ───────  ∫  dφ′  ∫  dλ λ e^{iλρ cos (φ − φ′)}
              4π²   0        0

              ⎡ μ₁γ₁ (k₂² − λ² cos² φ′) + μ₂γ₂ (k₁² − λ² cos² φ′)
          ×   ⎢ ───────────────────────────────────────────────── e^{iγ₁d}
              ⎣                     ωMN

                  k₁² − λ² cos² φ′            ⎤
              +   ────────────────  sin γ₁ d  ⎥ e^{iγ₁z}
                      iωε̃₁γ₁                  ⎦
```
— printed p. 616 (unnumbered; continues on p. 617)

### p. 617

```
             1     ∞      ⎡ μ₁γ₁k₂² + μ₂γ₂k₁²             k₁²              ⎤
   =  −  ───────   ∫ dλ λ ⎢ ─────────────────  e^{iγ₁d} + ─────── sin γ₁ d ⎥ e^{iγ₁z}
            4π     0      ⎣       ωMN                     iωε̃₁γ₁           ⎦

           2π                              1     ∞        ⎡ μ₁γ₁ + μ₂γ₂              sin γ₁ d ⎤
      ×    ∫  dφ′ e^{iλρ cos (φ − φ′)}  + ────    ∫ dλ λ³ ⎢ ───────────  e^{iγ₁d} + ──────── ⎥
           0                               4π     0       ⎣     ωMN                  iωε̃₁γ₁  ⎦

                   2π
      × e^{iγ₁z}   ∫  dφ′ e^{iλρ cos (φ − φ′)} cos² φ′.                          (5.4)
                   0
```
— printed p. 617
*[sic? — both prefactors in (5.4) are printed 1/4π, without the square, although the φ′ integrals are still written explicitly and the parent unnumbered display on p. 616 carries 1/4π². Verified at 300 dpi: no superscript 2 is present on either 4π in (5.4).]*

Prose: "A similar expression for E_{1y} is readily obtained. The integral representation of the Bessel functions"

```
              i^{−n}  2π
J_n(λρ)  =   ──────   ∫  e^{iλρ cos θ} e^{inθ} dθ                                (5.5)
               2π     0
```
— printed p. 617

"can now be used to obtain"

```
   1    2π
 ────   ∫  e^{iλρ cos (φ − φ′)} dφ′ = J₀(λρ),                                    (5.6)
  2π    0
```
— printed p. 617

```
   1    2π                                1
 ────   ∫  e^{iλρ cos (φ − φ′)} cos² φ′ dφ′ = ─ [J₀(λρ) − J₂(λρ) cos 2φ].        (5.7)
  2π    0                                 2
```
— printed p. 617

"With (5.6) and (5.7), standard differential and functional equations for the Bessel functions, and the convenient notation"

```
      μ₁γ₂ − μ₂γ₁            ε̃₁γ₂ − ε̃₂γ₁
P = ─────────────,      Q = ─────────────,                                       (5.8)
      μ₁γ₂ + μ₂γ₁            ε̃₁γ₂ + ε̃₂γ₁
```
— printed p. 617

"the components of the field have the following forms:
For region 1, where 0 ≤ z,"

```
            ωμ₁          ⎛ ∞
E_1ρ = −  ────── cos φ   ⎜ ∫  {k₁²J₀(λρ) − (λ²/2)[J₀(λρ) − J₂(λρ)]}
           4πk₁²         ⎝ 0

                                              ∞
              × γ₁⁻¹ e^{iγ₁|z − d|} λ dλ   +   ∫  {(γ₁Q/2)[J₀(λρ) − J₂(λρ)]
                                              0

                                                                        ⎞
              − (k₁²P/2γ₁)[J₀(λρ) + J₂(λρ)]} e^{iγ₁(z + d)} λ dλ        ⎠,        (5.9)
```
— printed p. 617

```
           ωμ₁           ⎛ ∞
E_1φ =   ────── sin φ    ⎜ ∫  {k₁²J₀(λρ) − (λ²/2)[J₀(λρ) + J₂(λρ)]} γ₁⁻¹ e^{iγ₁|z − d|} λ dλ
          4πk₁²          ⎝ 0

                ∞
           +    ∫  {(γ₁Q/2)[J₀(λρ) + J₂(λρ)] − (k₁²P/2γ₁)
                0

                                                              ⎞
           × [J₀(λρ) − J₂(λρ)]} e^{iγ₁(z + d)} λ dλ           ⎠,                  (5.10)
```
— printed p. 617

### p. 618

```
          iωμ₁          ∞
E_1z =  ────── cos φ    ∫  [± e^{iγ₁|z − d|} + Q e^{iγ₁(z + d)}] J₁(λρ) λ² dλ,    (5.11)
         4πk₁²          0
```
— printed p. 618

```
           μ₁           ⎛     ∞                                     ∞
B_1ρ = −  ──── sin φ    ⎜ ±   ∫ J₀(λρ) e^{iγ₁|z − d|} λ dλ    +      ∫ {(Q/2)[J₀(λρ) + J₂(λρ)]
           4π           ⎝     0                                     0

                                                              ⎞
           − (P/2)[J₀(λρ) − J₂(λρ)]} e^{iγ₁(z + d)} λ dλ      ⎠,                  (5.12)
```
— printed p. 618

```
           μ₁           ⎛     ∞                                      ∞
B_1φ = −  ──── cos φ    ⎜ ±   ∫ J₀(λρ) e^{iγ₁|z − d|} λ dλ    +       ∫ {(Q/2)[J₀(λρ) − J₂(λρ)]
           4π           ⎝     0                                      0

                                                              ⎞
           − (P/2)[J₀(λρ) + J₂(λρ)]} e^{iγ₁(z + d)} λ dλ      ⎠,                  (5.13)
```
— printed p. 618

```
          iμ₁          ∞
B_1z =   ──── sin φ    ∫  [e^{iγ₁|z − d|} − P e^{iγ₁(z + d)}] γ₁⁻¹ J₁(λρ) λ² dλ.  (5.14)
          4π           0
```
— printed p. 618

Prose: "Where two signs appear, the upper one is for the range d < z, the lower one for 0 ≤ z ≤ d." Then: "For region 2, where z ≤ 0,"

```
            1          ∞      ⎧ ωμ₁μ₂                          γ₁γ₂
E_2ρ = −  ──── cos φ   ∫ dλ λ ⎨ ────── [J₀(λρ) + J₂(λρ)]   +   ──── [J₀(λρ)
           4π          0      ⎩   M                             ωN

                        ⎫
           − J₂(λρ)]    ⎬ e^{i(γ₁d − γ₂z)},                                       (5.15)
                        ⎭
```
— printed p. 618

```
           1           ∞      ⎧ ωμ₁μ₂                          γ₁γ₂
E_2φ =   ──── sin φ    ∫ dλ λ ⎨ ────── [J₀(λρ) − J₂(λρ)]   +   ──── [J₀(λρ)
          4π           0      ⎩   M                             ωN

                        ⎫
           + J₂(λρ)]    ⎬ e^{i(γ₁d − γ₂z)},                                       (5.16)
                        ⎭
```
— printed p. 618

```
            i            ∞        γ₁
E_2z = −  ──── cos φ     ∫ dλ λ² ──── J₁(λρ) e^{i(γ₁d − γ₂z)},                    (5.17)
           2π            0        ωN
```
— printed p. 618

```
          μ₂           ∞      ⎧ μ₁γ₂                         ε̃₂γ₁
B_2ρ =   ──── sin φ    ∫ dλ λ ⎨ ───── [J₀(λρ) − J₂(λρ)]   +  ───── [J₀(λρ)
          4π           0      ⎩   M                            N

                        ⎫
           + J₂(λρ)]    ⎬ e^{i(γ₁d − γ₂z)},                                       (5.18)
                        ⎭
```
— printed p. 618

```
          μ₂           ∞      ⎧ μ₁γ₂                         ε̃₂γ₁
B_2φ =   ──── cos φ    ∫ dλ λ ⎨ ───── [J₀(λρ) + J₂(λρ)]   +  ───── [J₀(λρ)
          4π           0      ⎩   M                            N

                        ⎫
           − J₂(λρ)]    ⎬ e^{i(γ₁d − γ₂z)},                                       (5.19)
                        ⎭
```
— printed p. 618

### p. 619

```
          iμ₂           ∞        μ₁
B_2z =   ──── sin φ     ∫ dλ λ² ──── J₁(λρ) e^{i(γ₁d − γ₂z)}.                     (5.20)
          2π            0        M
```
— printed p. 619

Closing prose of §11.5: "Definitions for M and N are given in (4.1), for P and Q in (5.8). This completes the specification of the components in cylindrical coordinates of the electromagnetic field in both half-spaces when a horizontal electric dipole with moment IΔl = 1 is in region 1 at a distance d from the boundary. The integrations with respect to λ remain and these are complicated."

---

## §11.6 Subsurface Transmission in the Earth

### p. 619

Setup prose: the problem requires the general formulas for an infinitesimal electric dipole **parallel to the interface** between two half-spaces of different materials. The transmitting dipole oscillates at frequency *f* at depth *d* in a homogeneous, isotropic half-space with the properties of some part of the earth's surface — sea water, lake water, or dry soil. The study is of the field over wide ranges of radial distance ρ and frequency *f*, to determine which experiences the smallest attenuation and in which direction. "In order to answer these questions, it is convenient to determine the field at the same depth below the surface as that of the transmitter. That is, let z = d."

Stated specializations (printed p. 619): "Because the relevant materials are nonmagnetic, μ₁ = μ₂ = μ₀ so that in (4.1) M = μ₀(γ₂ + γ₁) and in (5.8) P = (γ₂ − γ₁)/(γ₂ + γ₁). Also, because k₁² = ω²μ₀ε̃₁, k₂² = ω²μ₀ε̃₂ = ω²μ₀ε₀ = ω²/c², where c = 3 × 10⁸ m/sec, it follows that in (4.1) N = (k₁²γ₂ + k₂²γ₁)/ω²μ₀ and in (5.8) Q = (k₁²γ₂ − k₂²γ₁)/(k₁²γ₂ + k₂²γ₁). From (5.9) through (5.11), the components of the electric field in the earth are"

*(Note: here region 1 = the earth/water half-space containing both the dipole and the observer; region 2 = air, with k₂² = ω²/c².)*

```
            ωμ₀          ⎛ ∞
E_1ρ = −  ────── cos φ   ⎜ ∫  {k₁²J₀(λρ) − (λ²/2)[J₀(λρ) − J₂(λρ)]} γ₁⁻¹ λ dλ
           4πk₁²         ⎝ 0

                 ∞    ⎧ γ₁ (k₁²γ₂ − k₂²γ₁)
            +    ∫    ⎨ ─────────────────── [J₀(λρ) − J₂(λρ)]
                 0    ⎩ 2 (k₁²γ₂ + k₂²γ₁)

                  k₁²(γ₂ − γ₁)                    ⎫                     ⎞
            −   ──────────────  [J₀(λρ) + J₂(λρ)] ⎬ e^{i2γ₁d} λ dλ      ⎠,
                  2γ₁(γ₂ + γ₁)                    ⎭
                                                                                  (6.1)
```
— printed p. 619

### p. 620

```
           ωμ₀           ⎛ ∞
E_1φ =   ────── sin φ    ⎜ ∫  {k₁²J₀(λρ) − (λ²/2)[J₀(λρ) + J₂(λρ)]} γ₁⁻¹ λ dλ
          4πk₁²          ⎝ 0

                 ∞    ⎧ γ₁ (k₁²γ₂ − k₂²γ₁)
            +    ∫    ⎨ ─────────────────── [J₀(λρ) + J₂(λρ)]
                 0    ⎩ 2 (k₁²γ₂ + k₂²γ₁)

                  k₁²(γ₂ − γ₁)                    ⎫                     ⎞
            −   ──────────────  [J₀(λρ) − J₂(λρ)] ⎬ e^{i2γ₁d} λ dλ      ⎠,        (6.2)
                  2γ₁(γ₂ + γ₁)                    ⎭
```
— printed p. 620

```
          iωμ₀           ∞    ⎡        k₁²γ₂ − k₂²γ₁            ⎤
E_1z =   ────── cos φ    ∫    ⎢ ± 1 + ───────────────  e^{i2γ₁d}⎥ J₁(λρ) λ² dλ.   (6.3)
          4πk₁²          0    ⎣        k₁²γ₂ + k₂²γ₁            ⎦
```
— printed p. 620

Prose: "These are the components per unit dipole moment; that is, with IΔl = 1. In (6.3) the upper sign is for d < z, the lower sign for 0 ≤ z ≤ d."

Then: "It is appropriate to note that these formulas can be obtained from the following formulation, which is based on the work of Baños, who first calculated the components of the Hertz potentials and, from these, the electromagnetic field.³ The electric field due to a unit electric moment (IΔl = 1) is given by"

```
          iωμ₀        ⎛ ∂²F           ⎞
E_1ρ =   ────── cos φ ⎜ ──── + k₁²G   ⎟,                                          (6.4)
          4πk₁²       ⎝ ∂ρ²           ⎠
```
— printed p. 620

```
            iωμ₀        ⎛ 1  ∂F            ⎞
E_1φ = −   ────── sin φ ⎜ ─  ──  + k₁²G    ⎟,                                     (6.5)
            4πk₁²       ⎝ ρ  ∂ρ            ⎠
```
— printed p. 620

```
          iωμ₀          ∂²H
E_1z =   ────── cos φ  ──────,                                                    (6.6)
          4πk₁²        ∂ρ ∂z
```
— printed p. 620

"where"

```
      e^{ik₁R₁}     e^{ik₁R₂}
F =  ─────────  −  ─────────  +  k₁² V₁₁,                                         (6.7)
         R₁            R₂
```
— printed p. 620

```
      e^{ik₁R₁}     e^{ik₁R₂}
G =  ─────────  −  ─────────  +  U₁₁,                                             (6.8)
         R₁            R₂
```
— printed p. 620

```
      e^{ik₁R₁}     e^{ik₁R₂}
H =  ─────────  +  ─────────  −  k₂² V₁₁,                                         (6.9)
         R₁            R₂
```
— printed p. 620

"and R₁ = [ρ² + (z − d)²]^{1/2}, R₂ = [ρ² + (z + d)²]^{1/2}. The functions U₁₁ and V₁₁ are the integrals"

```
             ∞
U₁₁ = 2i     ∫  (γ₂ + γ₁)⁻¹ e^{iγ₁(z + d)} J₀(λρ) λ dλ,                          (6.10)
             0
```
— printed p. 620

### p. 621

```
             ∞
V₁₁ = 2i     ∫  (k₁²γ₂ + k₂²γ₁)⁻¹ e^{iγ₁(z + d)} J₀(λρ) λ dλ.                    (6.11)
             0
```
— printed p. 621

"Note that"

```
(∂²/∂ρ²) J₀(λρ) = − λ (∂/∂ρ) J₁(λρ) = − (λ²/2)[J₀(λρ) − J₂(λρ)].                 (6.12)
```
— printed p. 621

Prose after (6.12): "When the indicated differentiation is carried out and the terms are rearranged, (6.4) through (6.6) yield precisely (6.1) through (6.3). The forms (6.4) through (6.6) are interesting because the contributions to the field are expressed in three parts: the direct contribution from the dipole (e^{ik₁R₁}/R₁), the contribution from a fictitious ideal image in a perfectly conducting region 2 (−e^{ik₁R₂}/R₂), and the corrections to take account of the fact that region 2 is not a perfect conductor. These last are contained in the complex integrals U₁₁ and V₁₁ with the appropriate constant factors."

---

## Remaining pages 621–635: no further numbered equations

From here to the end of the assigned range the text is numerical-method discussion, figures, and results prose. **No numbered equations appear on printed pages 621–635** (verified page by page). The substantive content, summarized:

**p. 621.** Direct analytical integration in closed form with respect to λ has not been achieved; approximate procedures including saddle-point integration have limited application because the parameter ranges are so wide: ρ from 1 m to 1000 km, f = 1 to 10⁹ Hz, real effective relative permittivities ε_er = 2 to 81, real effective conductivities σ_e = 10⁻⁸ to 10 Si/m. Numerical evaluation faces two problems: (a) a sharp peak at the branch points — integrands illustrated in figure 11.6.1 at f = 0.1 MHz, ρ = 20 km for (a) dry earth σ_e1 = 4 × 10⁻⁵ Si/m, ε_er1 = 4; (b) sea water σ_e1 = 4 Si/m, ε_er1 = 80; (c) lake water σ_e1 = 4 × 10⁻³ Si/m, ε_er1 = 80 — handled by the Romberg method along the real axis; and (b) oscillation of the Bessel functions (figure 11.6.2).

**p. 622.** Figures only. Figure 11.6.1 caption: "Examples of real part of integrands near λ = k₂ of integrals in expression for E_ρ in (a) dry earth, (b) salt water, and (c) lake water; f = 10⁵ Hz, ρ = 20 km." Figure 11.6.2 caption: "Examples of integrands in integrals in expression for E_ρ in lake water at f = 10⁵ Hz with (a) ρ = 20 km and (b) ρ = 200 m." (Axis annotations in 11.6.1: λ from .002075 to .002116; ordinates 9×10⁻⁷/7×10⁻⁷/5×10⁻⁷ in (a), 2×10⁻⁷/10⁻⁷/0 in (b), 6×10⁻⁷/0/−6×10⁻⁷ in (c).)

**p. 623.** Because a Bessel function of order p multiplied by the independent variable raised to the power (p + 1) is integrable exactly, the non-Bessel part of each integrand was approximated by a degree-16 polynomial via the Remez method, and the product integrated directly; maximum error known, so integration error is known. The quantities actually calculated are the normalized components of (6.4)–(6.6) in the directions of their respective maxima with respect to φ: **E_ρ = E_1ρ(φ = 0°), E_φ = E_1φ(φ = 90°), E_z = E_1z(φ = 0°)**, with IΔl = 1. Computed for infinitesimal horizontal dipoles in sea water (σ_e1 = 4 Si/m, ε_er1 = 80), lake water (σ_e1 = 4 × 10⁻³ Si/m, ε_er1 = 80), and dry earth (σ_e1 = 4 × 10⁻⁵ Si/m, ε_er1 = 4), over ρ from 1 m to 50 km and f from 10 to 10⁸ Hz.⁴ **Transmitting dipole and point of observation at the same depth, z = d = 0.15 m or 1.5 m.** No universal curves in dimensionless quantities such as β₁ρ and α₁/β₁ are possible. Subsection "Electric Field in Three Media at Specific Frequencies": loss tangent p_e1 = σ_e1/ωε_e1 is near 9,000 for sea water, 9 for lake water, 1.8 for dry earth at f = 0.1 MHz; at f = 10 MHz p_e1 is 90 (sea water), 0.09 (lake water), 0.018 (dry earth).

**p. 624.** Discussion of figure 11.6.3a (f = 10⁵ Hz; subscripts E = dry earth, L = lake water, S = sea water): for dry earth |E_ρ| largest from ρ = 1 m to ≈ 300 m, |E_φ| largest between ρ ≈ 0.3 km and ρ ≈ 1.2 km, |E_ρ| again largest from 1.2 km outward; |E_z| exceeds |E_φ| near ρ ≈ 3 km and remains the smallest to at least ρ ≈ 50 km. Figure 11.6.3a caption: "Components of electric field of horizontal dipole below surface of a material half-space." Figure legend text: f = 10⁵ Hz; EARTH σ_e1 = 4×10⁻⁵ Si/m, ε_er1 = 4, p_e1 = 1.8; LAKE WATER σ_e1 = 4×10⁻³ Si/m, ε_er1 = 80, p_e1 = 9; SEA WATER σ_e1 = 4 Si/m, ε_er1 = 80, p_e1 = 9000; curves |E_ρ|, φ = 0°; |E_φ|, φ = 90°; |E_z|, φ = 0°; z = d = 0.15 m.

**p. 625.** Sea water: |E_ρ| largest except between two crossover points with |E_φ| — |E_ρ| largest for ρ less than 1 m and greater than 1.1 km, |E_φ| largest between; |E_z| much smaller than both, probable crossover beyond the graph. Summary: for all three media at f = 0.1 MHz the radial component along the dipole axis (φ = 0) is largest both near and far, with an intermediate region where |E_φ| leads, beginning at ρ ≈ 1 km and extending back to 300 m, 30 m, and 1 m for dry earth, lake water, and sea water respectively; |E_ρ| is the most useful component over the whole range at f = 10⁵ Hz. At f = 10 MHz (figure 11.6.3b) crossovers shift to shorter distances for sea water; the E_ρ/E_φ second crossing near ρ = 10 m at 10 MHz versus ρ = 1 km at 0.1 MHz; E_φ/E_z crossover moves from ρ > 100 km at 0.1 MHz to ρ ≈ 1 km at 10 MHz. Dry earth at 10 MHz behaves like a dielectric, so exponential attenuation of the direct wave is greatly reduced and all three components come much closer together.

**p. 626.** Figure 11.6.3b (f = 10⁷ Hz; DRY EARTH σ_e1 = 4×10⁻⁵ Si/m, ε_er1 = 4, p_e1 = 0.018; LAKE WATER σ_e1 = 4×10⁻³ Si/m, ε_er1 = 80, p_e1 = 0.09; SEA WATER σ_e1 = 4 Si/m, ε_er1 = 80, p_e1 = 90; z = d = 0.15 m). Beyond ρ = 200 m, |E_ρ| again greatest; the most useful component at f = 10 MHz is again E_ρ. Subsection "Radial Electric Field E_ρ as a Function of Distance and Frequency": computations tabulated in Appendix B for |E_ρ| at a depth 0.15 m, source dipole also at 0.15 m; tables B.1 (long distances) and B.2 (short distances) give |E_ρ| in dB referred to 1 volt/m, with distances in table B.3; ε_er1 in the range 2 to 80 and seven values of σ_e1.

**p. 627.** Practical ranges: for ε_er1 = 80, σ_e1 from 4 × 10⁻³ Si/m (lake water) to 4 Si/m (sea water); values ε_er1 = 4, 8, 16, 20 with σ_e1 from 4 × 10⁻⁵ to 4 × 10⁻² Si/m characterize dry to wet soil; ε_er1 = 40 and extended σ_e1 ranges included for continuity. Graphs in figures 11.6.4 through 11.6.9; comparison later with Baños's simple analytical approximations. Systematic tabulation limited to 0.1 km to 100 km but complete frequency range 10 Hz to 1 GHz. Figures 11.6.4 (water, ε_er1 = 80, σ_e1 = 0.004, 0.04, 0.4, 4 Si/m) and 11.6.5 (dry earth, ε_er1 = 4, σ_e1 = 4 × 10⁻⁵, 4 × 10⁻⁴, 4 × 10⁻³, 4 × 10⁻² Si/m) plot |E_ρ| versus ρ with f as parameter; each graph consists of two roughly linear parts with different slopes, the knee closer to the dipole the higher the frequency — near ρ = 50 km at f = 10³ Hz, ρ = 5 km at f = 10⁴ Hz, ρ = 0.5 km at f = 10⁵ Hz. Figures 11.6.6 and 11.6.7 show the same data with frequency as the variable and ρ as parameter.

**p. 628.** Figure 11.6.4 (four panels; |E_ρ| in dB versus ρ in km from .1 to 10²; ε_er1 = 80 with σ_e1 = 0.004, 0.04, 0.4, 4 Si/m; frequency labels 10 through 10⁹). Caption: "Radial electric field |E_ρ| for water as a function of radial distance ρ with frequency f as the parameter; d = z = 0.15 m."

**p. 629.** Figure 11.6.5 (four panels; ε_er1 = 4 with σ_e1 = 0.00004, 0.0004, 0.004, 0.04 Si/m). Caption: "Radial electric field |E_ρ| for earth as a function of radial distance ρ with frequency as the parameter; d = z = 0.15 m."

**p. 630.** Figure 11.6.6 (four panels, |E_ρ| in dB versus f in Hertz from 10 to 10⁹, ρ = 0.1 to 100 km as parameter; ε_er1 = 80 with σ_e1 = 0.004, 0.04, 0.4, 4.0 Si/m). Caption: "Radial electric field |E_ρ| for water as a function of frequency f with the radial distance ρ as the parameter; d = z = 0.15 m."

**p. 631.** Figure 11.6.7 (four panels; ε_er1 = 4 with σ_e1 = 0.00004, 0.0004, 0.004, 0.04 Si/m; ρ in km as parameter). Caption: "Radial electric field |E_ρ| for earth as a function of the frequency f with radial distance ρ as the parameter; d = z = 0.15 m."

**p. 632.** The low-frequency range is essentially the near field, the high-frequency range the far field, the diagonal transition the intermediate field. At higher conductivities a maximum develops in the high-frequency range followed by a steep decline (exponential attenuation), as in sea water with σ_e1 = 4 Si/m. Contours of constant |E_ρ| versus ρ and f (or λ = c/f, c = 3 × 10⁸ m/sec, "the free-space velocity of unbounded electromagnetic waves") are given in figure 11.6.8 (water, ε_er1 = 80) and figure 11.6.9 (earth, ε_er1 = 4), four conductivities each. Examples: for lake water (ε_er1 = 80, σ_e1 = 0.004 Si/m), |E_ρ| = −150 dB at both ρ ≈ 59 km for f ≥ 10⁶ Hz and ρ ≈ 1 km when f ≤ 10⁴ Hz; for earth (ε_er1 = 4, σ_e1 = 4 × 10⁻⁵ Si/m), |E_ρ| = −150 dB at both ρ ≈ 44 km for f ≥ 10⁵ Hz and ρ ≈ 5.4 km for f ≤ 10⁴ Hz. In sea water (ε_er1 = 80, σ_e1 = 4 Si/m) it is possible to maintain |E_ρ| at −180 dB at ρ = 30 km at f ≐ 5 MHz and at only 0.35 km at f ≤ 1 kHz; at f > 50 MHz, |E_ρ| drops precipitously.

**p. 633.** Figure 11.6.8 (four contour panels; ρ in kilometers versus f in Hertz, with λ₂ in kilometers on the upper axis; ε_er1 = 80 with σ_e1 = 0.004, 0.04, 0.4, 4 Si/m; contour labels |E_ρ| = −50 to −350 dB). Caption: "Contours of constant |E_ρ| for water as functions of frequency f and radial distance ρ; d = z = 0.15 m."

**p. 634.** Figure 11.6.9 (four contour panels; ε_er1 = 4 with σ_e1 = 0.00004, 0.0004, 0.004, 0.04 Si/m). Caption: "Contours of constant |E_ρ| for earth as functions of frequency f and radial distance ρ; d = z = 0.15 m."

**p. 635.** At fixed ρ, |E_ρ| at low frequencies is considerably greater than at very high frequency (f ≥ 50 MHz) but substantially lower than near f = 5 MHz. Graphs like figures 11.6.4 through 11.6.9 can be constructed from the Appendix B tables for 2 ≤ ε_er1 ≤ 80, 4 × 10⁻⁶ ≤ σ_e1 ≤ 4 Si/m. Subsection "Transverse Electric Field E_φ in Lake Water": |E_φ| in lake water shown in figure 11.6.10 versus ρ with f as parameter and in figure 11.6.11 versus f with ρ as parameter; similar to |E_ρ| but with a less pronounced knee in the radial dependence; as with |E_ρ|, |E_φ| is greater at higher frequencies than at lower ones as ρ increases. Figure 11.6.10 caption: "Transverse electric field of horizontal dipole 0.15 m below surface of lake water as a function of the radial range; parameter is the frequency in Hertz." (Panel annotations: σ_e1 = 4×10⁻³ Si/m, ε_er1 = 80, φ = 90°.)

---

## Index of numbered equations transcribed

| Equation | Printed page |
|---|---|
| (5.1) | 616 |
| (5.2) | 616 |
| (5.3) | 616 |
| *(unnumbered E_1x first step)* | 616 |
| (5.4) | 617 |
| (5.5) | 617 |
| (5.6) | 617 |
| (5.7) | 617 |
| (5.8) | 617 |
| (5.9) | 617 |
| (5.10) | 617 |
| (5.11) | 618 |
| (5.12) | 618 |
| (5.13) | 618 |
| (5.14) | 618 |
| (5.15) | 618 |
| (5.16) | 618 |
| (5.17) | 618 |
| (5.18) | 618 |
| (5.19) | 618 |
| (5.20) | 619 |
| (6.1) | 619 |
| (6.2) | 620 |
| (6.3) | 620 |
| (6.4) | 620 |
| (6.5) | 620 |
| (6.6) | 620 |
| (6.7) | 620 |
| (6.8) | 620 |
| (6.9) | 620 |
| (6.10) | 620 |
| (6.11) | 621 |
| (6.12) | 621 |

Printed pages 622–635 contain no numbered equations.
