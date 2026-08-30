# momwire#524 phase 2 — near-interface corner asymptotics of the transmitted family

Session artifact, 2026-08-26 (session 5). The load-bearing build named by
session 4's verdict (PLAN.md §NEXT EXPERIMENTS item 1): designed evaluation
of {U_T, V_T, W_T, ∂zW_T} at the interface corner z, z′ → 0, ρ → 0 — the
phase-0 z′-clamp edge, the only unvalidated entries in the matrix.

Status marks: **[derived]** = algebra on this page, **[pinned]** = verified
numerically by a probe, **[open]** = awaiting one.

## 0. Why the shipped contour fails at the corner [derived + probe12]

Every kernel of the family is `2∫₀^∞ (·) Ẽ J₀(λρ) λ dλ` with
Ẽ = e^{−γ₋|z′| − γ₊z}. Tail convergence has exactly two sources: the
exponent (decay length s = z + |z′|) and the Bessel oscillation (decay
J₀ ~ λ^{−1/2}, panelled at the J₀ zeros with spacing π/ρ). At the corner
BOTH die: s → 0 kills the exponent and ρ → 0 pushes the J₀ zeros to
infinity — the shipped tail panelling has nothing to panel on. This is not
a budget problem; the real-axis tail is structurally non-convergent there
(probe12), and the z′ = −1e-9 clamp never addressed it (the clamp moves
the evaluation point; the tail's non-decay is unchanged as s → 0).

Note z + |z′| = z − z′ for z ≥ 0 ≥ z′, so s is the TRUE vertical
separation, not an image distance: R = √(ρ² + s²) is the physical pair
distance, and "the corner" is genuinely R → 0.

## 1. The corner singularity structure [derived]

Large-λ expansion, u = 1/λ, p = k₊², m = k₋² = ε̃k₊²:

    γ± = λ(1 − k±²u²/2 − k±⁴u⁴/8 − …)
    γ₊+γ₋      = 2λ·(1 − (p+m)u²/4 + …)
    k₋²γ₊+k₊²γ₋ = (p+m)λ·(1 − mp·u²/(p+m) + …)
    γ₊−γ₋      = ((m−p)/2)·u·(1 + (m+p)u²/4 + …)

Leading tail behaviour of the four integrands (the S₀ factor 2 and the
measure λ dλ folded in), with Ẽ → e^{−λs}:

    U_T    :  e^{−λs} J₀(λρ) · [1 + O(u²)]
    V_T    :  e^{−λs} J₀(λρ) · [2/(p+m) + O(u²)]
    W_T    :  e^{−λs} J₀(λρ) · [(m−p)/(m+p)·u + O(u³)]
    ∂zW_T  :  e^{−λs} J₀(λρ) · [−(m−p)/(m+p) + O(u²)]

and ∫₀^∞ e^{−λs}J₀(λρ)dλ = 1/R, ∫^∞ e^{−λs}J₀(λρ)dλ/λ = −ln(s+R) + …, so
the corner singularities are

    U_T     =  1/R                      + O(ln R)·k²-scale
    k₊²V_T  =  2/(1+ε̃) · 1/R           + O(ln R)·k²-scale     [the static term]
    W_T     =  −(ε̃−1)/(ε̃+1) · ln R     + finite               [log only]
    ∂zW_T   =  −(ε̃−1)/(ε̃+1) · 1/R      + O(ln R)·k²-scale

(k₊²·2/(p+m) = 2/(1+ε̃); (m−p)/(m+p) = (ε̃−1)/(ε̃+1).) The static factor
2/(1+ε̃) matches the same-medium node weights (1−C₂)/ε₀ ≡ (1−A_m)/ε̃ε₀
scaled — DERIVATION-SAME-MEDIUM.md §3's static consistency, now from the
transmitted side. At ε̃ = 1 exactly: γ₊ ≡ γ₋, W̃ ≡ 0, and

    U_T = k₊²V_T = e^{−jk₊R}/R,   W_T = ∂zW_T = 0   (all R — exact gate)

## 2. The designed evaluation: a rotated tail, not a clamp [derived]

Split each integral at Λ = 8·max(|k₊|, |k₋|):

  * **head** [0, 1.1K]: the shipped first-quadrant sinusoidal detour
    (`_head`), unchanged — branch points and the transmitted pole live
    here and it already handles them at every SPEC soil.
  * **mid** [1.1K, Λ]: real-axis adaptive Gauss — the integrand is smooth
    and pole/cut-free there.
  * **tail** [Λ, ∞): rotate into the complex plane along λ = Λ + t·e^{±jπ/4}.
    - ρ = 0: J₀ = 1; ONE up-ray (+π/4). |integrand| ~ e^{−ts/√2}.
    - ρ > 0: J₀ = (H₀⁽¹⁾ + H₀⁽²⁾)/2; H⁽¹⁾ up-ray, H⁽²⁾ down-ray.
      |integrand| ~ e^{−t(s+ρ)/√2} on each.

    Decay is governed by s + ρ ≈ R — positive at every evaluated point —
    so the tail converges UNIFORMLY through the corner: z′ = 0 exact,
    z = 0 exact, any R > 0. No clamp anywhere.

Legitimacy of the rotation [derived]: under e^{+jωt} both branch cuts run
downward from k₊ and k₋; the k₋ cut follows Re(λ²) = Re m, i.e. the
hyperbola 2·Reλ·Imλ = Im m, which stays at Re λ ≤ |k₋| ≪ Λ; the k₊ cut is
the real segment |λ| < k₊ plus the imaginary axis. The transmitted pole
k₋²γ₊ + k₊²γ₋ = 0 sits at |λ_p| ≈ |k₊k₋|/|k₊²+k₋²|^{1/2} < K ≪ Λ. The
sector swept by the rotation (|λ| ≥ Λ, |arg(λ−Λ)| ≤ π/4) contains neither,
and each half-integrand decays in its own half-plane, so the deformation
is exact, not asymptotic. The down-ray keeps Re γ± ≥ 0 on the principal
branch (both cuts untouched), so Ẽ decays there too.

## 3. What ρ to evaluate at — the missing radius [derived from src]

The shipped cross fill (`bspline.py` `_transmitted_plan`/fill, crho at
:4349) uses AXIS-to-axis horizontal distance and never folds in the wire
radius. On the coaxial crossing deck crho ≡ 0, and then two continuum
integrals at the node are LOG-DIVERGENT, finite only by quadrature
truncation:

  * the field-form corner content (∂z∂z′-class kernel ~ 1/s³ against two
    value-1 ends) — probe14d's measured 9.58× truncation;
  * the end-evaluation columns ∫ f′_n V(ρ=0, 0, z′) dz′ ~ ∫ dz′/|z′| —
    the by-parts boundary terms themselves.

The physical regularization is the thin-wire radius: observer on the wire
surface, R never below a. The shipped same-medium MP blocks do exactly
this (R = √(Δz² + a²) via the segment moments); the cross block never
did. **Design rule: every cross-family evaluation whose pair distance can
reach the a-scale carries the thin-wire offset — coaxial pairs evaluate
at ρ = a.** For pairs at R ≫ a the offset is invisible (O(a²/R²)); at the
node it is the difference between a designed number and a truncated
divergence. The corner value (node against itself) is the designed table
at (ρ = a, z = 0, z′ = 0) — R = a exactly, the same scalar-distance
convention as probe14's same-medium corners G(a) = e^{−jka}/a.

## 4. Two auxiliary surfaces close the by-parts identities [derived]

Gate 1 (the identity's node row) needs the field-side forms evaluated on
the SAME designed kernels. Derivative bookkeeping ∂z ↔ −γ₊, ∂z′ ↔ +γ₋
gives two more integrands on the same contour:

    ∂z∂z′V_T ↔ −γ₊γ₋ Ṽ         (the Φ term's field form)
    ∂z′W_T   ↔ +γ₋ W̃           (the W cross terms' field form)

With these, every by-parts move mp_cross makes is checkable as an exact
1-D identity at fixed ρ = a:

    ∬ f_m f_n ∂z∂z′V = ∬ f′_m f′_n V − Σ_E σ f_m(E)∫f′_n V(E,·)
                        − Σ_E′ σ′ f_n(E′)∫f′_m V(·,E′)
                        + ΣΣ σσ′ f_m(E)f_n(E′) V(E,E′)
    ∬ f_m f_n ∂z′W   = Σ_E′ σ′ f_n(E′)∫f_m W(·,E′) − ∬ f_m f′_n W

(sign structure −,−,+ as pinned by probe14 on the same-medium families).
Both sides finite and quadrature-resolvable at ρ = a with log-graded
within-arm quadrature toward the node.

## 5. The below-remainder's R₁ → 0 edge [derived, deferred to measurement]

The below/below reflected remainder (`_six_integrals_below`) decays as
e^{−λh}, h = |z|+|z′| — the same corner class when both points approach
the interface at ρ = 0. The identical rotated-tail design applies verbatim
(its integrands are functions of (ρ, h) only). Built only if gate 2 shows
the below self block's node entries are load-bearing at the 3 Ω signal —
the shipped graded solves (probe19: B+split → Δ ≈ 0 stable) suggest the
self blocks are not the diverging piece, so this edge is assessed AFTER
the cross-table swap, not before.

## 6. Probe ledger

| # | claim | instrument | status |
|---|---|---|---|
| 21a | designed ≡ shipped contour tables where the latter converges (moderate R, all four kernels) | overlap grid | **PINNED 2026-08-26**: max rel 7.9e-13 over 6 points, all four kernels |
| 21b | Λ/ray-independence: Λ = 8K vs 12K | corner-adjacent grid (incl. R = a corner, z′ = 0 exact, old dead zone) | **PINNED**: 4.2e-9. TRAP fixed on the way: ray panels must START at the Λ scale and double toward the decay scale — starting at the decay scale under-resolves the 1/λ log content when s + ρ is tiny (measured 44 % error on dW/dln s at s = 1e-5, silently plausible values) |
| 21c | §1 singular structure: s·U_T → 1, s·k₊²V_T → 2/(1+ε̃), s·∂zW_T → −(ε̃−1)/(ε̃+1), dW_T/d ln s → −(ε̃−1)/(ε̃+1) | small-s sweep at ρ=0 | **PINNED**: all four to ≤ 7.5e-6 at s = 1e-5 (finite-s correction scale) |
| 21d | ε̃ = 1: U_T = k₊²V_T = e^{−jk₊R}/R exact, W ≡ ∂zW ≡ 0 | closed form | **PINNED**: 2.2e-16; W, dzW exactly 0 |
| 21e | auxiliary surfaces are the derivatives they claim (FD check at a benign point) | finite differences | **PINNED**: dzpV 1.2e-7 (FD-limited), dzpW/dzW ≤ 2.3e-10 |
| 22 | gate 1: §4 identities' node rows close to the interior floor on designed kernels at ρ = a | log-graded quadrature | **PASSED 2026-08-26**: node×node V 5.7e-11-of-max, W 7.4e-14; interior pairs ≤ 1.6e-19 (V) / 2.9e-16 (W). The 1.29-of-max node defect is DEAD on designed kernels — kernels, radius rule and corner bookkeeping mutually consistent to machine class |
| 23 | gate 2 (first pass): designed cross tables alone | probe23 | **RUN**: blow-up unchanged — the defect is not only in the cross kernels |
| 25 | outer quadrature + image truncation | probe25 node cell | **RUN**: all corrections small; blow-up unchanged — eliminated |
| 26 | node-diagonal decomposition | probe26 | **RUN**: remainders EXONERATED at the node (k²-class, ~1e-2); self_aa ≡ mono contact diagonal; the defect reframed — see below |
| 27 | **the complete spelling**: cross M+SW+SQ+BT+designed corner; self + closed-form bnd WITH corners, graded axes | probe27 | **P1 PINNED**: designed corner c1·V(a) = 14538.62−15858.88j ≈ c_bb (14534−15859j, §3 equality to 3e-4) and 9.585× the shipped truncated content (probe14d's 9.58 recovered exactly). **P2 PASSED — GATE 2 PROPER**: split ≡ merged ≡ V ≡ V+S to the digit, mesh-STABLE g1→g2 (67.1789−53.7349j → 67.1773−53.7557j): the divergence is DEAD, continuity + AGARD slope emerge from the fill's own physics. P3 apparent 87 Ω miss = column-spelling mismatch (completed crossing vs shipped mono) — probe28 matches the columns |

| 28 | matched-Δ attempt: complete BOTH columns | probe28 | **RUN, and it teaches the mono lesson**: completing the mono contact column WRECKS a validated serve (71.59−49.25j → 46.90−961.47j) — the shipped contact serve's omission of end charges IS the #151 continuation model, engine-validated. The columns cannot be matched by completion; Δ(complete-crossing vs shipped-mono) = +67−54j stable |
| 29 | **the ε̃ = 1 adjudicator** | probe29 | **PASSED 0.002 %**: complete+merged at ε̃ = 1 = 17.5619−758.1617j vs the independent free-space 12 m-wire truth 17.5621−758.1493j (0.0124 Ω), through a corner of magnitude 204,345 telescoping cleanly. The complete composition is exact where truth is known |
| 30 | adjudicator 1a: does the ENGINE's junction current satisfy its own AGARD condition? | phase-0 captures ×1..×8, quadratic end-extrapolation (session 6) | **MEASURED 2026-08-26 — NO, grossly and divergently**: I(0⁺) stable ≈ 1.14−0.03j (= contact-mono base); I(0⁻) ANTIPHASE, ~√n divergent (−0.35+0.16j ×1 → −1.07+0.34j ×8); KCL deficit 1.55 → 2.23 A INTO the interface point; |I′₊/I′₋| sweeps 0.178 → 0.0098 THROUGH AGARD 0.0547 without settling. The engine's junction = two independent contact ends + point sink, not an AGARD junction |
| 31 | adjudicator 1b: momwire-complete's junction currents (probe27 solve + solution stash) | probe31, g1+g2 | **MEASURED — AGARD emerges unconstrained**: continuity exact (deficit ~2e-7), slope-ratio magnitude → AGARD (0.0450 g1 → 0.0532 g2 vs 0.0547), below-arm profile a smooth physical decay (1.19 A node → 0.089 A at −1.9 m). Above-side currents nearly AGREE with the engine (1.19∠−6.0° vs 1.14∠−1.3° per unit feed) — the whole disagreement is the below arm |
| 32 | adjudicator 2a: engine Δ → 0 as σ → ∞ (stub → stake ≡ fiction) | probe32, fresh engine runs σ = 0.05/0.5/5 | **MEASURED**: Δ −2.82−1.69j → −1.19−1.04j → −0.46−0.34j → −0.17−0.09j; eps 13 ≡ 81 at σ=5; stable under below-refinement |
| 33 | adjudicator 2b: momwire-complete along the same ladder (stub shortened to the transmitted ladder's 0.25 λ_m reach; engine re-run on the IDENTICAL decks) | probe33 | **MEASURED — the physical limit is honored**: momwire Δ +67.2−53.7j → +31.7−2.1j → +6.9−3.6j → +1.1−2.6j; the complete crossing collapses onto the shipped mono exactly where the fiction becomes physical, and the mono column tracks engine mono within ~1.5 % at every σ. Two evaluator SCOPE fixes en route (underflow-quiet rays; far-pair kill cap λ ≤ 60/s), re-pinned, nothing pinned changed |
| 34 | adjudicator 3: consistent-omission spelling zoo (engine-parity hunt) | probe34, g1/g2, cached blocks | **MEASURED — no omission spelling reproduces engine Δ**: M-only −2.40−6.64j (stable, engine-like R, Im off ×4); M+SW / B ≈ 0 (stable, stub invisible); A-class = −1000j truncation garbage. The engine's Δ is not expressible as a consistent Galerkin spelling |

**The final defect naming (probes 23–27): every "drop" spelling is
truncation-regularized.** At resolved quadrature the retained ∬f′f′V's
ln(a)-class content diverges with its balancing end/corner terms deleted
(designed-B t_ab[na,nb] flips sign class vs shipped). The only
quadrature-convergent node treatment is the COMPLETE field-form-equivalent
spelling — all by-parts ends and corners, all four families, one
convention (designed kernels, radius rule, graded-to-a quadrature).

## 7. Session-5 verdict [measured 2026-08-26]

**The near-interface kernel build is DONE and both gates are PASSED.**
Designed evaluation of the six transmitted surfaces exists, is pinned to
machine class everywhere including the corner (probe21), closes the
by-parts identities at the node to 5.7e-11 (gate 1, probe22), and the
complete spelling kills the merge/V divergence outright — split ≡ merged
≡ V ≡ V+S to the digit, mesh-stable, with continuity AND the AGARD slope
condition emerging from the fill's own physics (gate 2 proper, probe27).
The ε̃ = 1 collapse of the whole composition reproduces independent truth
to 0.002 % (probe29) — the arithmetic is right.

**The adjudication ran in session 6 (probes 30–34) and is COMPLETE —
momwire-complete wins it on all three instruments:**

1. **Junction currents (probes 30/31).** The engine's own printed
   currents violate its own AGARD condition, divergently: I(0⁻) is
   antiphase to I(0⁺) and grows ~√n under refinement, with a KCL
   deficit of 1.55 → 2.23 A vanishing INTO the interface point; the
   slope ratio sweeps through the AGARD value without settling. Its
   junction is two independent contact ends + a point-electrode sink.
   momwire-complete, with NO constraint rows, produces exact continuity
   and a slope-ratio magnitude converging onto AGARD — and the two
   solutions nearly agree on the above arm (1.19∠−6.0° vs 1.14∠−1.3°
   per unit feed). The disagreement is entirely the below arm.
2. **High-σ limit (probes 32/33).** Both conventions converge to the
   same physics exactly where the contact fiction becomes exact:
   engine Δ → 0 and momwire-complete Δ → 0 (+67.2−53.7j at soil A
   → +1.1−2.6j at σ = 5, deck-matched short stubs), with the mono
   columns agreeing within ~1.5 % at every σ. momwire's composition
   passes the convention-free physical anchor; the two solvers disagree
   only where the fiction is wrong.
3. **No engine-parity spelling exists (probe34).** Every consistent
   omission spelling at resolved quadrature is either Δ ≈ 0
   (stub-invisible) or Δ = −2.40−6.64j (M-only; wrong Im), and every
   inconsistent one is the −1000j truncation class. The engine's
   −2.82−1.69j is not a Galerkin object.

**Standing verdict: momwire ships the exact-EM COMPLETE spelling as the
crossing serve.** The engine's crossing print is a different experiment
(the #151 contact fiction on both wire-ends) and is documented as such —
never gated against (the house rule: never gate cross-formulation
agreement). Production integration is the next arc: knot-edge-at-z=0
basis, graded node cell, ×5 ladder + contact anchors (P3),
ANCHOR_ENVELOPE_OHM re-derivation from the adjudicated ground truth.
