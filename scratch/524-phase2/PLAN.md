# momwire#524 phase 2 — the interface-crossing junction prototype (A-2)

Started 2026-08-26, the session after #567 phase 0 re-sequenced arc A
(A-2 before A-3, verdict `momwire#567 issuecomment-5431512077`). This is
the load-bearing step for BOTH the bonded fan (arc definition-of-done) and
the detached contact anchors: phase 0 measured that even the DETACHED decks
miss by 12.9/17.2 Ω without the contact current spreading into the soil,
and no scalar endpoint weight blind-transfers between decks.

## The question this prototype answers

Can a crossing/continuation basis — a current basis whose support straddles
z = 0, built on the AGARD (15)–(16) = NEC-4 (3-45) junction condition —
close the three engine anchors inside one defensible envelope?

    I₊ = I₋                    (current continuous at the interface)
    I′₊ / I′₋ = ε̃₊ / ε̃₋       (slope jump; charge discontinuous by ε ratio)

Validity: strictly normal incidence; NEC uses it to ~60° from normal.
NEC-4's own caveat: converges POORLY just above the interface — junction
segments there need to be on the order of the screen height.

## The three anchors (all soil A: eps_r 13, sigma 0.005; 7 MHz)

| deck | cards | engine prints | today |
| --- | --- | --- | --- |
| crossing | `GW 1,4,0.,0.,-2.,0.,0.,0.,.001` + `GW 2,15,0.,0.,0.,0.,0.,10.,.001`, fed EX 4,2,7 | 74.761 − 57.730j | refused (no crossing basis) |
| lone-radial | banked in `momwire/tests/golden_buried_anchor_nec5.py` | 92.130 − 70.141j | best MP spelling misses 12.91 Ω |
| four-radial | same golden module (re-banked, PR #658) | 90.051 − 70.731j | best MP spelling misses 17.16 Ω |

Crossing captures + odd-multiplier ladders: `scratch/524-phase0/oracle/`
(captures.json; SPEC.md deck 3). The A/B workaround spread is zero in
range (phase-0 finding — the asymptotic branch never fires on these decks).

## Construction sketch

A crossing junction node at z = 0 carries ONE degree of freedom shared by
the last above-segment and the first below-segment. Its basis is a tent
with value 1 at the interface, slope-scaled arms:

    f₊(z) on the air arm, f₋(z) on the soil arm,
    f₊(0) = f₋(0) = 1,  f₊′(0)/f₋′(0) = ε̃₊/ε̃₋.

With every basis then either vanishing at its support ends or KCL-clean at
the interface node, the by-parts boundary terms of the transmitted MP
family cancel BY CONSTRUCTION — field form ≡ MP identically, and the
phase-0 boundary-term problem (the 2.484) dissolves rather than being
repaired.

For the CONTACT decks (monopole ending AT z = 0, radials detached below):
the contact node becomes a crossing node whose below-arm is the spreading
current the refusal prose names — a short continuation conductor into the
soil (length ~ the junction-segment scale) carrying the ε̃-scaled slope.
Whether that continuation is (a) a real appended segment, (b) a half-basis
with prescribed decay, or (c) the C₂ machinery re-derived, is what the
prototype measures — score all spellings against the anchors, as phase 0
did for A/B/C.

## Fill pieces (all four exist; the prototype composes them)

| block | source |
| --- | --- |
| (+,+) above/above | shipped free-space + reflected fill |
| (−,−) below/below | shipped #553 U2 (`_d12` swapped-args remainder) |
| (+,−), (−,+) transmitted | shipped U3 field form; phase-0 MP `mp_cross.py` tables {U_T, V_T, W_T, ∂zW_T} |
| crossing basis rows/cols | NEW — arms decompose into the four blocks above |

Reuse: `scratch/567-phase0/proto/mp_cross.py` (tables + seeded()),
`probe3.py`'s `_field_galerkin_block` monkeypatch pattern (w=1 reproduces
production to 0.01 Ω), `results/fan-tables.npz` (fan tables cached, 4 min
to refill).

## Probe ladder

- P0. ε̃ → 1 collapse: with ε̃₊ = ε̃₋ the slope condition degenerates to an
  ordinary interior tent; the crossing fill must reproduce the free-space
  fill at the phase-0 identity floor (~1e-4). Constitutionally BLIND to
  W_T (phase-0 lesson) — this is a wiring check, not an agreement claim.
