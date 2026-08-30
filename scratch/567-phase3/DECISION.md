# momwire#567 phase 3 — the arc-shape decision (on paper, before any build)

Session artifact, 2026-08-28. This is the restart note's FIRST TASK: with
the #524 phase-2 crossing serve on main and battle-hardened, re-derive the
#567 arc shape. The question as posed:

> does the contact become a served spelling via crossing/continuation
> physics (a below-side continuation carrying the spreading current — the
> phase-3 question), or is the original U1–U4 surface build (5→8 surfaces,
> drop spelling) still the path, now with the crossing toolkit for the
> residual?

Verdict up front: **neither, as literally posed. The U1–U4 surface build is
DEAD as a serve path (measured twice, on two independent kernel
generations), and the exact-EM crossing respelling of the contact node is
the WRONG EXPERIMENT for the detached class (adjudicated, and the banked
numbers put it ~47 Ω away in the wrong direction). The live path is a
third shape both parents point at: keep the #151 contact serve exactly as
shipped, keep the continuation-consistent M-only cross spelling, and add
the one physical object every measurement says is missing — the below-side
GHOST CONTINUATION of the contact current (prescribed, parameter-free,
carrying I(0) into the soil with the soil propagation decay), coupled to
the DETACHED radials only.** Phase 3 = score that spelling against both
anchors with a blind transfer, exactly as phase 0 scored A/B/C.

## 1. Why the U1–U4 surface build is dead (the measured case)

The original A-3 plan (surfaces 5→8, MP assembly, drop-endpoint spelling)
was conceived as the repair for the 46.6/141.5 Ω field-form misses. Every
piece of it has since been either built in a better form or refuted:

- The MP machinery EXISTS and is production code: the designed
  near-interface evaluator (`_near_interface.py` + C++ twin, z′=0 exact by
  design, corner asymptotics pinned) plus `_crossing_fill.cross_complete_
  block` supersede the planned grid-table build. No 5→8 surface
  tabulation is needed for anything phase 3 does — the crossing fill
  evaluates designed-DIRECT, no grids.
- The drop spelling's best case was re-measured on those designed kernels
  (probe35, 2026-08-27) and reproduces phase-0's B(drop) TO THE DIGIT:
  lone 103.8272−75.5958j (miss 12.907), fan 105.2020−78.7769j (miss
  17.155). Same residual on two independent kernel implementations ⇒ the
  residual is PHYSICS (the spreading soil current), not spelling,
  quadrature, or tabulation. A surface build cannot buy those ohms.
- Session-5's defect-class naming closed the whole spelling axis: every
  "drop" spelling is truncation-regularized; the only quadrature-convergent
  node treatment is the complete spelling — and probe35 v1 measured the
  complete spelling WRECKING the lone anchor (probe28's mono lesson in the
  cross block: completion belongs only where a real below-conductor
  exists).

So: no U1–U4. The surfaces that were its point already ship.

## 2. Why the exact-EM crossing respelling is the wrong experiment here

Tempting shape: "the contact node becomes a crossing node whose below-arm
is the spreading current" — respell the anchor decks as crossing decks
with a real appended soil stub. Refuted on the banked record:

- The adjudication (probes 30–34) established that the exact-EM crossing
  junction and the engine's contact treatment are DIFFERENT EXPERIMENTS:
  momwire drives the full base current through the node into the real
  stub; the engine sheds it into a point-sink contact fiction. They agree
  only at high σ where the fiction becomes exact.
- The anchors for #567 are engine prints of the CONTACT-FICTION
  convention — and they are legitimate gates precisely because momwire's
  shipped #151 contact serve is the same fiction family (mono tracks the
  engine mono ladder within ~1.5 % across the whole σ ladder, probe33).
  An exact-EM stub respelling abandons that shared convention: momwire
  mono 71.56−49.43j → crossing-with-2 m-stub 138.77−102.99j (Δ ≈
  +67−54j), while the engine's own stub Δ is −2.8−1.7j. Chasing
  92.130−70.141j with the exact-EM junction starts ~47 Ω away in the
  wrong direction and re-derives a solved adjudication.
