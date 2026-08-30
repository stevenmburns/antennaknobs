# momwire#524 phase 2 — the same-medium families' by-parts structure

Session artifact, 2026-08-26 (session 4). Extends
`scratch/567-phase0/FORMULATION.md` §5–§6 from the transmitted family to
the two SAME-MEDIUM families (above/above, below/below), so that the node
terms of all four blocks of the crossing deck can be spelled consistently
under the merged crossing dof (PLAN.md §NEXT EXPERIMENTS item 1).

Status marks as in FORMULATION.md: **[derived]** = algebra on this page,
**[pinned]** = verified numerically by a probe, **[open]** = awaiting one.

## 1. What the shipped self blocks actually are [derived from src]

`_compute_Z_operator_buried` composes each same-medium block from THREE
pieces (bspline.py:4461–4519):

    Z_aa = MP_direct(k₊, ε₀)  −  C₂ · MP_image(k₊, ε₀)   −  R_aa(field form)
    Z_bb = MP_direct(k₋, ε̃ε₀) −  A_m · MP_image(k₋, ε̃ε₀) −  R_bb(field form)

with A_m = (1−ε̃)/(1+ε̃) = −C₂, and R_** the Sommerfeld REMAINDER blocks
(`remainder_field_proj` / `remainder_field_proj_below`), i.e. full
reflected minus the closed-form image.

The two MP pieces are `_assemble_Z` / `_image_Z_weighted` shapes: the Φ
term is pure `f_m′ G f_n′ / (jωε)` — **no endpoint terms** (FORMULATION
§6). The remainder blocks are pointwise field projections of dipole
fields, which carry every endpoint effect implicitly and exactly (the
dipole charges telescope to line charge −f′/jω plus endpoint charges).

**Consequence [derived]: the same-medium families need NO new contour
tables.** Their entire by-parts deficit lives on the two CLOSED-FORM
kernels (direct e^{−jkR}/R and its weighted image), because the only
piece assembled in MP form is direct + image. The reflected family's
"W-analog / dynamic node terms" (session-3 suspect) are already inside
the exact remainder blocks — there is nothing to add there.

## 2. The by-parts identity and its signs [derived]

For one scalar kernel G(z, z′) and vertical test/source bases f_m, f_n
(d/dl = ∂z on both arms of this deck), double integration by parts gives
the exact identity

    ∬ f_m f_n ∂z∂z′G  =  ∬ f_m′ f_n′ G
                        − Σ_E  σ  f_m(E)  ∫ f_n′ G(E, ·)      (test end)
                        − Σ_E′ σ′ f_n(E′) ∫ f_m′ G(·, E′)     (source end)
                        + Σ Σ  σσ′ f_m(E) f_n(E′) G(E, E′)     (corner)

σ = +1 at a support end where the tangent points OUT of the wire (far
end), −1 where it points in (near end). Equivalently, in charge form:
∇·(f 1_[lo,hi] t̂) = f′ interior **minus** σ f(E) δ_E at the ends, so the
endpoint charge is +σ f(E)/(jω) against the line charge −f′/(jω) — the
single-end products pick up a RELATIVE MINUS against the f′f′ term and
the corner picks up a relative plus. (The naive "all charge products
positive" reading drops the δ-coefficient sign and is exactly the
probe12 sign trap: it predicts pairwise cancellation where the true
structure ADDS.)

So, per family, with β the family's own Φ prefactor (the constant
multiplying its ∬f′f′G in the shipped assembly, sign included):

    bnd[m,n] = β · [ − Σ_E  σ  f_m(E) ∫ f_n′ G(E,·)
                     − Σ_E′ σ′ f_n(E′) ∫ f_m′ G(·,E′)
                     + Σ Σ  σσ′ f_m(E) f_n(E′) G(E,E′) ]

and the EXACT block is  MP_block + bnd.  For the image piece the same
expansion holds verbatim with G_img(z, z′) = G(|r − mirror(r′)|): the
ends stay the ORIGINAL ends with the original σ′, only the kernel is
evaluated at mirrored source points (∂z∂z′ flips sign for a z+z′ kernel,
but the ∂z′ chain-rule sign flips with it — net: identical structure).

The exact same-medium blocks are therefore

    Z_aa^exact = Z_aa^shipped + β₊  bnd(G_{k₊})      − β₊ᶦ bnd(G_{k₊}^img)
    Z_bb^exact = Z_bb^shipped + β₋  bnd(G_{k₋})      − β₋ᶦ bnd(G_{k₋}^img)

with the minus on the image pieces inherited from the fill's global
`Z −= image` convention, and β₋, β₋ᶦ carrying the 1/ε̃ of the medium and
the A_m weight respectively. All four β are pinned numerically (probe14)
by least-squares against the shipped MP pieces on well-separated entries
— the probe5 way — rather than trusted from this page.