- P1. Reciprocity of the crossing rows (transpose at the I1 floor).
- P2. Crossing anchor: solve the crossing deck, score vs 74.761 − 57.730j,
  ladder with ODD multipliers (fed segment stays centered; ×1 anchors are
  ~11 Ω under-converged — tolerances vs ladder LIMITS, not ×1 prints).
  Junction-segment scale sweep near the interface (NEC-4's caveat) is part
  of this probe, not a follow-up.
- P3. Contact anchors with the continuation spelling(s): re-score
  12.91/17.16 Ω and re-derive `ANCHOR_ENVELOPE_OHM` from what is actually
  achievable. GO = one spelling lands inside a defensible envelope of ALL
  THREE anchors.
- P4. The bonded fan (radials RISING to z=0 and bonding) if P2+P3 pass —
  the arc's definition-of-done deck class.

## Traps (phase-0 memory, verified sources)

- nec5cl caches SOMMPD.NEX in cwd and silently reuses — scrub `*.NEX`
  every run; error exits still return 0 — scan output text.
- EX 4 = 1 A CURRENT source, not 1 V.
- Engine below-ground NEAR FIELDS are not an oracle at any depth (fifth
  surface defect, depth-flat E_z; empymod sides with the prototype).
- empymod near-singular for source AND observer at the interface — do NOT
  gate on empymod for crossing geometry; ht='quad' (ppd 600) elsewhere.
- `t_surfaces_direct` returns surfaces with the divide-out divided out —
  multiply by `divide_out_transmitted` before treating as fields.
- Never gate cross-basis AGREEMENT (razor vs bspline formulation gaps are
  not defects).
- Convention check at the top of every script: e^{+jωt}, ε̃ = ε_r − jσ/ωε₀,
  assert e^{−jk₋R}/R decays in the lossy medium.

## Entry points measured (2026-08-26)

- `_medium_spec.wire_media` labels per-WIRE (ABOVE/BELOW); the crossing
  deck's buried vertical (zmax = 0, end standing in the plane) hits
  `crossing_refusal`, and `CROSSING_ANCHOR = "74.761 - 57.730j ohm"` is
  already quoted in that prose — the gate the basis has to meet is named in
  src. `seeded()`-style override for the crossing deck: GW1 = BELOW,
  GW2 = ABOVE, then build the ONE junction tent straddling the bond at
  z = 0 by hand; `probe3.py`'s `_field_galerkin_block` monkeypatch pattern
  carries the rest.
- Junction machinery: `bspline.py` junction directional bases (value-1
  tents + KCL Lagrange constraint at K-wire junctions) + `_junction_rule.py`;
  a ground junction (#151) already keeps the value-1 tent and drops the
  plane-crossing HALF — the crossing basis is that dropped half restored
  with the ε̃-scaled slope. The crossing node is a K=2 junction whose
  below-arm slope is scaled by ε̃₊/ε̃₋.
- The crossing deck CARDS are still only in untracked scratch
  (`scratch/524-phase0/oracle/*/deck.nec`). When A-2 builds its gates, add
  the crossing deck to `momwire/scripts/capture_buried_anchor_nec5.py`
  (PR #658's durable home) alongside the two contact anchors — plus the
  odd-multiplier ladder rungs, since the ×1 print is ~6 Ω under-converged
  (ladder limit ≈ 68.9 − 49.7j at ×8; tolerances vs LIMITS, not ×1).

## Pre-probe results (`proto/probe0_construct.py`, 2026-08-26)

- Convention gate passes: k_m = 0.5801 − 0.2382j at soil A / 7 MHz,
  |e^{−jk_mR}/R| decays (0.79 → 6.1e-2 → 4.3e-4 at 1/5/20 m).
- The crossing deck CONSTRUCTS without refusal; `crossing_refusal` fires at
  SOLVE time (wire 0's polyline z runs −2 → 0, end standing in the plane).
  So `seeded()`-style media override works here exactly as in phase 0:
  `_cached_wire_media = (BELOW, ABOVE)` gets a clean geometry — 19
  segments, 4 below / 15 above, seg_offsets [0, 4, 19].
- `geom` carries no junction structure — junctions are a BASIS-level kwarg
  (`junctions=[[(0,"end"),(1,"start")]]` must be declared; the solver-API
  crossing deck in `probe0_construct.py` currently declares none, unlike
  the deck route which auto-joins shared points). First real P0 step next
  session: declare the junction, inspect the K=2 value-1 tent + KCL dofs
  that appear, then build the ε̃-slope-scaled replacement.
- k_medium signature trap: `k_medium(eps_t, k2)` takes the COMPLEX ε̃, not
  the (eps_r, sigma) tuple — compute ε̃ = ε_r − jσ/(ωε₀) first.
- **With `junctions=[[(0,"end"),(1,"start")]]` declared: 21 bases and ZERO
  KCL rows — because the junction is GROUNDED** (CORRECTED 2026-08-26;
  the first reading of this probe as "C¹ chain" was wrong). Mechanism
  (`_build_basis_polynomials` + `_grounded_junctions`): every junction
  member end keeps a value-1 directional basis with outflow sign ±1, one
  KCL row per junction — but a junction whose shared point lies at
  `ground_z` loses its KCL row (#151: current may leave through the ground
  stake / image). So TODAY the crossing deck's two arms are two
  INDEPENDENT ground-contact ends, each continuing into its own image
  fiction, with no continuity between them. The crossing prototype
  therefore adds TWO Lagrange rows in the house KCL pattern:
    row 1 (continuity)  = the dropped KCL row (signs from junction_dirs);
    row 2 (slope jump)  = (dI/dz)₊ − (ε̃₊/ε̃₋)(dI/dz)₋ = 0, coefficients
      from one-sided basis derivatives at the node (both wires run t̂ = +ẑ
      so dI/dl = dI/dz on both sides; ε̃₊/ε̃₋ = 1/(13 − 12.84j) at soil A —
      the air-side slope is ~18× the smaller one).
  And the fill side must REMOVE the contact-image continuation for these
  two bases (the below arm IS the continuation) — the "contact fiction
  dies" step; finding that switch in the ground blocks is part of task 3.
  `supp_seg` rows are zero-padded — don't read pad zeros as "supports
  segment 0" (probe0's straddle printout has this bug; harmless, noted).

## Razor refusal parity (task 5 design — user decision 2026-08-26)

Razor's `razor.py` ~:1105 raises the blanket "wire {i} dips below the
ground plane (min z … ) — geometry error" for ANY below-`gz` wire. Parity
change: route the classification through `_medium_spec.wire_media`
(lower_medium = razor's sommerfeld-ground state) so that:
  - crossing wires → the SHARED `crossing_refusal` (names #524 ph2 and the
    74.761 − 57.730j gate);
  - contact + buried combinations → the SHARED contact_with_buried
    sentence (the two anchors);
  - wholly-buried DETACHED wires (bs2 SERVES these) → razor's honest
    own-gap sentence until razor's buried fill lands (G-U5-12's razor row
    documents this split — its `_TRUNK_REFUSAL` entry keys on "dips below
    the ground plane" and must move with this change).
End state per the user: BOTH trunks serve buried ground; razor consumes
the basis-agnostic buried tables (no blocker, phase-0 finding).

## Baseline (task 2, `proto/probe1_baseline.py` + scratch controls, 2026-08-26)

- Naive seeded solve of the crossing deck at ×1: **24.8200 − 1013.5571j**
  vs the engine's 74.761 − 57.730j — miss 957 Ω (22 s solve).
- Junction declaration is a NO-OP today: declared vs undeclared give
  byte-identical Z (the K=2 grounded junction only swaps the monopole-base
  basis kind "gnd" → "dir"; neither carries a KCL row, and the fill treats
  both kinds alike).
- Control: the contact monopole ALONE (shipped serve, same mesh) =
  71.5556 − 49.4339j — sane, and near the engine's ×8 crossing limit.
  Adding the buried arm bonded at the origin is what destroys it: the two
  value-1 bases stand their ends at the SAME point, so the near-singular
  cross-medium entries + the contact boundary term (phase 0's 2.5-relative
  defect class) dominate. This is the number the crossing correction must
  recover from — expect the fix to be mostly about those contact-node
  entries, exactly as the phase-0 verdict predicted.

## USER DECISIONS (2026-08-26, this session)

- **#651 resolved: razor is IN scope for buried ground.** Both bs2 and
  razor must handle it, with IDENTICAL refusals. Interim deliverable:
  route razor's below-`ground_z` geometry error through `_medium_spec`'s
  named refusals (touches G-U5-12's `_TRUNK_REFUSAL` razor rows, which key
  on "dips below the ground plane"). Long-term: razor's testing side
  consumes the basis-agnostic buried tables.

## Constraint-row spellings (task 3, `proto/probe2_crossing.py`, ×1)

With rows appended to the production Schur solve (`_solve_with_kcl`
accepts complex rows): S1 continuity-only −75.4 − 1089.2j; S2 continuity +
AGARD slope (r = 0.03894 + 0.03846j) −86.6 − 1130.5j; S3 continuity +
r = 1 slope −76.3 − 1085.2j. All within 46 Ω of each other and >1040 Ω
from the engine, R gone NEGATIVE. **The constraint space is not the
problem; the fill is.** Row plumbing works (row V nonzeros land exactly on
bases 4/5, the two node value-1 bases) and is kept for the corrected fill.

## Poison localization (task 3, `proto/probe3_poison.py`, ×1)

- **Amputating the below arm (rows/cols 0–4 pinned) reproduces
  monopole-alone through the buried path: 71.5901 − 49.2409j vs
  71.5556 − 49.4339j, 0.196 Ω.** The above/above block is CLEAN; all
  ~957 Ω of the naive miss lives in the below arm's self + cross entries.
- The smoking entry: Z[4,5] = −1177 + 1284j — the cross entry between the
  two COINCIDENT value-1 end bases, ~5× the below arm's own self entry
  Z[4,4] = 251 − 271j. Phase 0's contact-basis cross-medium defect (2.5
  relative) at point-blank range.
- Next step (the load-bearing one): swap the cross blocks for the phase-0
  MP machinery (`scratch/567-phase0/proto/mp_cross.py` — tables
  {U_T, V_T, W_T, ∂zW_T}, explicit by-parts boundary terms) with the
  endpoint-charge spelling axis (keep / drop / weight), on top of the
  constraint rows. CAVEAT: phase 0 validated MP ≡ field form on
  vertical-above × HORIZONTAL-below pairs only; the crossing deck is
  vertical × vertical — re-run the block-level identity on THIS deck
  before trusting either form there. Also suspect the below arm's SELF
  block with its end AT the interface (phase-0 decks were strictly 15 cm
  down; the R₁ → 0 interface corner of the below/below remainder is
  unexercised).

## MP identity on this deck (`proto/probe5_mp_identity.py`)

- First run hit a REAL scope edge: `mp_tables` refuses source depth
  exactly 0, and the crossing deck's below arm ENDS at z′ = 0 — the
  source-side by-parts boundary term must be evaluated AT the interface,
  which no phase-0 deck exercised (radials sat 15 cm down). The z′ → 0⁻
  limit is continuous (e^{−γ₋|z′|} → 1); the probe clamps end evaluations
  to z′ = −1e-9 m (error O(γ·1e-9)). The production crossing fill needs
  the tables' z′ = 0 edge handled by design, not by clamp.
- ε̃ = 1 economics: G-U5-3's shipped collapse tests use eps = (1.0, 0.0)
  but are BLOCK-level and still marked slow; a full-solve collapse of the
  crossing deck (probe4) burned >320 CPU-min on the near-lossless contour
  before finishing. If a full-solve ε̃=1 gate is ever wanted in CI, it
  will need its own cached grids or a block-level restatement.

## MP identity + MP-swapped solves (probes 5/6 — THE RESULT SO FAR)

- Identity on this deck (probe5, z′-clamped): shipped field form ≡ MP to
  5.97e-3-of-max on INTERIOR below bases, but **1.29-of-max disagreement
  on the node basis 4** (the below arm's interface-end basis) — the
  phase-0 defect class, now named at block level on a vertical×vertical
  deck. Shipped transpose identity 1.6e-16. Blocks saved:
  `results/probe5-blocks.npz`.
- Full solves with MP swapped in (probe6, ×1):

  | spelling | rows | Z | miss vs engine ×1 |
  | --- | --- | --- | --- |
  | A field (keep q) | none | −692.7 + 174.0j | 801.7 |
  | A field | V | −41.9 + 208.4j | 290.6 |
  | A field | V+S | 73.7 + 198.7j | 256.4 |
  | **B drop q** | **none** | **72.2848 − 49.8207j** | **8.288** |
  | B drop q | V | 115.4 − 98.5j | 57.6 |
  | B drop q | V+S | 132.0 − 107.2j | 75.7 |

  **B_dropq with NO constraint rows: 8.3 Ω from the engine's ×1 print**
  (from a 957 Ω baseline). The endpoint charge is the poison (A is
  catastrophic); constraint rows on top of B over-constrain and HURT —
  with the charge gone, the fill's own physics couples the node.
- B+none sits ~0.9 Ω from the amputation control and ~3.4 Ω from the
  engine's ×8 LIMIT (68.9 − 49.7j) — momwire at ×1 may be near-converged
  where the engine's ×1 is ~6 Ω high (the N4PC shape). ⇒ the ×3 rung
  (probe7, running) decides: if momwire holds ~70 − 50j while the engine
  ladder descends onto it, this spelling is serve-grade.
- CAUTION for the write-up: B+none being close to monopole-alone (72.3 vs
  71.6) means the stub's net effect is small at ×1 in momwire — the
  ladder + a stub-length sensitivity check must confirm the below arm is
  actually LIVE (not silently decoupled) before claiming the physics.

## THE DELTA INSTRUMENT (engine runs 2026-08-26; scratchpad
## `stub_sense.py` / `mono_ladder.py`, capture cache `nec5-cap/`)

The buried stub is a SMALL perturbation at the drive point, so the honest
gate is the house difference-of-columns: Δ = Z(crossing) − Z(mono-alone)
at matched mesh, which cancels the contact-monopole formulation gap.

| mult | engine mono | engine crossing | engine Δ |
| --- | --- | --- | --- |
| ×1 | 77.0870 − 57.0170j | 74.7610 − 57.7300j | −2.3260 − 0.7130j |
| ×3 | 73.5420 − 50.2520j | 70.8580 − 51.6780j | −2.6840 − 1.4260j |
| ×5 | 72.8580 − 49.0230j | 70.0380 − 50.7170j | −2.8200 − 1.6940j |

- Engine Δ converges to ≈ **−2.8 − 1.7j Ω** — the crossing physics signal.
- Engine mono ladder descends onto momwire's ×1 mono answer (71.56 −
  49.43j): momwire near-converged at ×1 where the engine is ~5 Ω high —
  the N4PC shape, for the contact column itself. (So probe6's "8.3 Ω
  miss" was mostly the mono column; in Δ, momwire-B+none reads
  +0.73 − 0.39j vs engine −2.33 − 0.71j at ×1 — wrong SIGN in R: the
  stub still acts as a weak parasitic, not a continuation.)
- Stub-length sweep (engine): mono 77.09, 0.5 m 75.19, 2 m 74.76, 4 m
  75.22 — shallow but real dependence; also re-validated the ×1 anchor
  deck to the printed digit.

**P2 restated: momwire's Δ must land near −2.8 − 1.7j and track the
ladder.** Next spelling axes to try (blocks in hand): (a) split
`bnd_src_W` into its W piece and the below-end charge piece and drop the
charges on BOTH sides; (b) the below/below SELF block's endpoint term at
z′ = 0 (phase 0 never spelled the self block — the stub's loading may
live there); (c) continuity row re-tested after (a)/(b).

## Δ ladder verdict (probe7 ×3, 2026-08-26 — where the prototype stands)

| mult | momwire mono | momwire crossing (MP-B) | momwire Δ | engine Δ |
| --- | --- | --- | --- | --- |
| ×1 | 71.5556 − 49.4339j | 72.2848 − 49.8207j | +0.7292 − 0.3868j | −2.3260 − 0.7130j |
| ×3 | 71.4922 − 49.0045j | 73.7470 − 47.9562j | +2.2548 + 1.0483j | −2.6840 − 1.4260j |

- Absolute miss shrank ×1→×3 (8.3 → 4.7 Ω) but ONLY because the engine's
  mono column descended onto momwire's converged one — the Δ instrument
  shows the truth: momwire's crossing signal is +2.25 + 1.05j where the
  engine's is −2.68 − 1.43j (5.5 Ω apart, DIVERGING under refinement,
  wrong sign). **The stub couples as a weak parasitic; the continuation
  physics is not yet in the fill.** MP block build cost at ×3: 412 s.
- The ε̃=1 full-solve collapse (probe4) was killed after ~7 CPU-hours with
  no output — near-lossless contour pathology; its question (shipped-path
  wiring) is superseded by probe5's block-level identity. P0 for the
  production unit should be a BLOCK-level collapse gate.

## Session 3 (2026-08-26, probes 8–13) — the charge axis dies, the corner
## term is found, and the question becomes delta*

- Re-baseline: momwire synced c0fe0fd → 580b8ca (v0.40.0, peer's #570 RP
  refusal + portal tests — no fill physics). B_dropAboveQ+none reproduces
  probe6 exactly after the sync.
- **probe8 (charge-split grid): the cross-block charge axis is EXHAUSTED.**
  {drop above q (=B), drop both, drop below q} × {none, V row}: best is
  still B+none (dist 3.07 in Δ); drop-both ≈ mono to 0.06 Ω (stub
  invisible); keeping the above charge alone is catastrophic (−568 Ω).
  The −2.8 Ω continuation signal is NOT in the cross-block by-parts terms.
- **probe9 (Z-matrix sensitivity): no O(1) scaling of the below-side
  blocks reaches the engine Δ** (best dist 1.36 at interior-below × 0.8;
  everything else ≥ 2.3). Two internal checks pass: cross × 0 ≡ the
  amputation control; cross × −1 ≡ unperturbed (similarity transform).
  Z[4,5] under MP-B = 112.8−123.4j (was −1177+1284j naive).
- **probe10 (merged crossing dof): merging ≡ the Lagrange V row** for
  symmetric Z (numerically identical to 4 decimals on every fill
  spelling) — so the C⁰ crossing basis was already measured, and it HURTS
  (+43.9−49.1j in Δ). Un-merged B+none solution has I[node_below] ≈ 0:
  the fill makes the stub too expensive to drive. Both node tents vanish
  at the feed ⇒ v[4] = v[5] = 0 ⇒ merge is a pure Z-hook.
- **probe11 (delta* hunt): a lumped node correction delta* =
  −39.3219+28.8343j** at the merged dof lands Z_in exactly on
  mono + engine Δ at ×1. The below block's own stub driving-point Z =
  56.1−23.0j — SANE vs the ground-rod estimate (~64−64j): the below
  interior is not broken; the defect is node-local.
- **probe5's mystery SOLVED: the 1.29-of-max node disagreement is a
  SINGLE ENTRY — the omitted CORNER term.** mp_cross.py's by-parts
  bookkeeping skips the (test-end × source-end) corner ("every below end
  is KCL-clean or free" — false on the crossing deck: both node tents
  have value 1 at coincident ends). Residual [5,4] = 1512.61−1658.55j,
  next-largest 77× smaller. shipped[5,4] = 1176.95−1283.78j,
  mp-no-corner[5,4] = −335.66+374.77j. mp_cross.py now returns the split
  pieces (main_raw / bnd_src_Wp / bnd_src_q).
- **probe12 (drop-all + merge): the pairwise-cancellation story is
  sign-WRONG.** Numerically: "drop self T/S only + merged" ≡ "keep cross
  SQ+BT + merged" to 4 decimals — the self node-charge columns (computed
  with the interface-consistent transmitted kernel, on-axis ρ=0) equal
  the cross terms' merged content with the SAME sign, so node charges ADD
  under merge, and blanket-dropping double-counts (blow-ups to −1088j).
  An exact self-block drop needs the reflected-family by-parts derivation
  (phase-0 style, for above/above and below/below) — sign structure
  included. Trap for that derivation: the contour cannot converge with
  both legs on the interface at ρ=a (corner values must come from
  residual measurement or asymptotics, not the table).
- **probe13 VERDICT: delta* is NOT mesh-stable.** delta*(×3) =
  4.4840+23.2053j vs delta*(×1) = −39.3219+28.8343j (complex ratio
  0.21−0.44j); B+merged-no-corr Δ also swings ×1→×3 (+43.9−49.1j →
  −13.0−31.5j). The lumped node correction is a discretization artifact.
  ⇒ **The load-bearing next step is the phase-0-style by-parts derivation
  of the two SAME-MEDIUM families** (above/above = air direct +
  reflected; below/below = soil direct + below-reflected), signs and
  W-analog terms included, so the node-charge terms of all four blocks
  can be spelled consistently under the merged crossing dof. Session-
  scale; extends FORMULATION.md §5–§6 to the reflected families. The ×3
  MP pieces are cached (results/probe8-blocks-x3.npz, nb=12/na=13,
  n_basis=59; build 158 s after warm grids).

## Session 4 (2026-08-26, probes 14–18) — the same-medium derivation lands,
## every bookkeeping axis closes, and the defect class is NAMED

Deliverable doc: `DERIVATION-SAME-MEDIUM.md` (FORMULATION.md §5–§6
extended to the same-medium families; probe ledger inside).

- **The derivation (item 1) is DONE and PINNED.** Key structural result:
  the shipped self blocks are MP(direct) − w·MP(image) − field-form
  remainder, so their whole by-parts deficit lives on the two CLOSED-FORM
  kernels — no new contour tables. The sign structure is −,−,+ (test-end,
  source-end, corner) relative to the f′f′ term: the endpoint delta in
  ∇·(f·1_[lo,hi]) carries −σf(E), which is exactly probe12's sign trap
  (naive all-plus charge products predict pairwise cancellation; true
  structure ADDS). Identity pinned per family to 1e-8..1e-12-of-max
  (probe14, ×1 and ×3); above-family β pinned analytic at 3e-10 (n=110);
  σ_b=+1, σ_a=−1; node-only support confirmed.
- **Static consistency + corner discovery (probe14d)**: (1−A_m)/ε̃ε₀ ≡
  (1−C₂)/ε₀ to machine (= the transmitted static factor — the three
  families agree at the node statically, as probe12 saw). Self corners
  c_bb ≈ c_aa = 14534−15859j, mesh-independent. **probe5's measured cross
  corner (1512.61−1658.55j) is 9.58× smaller at the SAME complex phase**
  — a real factor ⇒ the shipped cross block's implicit corner content is
  quadrature-TRUNCATED ~10× (its Gauss nodes never come within ~a of the
  node). Corner spellings must therefore be consistent-by-omission:
  telescoping says c_bb + c_aa − 2c_cross ≈ 0 under merge only if all
  four use one convention.
- **probe15 (the exact spelling) REFUTES the bookkeeping route**: shipped
  self + BND (closed-form by-parts, no corners) + MP-A-no-corner cross +
  merge lands Δ = +80.47−54.62j (dist 98.8). The two corner-mix controls
  blow up exactly as the telescoping predicts (−1021j, −923j) — the sign
  wiring is validated; the spelling fails because the node entries are
  O(100)-Ω levers and the mixed quadrature conventions (analytic moments
  vs Gauss tables vs closed forms) are inconsistent at the O(10 %) level
  against a 3 Ω signal. Also reproduced: MPcrossA+merge ≡ probe6's A+V
  (−41.90+208.40j exactly).
- **probe17 (straddling basis) kills the dissolution hope**: the deck as
  ONE polyline wire (knot edge at z=0, `_below_segments` per-segment
  z-truth, `_build_J_blocks_subset` per-EDGE guard — shipped guard
  assumes whole-wire subsets and mis-slices/skips on a straddling wire)
  solves to −76.35−1085.23j ≈ two-wire + continuity row (probe2 S1) ≈
  naive merged. The per-class fill CUTS the straddling basis at z=0 and
  the field-form cross blocks carry the cut charge implicitly — the
  swamp relocates, it does not dissolve. (Merge-hook ≡ V-row ≡
  single-wire: one instrument, three spellings, all measured equal.)
- **VERDICT: all three bookkeeping axes are closed** (cross charge axis,
  probe8; lumped node correction, probe13; same-medium by-parts + corner
  conventions, probes 14/15/17). Δ diverging under uniform refinement
  while the engine ladder converges is the signature of NEAR-INTERFACE
  QUADRATURE INCONSISTENCY across the four families' entries, not of a
  basis-space limit or missing analytic term. Exits: (α) graded mesh
  toward the interface — probe18; (β) a designed near-interface cell
  (one log-refined quadrature convention for every entry whose support
  touches z=0, transmitted z′=0 edge by design, not clamp).
- **probe18 (graded straddle): exit (α) is DEAD for the naive/field-form
  fill.** h_node 0.5 → 0.05 → 0.0125 m (40×) moves Δ only
  −48.5−934.7j → −43.0−926.6j: the −1000j near-interface garbage is
  SELF-SIMILAR under refinement (finer segments put Gauss nodes
  proportionally closer to the singular corner and regenerate the same
  unintegrable content). Mesh grading cannot repair the field-form cross
  blocks. (mono column graded identically: 71.59−49.25j, stable ✓.)
- **probe19 (graded two-wire + MP-B cross pieces at the graded mesh):
  the sharpest physics statement of the arc so far.** B+SPLIT under
  interface grading CONVERGES — to Δ ≈ 0 (+0.065+0.033j at h_node
  0.05 m, +0.100−0.060j at 0.0125 m): with the interface resolved and no
  continuity imposed, momwire's four-family fill says the stub is
  INVISIBLE. B+MERGED under grading goes UNSTABLE (−462−136j, then
  −258−948j): the coincident-tent continuity gets worse as the tents
  shrink. So: continuity is the missing physics (engine: −2.8−1.7j),
  momwire's node-region entries misprice it, and without it the stub
  fully decouples. (MP piece builds at graded meshes: 47 s / 77 s,
  cached probe19-blocks-g{1,2}.npz.)
- **probe20 (AGARD rows on the graded MP-B fill): the elimination is
  TOTAL.** B+V ≡ B+merged EXACTLY (−461.74−135.89j at g1 — the
  V-row/merge equivalence holds even in blow-up), diverging worse at g2
  (−258−948j); B+S alone is benign and converges to Δ ≈ 0 (slope without
  continuity constrains nothing); B+V+S intermediate garbage, worse
  under grading. Every discrete mechanism that forces current THROUGH
  the node explodes, and grows worse as the interface tents shrink.
- **SESSION-4 VERDICT: the crossing physics is unreachable by any
  (spelling × mesh × constraint) combination on the EXISTING kernel
  machinery.** The engine's Δ (−2.8−1.7j) is generated entirely by its
  interface-junction treatment; momwire's fill prices interface-crossing
  current with entries built from the ONLY unvalidated numbers in the
  matrix — the transmitted tables at z, z′ → 0, ρ → 0 (the phase-0
  z′-CLAMP edge; the contour provably cannot converge at that corner,
  probe12; the phase-0 identity's 1.29-of-max node discrepancy lives
  exactly there). The load-bearing next build is the NEAR-INTERFACE
  KERNEL EVALUATION: designed analytic z′ = 0 / z = 0 / ρ → 0 limits
  (corner asymptotics of the transmitted Sommerfeld integrals, and the
  below-remainder's R₁ → 0 edge) — new TABLE work, not new algebra.
  `DERIVATION-SAME-MEDIUM.md` + the probe ledger is its specification;
  the by-parts bookkeeping (probe14 npz machinery) is DONE and waiting
  for trustworthy kernels to plug into. Idea parked (unmeasured): a
  circuit-level shortcut — attach the stub's measured driving-point Z
  (56−23j, probe11) at the contact node as a load, NEC-4 LD-style —
  could serve production before the tables land; needs a defensible
  contact-node Thevenin, do not build on it without measuring.

## NEXT EXPERIMENTS (re-sequenced after session 5; session-4 item 1
## DONE — designed kernels built, both gates passed, ε̃=1 adjudicator
## passed; the question is now ADJUDICATION, not repair)

1. **Engine junction currents vs AGARD (the sharpest adjudicator).**
   Print the engine's converged crossing-deck current tables at the
   junction (×3/×5 rungs, nec5-cap machinery) and measure whether its
   junction current satisfies its OWN AGARD slope condition
   I′₊/I′₋ = ε̃₊/ε̃₋. momwire-complete's does (probe27: V+S rows change
   nothing). Also compare I(0) magnitude/phase between the two solutions
   — a current-level disagreement localizes the convention difference
   far more sharply than Z_in.
2. **High-σ limit**: sea-class soil (σ = 5+) where the stub → perfect
   stake: engine crossing must → engine mono; momwire-complete crossing
   →? A convention-free physical expectation anchors both.
3. **The consistent-omission spelling zoo at resolved quadrature**: build
   the engine-parity serve — drop ALL terms ∝ f_node(0) consistently
   across the four families (the #151 omission extended to the crossing
   node), measure whether it reproduces engine Δ ≈ −2.8−1.7j while
   staying mesh-stable. If yes: momwire ships BOTH spellings (exact-EM
   complete + engine-parity omission), the way A/B spellings were scored
   in phase 0.
4. If an adjudicated serve lands: ×5, the two CONTACT anchors (P3),
   re-derive ANCHOR_ENVELOPE_OHM, production basis (knot edge at z = 0;
   probe25's graded_axis_data + probe27's complete assembly are the
   prototype of the production near-interface cell).
5. Cheap fallback still in view (unmeasured): the contact-node LOAD
   shortcut (stub driving-point 56−23j attached NEC-4 LD-style).
4. DONE (momwire PR #660 MERGED → `24811c7` + `15a5f0e`, issue comment
   `issuecomment-5432907775`): razor refusal parity — razor routes buried
   readings through `_medium_spec.wire_media` via a construction-time
   `_refuse_buried_geometry` (NOT inside `_ground_ends` — bare `__new__`
   probes of `_find_junctions` lack the ground attrs; caught by CI's
   one-segment census); four decks refuse byte-identically across trunks;
   own-gap sentence names BSplineSolver + the #651 continuation; G-U5-12
   razor row re-keyed. NOTE: `test_portal_fixtures.py::
   test_capture_is_idempotent` fails on clean main LOCALLY (passes in
   CI) — stale local portal fixture, pre-existing, not this branch.

## Session 5 (2026-08-26, probes 21–25) — the designed near-interface kernels

Deliverable doc: `DERIVATION-NEAR-INTERFACE.md` (corner asymptotics +
designed evaluation + the radius rule; probe ledger inside).

- **The designed evaluator EXISTS and is PINNED (probe21,
  `proto/corner_tables.py`)**: head (shipped detour) + mid + ROTATED-TAIL
  rays λ = Λ + t·e^{±jπ/4} (Hankel-split J₀ for ρ > 0), uniformly
  convergent through the corner — z′ = 0 and z = 0 EXACT, no clamp.
  Overlap vs shipped contour 7.9e-13; Λ-independence 4.2e-9; corner
  coefficients {1, 2/(1+ε̃), −(ε̃−1)/(ε̃+1)} to ≤ 7.5e-6; ε̃ = 1 collapse
  at machine (2.2e-16). Six surfaces: the four + {∂z∂z′V, ∂z′W}.
  TRAP: ray panels must start at the Λ scale, not the decay scale (44 %
  silent error on the W log content otherwise).
- **The missing RADIUS named (derivation §3)**: the shipped cross fill
  evaluates pair distance axis-to-axis (crho, bspline.py:4349) — on the
  coaxial deck ρ ≡ 0 and two node integrals are LOG-DIVERGENT in the
  continuum, finite only by quadrature truncation (probe14d's 9.58× was
  this). Design rule: cross-family evaluations fold ρ_eff = √(ρ² + a²)
  (the same-edge moments' convention extended). With the radius in, all
  node kernels are BOUNDED → graded quadrature converges.
- **GATE 1 PASSED (probe22)**: by-parts identities (V double, W single)
  on designed kernels at ρ = a with log-graded quadrature: node×node row
  closes to 5.7e-11-of-max (V) / 7.4e-14 (W); interiors ≤ 1e-16 class.
  The phase-0 1.29-of-max node defect is DEAD on designed kernels.
- **GATE 2 first pass (probe23): cross tables alone do NOT stop the
  merge/V blow-up** (g1 −385−82j, g2 −575−706j — still diverging;
  B+split still Δ ≈ 0). Diagnosis: the merged node diagonal telescopes
  only under ONE convention; the designed cross now carries RESOLVED
  corner-class content while the shipped SELF blocks still carry
  truncated content — (i) the image pieces' off-edge Gauss (the "mirror
  is 2·depth away" premise dies at the node), (ii) the outer Galerkin
  quadrature of every node-touching entry.
- **probe25 (node cell v2): outer quadrature + image truncation are NOT
  the blow-up** — all corrections small (cross entries move ~2 %, image
  O(3–80), direct graded-vs-analytic agrees), merge/V unchanged
  (−404 g1, −578−701j g2).
- **probe26 (node-diagonal decomposition): the remainders are
  EXONERATED at the node** (R_aa[na,na] = −0.008−0.069j, R_bb ~ 1e-3 —
  physically right: reflected−image is k²-class at the corner), and
  **self_aa net ≡ the mono deck's contact diagonal** (27715 vs 27722 —
  the shared column cancels in Δ, aa validated).
- **THE DEFECT CLASS, FINAL NAMING: every "drop" spelling is
  truncation-regularized.** At resolved quadrature the retained
  ∬f′f′V's ln(a)-class content diverges with its balancing end/corner
  terms deleted — designed-B t_ab[na,nb] flips SIGN class vs the shipped
  field entry (−1406+1533j vs +1177−1284j). Spelling B was only ever
  finite by quadrature truncation; so were the shipped self blocks'
  missing bnd terms. The ONLY quadrature-convergent node treatment is
  the COMPLETE field-form-equivalent spelling (all ends + corners) on
  ALL FOUR families — which is exactly what probe15 tried with OLD
  kernels/ρ=0/coarse quadrature and lost to 10 % convention mismatch.
- **probe27 (the complete spelling): GATE 2 PASSED.** P1: designed
  corner c1·V(a) = 14538.62−15858.88j ≈ c_bb (§3 equality to 3e-4),
  exactly 9.585× the shipped truncated content (probe14d's 9.58). P2:
  split ≡ merged ≡ V ≡ V+S TO THE DIGIT, mesh-stable g1→g2
  (67.1789−53.7349j → 67.1773−53.7557j in Δ vs shipped mono): the
  divergence is DEAD; continuity + AGARD slope emerge from the fill.
- **probe28 (the mono lesson)**: completing the mono contact column
  wrecks a validated serve (71.59−49.25j → 46.90−961.47j) — the shipped
  contact serve's end-charge omission IS the #151 continuation model.
  Columns cannot be matched by completion.
- **probe29 (ε̃ = 1 adjudicator): PASSED 0.002 %** — complete+merged at
  ε̃ = 1 reproduces the independent free-space 12 m-wire truth
  (17.5619−758.1617j vs 17.5621−758.1493j, 0.0124 Ω) through a
  204,345-magnitude corner telescoping. The composition is EXACT where
  truth is known.
- **SESSION-5 VERDICT: the named build is DONE, both gates PASSED, and
  the remaining real-soil gap (momwire exact-Galerkin crossing
  138.77−102.99j vs engine ~70; Δ +67−54j vs engine −2.8−1.7j) is an
  ADJUDICATION question between the engine's junction/contact convention
  and exact-Galerkin EM — no longer a momwire quadrature defect.** See
  DERIVATION-NEAR-INTERFACE §7 for the three adjudicators (engine
  current printouts vs AGARD; high-σ limit; consistent-omission spelling
  zoo for an engine-parity serve).

## Session 6 (2026-08-26, probes 30–31) — adjudicator 1: the engine fails
## its own AGARD condition; momwire-complete satisfies it emergently

- **probe30 (engine junction currents, from the PHASE-0 CAPTURES — no
  re-run needed; `anchor-crossing-x{1,2,3,4,5,8}` already printed
  currents; stock ≡ ezoff to the digit)**: the engine's junction current
  VIOLATES both AGARD conditions, and the violation GROWS under
  refinement. I(0⁺) is stable ≈ 1.14 − 0.03j A (= its contact-mono base
  current); I(0⁻) is ANTIPHASE (−0.35+0.16j at ×1 → −1.07+0.34j at ×8,
  ~√n divergence; I′(0⁻): −0.41 → −8.18). KCL deficit at the node grows
  1.55 → 2.23 A — more than twice the fed current vanishes INTO the
  interface point (a point-electrode/stake sink). |I′₊/I′₋| sweeps
  0.178 → 0.0098 monotonically THROUGH the AGARD value 0.0547 without
  settling. The engine's converged Z_in rides on a locally
  NON-CONVERGENT junction current: its crossing treatment is two
  independent contact ends (the #151 fiction on both wire-ends), not an
  AGARD junction. Results: `results/probe30-engine-currents.json`.
- **probe31 (momwire-complete currents, probe27 assembly + solution
  stash, g1+g2 cached blocks)**: with NO constraint rows, continuity is
  EMERGENT-EXACT (KCL deficit ~2e-7 of feed) and the slope-ratio
  magnitude CONVERGES ONTO AGARD under grading: 0.0450 (g1) → 0.0532
  (g2) vs 0.0547 (complex phase not yet settled at g2 — one-sided
  tent-derivative estimate is first-order). Below-arm profile is a
  smooth physical decay (1.19 A at node → 0.089 A at z=−1.9 m).
  **The above-side solutions nearly AGREE**: I(0⁺)/I_feed = 1.19∠−6.0°
  (momwire) vs 1.14∠−1.3° (engine ×5) — the entire disagreement is the
  below arm, where the engine carries antiphase divergent current into
  its node sink while momwire drives the stub continuously.
  Results: `results/probe31-currents.json`.
- **ADJUDICATOR 1 VERDICT: momwire-complete is the one solving the
  AGARD junction; the engine is not** (on this deck class its junction
  = two contact ends + point sink). The Z discrepancy (+67−54j vs
  −2.8−1.7j in Δ) is the two conventions doing DIFFERENT experiments,
  exactly as the mono lesson predicted: momwire pushes the full ~1.19 A
  base current through the node into the real stub; the engine sheds
  ~1.8–2.2 A into the contact fiction and barely loads the stub.
- **probe32 (adjudicator 2, engine side)**: engine Δ → 0 as σ → ∞
  (−2.82−1.69j at 0.005 → −1.19−1.04j at 0.05 → −0.46−0.34j at 0.5 →
  −0.17−0.09j at 5; eps 13 vs 81 indistinguishable at σ=5; stable
  under below-refinement nb 100→150). Engine crossing → engine mono as
  the stake fiction becomes exact. `results/probe32-highsigma-engine.json`
  + capture cache `results/probe32-nec5-cap/`.
- **probe33 (adjudicator 2, momwire side) — the σ-ladder, deck-matched**:
  the shipped transmitted plan's z′ ladder reaches 0.25 λ_m only, so at
  σ ≥ 0.05 the stub is SHORTENED per medium to ~0.9× that limit (0.84 /
  0.27 / 0.085 m — each ≥ ~1 soil decay length) and the ENGINE re-run on
  the identical decks. momwire-complete Δ: +67.2−53.7j (0.005, 2 m) →
  +31.7−2.1j (0.05) → +6.9−3.6j (0.5) → +1.1−2.6j (5): **the complete
  crossing collapses onto the shipped mono exactly in the limit where
  the fiction becomes physical** (|Δ| 86 → 32 → 7.8 → 2.8), while the
  momwire mono column tracks engine mono within ~1.5 % across the whole
  ladder (71.6/72.9, 66.1/66.8, 58.5/59.2, 55.0/55.6). Two designed-
  evaluator SCOPE fixes landed en route (`corner_tables.py`, neither
  touches pinned behavior): (i) exact-underflow rotated-tail panels
  count as quiet (σ=5 far pairs underflow e^{−1330} to 0.0 and starved
  the quiet counter); (ii) far-pair contour kill cap λ ≤ 60/s (keeps
  k₊ branch point + pole; relative truncation e^{−60}) — without it the
  adaptive head grinds e^{−100}-dead range at |k₋| ≫ k₊ (minutes per
  pair). Re-pinned after both: soil-A corner statics unchanged, cap
  consistency 3e-18, σ=5 corner Λ-independence 3e-16.
  `results/probe33-highsigma-momwire.json`.
- **probe34 (adjudicator 3): NO consistent-omission spelling reproduces
  the engine Δ.** Zoo at resolved quadrature (shipped self + designed
  cross minus bnd pieces, split, g1/g2): M-only Δ = −2.40−6.64j
  (mesh-STABLE, engine-like R, Im off by 5); M+SW ≈ −0.00−0.13j and
  B ≈ +0.06+0.06j (stable, stub invisible); A and A+corner-no-selfcomp
  = the −1000j truncation class. The engine's −2.82−1.69j is not
  expressible as a consistent Galerkin spelling — corroborating
  adjudicator 1 (its junction is not a Galerkin object). The "ship both
  spellings" option dies; there is no engine-parity serve.
  `results/probe34-omission-zoo.json`.
- **SESSION-6 VERDICT — THE ADJUDICATION IS COMPLETE, momwire wins it:**
  (1) the engine violates its own AGARD junction condition divergently;
  momwire-complete satisfies it emergently, and the two solutions agree
  on the above arm; (2) both conventions converge to the same physics
  exactly where the contact fiction becomes exact (high σ), and only
  there do they agree — momwire's composition passes the convention-free
  physical limit; (3) the engine's Δ is unreachable by any consistent
  spelling. momwire ships the exact-EM COMPLETE spelling as the crossing
  serve; the engine's crossing print is a different experiment (contact
  fiction on both wire-ends) and is documented as such, not gated
  against. Next: production integration (item 4) —
  `NEXT-SESSION-524-PRODUCTION.local.md`.

## Session 7 (2026-08-27) — PRODUCTION integration: the crossing serve
## ships in momwire (branch `524-crossing-serve`)

- **Item 1 DONE — the serve is production code.** `_near_interface.py`
  (the designed evaluator, verbatim from `corner_tables.py` incl. both
  session-6 scope fixes) + `_crossing_fill.py` (graded axes, complete
  cross M+SW+SQ+BT+corner, self bnd+corner completions with the closed
  forms generalized to 3D positions + ground_z) + `bspline.py` routing:
  `_medium_spec.wire_media` gains the `crossing_ends` junction exemption
  (razor passes nothing, keeps refusing verbatim), `_crossing_junctions`
  validates scope (K=2 only, one radius, no other junctions — each
  refused by NAME), and `_compute_Z_operator_buried` fills the cross
  pair designed-direct (no grid) on crossing decks. **Ships SPLIT node
  dofs** — probe27 measured split ≡ merged ≡ V ≡ V+S to the digit, so
  no dof surgery anywhere in the solve paths; continuity emerges.
- **Verification**: production g1 cross block BIT-IDENTICAL to
  probe27-blocks-g1.npz (+ corner 14538.6217−15858.8780j to the digit);
  g1 solve 138.7671−102.9889j (6e-5 Ω from bank); g2 138.7691−102.9893j
  (4e-5 Ω); ε̃=1 collapse + g1 anchor as pytest slow gates PASSED
  (`tests/test_crossing_serve_524.py`, G-524 rows: labeling, scope
  refusals, ε̃=1 kernel identity, soil-A anchor, ε̃=1 collapse).
- **Item 2 DONE — the grading ladder through the production path**
  (`results/production-ladder.json`): g0 UNIFORM (h_node 0.5 m)
  138.9796−102.7291j; g1 138.7671−102.9889j; g2 138.7691−102.9893j; g3
  (h_node 3.1 mm) 138.7702−102.9881j. Even the crude uniform mesh is
  0.33 Ω from converged; the graded rungs sit inside 0.002 Ω. The g1↔g2
  0.021 Ω movement stands as the serve-gate envelope (test gates 0.05).
- **Item 4 DONE — prose + gates + capture.** `CROSSING_ANCHOR` →
  `ENGINE_CROSSING_PRINT` (documented as the adjudicated
  fiction-convention print, never a gate); `crossing_refusal` fires
  only for MID-SPAN crossers and names the served split spelling; eznec
  seam + nec2 portal sentences point at the native serve + convention
  difference; `capture_buried_anchor_nec5.py` runs the six crossing
  rungs (engine re-print verified identical: x1 74.761−57.730j … x8
  68.882−49.733j) into `CROSSING_ENGINE_PRINTS` — record, not gate.
- **Item 5 DONE**: momwire#666 (z′ ladder extension past 0.25 λ_m, ~8
  rungs per extra quarter λ_m, NOT built) + momwire#667 (seam adoption
  of the crossing serve, with the convention-documentation decision).
- **Item 3 DONE (probes 35/36/37) — P3 VERDICT: the contact+buried
  class STAYS REFUSED; the served alternative is the RISE respelling.**
  probe35 on the CANONICAL decks (results/probe35-contact-anchors.json):
  shipped grid block ≡ complete M+bnd by the by-parts identity (0.01 Ω
  apart; 46.570 lone / 141.486 fan vs the anchors — same experiment);
  continuation-consistent M-only = 103.8272−75.5958j / 105.2020−78.7769j
  → misses 12.907 / 17.155 Ω, REPRODUCING #567 phase-0's B(drop)
  12.91/17.16 to the digit on designed kernels — the residual is the
  spreading current the deck has no conductor for, NOT quadrature.
  Fan M+hub ≡ M to the DIGIT (hub by-parts cancel through its KCL row,
  as derived). `ANCHOR_ENVELOPE_OHM` re-derived 4.0 → 18.0 with the
  landscape in its comment; both contact+buried refusals now state the
  measurement and point at the rise respelling.
  **probe36 (rise spelling, THROUGH PRODUCTION)**: the radial risen to
  the surface and junction-joined = served crossing deck; soil-A answer
  = **358.2203−80.4596j** (results/probe36-rise-spelling.json) — a
  different experiment from the engine's detached-stake deck, never
  gated against it. **probe37 adjudicates it**: at ε̃ = 1 the rise deck
  reproduces the independent free-space bent-wire truth to **0.0019 Ω
  (0.000 %)** — the composition is exact on the ends-at-node
  orientation AND the bent below wire (results/probe37-rise-eps1.json);
  banked as slow gate `test_g524_6_rise_deck_eps1_collapse`.
  **TWO PRODUCTION DEFECTS found+fixed by these probes**: (i) the
  corner is the INTERFACE corner — end pairs both in the plane only
  (fan hub got a spurious corner otherwise; 37c1ac3); (ii) **the corner
  sign is ORIENTATION-CARRIED: −σ_test·σ_src·c1·V(a)** — the banked
  +c1·V(a) is the σσ′=−1 (above-arm-starts-at-node) branch; blind +
  wrecked the rise deck to 10.15−1006.53j, the −1000j class (9f95b59).
  Never re-pick per medium; DO re-carry per orientation.
  TRAP FOUND EN ROUTE: the anchor decks feed at arclength 4.3333 on
  the 10→0 monopole (= EX 4,1,7); probe35 v2 improvised 10−4.333 and
  every number was silently ~50 Ω wrong. Use `contact_deck`/`fan_deck`
  from test_buried_serve_553, always.
- Portal note RESOLVED upstream: the transient
  `test_capture_is_idempotent@portal` failure (stale local SimNEC
  oracle 1.17 vs fixtures' 1.23) was fixed on main by a36c08b
  ("--check is a maintainer tool, not a gate; and find the oracle by
  looking"); branch rebased onto that main mid-session, all touched
  fast tests green post-rebase.

## Session 8 (2026-08-27) — the FAN WIDENING (1 above × N below)
## (branch `524-fan-widening`)

- **Scope widened** (`_crossing_junctions`): one crossing junction now
  admits ONE above member and N ≥ 1 below members; >1 above member
  refused by name (the above×above interface corner has no measured
  convention). The fill machinery was already N-general — the corner
  loop gained a coincidence assert (every in-plane value-1 end stands
  at the ONE crossing node) and the orientation-carried sign prose.
- **The buried hub is an allowed OTHER junction** (below-side,
  off-plane only): probe35's cancellation (fan M+hub ≡ M through the
  hub's KCL row) is the licence; above-side/in-plane other junctions
  stay refused by name.
- **PRODUCTION DEFECT found+fixed by the ladder**: `_buried_serve_plan`
  θ-floor-validated the transmitted cross grid on crossing decks — a
  grid the designed direct evaluation never builds — so a node-graded
  crossing mesh (quadrature nodes 0.84 mm deep) refused on the cost law
  of an unbuilt grid. The plan now skips the cross-medium section
  exactly where the fill skips the grid.
- **THE ADJUDICATION (probe38): the composition is NOT ε̃=1-exact past
  K = 2 — the residual is a node-mesh CONVERGENCE class, not
  bookkeeping.** |fan − free-space-5-wire-truth| at ε̃ = 1:
  N=1 0.0043 Ω (probe37's class, builder validated) → N=2 0.1327 →
  N=4 0.2269; the hub spelling lands the SAME residual (0.2194) with
  no coincident wires and K=2 at the interface, and node-grading
  shrinks N=4 steadily with no plateau: 0.2269 → 0.1487 (g1
  [14,4]/[22]) → 0.1060 (g2 [20,6]/[30]). Sign-class errors are
  excluded by magnitude (a wrong corner sign is the −1000j/1e5 class).
  Cross-wire touching pairs cancel exactly in the diff (both fills use
  the same offedge quadrature) — the residual lives in the restored
  multi-tent by-parts terms' quadrature. Gate `test_g524_7` holds the
  measured envelope (0.30) and names grading, not corner loops, as the
  tightening lever.
- **probe39 (ends scope): NULL with a bonus.** Stripping the 5
  hub-tent ends from the ends tables reproduces the unstripped hub
  answer TO THE DIGIT (32.8076−340.9092j both) — probe35's cancellation
  (hub by-parts terms cancel through the hub's KCL row) now measured
  through production, and the ends tables are NOT the residual's
  source. No production change; the tables stay as they are (the hub
  terms are exactly-cancelling flops, not error).
- **The two screen spellings are DIFFERENT STRUCTURES, not one deck
  spelled twice**: the fan's N coincident rises are a bundle conductor
  — the spellings' ε̃ = 1 TRUTHS sit ~9 Ω apart (33.14−332.26j fan vs
  32.80−341.13j hub), and each fill tracks its OWN truth at the same
  0.22 class. The handoff's "gate hub ≡ N-rises" is therefore not a
  valid gate and was dropped; each spelling carries its own ε̃ = 1
  collapse gate at the measured envelope (`test_g524_7` fan 0.2269,
  `test_g524_8` hub 0.2194, both gated 0.30).
- Prose served: `_REFUSE_CONTACT_WITH_BURIED` + eznec `_serve` now
  point the respelling at whole SCREENS (fan widening + hub spelling);
  `golden_buried_anchor_nec5` regenerated with the four-radial
  convention note (engine re-print verified identical, x1–x8).
- **Soil-A banks are RECORDS, not anchors** (probe38, all in
  `results/probe38-fan-widening.json`): fan base-mesh
  143.9327−26.2135j, fan node-graded 142.6822−33.5867j — a **7.48 Ω
  mesh move**, the ε̃=1 convergence class amplified ~30× by the lossy
  transmitted kernels — hub 140.9839−43.6025j (17.6 Ω from the fan:
  two structures). No soil-A anchor gate exists for the fan class at
  practical meshes; the serve's correctness gates are the ε̃=1
  collapses, and the K>2 node convergence rate is the filed follow-up.
  (Engine four-radial print 90.051−70.731j sits 69.9 Ω from the
  connected fan — the detached-stake convention difference, recorded
  next to `ANCHOR_FOUR_RADIAL`, never a target.)

### A-3 opens in the same sitting: the #680 measurement round (probe40)

- PR #676 MERGED (rebase, main 77a52a5); slow lane back to 6m39s (the
  eps1 collapses moved to the merge-to-main `crossgate` lane; g524_8
  retired — probe39 measured its unique content at exactly zero).
- **probe40 (results/probe40-accel-profile.json + probe40-profile-g1
  .txt): `six_point` = 99.6 % of a warm crossing solve** (157.9 of
  158.5 s on g1 K=2; all else 0.6 s); 15,385 points @ 10.26 ms/pt,
  ~40 `_adaptive_segment` calls/pt (608k), head 77.3 s ≈ rays 76.1 s;
  tottime of every named frame ≤ 5 s ⇒ the cost is small-array Python
  dispatch, the 20–100× C++ profile.
- **Census: the fan cross mesh is EXACTLY 4.00× duplicated** (80,032
  pairs, 20,008 unique exact triples; K=2 = 1.00×) — symmetry produces
  IEEE-exact duplicate distances.
- Plan posted to momwire#680: U1 exact-triple memo (bit-identical,
  fan ÷4, ~a day) → U2 C++ twin (port the WALK; complex-Hankel Amos
  dependency is the flagged risk; parity per the probe ledger at 1e-12
  RELATIVE, never bit; crossgate re-run on the twin) → U3 OpenMP over
  unique points. Follow-on scope: the same adaptive core serves the
  grid fills. U1 BUILT this sitting (branch `680-u1-triple-memo`).

## Session 9 (2026-08-27) — A-3 U2: the C++ twin of the designed walk
## (momwire branch `680-u2-cpp-twin`)

- **U2 SHIPPED: `_near_interface_accel`, a WALK port of `six_point`**
  (shared walk + limit, the house twin rule). The head detour and
  real-axis mid ride the #568 contour engine header UNCHANGED
  (`adaptive_segment` / `head_contour` / the complex J₀ kernels were
  already faithful, gated twins); the one structure the engine did not
  carry — the rotated-ray tail λ = λ_top + t·e^{±jπ/4} — is transcribed
  with every measured rule intact (panel start at the λ0 scale, the
  underflow-quiet rule, the 60/s kill cap, ρ = 0 single ray, the
  −γ₊/+γ₋ derivative bookkeeping).
- **scipy/xsf VENDORED** (`momwire/extern/xsf`, commit 261e034,
  BSD-3, header-only C++17): `cyl_hankel_1/2` at complex argument =
  scipy.special's own Amos translation (Boost has no complex Hankel).
  Its underflow contract is load-bearing and verified: Amos underflow
  (`nz != 0` → SF_ERROR_UNDERFLOW) returns the exact 0.0, never NaN —
  precisely the quiet-panel rule. Values spot-checked bit-identical to
  installed scipy 1.18.0; gates RELATIVE anyway (versions drift).
- **Own extension at C++17** behind its own capability flag
  `near_interface_680` + `MOMWIRE_NEAR_INTERFACE_FORCE_NUMPY` /
  `_FORCE_NUMPY` switches (the below-fills dispatch pattern);
  `_accelerators` stays gnu++11 byte-untouched. MANIFEST grafts the
  vendored tree; the wheel test-command now asserts BOTH extensions
  import and the flag is up.
- **The U1 memo layer stays in Python**: `designed_tables` dedups
  first and hands the batch only unique triples. **U3's content
  shipped inside U2**: the batch entry runs OpenMP `dynamic` over the
  unique-triple list (the engine's #568 reentrancy contract makes it
  free), GIL released — so there is no separate U3 unit left to build.
- **Parity ledger** (`tests/test_near_interface_accel_680.py`, fast
  lane): corner (ρ=a, z=z′=0), ε̃=1 identity points (identity held BY
  the accel at ≤1e-12, not just tracked), high-σ underflow far pair,
  ρ=0, kill-cap, tiny-s — worst measured **3.9e-16 relative**, gated
  1e-12 RELATIVE, never bit. `test_g524_3_triple_memo` now forces
  numpy (its counting monkeypatch + bit-equality pin the REFERENCE).
- **Integrated gates through the accel path, all green**: g524_4
  soil-A anchor passed in 16 s (the solve was ~158 s); the crossgate
  lane's three ε̃=1 collapses passed in **13.4 s** (was ~18 min
  serial); full fast lane 6469 passed / 85 skipped / 6 xfailed in
  4:27.
- **Speed proof (probe40 `accel` subcommand, banked in
  results/probe40-accel-profile.json next to the untouched Python
  baseline)**: g1 mesh 15,120 unique triples — **0.222 ms/pt
  parallel batch** (inside the 0.1–0.5 ms target), 1.58 ms/pt serial,
  11.44 ms/pt numpy walk on the same sample; **g1 K=2 solve
  158.5 → 4.3 s (37×)**, Z = banked 138.7671−102.9889j; **fan soil-A
  174 → 6.6 s** (26× on U1, 118× vs pre-U1), Z = probe38's record
  **143.9327−26.2135j TO THE DIGIT**. Crossing solves are now
  grid-fill/other-bound; momwire#674's K>2 grading rungs are
  affordable.
- The corner `six_point` call in `_crossing_fill` (one V(a) per fill)
  deliberately stays on the Python walk — the orientation-carried sign
  −σσ′·c1·V(a) lives there untouched.
- Follow-on (recorded, not this sitting): the same C++ core could
  serve the below/transmitted GRID fills' `_adaptive_segment`/`_head`
  Python paths; v0.41.0 release stays DEFERRED.

## Session log

- 2026-08-27 session 9: A-3 U2 (branch `680-u2-cpp-twin`) — scipy/xsf
  vendored (261e034, complex Hankel), `_near_interface_accel` C++17
  extension = walk port of `six_point` on the #568 engine header +
  transcribed rotated-ray tail; U1 memo stays in Python, OpenMP batch
  over unique triples (U3 delivered inside U2); parity ledger worst
  3.9e-16 rel (gate 1e-12); g524_4 16 s, crossgate 13.4 s (was
  ~18 min), fast lane 6469 green; 0.222 ms/pt parallel, g1 solve
  158.5→4.3 s, fan soil 174→6.6 s with probe38's record to the digit.
  NO release (v0.41.0 still deferred).

- 2026-08-27 session 8: the FAN WIDENING (branch `524-fan-widening`) —
  scope widened to 1 above × N below + the buried-hub OTHER junction;
  cross-grid plan defect found+fixed (θ-floor on an unbuilt grid);
  adjudicated: composition NOT ε̃=1-exact past K=2, a node-mesh
  convergence class (0.0043/0.1327/0.2269 for N=1/2/4, →0.1060 under
  grading, hub 0.2194, hub ends cancel to the digit), spellings are two
  structures (~9 Ω apart); soil-A banked as records (fan
  143.93−26.21j, 7.48 Ω mesh envelope, hub 140.98−43.60j); gates =
  ε̃=1 collapses (g524_7/g524_8 at 0.30) + fast scope/labeling/plan
  rows; prose+capture regenerated; momwire#674 filed (K>2 convergence
  study). AK: three buried catalog designs built on a worktree branch
  (`buried-radial-catalog`, delegated build, reviewed) — BLOCKED on
  the momwire release + pin bump before its PR can merge.