- probe28's lesson stands: touching the validated mono contact column
  (completing it, or re-basing it as an exact-EM junction) wrecks a
  validated serve. The mono column is NOT the deficit — probe35's misses
  are coupling-shaped, not self-shaped (see §3).
- The exact-EM crossing serve already OWNS the bonded/rise class (its
  ε̃=1-exact adjudication, probe37). It stays what it is: the served
  respelling for users who bond the screen. It is not the detached serve.

## 3. The deficit is coupling, and it is coherent across decks

From the continuation-consistent M-only spelling, the move still needed to
reach each anchor:

    lone:  92.130−70.141j − (103.827−75.596j) = −11.70 + 5.45j Ω
    fan:   90.051−70.731j − (105.202−78.777j) = −15.15 + 8.05j Ω

Same complex direction, magnitude growing with the radial system — the
signature of a real coupling mechanism between the contact node and the
detached radials, NOT of any endpoint scalar (phase 0 killed the scalar
axis: w*(lone) blind-transferred to the fan is WORSE than plain drop).
The refusal prose has named this from the start: the contact current
SPREADING into the lower medium — a real soil current with no conductor
in the deck. What the deck is missing is not a spelling; it is a SOURCE.

## 4. The proposed spelling: the ghost continuation (coupling-only)

Keep everything that is validated; add the missing source:

- **Above side / mono column: untouched.** The #151 contact serve is the
  convention the anchors share; it already carries the fiction's
  above-side bookkeeping (that is why mono agrees with the engine).
- **Cross block: M-only** (all end terms omitted) — the
  continuation-CONSISTENT bookkeeping: dropping the endpoint charge is
  exactly the statement that I(0) does not terminate. 72–88 % of the
  field-form miss closes here already.
- **NEW: the ghost continuation.** A prescribed (non-dof) current below
  the contact node: I_g(z) = I(0) · e^{−jk₋|z|} on the monopole axis,
  z < 0, radius = the monopole's, truncated converged (several soil decay
  lengths; 1/Im(k₋) ≈ 4.2 m at soil A). τ = 1 is NOT a choice: the house
  design doc (`docs/design/contact-over-finite-ground.md` §2.2/§2.3(a)/
  §4.1) already fixes the continuation coefficient at exactly 1 by charge
  conservation — any c ≠ 1 leaves (1−c)·I₀ as a point charge at the node
  and "should not be built". NO free parameter. Its Galerkin coupling to the DETACHED
  below bases (radial tents) is added to the contact basis's row and
  column (symmetric ⇒ reciprocity preserved); its charge (∂I/∂z ≠ 0)
  rides the same tent bookkeeping. Below/below family kernels only — the
  ghost lives in the soil with the radials; the mature #553 U2 machinery
  evaluates it, with the designed evaluator available for the z′→0 head.
- **Deliberately OMITTED: ghost↔above coupling and the ghost self term.**
  Not caution — bookkeeping: #151's image treatment IS the fiction's
  above-side account (validated against the engine mono ladder); adding
  the ghost's above-side field would double-count it. The ghost exists
  only to illuminate what #151, an above-only construct, cannot see: the
  detached conductors in the soil.

Why this can be decided on paper as THE candidate: it is the unique
spelling that (a) preserves the anchor-shared convention (§2), (b) is
consistent with the M-only bookkeeping (§1), (c) has the measured shape of
the deficit (§3), and (d) is parameter-free, so the fan blind-transfer is
a genuine adjudication, not a fit.

Known risks, named now:

- R1. The needed move's SIGN is not armchair-derivable; the ghost may
  move the anchors the wrong way. That is probe P3.1's first number.
- R2. Fan hub sits ON the ghost axis (0,0,−0.15): touching-pair/ρ→0
  entries. The designed ρ_eff = √(ρ²+a²) rule and the same-edge moment
  machinery cover this class; watch it explicitly.