## 3. Support: on this deck the terms are node-only [derived]

Every basis of the crossing deck vanishes at its own support ends except
the two value-1 node tents (below nb, above na). Free outer ends (z=−2,
z=+10) carry no basis; interior tents vanish; the feed is interior. So

  * bnd_bb touches only row/col nb (+ corner [nb,nb]),
  * bnd_aa touches only row/col na (+ corner [na,na]),

with σ_b = +1 (below arm ENDS at the node) and σ_a = −1 (above arm
STARTS there).

Because the node sits ON the mirror plane, the mirrored node end is the
node itself and mirroring preserves distances to any point ON the plane:
each family's image end-pieces coincide GEOMETRICALLY with its direct
end-pieces. The static net weights are

    above:  (1 − C₂)/ε₀        = 2/(ε̃+1) /ε₀
    below:  (1 − A_m)/(ε̃ε₀)   = 2/(ε̃+1) /ε₀

— equal, and equal to the transmitted kernel's static node factor. This
is the static-consistent picture probe12 measured (its T/S columns ≡
cross SQ/BT content); what the same-medium spelling adds beyond it is the
DYNAMIC part, carried per-family by e^{−jk₊R} vs e^{−jk₋R} vs the
transmitted contour — i.e. precisely the "beyond the static-consistent V
picture" content session 3 predicted, now in closed form for the
same-medium half.

## 4. Corners telescope under merge; spell them consistently [derived]