- 2026-08-27 session 7: PRODUCTION integration (branch
  `524-crossing-serve`, rebased onto main @ 12ff673 mid-session) — all
  five restart items done: the crossing serve ships (`_near_interface`
  + `_crossing_fill` + routing, split dofs, bit-parity with the bank),
  ladder g0–g3 banked, prose/gates/capture adjudication-consistent,
  issues #666/#667 filed, P3 adjudicated (class stays refused,
  envelope 18.0, rise respelling served + ε̃=1-exact, corner
  orientation-sign defect found and fixed). PR next.
- 2026-08-26: plan written; queue item 1 (fan re-bank + card banking)
  landed as momwire PR #658 first.
- 2026-08-26 (same session, user go): tasks 1–3 run — junction wiring
  verified (grounded K=2, no KCL), baseline 24.82 − 1013.56j (957 Ω miss),
  constraint rows measured irrelevant, poison localized to the below-arm
  fill entries. P0 ε̃=1 collapse audit (`probe4_collapse.py`) launched —
  result goes here. USER DECISIONS logged: razor buried parity (#651),
  #532 signing plan + scipy census.
- 2026-08-26 session 3: probes 8–13 (see the session-3 section above) —
  charge axis exhausted, merged dof ≡ V row measured, corner term found
  and measured off probe5's residual, delta* refuted at ×3. Razor parity
  shipped as momwire PR #660. Next sitting = the reflected-family
  derivation (item 1 above).
- 2026-08-26 session 5: probes 21–29 (section above) — designed
  near-interface kernels built and pinned (`corner_tables.py`,
  `DERIVATION-NEAR-INTERFACE.md`), gate 1 passed (5.7e-11), the
  radius rule named, "drop spellings are truncation-regularized"
  named, gate 2 passed via the complete spelling (divergence dead,
  mesh-stable, constraint-free), mono lesson measured, ε̃=1
  adjudicator passed at 0.002 %. Remaining: engine-convention
  adjudication (items 1–3 above). Restart =
  `NEXT-SESSION-524-ADJUDICATION.local.md`.
- 2026-08-26 session 6: probes 30–34 (section above) — the three
  adjudicators run and decided: engine junction currents violate AGARD
  divergently (probe30) while momwire-complete's satisfy it emergently
  (probe31); both conventions meet only at high σ where the fiction is
  exact (probes 32/33, with two designed-evaluator scope fixes); no
  consistent-omission spelling reproduces engine Δ (probe34). Verdict:
  ship exact-EM complete; engine crossing print = different experiment.
  Restart = `NEXT-SESSION-524-PRODUCTION.local.md`.
- 2026-08-26 session 4: probes 14–20 (section above) — same-medium
  by-parts derivation DONE and PINNED (`DERIVATION-SAME-MEDIUM.md`),
  exact spelling scored and refuted, straddling/single-wire ≡ merged ≡
  V-row measured, corner truncation 9.58× discovered, grading closes the
  mesh axis (garbage self-similar; B+split → stub invisible; every
  continuity mechanism blows up worse under grading). Verdict: the
  missing physics is unreachable without trustworthy NEAR-INTERFACE
  transmitted kernels — next sitting = the corner asymptotics (item 1
  above). Restart = `NEXT-SESSION-524-NEAR-INTERFACE.local.md`.