- R3. ε̃=1 behaviour: the ghost does not vanish at ε̃=1 (a fiction, like
  #151 itself, whose contact row already reads 2.484 non-collapsed).
  G-U5-3's three-band tripwire may read "moved but NOT fixed" — its
  semantics-break is already on record; the lift criterion moves to the
  anchor gates (G-U5-12 + deck-route pair, self-arming).
- R4. Decay-model crudeness (exponential line vs true spreading volume
  current). Mitigation is the sensitivity axis in P3.2: if the anchors
  select the physical decay (best at ×1.0 of 1/Im k₋, degrading at ×0.5
  and ×2), the model is corroborated, not fitted.

## 5. Phase-3 probe ladder (scratch work, no production code)

Harness = probe35's (canonical `contact_deck`/`fan_deck` from
test_buried_serve_553 — feed arclength 4.3333, NEVER improvised — seeded
media, `capture(t_ab=…)` swap). Ghost implemented as a prescribed-current
contraction over a finely-meshed ghost wire's fill columns (tents
reconstruct e^{−jk₋|z|}; charge bookkeeping comes free).

- **P3.0** Regression: reproduce probe35's M-only numbers through today's
  main (103.8272−75.5958j / 105.2020−78.7769j). Guards against drift.
- **P3.1** Lone anchor + ghost: Z vs 92.130−70.141j. Truncation-depth
  ladder (2/4/8 decay lengths) and ghost-mesh refinement must converge.
  GO/no-go on sign and magnitude of the move.
- **P3.2** Sensitivity: decay ×{0.5, 1, 2}. The anchors should SELECT
  ×1.0 or the decay model is wrong. (τ is doctrine-fixed at 1; a τ≠1
  point gets at most one for-the-record falsification line.)
- **P3.3** Fan blind transfer (the kill test): same spelling, no refit,
  vs 90.051−70.731j. Both-anchors envelope re-derives
  `ANCHOR_ENVELOPE_OHM` (currently 18.0 = the no-ghost landscape).
- **P3.4** Trend anchor: the AK catalog `detached` variant vs the banked
  NEC-5 density ladder (49.763+19.772j → 50.585+24.000j,
  scratch/buried-quality-post/results.json) — a same-class,
  catalog-scale check the 2026 anchors never had.
- **P3.5** High-σ ladder: as σ → ∞ the fiction becomes exact and the
  ghost's marginal effect must shrink (engine Δ → 0 precedent,
  probe32/33 pattern).