Under the merged crossing dof the node's corner content is

    [nb,nb]: σ_b² bnd-corner(bb)  +  [na,na]: σ_a² bnd-corner(aa)
    + [na,nb] + [nb,na]: σ_aσ_b × transmitted corners (probe5's residual)

= (+1)·c_bb + (+1)·c_aa − 2·c_cross. All four are the SAME coincident
point pair (the node against itself at wire-radius range), and §3 says
their static parts are all equal ⇒ **the O(1/a) corner singularities
cancel exactly under merge; only the finite dynamic difference
survives.** Two internally-consistent spellings follow:

  (i) **no corners anywhere**: MP-A-no-corner cross blocks (probe8's
      M+SW+SQ+BT — mp_cross never had the corner) + self bnd WITHOUT
      corners. Drops the same static content from all four blocks;
      neglects the finite dynamic corner residue.
 (ii) **corners everywhere**: shipped field-form cross blocks (whose
      corner content probe5 MEASURED as the [na,nb] residual —
      1512.61−1658.55j at ×1) + self bnd WITH closed-form corners
      G(a) = e^{−jka}/a.

Mixing them (self corners against corner-less cross, or vice versa)
leaves uncancelled O(1/a) static garbage — the probe12 blow-up class.
Both consistent spellings are scored; their difference measures the
dynamic corner residue plus any quadrature-convention mismatch between
the closed-form corners and the shipped cross block's implicit ones.

## 5. Probe ledger

| # | claim | instrument | status |
|---|---|---|---|
| 14a | shipped MP self pieces ≡ α·S_A + β·S_Φ quadrature shapes, all four (direct/image × above/below), with β the family constants of §2 | lstsq on separated entries | **PINNED 2026-08-26**: above β/expected = 1.000000 (resid 3e-10, n=110) for BOTH direct and C₂-weighted image — the convention is analytic; below corroborated at 0.992−0.053j / 0.959+0.064j on the only 2 separated pairs the 4-seg arm affords (naive-Gauss-vs-analytic-moment error); saved matrices use the analytic β |
| 14b | the §2 identity: P-quad ≡ f′f′-quad + bnd, per family, node column | closed-form ∂z∂z′G vs pieces, separated entries | **PINNED**: node-column residual drops 3.6/3.7/5.8/10.2-of-max → 1e-8/4e-12/5e-10/1e-12 (bb_dir/aa_dir/bb_img/aa_img at ×1; same at ×3) — the −,−,+ sign structure confirmed on all four families |
| 14c | node-only support (§3): ends tables reduce to the node with σ_b=+1, σ_a=−1 | ends tables | **PINNED** (plus a harmless 1e-16-noise end row at the far tip) |
| 14d | §3 static consistency + corner equality | closed forms | **PINNED**: (1−A_m)/ε̃ε₀ ≡ (1−C₂)/ε₀ to machine; c_bb = 14528.9−15860.7j vs c_aa = 14539.2−15858.2j (mesh-independent, equal to 0.07 %). **Discovery**: probe5's measured cross-corner residual (1512.61−1658.55j) is 9.58× smaller at the SAME complex phase — a real scale factor ⇒ the shipped cross block's implicit corner is quadrature-TRUNCATED (its Gauss nodes never come within ~a of the node), not a physics factor |
| 15 | Δ with the exact spelling, merged, both consistent corner spellings, ×1 | probe15 grid | **RUN 2026-08-26, REFUTED as the fix**: the consistent no-corner spelling Δ = +80.47−54.62j (dist 98.8 from engine −2.33−0.71j); corner-mix controls blow up exactly as §4 predicts (−1021j, −923j) — sign wiring validated, spelling fails |

## 6. Verdict [measured 2026-08-26]

**The derivation stands and the approach dies.** The by-parts structure
of the same-medium families is now derived, sign-pinned to 1e-8-of-max
and better on all four kernels (probe14), and the corner-consistency
predictions of §4 are confirmed by the blow-up controls — but no spelling
of the node terms lands the engine's crossing signal, because the
two-value-1-tents node is **quadrature-unstable by construction**: the
node entries are O(100)-ohm levers on Z_in, the coincident-end kernels
carry 1/a-scale content that Gauss segment quadrature truncates ~10×
(measured, ledger 14d), and the physics signal is 3 Ω. Analytic self
moments, Gauss cross tables and closed-form endpoint terms can never be
made mutually consistent at that node to the required 1 %.

This closes the third and last bookkeeping axis (after the cross-block
charge axis, probe8, and the lumped node correction, probe13).

**probe17 (measured)**: the straddling basis does NOT dissolve the swamp
either. The crossing deck as ONE polyline wire (knot edge at z = 0,
media per segment, per-edge subset fill) solves to −76.35−1085.23j —
numerically the two-wire deck + continuity row (probe2 S1:
−75.4−1089.2j), and ≈ the merged naive fill. Mechanism: the per-class
fill CUTS every straddling basis at z = 0, and the field-form cross
blocks then carry the cut sub-basis's fictitious end charge implicitly —
the same coincident-end content, unspelled. Basis restructuring relocates
the bookkeeping; it does not remove the near-interface quadrature
inconsistency. (Useful validation: merge-hook ≡ V-row ≡ single-wire, one
instrument, three spellings.)

Together with the Δ ladder's DIVERGENCE under uniform refinement
(+0.73 → +2.25 while the engine descends, PLAN.md session 3), the
evidence names the defect class: the near-interface entries of the four
families are mutually inconsistent at practical quadrature (analytic
within-arm moments vs Gauss cross tables vs grid-edge remainders), and
no bookkeeping on top can be consistent to the 3 Ω signal. The two
production-shaped exits: (α) grade the mesh toward the interface
(NEC-4's junction prescription), and/or (β) a designed near-interface
cell: one quadrature convention (log-refined toward the node) for ALL
four families' entries whose supports touch z = 0, with the transmitted
z′ = 0 edge designed rather than clamped.

**probe18 (measured)**: exit (α) is dead for the naive/field-form fill —
grading h_node 40× (0.5 → 0.0125 m) moves the straddle Δ only
−48.5−934.7j → −43.0−926.6j. The near-interface garbage is self-similar
under refinement, as a log/1/R corner content must be: refining brings
the Gauss nodes proportionally closer to the singularity and regenerates
it.

**probe19/probe20 (measured — the arc's sharpest physics statement)**:
on the graded mesh with the SANE cross spelling (MP-B), the un-merged
solve CONVERGES — to Δ ≈ 0 (+0.065+0.033j → +0.100−0.060j): with the
interface resolved and no continuity imposed, momwire's fill says the
stub is INVISIBLE. Every mechanism that then forces current through the
node — merge, V row (measured ≡ merge to the digit, even in blow-up),
V+S — EXPLODES, and explodes worse as the interface tents shrink
(−462−136j → −258−948j). S alone constrains nothing (Δ → 0 again).

**Final verdict of session 4**: the engine's crossing signal
(−2.8−1.7j) is generated entirely by its interface-junction treatment,
and momwire prices interface-crossing current with the only unvalidated
numbers in the matrix: the transmitted-family tables at z, z′ → 0,
ρ → 0 — the phase-0 z′-CLAMP edge, where the contour provably cannot
converge (probe12) and where the phase-0 identity already showed the
1.29-of-max node discrepancy. No (spelling × mesh × constraint)
combination on the existing kernels can work around untrustworthy node
kernels. The load-bearing next build is the near-interface kernel
evaluation: designed corner asymptotics of {U_T, V_T, W_T, ∂zW_T}
(static 2/(1+ε̃)/R term + dynamic series) and the below-remainder's
R₁ → 0 edge. This document plus the probe14 bnd machinery is the
bookkeeping specification those kernels plug into.
