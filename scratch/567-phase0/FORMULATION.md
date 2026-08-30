# momwire#567 phase 0 — the mixed-potential cross-medium reduction

Session artifact, 2026-08-26. The GO/NO-GO question of the ground-arcs plan
(`PLAN-BURIED-AND-CONTACT-ARCS.local.md` A-1):

> **Do (V_T, U_T) suffice for a mixed-potential cross-medium block, or does
> the Michalski–Zheng gauge-correction term (Formulation C) appear for
> horizontal sources?**

Status of each claim is marked: **[derived]** = algebra done in this
document, **[pinned]** = verified numerically by a probe in `proto/`,
**[open]** = awaiting a probe. Nothing here rests on a fresh reading of an
image-scan primary: the two scalars and the five field surfaces are consumed
in the exact spelling `_sommerfeld_transmitted.py` ships and gates (G-U3-5
ε̃=1 collapse, reciprocity 0.0, #568's pointwise mutation gate). The one NEW
kernel this document introduces (§4) is cross-confirmed by two open sources
already transcribed in `BURIED-FORMULATION-SOURCES.local.md` (Baños (2.59),
Poljak/Grcev's W₁₁) — it is the transmitted twin of a kernel three
literatures agree on.

## 1. Conventions and the two scalars

`e^{+jωt}`, interface z = 0, `+` = air above, `−` = ground below,
γ_i = (λ²−k_i²)^{1/2} with Re γ ≥ 0, C₁ = −jωμ₀/4π. Source below at z′ < 0,
observer above at z ≥ 0 (the swap twin exchanges the sides, not the roles).

Spectral kernels under the S₀ transform `2∫₀^∞ (·) J₀(λρ) λ dλ` with
Ẽ = e^{−γ₋|z′| − γ₊z}:

    Ṽ = Ẽ / (k₋²γ₊ + k₊²γ₋)          (7f — the V_T kernel)
    Ũ = Ẽ / (γ₊ + γ₋)                (7g — the U_T kernel)

Derivative bookkeeping (matches `_integrand_six_transmitted` exactly):

    ∂/∂z  ↔ −γ₊        (observer leg, e^{−γ₊z}, z > 0)
    ∂/∂z′ ↔ +γ₋        (source leg, e^{−γ₋|z′|}, z′ < 0 so ∂|z′|/∂z′ = −1)
    horizontal translation invariance holds: ∂/∂x = −∂/∂x′
    vertical translation invariance does NOT: the two legs carry different γ

That last line is the entire content of the gauge problem. Horizontal
derivatives transfer freely between observer and source (and hence onto a
source basis function by parts); z-derivatives pick up γ₊ on the observer
side and γ₋ on the source side, and no gauge choice can make those equal
across a real interface.

The shipped transmitted dyad, in the observation medium (air), per
`t_surfaces_direct`:

    vertical source:    E_ρ = C₁ ∂ρ∂z V           E_z = C₁ (∂z² + k₊²) V
    horizontal source:  E_ρ = C₁ cosφ (∂ρ²V + U)   E_φ = −C₁ sinφ ((1/ρ)∂ρV + U)
                        E_z = −C₁ cosφ ∂ρ∂z′ V

## 2. The mixed-potential ansatz

Seek E(r) = C₁ [ G^A · α̂′ − (1/k₊²) ∇ ∂α′ K ] for a unit current element in
direction α̂′, i.e. vector potential dyad G^A plus ONE scalar-potential
kernel K, with the charge derivative written on the source (∂α′ = α̂′·∇′) so
a Galerkin assembly can move it onto the basis polynomial — exactly the
`_assemble_Z` shape: jωμ₀ on the A term, 1/(jωε₀) on the Φ term (the k₊²
normalization of K is what makes the divisor the OBSERVATION medium's ε₀;
any other choice just moves a constant into K).

Free-space check: K = k₊²V → G, G^A = I·G — the shipped MP fill. ✓

## 3. Horizontal source [derived]

Choose K = k₊²V. Then, using ∂x′ = −∂x on the ρ-dependence:

    −(1/k₊²)∇∂x′K = +∇(cosφ ∂ρ V)
       ρ:  cosφ ∂ρ²V          — matches (7c)'s V term exactly
       φ: −sinφ (1/ρ)∂ρV      — matches (7d)'s V term exactly
       z:  cosφ ∂ρ∂z V ↔ −γ₊ cosφ ∂ρṼ

so A_xx = A_yy = U closes E_ρ and E_φ **with no correction**. But the true
E_z (7e) is −∂ρ∂z′V ↔ −γ₋ cosφ ∂ρṼ: the gradient of the scalar potential
delivers **γ₊** where the field carries **γ₋**. The deficit is

    E_z^def = C₁ cosφ ∂ρ [ (γ₊ − γ₋) Ṽ ]  =  C₁ ∂x W,

which must be carried by a vector-potential component:

    A_zx = ∂x W,      W̃ ≡ (γ₊ − γ₋) Ṽ  =  (γ₊ − γ₋) Ẽ / (k₋²γ₊ + k₊²γ₋).

**This is the Michalski–Zheng Formulation-C correction, named.** Two scalars
do NOT close the horizontal cross-medium block; the third kernel W_T does.

Cross-confirmation without any new primary: Baños & Wesley (2.59) define
g = −2(γ₁−γ₂)/(k₂²γ₁+k₁²γ₂) — with their medium-1 = ground this is
(γ₊−γ₋)/(k₋²γ₊+k₊²γ₋) up to the family's constant 2 — and Poljak & Dorić's
below/below W₁₁ (their eq. 11) is the same spectral factor against the
below/below exponent. The kernel is not novel; only its role in the
TRANSMITTED mixed-potential block is.

## 4. Vertical source [derived]

Same K = k₊²V. −(1/k₊²)∇∂z′K = −∇(γ₋V):

    ρ:  −γ₋ ∂ρṼ     where (7a) needs −γ₊ ∂ρṼ    → deficit −∂ρW = A_ρz action
    z:  +γ₊γ₋ Ṽ     and (7b) needs λ²Ṽ          → A_zz = (λ² − γ₊γ₋) Ṽ

and since λ² − γ₊γ₋ = γ₊(γ₊−γ₋) + k₊²:

    A_zz = k₊² V − ∂z W          [∂z ↔ −γ₊, so γ₊W̃ = −∂zW]
    A_ρz = −∂ρ W  = +∂ρ′... (sign pinned numerically; see §7)

So the complete single-scalar mixed-potential family for the transmitted
regime is

    G^A = U (x̂x̂ + ŷŷ) + (k₊²V − ∂zW) ẑẑ + ẑ(∇_⊥W)ᵀ − (∇_⊥W)ẑᵀ ,   K_Φ = k₊² V

three scalar kernels {U_T, V_T, W_T} plus one z-derivative surface ∂zW_T.
The alternative (per-orientation scalar potentials, K_V = k₊²(γ₊/γ₋)V for
vertical sources) avoids ∂zW but introduces a fourth spectral shape with a
1/γ₋ factor and forfeits the single-Φ Galerkin tensor; it is not pursued.

ε̃ → 1 behaviour [derived]: γ₋ → γ₊ makes W̃ ≡ 0 **identically in λ**, and
A_zz → k₊²V → G, K → G, U → G — the free-space MP fill. **The ε̃ = 1 collapse
is therefore constitutionally blind to every term this document adds**: it
validates the (U, V) plumbing and nothing about W or the gauge. This is the
analytic form of the plan's warning that the collapse "cannot validate the
cross-medium reduction". Any probe of W must run at ε̃ ≠ 1 against the
field-form dyad, which is gated independently.

## 5. The Galerkin block [derived, signs to pin]

For test basis m (tangent t̂_m, polynomial f_m) above and source basis n
below, moving ∂α′ onto f_n (by parts) and horizontal observer derivatives
onto f_m where they occur:

    Z_mn = jωμ₀/4π [ ∬ (t̂_m·t̂_n)_⊥ f_m f_n U
                     + ∬ t_mz t_nz f_m f_n (k₊²V − ∂zW)
                     + s₁ ∬ t_mz f_m f_n′ W
                     + s₂ ∬ f_m′ t_nz f_n W ]
           + 1/(j4πωε₀) ∬ f_m′ f_n′ k₊²V
           − boundary terms (§6)

(t̂·t̂)_⊥ = horizontal components only. The two W cross terms use ONE scalar
table each — the horizontal derivative always lands on a basis polynomial
via translation invariance, never on the table. s₁, s₂ = ±1 are pinned by
probe 1 rather than trusted from this page (the ∂x vs ∂x′ and ρ̂-orientation
sign traps live exactly here, the `_combine_transmitted_transposed`
docstring's "one silent sign error available"). The ∂zW surface CAN be
by-parts'd onto f_m for a vertical test wire (d/dl = ∂z), at the price of a
second boundary term at the contact — the prototype evaluates it as a
derivative surface instead and leaves that trade to U1.

Tabulation consequence for U1 if phase 0 GOes: the surface family is
5 → 8, not 5 → 7: the five field surfaces stay (razor-side and gates), plus
U_T (exists as index 5's integrand but not as a surface), V_T (genuinely
new, the scoping comment's point), W_T, and ∂zW_T. All four new integrands
ride the same contour; none re-derives index 1 (#568's conditioning rule).

## 6. The contact boundary term [derived; the 2.484 explained]

`_assemble_Z`'s Φ term is pure f′f′ — no endpoint terms. That is exact only
because tent bases vanish at their support ends (or cancel across a
junction by KCL). Integration by parts on the TEST side gives, per basis,

    −∫ f_m t̂_m·∇Φ dl = +∫ f_m′ Φ dl − [ f_m Φ ]_ends

and the momwire#151 contact basis is the one basis in the tree with
f_m(end) ≠ 0 — its support terminates ON the interface. The field-form
Galerkin (`_field_galerkin_block`) does no integration by parts at all, so
it carries the endpoint term implicitly and exactly.

**Prediction P2a [open]:** at ε̃ = 1 on the contact deck, the MP cross block
of §5 (W ≡ 0 there) differs from the field-form block by exactly the
contact-basis boundary term [f_m(0)·Φ_n(contact point)], and restoring that
one term closes the G-U5-3 instrument's 2.3–2.5 to the elevated deck's
1e-8 scale. If P2a holds, the 2.484 is not a mystery defect — it is the
integration-by-parts boundary term, quantified, and `_compute_Z_operator_
buried`'s docstring already says so in prose ("the fifth inversion").

The radials contribute no boundary terms: detached free ends carry no
basis (current vanishes there), so f_n = 0 at every below endpoint.

## 7. What the physics of the contact end SHOULD be [open — anchors decide]

At a real contact over finite ground the current does not stop at z = 0:
the contact node exchanges current with the ground half-space. The three
candidate spellings of the cross block differ only in the contact column:

  A. **field form as shipped** (= MP + full endpoint term): the tent ends
     with a hard stop and a point charge at the interface. The A-0 liveness
     run scored this path 46.57 Ω / 142.04 Ω from the anchors.
  B. **MP, endpoint term dropped**: the endpoint charge is deleted — the
     spelling the free-space fill uses for bases that vanish, applied to
     one that doesn't.
  C. **MP with the endpoint term weighted** by the contact continuation the
     above-block already uses (the C₂-image machinery's account of how much
     of the tent continues into the ground).

Probe 3 scores A/B/C against both engine anchors. The GO condition is that
at least one spelling lands within a defensible envelope of BOTH anchors —
that spelling becomes U2/U3's specification and its miss becomes the
re-derived `ANCHOR_ENVELOPE_OHM`.

## 8. Probe ledger (measured 2026-08-26, `proto/`, results in `../results/`)

| # | claim | instrument | status |
|---|---|---|---|
| 1 | §3–§5 assembly: MP block + boundary ≡ field-form block at ε̃ ∈ {13−12.84j, 1, 4−1j} | block-level vs direct `t_surfaces_direct` Galerkin (itself ≡ shipped grid block to 5.8e-6) | **PINNED**: 7.0e-5 off-contact, 2.6e-4 on the contact row, all three soils |
| 1b | W_T is load-bearing at real soil | same identity with W zeroed | **PINNED**: degrades 55× to 1.44e-2, on INTERIOR bases (the ε̃=1 collapse can never see it) |
| 2 | s₁ = s₂ = +1 and t_ba = t_abᵀ | transpose vs the shipped swap-dyad block | **PINNED**: equal at the I1 floor (2.6e-4), and shipped t_ab vs t_baᵀ = 1.8e-16 |
| 3 | P2a: the 2.484 IS the contact boundary term | G-U5-3's own instrument at ε̃ = 1 | **PINNED**: shipped reads 2.48422, the §6 term predicts 2.48551 (Δ ≈ 1.3e-3 = quadrature floor) |
| 4 | real-soil serve vs the two anchors | full solves, cross block swapped | lone radial: A(keep) = 46.56 Ω (≡ production liveness, to 0.01 Ω), B(drop) = 12.91 Ω, C(1−C₂) = 11.98 Ω; **w-scan + fan deck in flight** |
| 5 | reciprocity of the construction | I3 in probe1 | **PINNED** at the I1 floor |

Probe 4 complete: fan A(keep) = 142.02 Ω (≡ production liveness), B(drop) =
16.91 Ω, C = 15.59 Ω. **The blind transfer kills the scalar-weight
hypothesis**: w*(lone) = 0.4197+0.1510j closes its own deck to 0.029 Ω (2
dof on 2 targets — trivially), but applied blind to the fan gives 18.78 Ω,
worse than plain drop; the fan's own refit is a different weight
(0.2975+0.0408j). No single endpoint weight is the contact physics.

**Oracle findings (probe 6, `proto/oracle_ab.py`)**: the x13 asymptotic
workaround NEVER fires on either anchor deck — `EZParam.txt` off/on spread
is 0.0000 Ω on both — so the patched-oracle uncertainty band is nil here
(shallow-radial safe regime, as §1.5 of the sources note predicted). The
lone-radial deck reconstruction reproduces its banked anchor to the printed
digit (92.1300 − 70.1410j). **The four-radial bank is mis-provenanced**:
the engine prints 90.0510 − 70.7310j for the deck the provenance describes,
stable across radial segmentation 5/10/15/20/43, radial spelling
(axis/diagonal/tip-to-center/two-through-wires), and GN 0 vs GN 2 — never
the banked 89.985 − 71.401j (0.67 Ω away). Re-scored against the corrected
anchor: B(drop) = 17.16 Ω, C = 15.99 Ω.

## 9. Verdict

**The GO/NO-GO question is answered: two scalars do NOT close; the
correction term is named.** The complete transmitted mixed-potential family
is {U_T, V_T, W_T, ∂zW_T} with the single scalar kernel K_Φ = k₊²V_T and
explicit by-parts boundary bookkeeping — validated against the shipped
field form to 7.0e-5 off-contact at real soil, reciprocity exact, W_T
load-bearing at 1.4e-2 of the block, and the shipped 2.484 reproduced
analytically to 1.3e-3 as the contact tent's boundary term.

**But #567 standalone cannot reach the anchors.** Removing the unbalanced
endpoint charge (the best defensible MP spelling, B) closes 72–88 % of the
liveness misses (46.57 → 12.91 Ω, 142.04 → 17.16 Ω) and no scalar endpoint
rule transfers between decks. The residual is the physics the refusal
prose already names: the contact current SPREADING into the lower medium —
a real soil current the deck has no conductor for, whose transmitted field
on the radial is absent in every spelling. That is momwire#524 phase 2's
crossing/continuation basis, and this measurement promotes it from "the
bonded decks need it" to "even the DETACHED anchors need it".

Build-ladder consequences:

1. **Re-sequence arc A: A-2 (#524 phase 2) is the load-bearing step**, not
   A-3. The crossing basis also removes the contact fiction outright, and
   with every basis then vanishing at its ends (or KCL-clean), field form
   and MP coincide by construction — the boundary-term problem dissolves
   rather than being repaired.
2. If A-3's MP machinery is still built (U1–U3): surfaces go 5 → 8, index 1
   is never re-derived (#568), spelling B, and **G-U5-3's tripwire semantics
   are wrong after U3**: the ε̃ = 1 collapse then reads < 5e-5 and the
   tripwire demands the refusal lift, while the armed anchor gates would
   fail at 4.0 Ω. The lift criterion must move from "collapse fixed" to
   "anchor gates pass". Consistency ≠ engine agreement — measured.
3. **`ANCHOR_ENVELOPE_OHM = 4.0` stays provisional and untouchable from
   here**; today's achievable is 12.9/17.2 Ω. Phase 2's prototype
   re-derives it.
4. **Re-bank the fan anchor** as 90.0510 − 70.7310j WITH its deck cards
   (they live in `proto/oracle_ab.py`; the lone deck's exact match is the
   validation). Three prose copies + G-U5-12 constants.
5. **#651 (razor buried scope)**: the four tables are basis-agnostic —
   razor's testing side could consume them; no blocker found. The contact
   continuation question applies to razor's grounded tents identically.