GO = one parameter-free spelling inside a defensible envelope of BOTH
anchors with the sensitivity axis selecting the physics. Then the build
(delegated, stacked if >1 unit): production ghost-coupling in the buried
fill for `contact+buried` decks, refusal lift in its three copies,
envelope re-derivation, G-U5-12 arming + slow marks, G-U5-3 semantics
note. NO-GO = the class stays refused with the measurement appended to
the refusal prose and the rise respelling remains the served alternative;
the electrode-load shortcut (probe11's 56−23j Thevenin) is the recorded
fallback axis — self-shaped, so it is NOT expected to close a
coupling-shaped deficit; it gets one line of measurement only if P3.1
fails on sign.

## 6. Code entry points (explorer-verified, 2026-08-28)

- Refusal raise: `_medium_spec.wire_media` (`_medium_spec.py:262-273`) —
  any BELOW wire + any `contact_ends` not in `crossing_ends`. The ONLY
  escape is `crossing_ends` membership (junction-derived,
  `bspline.py:1267-1287`). Routing gate `_crossing_junctions()`
  (`bspline.py:1289-1359`) requires the junction to span both media
  (`len(sides) == 2`), so a contact node with no below member never
  reaches the crossing branch.
- The crossing branch: `bspline.py:4645-4666` — `_crossing_fill.
  cross_complete_block_split` (designed MP, ends+corner, no grid);
  non-crossing buried decks keep the field-form transmitted-grid cross
  block (`bspline.py:4667-4694`).
- `_crossing_fill.axis_data` ends table already admits CONTACT tents
  ("value-1 junction/contact tents"), the corner fires only for
  in-plane×in-plane end PAIRS, and `six_point` takes z=0/z′=0 exactly —
  the machinery is contact-ready; the gate and the physics are what
  stand between.
- Maintainer position in-src (`bspline.py:4563-4564`): the refusal
  "still stands while P3 re-scores its anchors under the same
  machinery" — probe35 WAS that re-scoring; this decision is its sequel.
- Prototype harness: `scratch/524-phase2/proto/probe35_contact_anchors.py`
  (canonical decks from `test_buried_serve_553`, `probe9_sense.capture`,
  `cross_complete_block` with ends-stripped axes = M-only).
- Continuation doctrine: `docs/design/contact-over-finite-ground.md`
  §2.2/§2.3/§4.1 (coefficient 1 by charge conservation; image
  coefficient ≠ continuation coefficient).

## 6b. Round-1 results (measured 2026-08-28, probes P3.0–P3.5,
## results/*.json — the line ghost is adjudicated)

- **P3.0 regression**: M-only through today's main reproduces probe35 to
  0.0001 Ω on BOTH decks. Harness sound.
- **Trap found**: `_wire_endpoint_status` skips BELOW wires entirely, so
  a seeded below wire standing its end in the plane gets NO value-1 top
  tent (first run measured g0 = 0); the aux ghost needs a one-member
  junction at its top to keep the tent.
- **P3.1 lone**: 103.83−75.60j → **96.0971−76.9498j, miss 12.907 →
  7.880 Ω**. Truncation-converged (L = 4.2 vs 8.4 m: 0.16 Ω),
  ghost-mesh-converged (<0.005 Ω over d1→d3, fit_rel 5.8e-2 → 3.3e-2 —
  the coupling doesn't care), and the decay axis has its MINIMUM AT THE
  PHYSICAL k_m (×0.5 → 10.50, ×1 → 7.88, ×2 → 8.21): the anchor selects
  the soil propagation constant. R4 partially retired.
- **Ghost self term** (recorded, doctrine omits): +self blows up
  (600.6−158.9j at L=4.2, 310.4−78.6j at 8.4 — L-unstable garbage).
  Doctrine corroborated by measurement.
- **P3.3 fan blind transfer**: 105.20−78.78j → 84.73−85.31j, miss
  17.155 → **15.516**. Better, NOT the phase-0 worse-than-drop kill —
  but weak, R overshoots below the anchor, and X moves the wrong way on
  BOTH decks (needed +5.45/+8.05j, ghost gives −1.35/−6.53j).
- **P3.4 decomposition**: hub dir-basis coupling cancels EXACTLY through
  the hub KCL row (probe35's cancellation, re-measured); fan near-ring
  coupling (reach ≤ 1.85 m) HURTS (miss 21.33) while the far ring
  helps; lone-deck benefit is distributed. The line ghost over-drives
  the near region — 4-fold on the fan. R2 confirmed as the live defect:
  the ANGULAR distribution is wrong, not amplitude or decay.
- **P3.5 β instrument**: a complex scale on the row closes EACH deck to
  0.001 Ω (lone β* = 1.3586−0.4996j, fan β* = 0.7732−0.4838j) — but
  β* does NOT transfer. Im(β*) nearly agrees (−0.50 vs −0.48); Re
  splits 1.76× — the near-ring strength again. No member of the
  interface-coefficient family {1, 2/(1+ε̃), (ε̃−1)/(ε̃+1), 1/ε̃}
  matches either β*.

**ROUND-1 VERDICT: the vertical-line ghost (buried-rod model) is the
right physics FAMILY (right direction, decay selected, robust to every
numerical axis, transfers better-not-worse) but the wrong angular
distribution of the spreading current, and by the phase-0 blind-transfer
discipline it is NOT a serve spelling.** The refusal stands unchanged.

Round-2 candidate (derivation, not fitting — the only honest
continuation): the SPREADING ghost — replace the prescribed line current
with the point-electrode spreading solution of the lossy half-space
(hemispherical-class volume current; its below-side field family is
expressible on the designed kernels, whose z′ = 0 edge is exact by
design). Parameter-free; its lone/fan predictions are then genuine blind
scores because the geometry is derived, not chosen. Session-scale
derivation; NOT started here so it stays blind. Do NOT iterate discrete
leg geometries against the anchors — that is anchor-fitting, the exact
failure mode phase 0 named.

## 6c. Round-2 results (measured 2026-08-28, probe_r2_spread.py — the
## derived Born electrode adjudicated; the prescribed family exhausted)

The round-2 derived spelling: hemispherical solid-angle spreading (Gauss
in cosα × equal azimuths), charge-field Born profile (1+jk₋s)e^{−jk₋s}
per ray, derived soil partition τ_soil = ε̃/(ε̃+1) = 0.9612−0.0356j.
Zero anchor-informed knobs; harvested per leg-group through seeded
all-below aux decks (tilted buried wires verified served first).

- **The spread ghost is a NULL**: every ladder cell (n_α 3/4, n_φ 8/16,
  half-step rotation, L 4.2/8.4) lands within ~0.1 Ω of the M-only
  baseline (miss ~12.93–13.03 vs 12.907). Converged, and rotation-
  invariant.
- **Machinery certified TO THE DIGIT**: the round-1 spelling pushed
  through the round-2 harvester reproduces round 1's L=8.4 cell exactly
  (96.2251−76.8549j both). The null is physics, not a bug.
- **Mechanism, measured**: per-leg norms show no grazing-image collapse;
  the aligned grazing leg couples hugely (‖row‖ 62.3 vs 2–7 for the
  rest) and is simply DILUTED 8× by uniform azimuth; and the vertical
  control with the Born profile weakens round 1's move ~5× (the
  (1+jk₋s) factor phase-rotates the coupling toward cancellation).

**ROUND-2 VERDICT: the prescribed-source family is EXHAUSTED.** The rod
(round 1) has the right family and wrong angular distribution; the
derived electrode (round 2) nulls out. Combined with the β non-transfer
and probe30's junction-current record, the synthesis is that the
engine's stake sink strength is deck-SOLVED, not prescribed — which
names round 3: the SOLVED stub dof under the fiction-consistent M-only
omission spelling (probe34's mesh-stable zoo cell M — shipped self
blocks + designed cross with all by-parts terms stripped, split node
dofs). No prescribed profile or amplitude; stub length/mesh are
convergence parameters. probe_r3_stub.py measures it.

## 6d. Round-3 results (measured 2026-08-28, probe_r3_stub.py) and THE
## PHASE-3 FINAL VERDICT

Round 3 — the solved stub dof under the M-only omission spelling
(probe34's zoo cell M on the anchor decks; split node dofs, shipped
self blocks, ends-stripped designed cross; length/mesh as convergence
ladders):

- Mesh-stable at fixed length (L=2: d1 vs d2 differ 0.01 Ω) but
  WILDLY length-dependent: Z = 254.9−437.2j (L=0.5) → 224.8−291.3j
  (1.0) → 186.7−154.3j (2.0) → 302.0−3.0j (4.2) — hundreds of ohms
  from the anchor, X sign-flipping through the λ_m/4 ≈ 2.7 m soil
  resonance. The solved stub is DRIVEN like a real buried monopole
  where the engine's stake barely loads (its own Δ ≈ −2.8−1.7j).
- The other limit is already on the #524 record: under interface
  grading, omission-spelling node coupling collapses to stub-INVISIBLE
  (probe19 B+split → Δ ≈ 0; probe34's small M-only Δ was measured on
  g1/g2-graded node meshes). So the object is MESH-DEFINED — huge on
  coarse node tents, zero under grading — not a convergent spelling.
  Fan run skipped: the lone deck already refutes the family.

**THE PHASE-3 VERDICT (four families, all measured, all excluded for
distinct named reasons):**

1. Complete/exact-EM solved stub — convergent but a DIFFERENT
   EXPERIMENT (the #524 adjudication; Δ +67−54j vs engine −2.8−1.7j).
2. Omission-spelling solved stub — NOT a convergent object
   (mesh-defined; round 3 + probe19/34).
3. Prescribed rod ghost — robust and right-familied but wrong angular
   distribution; per-deck closable (0.001 Ω) with NON-TRANSFERRING β*
   (round 1).
4. Derived Born electrode — a NULL (round 2, machinery certified to
   the digit).

The engine's detached-class coupling is not expressible as any
consistent, convergent spelling in our frame — probe34's "the fiction
is not a Galerkin object" verdict, now established for the DETACHED
class. The 12.9/17.2 Ω residual is the fiction's un-spellable content.
**The `contact+buried` refusal is CORRECT AND FINAL, now with proof —
not provisional pending a better ghost.** The served alternatives (rise
respelling, bonded screens, elevated feed over buried counterpoise)
remain the answers; `ANCHOR_ENVELOPE_OHM = 18.0` stays as the recorded
landscape; the refusal prose as shipped ("no honest sub-ohm serve of
this deck class in either convention") was already the right sentence
and now has the measurement behind it. β*-non-transfer is the sharp
signature to cite: the engine's sink strength is deck-solved fiction,
so no fixed physical source can reproduce it across decks.

## 7. Defect found en route (independent of the decision)

The one-member-junction bypass: `normalize_junctions` allows one-member
groups (#172), `_grounded_junction_ends` admits them, so declaring
`junctions=[[(wire_at_contact, "end")]]` on a contact+buried deck lands
the contact end in `crossing_ends`, escapes `_REFUSE_CONTACT_WITH_
BURIED`, fails `_crossing_junctions`' two-media test, and silently
serves through the OLD field-form cross block — the exact O(1)
boundary-term configuration the refusal exists to prevent (the 46.6 Ω
class, worse than the refusal's own recorded 13-17 Ω). To verify, file,
and fix (small, delegable) regardless of phase 3's outcome.

## 6e. THE CORRECTED-FEED RE-DERIVATION (2026-08-28, post-#706 —
## supersedes every NUMBER in 6b–6d; the verdict structure survives)

The #706 erratum invalidated the quantitative frame of rounds 0–3: the
anchor builders fed momwire at 4.3333 where the engine's `EX 4,1,7`
drives the node at 4.6667 (PR #707 corrected the builders). Re-derived
at the matched feed, probes probe_r4_matched_ladder / probe_r5_engine_
ladder / probe35-rerun / probe_p35_beta-rerun (results/*.json):

**Cell grid at matched feed (x1 = 15/10 mesh):**

| cell | lone | fan |
| --- | --- | --- |
| shipped (field-form) | 51.43 Ω | 137.32 Ω |
| M-only (continuation-consistent) | 3.474 Ω | 4.976 Ω |
| M+bnd | 51.38 Ω | — |
| M+hub | — | ≡ M to the digit |

**Mesh ladders, matched feed, converged tails (Richardson, p fitted on
the last three rungs; stable <0.1 Ω under drop-last-rung):**

- momwire M-only: lone x1–x6 → tail 93.0896−66.3952j (p≈0.68);
  fan x1–x5 → tail 94.3605−69.2545j (p≈0.72)
- engine: x1–x8 (EX 4,1,7m — same physical node every rung) →
  lone tail 93.0080−63.3767j, fan tail 90.8676−64.0553j (p≈0.9;
  its x1 anchor prints sit 6.8 Ω from its own tails — the
  quote-ladders lesson again)

**THE HONEST DETACHED-CLASS RESIDUAL (converged vs converged):**

- lone: **3.02 Ω** — dR +0.08, dX −3.02 (the converged RESISTANCES
  agree to 0.08 Ω; the entire residual is reactive)
- fan: **6.26 Ω** — dR +3.49, dX −5.20

**Ghost re-score:** β* at the matched feed: lone 0.4821+0.3619j,
fan 0.3597−0.0721j — NON-TRANSFER STANDS (and neither is any
interface-family constant). The residual's structure is itself the
refutation: pure-X on lone, mixed R+X growing with collector count on
fan — a real spreading current's signature, not any fixed source
constant's. Families 1 (different experiment), 2 (mesh-defined) and 4
(derived null) were feed-independent in character and stand as argued.

**VERDICT (re-derived): the refusal STAYS.** 3.0/6.3 Ω converged is not
sub-ohm, no consistent spelling closes it, and the deficit is now
MEASURED as the un-modelled spreading current rather than inferred from
a contaminated 12.9/17.2. `ANCHOR_ENVELOPE_OHM` re-derives to 6.0 (the
x1-vs-x1 matched-feed frame the gates score in: worst miss 4.976 +
CI-margin). The refusal prose quotes ~3/~6 Ω at converged meshes.
#567 closes again on this record.
