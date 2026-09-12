# momwire#956 — the on-axis derivation: the W cross terms do not belong on a vertical pair

Session artifact, 2026-09-12 (Laptop-control). The unit Steve named on 09-12:
derive what `_crossing_fill._main_split` spells for an ON-AXIS above×below pair
against the field-form Galerkin integral −⟨f_m, E(f_n)⟩ of the same pair, and
find where the equality breaks. Haswell's record (`scratch/956-oracle/
MEASUREMENTS.md`) had narrowed the +2.1 Ω residual to that one term: 21 % off
at 0.86 m, 97 % next to the node, exact off-axis, kernel / contraction / oracle
all exonerated, corner and self completions exactly zero on every entry.

Nothing in `src/momwire` is touched. Probes: `probe1_wterms.py` (the identity),
`probe2_impedance.py` (patched solves vs NEC-5), `probe3_solve_blocks.py`
(block substitution + sensitivity), `probe4_converged.py` (refinement ladders),
`probe5_noncrossing.py` (the corrected spelling against momwire's own
transmitted-grid field form, no shared by-parts machinery).

## 0. The result in one paragraph

The sandwich's two W cross terms (`s_w1 = (F t̂z)_A W F′_B`, `s_w2 = F′_A W
(F t̂z)_B`) and the SW end term are the transmitted dyad's G_zx / G_zy content:
the z-directed potential driven by the source's **transverse** divergence,
∂x′J_x + ∂y′J_y = (1 − t̂z²) dI/dl on a straight wire. The fill spells that
divergence as the full arclength derivative F′, which is exact on a horizontal
wire (t̂z = 0) and **wrong on a vertical one**, where the transverse divergence
is identically zero. On every vertical(above) × vertical(below) pair the shipped
entry therefore exceeds the EFIE Galerkin entry by exactly `s_w1 + s_w2 + SW`,
a smooth k²-scale term that vanishes at ε̃ = 1 (W ≡ 0) — which is why every
ε̃ = 1 gate passed — and accumulates along the buried vertical conductor, which
is the rise-length scaling #956 measured. Masking the three terms by (1 − t̂z²)
of the F′-carrying member closes the residual:

| deck | NEC-5 (Richardson) | momwire shipped | Δ | momwire W-masked | Δ |
|---|---|---|---|---|---|
| #956 deck, 4 radials, hub 0.15 m | 78.080 + 45.974j | 75.870 + 40.559j | +2.21 + 5.42j | **78.154 + 46.445j** | **−0.07 − 0.47j** |
| crossing rod L = 0.30 m | 388.86 − 324.95j | 387.00 − 329.78j | +1.86 + 4.83j | 389.38 − 324.04j | −0.52 − 0.91j |
| crossing rod L = 0.60 m | 237.55 − 157.56j | 233.05 − 166.37j | +4.51 + 8.81j | 237.85 − 156.83j | −0.30 − 0.73j |
| crossing rod L = 1.20 m | 154.40 − 52.82j | 144.42 − 66.65j | +9.98 + 13.83j | 154.62 − 51.93j | −0.22 − 0.89j |

Soil A (13, 0.005), 7.1 MHz; momwire at the finest rung (its plateau), NEC-5
first-order Richardson from the last two rungs of a uniform ladder r = 1/2/4
(`probe4_converged.py`, logs `probe4_*.log`). The ~8 Ω/m through-the-origin
term is gone; what remains is −0.1 … −0.5 Ω and −0.5 … −0.9 Ω of X, inside the
NEC-5 side's own r = 2 → 4 step (0.1–0.4 Ω). The L = 0.15 m row is not quoted:
NEC-5's rungs there step −2.2 then −1.4 Ω (ratio 0.64, not first order), so its
extrapolation is not a number by the issue's own rule.

## 1. The derivation

Conventions as the fill documents them (`_near_interface._core`): every kernel
of the transmitted family is `2∫ (·) Ẽ J₀(λρ) λ dλ` on the same
Ṽ = 2λ e^{γ₋z′ − γ₊z}/(k₋²γ₊ + k₊²γ₋), with the bookkeeping
∂z ↔ −γ₊, ∂z′ ↔ +γ₋, W̃ = (γ₊ − γ₋)Ṽ, so ∂zW ↔ −γ₊W̃, ∂z′W ↔ +γ₋W̃,
∂z∂z′V ↔ −γ₊γ₋Ṽ. On an on-axis pair every node pair sits at the same
ρ_eff = a, so the algebra is exact per λ.

**The field form, vertical source × vertical test** (AGARD 7b, verified page
image): E_z^V = C₁(∂z² + k₊²)V_T, spectral coefficient γ₊² + k₊² = λ². And

    k²V − ∂zW − ∂z∂z′V  ↔  k² + γ₊(γ₊ − γ₋) + γ₊γ₋  =  k² + γ₊²  =  λ²

so, identically, (∂z² + k²)V = (k²V − ∂zW) − ∂z∂z′V. The first bracket is the
sandwich's own `s_zz` kernel. The second is the §4 identity of
`scratch/524-phase2/DERIVATION-NEAR-INTERFACE.md` (pinned by its probe 22):

    ∬ f_m f_n ∂z∂z′V = ∬ f′_m f′_n V − Σ_E σ f_m(E)∫f′_n V(E,·)
                       − Σ_E′ σ′ f_n(E′)∫f′_m V(·,E′) + ΣΣ σσ′ f_m(E) f_n(E′) V(E,E′)

Hence, with the code's own signs (BT = +σ f_m(E)∫F′_B V, SQ = +σ′ f_n(E′)∫F′_A V,
CORNER = −σσ′ c1 V(E,E′)):

    FIELD FORM (vertical × vertical) = s_zz + s_phi + BT + SQ + CORNER_all-end-pairs     (exact)

The shipped spelling is `s_u + s_zz + s_w1 + s_w2 + s_phi + BT + SW + SQ +
CORNER_in-plane`, so on a vertical × vertical pair (s_u = 0):

    shipped − field form = (s_w1 + s_w2 + SW) + (CORNER_in-plane − CORNER_all)

Spectral size of the W excess, writing a_m = ∫f_m e^{−γ₊z}, b_n = ∫f_n e^{γ₋z′},
E_m = [f_m e^{−γ₊z}]_ends (so a′_m = E_m + γ₊a_m, b′_n = E′_n − γ₋b_n):

    s_w1 + s_w2 + SW  ↔  (γ₊ − γ₋)² a_m b_n  +  (γ₊ − γ₋) E_m b_n

i.e. a bulk term ∬ f_m f_n (−∂zW − ∂z′W), smooth and k²-scale (at large λ
(γ₊−γ₋)² ≈ (k₋²−k₊²)²/4λ²), plus an end residue Σ_E σ f_m(E)∫f_n W(E,·) that
lives only on bases with a value at an end (the node tents). Both are
identically zero at ε̃ = 1.

**Where the W terms are right.** Horizontal source (x̂) × vertical test: the
field form is C₁∂x′∂z′V → by parts on the wire, −∬ f_m f′_n ∂z′V ↔ −γ₋; the
sandwich gives s_w1 + s_phi ↔ (γ₊ − γ₋) − γ₊ = −γ₋. Exact — and its end
terms close with BT + SW + SQ + CORNER_all exactly as above. The symmetric
case (horizontal test × vertical source) closes with s_w2 + s_phi ↔ γ₊. So the
three W terms are exactly Michalski's G_zx, G_zy (and their Galerkin
transposes), which act on the transverse divergence of J — (1 − t̂z²) F′ on a
straight wire — and never on a vertical current. The fill's F′ is the right
object for the potential term `s_phi` (full charge) and the wrong one for the
W terms.

**Why no gate saw it.** W ≡ 0 at ε̃ = 1, so the collapse gates (probe 29,
21d) are blind to it. Probe 22 checks the §4 by-parts identities, which hold
— they are about ∂z∂z′V and ∂z′W, not about which terms belong in the field.
momwire#813's derivation (b) measured that `s_w1 + SW` equals the direct form
built from the ∂z′W table (true: it is the by-parts of −∬ f_m f_n ∂z′W) and
concluded SW must stay; that identity is correct and the premise — that a
∂z′W term belongs in the vertical–vertical coupling at all — was never
tested against (7b). Every field-form comparison before Haswell's was on a
non-crossing deck through the transmitted grid, where the sandwich is not in
the path.

## 2. The measurements

`probe1_wterms.py`, the #956 deck (248 segments, 26 above / 222 below,
n_basis 255), the fill's own axes and designed tables:

- G1–G3: my term-by-term rebuild of `_main_sandwich` and `_ends_and_corner`
  equals the module's to 1e-16 / 2e-17, and main + ends = `cross_complete_block`.
- D1, pure vertical × vertical block (27 above × 8 rise bases):
  `shipped − (s_zz + s_phi + BT + SQ + CORNER_all) == s_w1 + s_w2 + SW + (C_in − C_all)`
  to **3.6e-14**. The two field-form spellings, by parts vs the direct
  kernel ∬ f f (k²V − ∂zW − ∂z∂z′V), agree to 1e-5 … 1e-7 away from the node
  and 1.4e-3 on the pair touching it (the ln(a)-class quadrature).
- D2: Haswell's entries reproduce (|Z| 1.4649e+02 and 1.1629e-01), and my
  direct field form equals his independent transmitted-grid contraction to
  6e-5 / 9e-5 (his grid accuracy; his (a) carries the Z sign, mine the block's).
- The W excess per entry: |s_w1 + s_w2 + SW| ≤ 0.56 (ten of the 216 live
  entries above 0.1), 29 % of the 239×222 entry Haswell quoted as 21–35 %.

**Departure (C), the omitted corner.** On 228×220 (node tent × hub-end rise
wing) the whole 97 % is `C_in − C_all` = 1.43e+02: the code emits the
by-parts corner −σσ′c1V(E,E′) only for end pairs BOTH in the plane, and this
pair is (node, hub). The self completions' `_bnd_and_corner` emits it for
every end pair, so the omission is specific to the cross block. It is real in
the matrix and **exactly null in the solve** (probe3: Z bit-identical with
it restored): the perturbation is const × Σ_hub-wings σ_b f_b(hub) I_b on the
node row and a uniform shift on the five hub-wing rows, both annihilated by
KCL at the hub. Recorded so the next reader does not chase it; not a fix.

`probe3_solve_blocks.py`, constant-block substitution (`solve_with`, the
harness Haswell gated bit-for-bit):

    shipped block                    Z = 75.8482 + 40.4523j   (the #956 literal)
    W terms masked, all entries      Z = 78.1321 + 46.3377j
    W terms masked, pure VV only     Z = 78.1321 + 46.3377j   (same: dW lives only there)
    corner restored (C_all)          Z = 75.8482 + 40.4523j   (null, see above)

and the patched-path blocks of `probe2_impedance.py` equal these to 4e-17.
Per-column sensitivity: every rise basis moves R by +0.03 … +0.6 Ω, all in the
same direction — a distributed term, not a node term.

`probe2_impedance.py e1`, NEC-5 run locally on the exported shipped-mesh deck:
77.8050 + 44.4680j; momwire shipped 75.8482 + 40.4523j (Δ +1.96 + 4.02j);
W-masked 78.1321 + 46.3377j (Δ −0.33 − 1.87j at that mesh; converged table in
§0).

`probe5_noncrossing.py`, the independent check: probe20's NON-crossing deck,
where the solver's own cross quadrant IS the transmitted-grid field form
(3.5e-10). The crossing fill's sandwich on that deck's axes: shipped departs
from the grid by **1.4e-2** on the vertical × vertical block (1–3 % per
entry), the W-masked spelling agrees to **1.2e-5** — the same 2e-5 the
off-axis wire shows for both, i.e. the grid's own accuracy. No by-parts
identity is shared between the two sides of that comparison.

## 3. What this does and does not settle

Settled:
- The named term (`_main_split` on on-axis pairs) is the W cross terms spelled
  with the full charge on a vertical member. The residual closes to the
  NEC-5 side's own extrapolation step on the #956 deck and on the crossing
  rod at three lengths, in R and in X.
- The rise-length scaling, the radial-count invariance (off-axis exact), the
  "flat under refinement" signature (the term is smooth) and the ε̃ = 1
  blindness are all consequences of the same spelling.
- Departure (C) exists and is solution-null on a Galerkin crossing deck.

Not settled here:
- The wholly buried vertical rod's −1.20 %-of-R invariant (mw#956 rod ladder)
  is a below→below question; no W term is in that path and nothing here
  touches it.
- Razor's path-tested rows (`path_test_axis`) and the reversed block's SW
  placement (`SW_BY_PARTS`) carry the same F′ and will need the same mask;
  untested here. The sinusoidal-Galerkin serve calls the same
  `cross_complete_block_split` and inherits the fix.
- Tilted members: the mask makes the W terms ∝ (1 − t̂z²) on a leaning wire.
  momwire#936's 0.70 pp lean drift, which scales as sin²α, is exactly the
  signature such a term would leave; prediction, not measurement.
- The same-medium families are not examined. Their W-analog question is a
  separate derivation (DERIVATION-SAME-MEDIUM.md §2 has the identities).

## 4. Footprint of the fix (for the PR, not done here)

- `_main_sandwich`: `s_w1` with `FdB_w * (1 − tzB²)`, `s_w2` with
  `FdA_w * (1 − tzA²)`.
- `_row_weights` / `_sandwich_dense` / the ACA far path in `_main_split`: a
  fifth row-weight `F′·w·(1 − t̂z²)` and the two W products on it.
- `_ends_and_corner`, `_ends_and_corner_reversed`: SW scaled by (1 − t̂z²) of
  the wire owning the end — `axis_data`'s ends table needs the tangent
  (extend the tuple; every consumer unpacks positionally or by index).
- `path_test_axis`: the razor rows' `Fd` weight, same rule.
- Gates that will move: every crossing-deck anchor (`test_crossing_serve_524`,
  the FAN_SOIL_A_N2 / G-674 crossgates, the P3 rise anchors, the
  ANCHOR_ENVELOPE_OHM derivation) by the amounts in §0 — re-pinning against
  NEC-5 is now a measurement, not an adjudication. The ε̃ = 1 gates do not
  move. antennaknobs' published buried-radial numbers (case study, validation
  page, #956's own literal) move with the release.

## 5. Traps met on the way

- Matching wire ends by POINT hands every hub end the tangent of whichever
  wire matched last: five wires share the hub. The first run of probe2 did
  that, stripped the radials' legitimate SW terms with the rise's, and read
  R = 111.65 — a +36 Ω move that was the harness. `end_tz` now replicates
  `axis_data`'s end loop in wire order.
- `_FORCE_DENSE` is read at import; patch the module attribute, not the env.
- Haswell's field-form (a) values carry the Z sign (Z −= block); the block
  itself is the negative. A "rel 2.000e+00" is agreement.
- `gh` auto-merge arming was blocked by the session's permission classifier
  tonight; PRs #1431 / #1433 are read and approved, unarmed.
