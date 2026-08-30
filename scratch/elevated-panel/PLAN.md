# The elevated-detached panel — the first honest same-antenna
# cross-engine comparison of the buried-radial space

Started 2026-08-28, immediately after #567 closed with the phase-3
disposition. User goal (Steve, this session): "compare NEC-5 buried
radial designs with momwire bs2/razor to say we have implemented
something in this space" — with refusals kept where we think an answer
would be wrong.

## Why this class

The #567 proof says the fiction only poisons decks where a wire TOUCHES
the interface. An ELEVATED vertical over DETACHED buried radials has no
contact node in either engine: both solve real coupled EM (parasitic
coupling through the soil, the Yagi mechanism), so agreement is
meaningful, disagreement is a genuine formulation difference, and — the
key licence — the class is SAME-CONVENTION, so it may be gated (the
house rule forbids gating cross-CONVENTION agreement only).

## The deck family (derived from the banked #567 anchors — one knob: h)

Exactly the anchor geometry with the base lifted by h: 10 m vertical
(top 10+h, base h), fed 4.3333 m from the TOP (EX 4,1,7 at x1 — the
anchor feed spelling, kept so h → 0 joins the banked contact anchors
92.130−70.141j / 90.051−70.731j), one or four detached 5 m radials
15 cm down, soil A (eps_r 13, sigma 0.005), 7 MHz. Heights h ∈
{0.25, 0.5, 1.0} m. Engine ladder: odd multipliers x1/x3/x5 (fed
segment stays centered: EX segment 7/20/33). momwire: matched x1 mesh
+ x2 refinement rung for its own envelope.

Expected shape: |Z_momwire − Z_nec5|(h) shrinking as h grows, both
engines' own ladders converged tighter than the cross-engine gap at
h = 0.25, and the h → 0 limit showing the fiction's 13–17 Ω signature
switching on. If the h ≥ 0.25 rows meet inside combined convergence
envelopes: bank as anchors + gates via the capture-script ritual
(momwire PR, delegated), and the panel becomes the sequel post's
centerpiece.

## Traps carried in

- Feed arclength 4.3333 is measured FROM THE TOP (wire spelled
  top → base); an improvised base-relative feed is silently ~50 Ω
  wrong (probe35 v2's lesson).
- Engine runs via `NEC5Engine.run_deck` exactly as
  `scripts/capture_buried_anchor_nec5.py` does; printed impedances
  only; NEC-5 internals never read or quoted (courtesy rule).
- The EZParam A/B (x13 asymptotic workaround) spread was 0.0000 on the
  contact decks (shallow-radial safe regime); spot-check one elevated
  deck the same way before banking.
- Odd multipliers only (even splits straddle the feed center).
- momwire decks need NO seeding — this class serves through the front
  door (elevated above + detached below). If anything refuses, that is
  a finding, not a workaround site.

## Round-1 results (2026-08-28, all in results/probe-e1.json)

- **The class serves through the front door on both sides** and both
  instruments converge tightly (engine x3→x5 ≤ 0.31 Ω raw / ≤0.007 in
  Δ; momwire d1→d2 ≤ 2 Ω raw / ≤0.001 in Δ).
- **Raw physics**: the elevated-detached family is the INSULATED-BASE
  answer (~21–25 − j975–1015 — the probe28 class, as the counterpoise
  discussion predicted). Radials perturb by only ~0.2–1.6 Ω = genuine
  parasitic-scale coupling.
- **The raw cross-engine gap is a near-constant −28 Ω X offset**
  (±0.4 over all 9 deck×height combos incl. the no-radial ref) — the
  feed-gap convention class (the buried post's "~35 Ω convention
  physics"), NOT soil physics. Differential physics agrees well in raw
  numbers (height slopes −2.8 vs −3.0 Ω/m; radial-count effect ~0.5 Ω
  both).
- **The delta instrument (Z − Z_ref, cancels the feed convention):
  converged DISAGREEMENT on the buried-radial coupling, 2.9–4.7×,
  GROWING with radial depth** (0.15→2.0 m ladder at h=0.5: engine
  −0.181+0.470j → +0.168+0.000j; momwire −0.097+0.146j →
  +0.028+0.023j). momwire's Δ decays like a real transmitted field;
  the engine's falls off too slowly — the fingerprint of its
  documented fifth-surface defect (depth-flat below-ground E_z,
  phase-0 record, empymod siding with our kernels at 7e-5). The
  defect now measured at the IMPEDANCE level, printed numbers only.

## Round-2 results (probe_e2_dipole.py — the RESONANT family; the raw
## apples-to-apples panel; results/probe-e2.json)

- The E1 offset's mechanism was IDENTIFIED before redesigning: engine
  EX 4 ≡ EX 0 to the digit, while momwire's three feed models (point /
  segment / smoothed) spread 26 Ω among THEMSELVES on the |Z|≈1000
  family — feed-region parasitic capacitance, ΔZ ≈ −jωC·Z² with
  C ≈ 0.6 pF between formulations. Prediction: resonant-class decks
  (|Z|≈80–100) shrink it ~150×.
- **Confirmed.** Family = center-fed 21 m vertical dipole, lower tip at
  h ∈ {0.25, 0.5, 1.0} over the same radials. Raw cross-engine gap:
  **0.33–1.67 Ω on ~95 Ω decks (≤1.7 %)**, with the engine's own
  ladder still moving ~0.9 Ω/rung toward momwire's converged value —
  converged endpoints ~1 Ω or less apart. THE raw panel; no offset to
  explain.
- **The buried-coupling disagreement persists** on the resonant family
  (delta instrument): engine sees ~3× momwire's radial effect (fan
  h=0.25: 0.090+2.380j vs −0.450+0.728j; lone: 0.150+0.857j vs
  −0.075+0.240j) — consistent with E1's depth-ladder fingerprint
  (the engine's fifth-surface / depth-flat below-field defect), now at
  practically-meaningful size on an antenna class people build.

## Round-3 results (probe_e3_knotfeed.py — the KNOT FEED closes E1;
## user suggestion 2026-08-28)

- **The E1 −28 Ω offset was bs2's feed spelling, not an irreducible
  convention**: the split-wire + node_gaps KNOT FEED (the #449 taper
  spelling — C0 kink restored at the fed knot; feeds=[] trap minded)
  collapses it. h=0.5 raw gaps vs engine x5: ref 0.099 (d2) / lone
  0.284 / fan 0.775.
- Envelope honesty (d3 rung): momwire's knot-feed ladder still climbs
  (+1.6, +0.7 per rung: −983.2 → −981.7 → −981.0) while the engine's
  climbs +0.3/rung (−983.5 → −981.7) — the CONVERGED values agree at
  the **~0.5–1 Ω level on |Z| ≈ 982 (0.05–0.1 %)**. Quote ladders,
  never a single lucky rung (the 0.099 was two moving ladders
  crossing).
- The residual raw gap now ORDERS BY RADIAL COUNT (ref 0.10 < lone
  0.28 < fan 0.78 at d2): what remains in the raw numbers IS the
  buried-coupling disagreement. momwire's coupling deltas are
  feed-independent (knot ≡ point to ~0.01), engine still ~3×.
- E2 (resonant) with the knot feed: essentially unchanged (~0.5–1.2 Ω
  class) — the feed artifact was already Z²-suppressed there; E2's
  ~1 Ω residual is genuine formulation-class difference.
- NOTE for #449's recorded escalation: this panel is now a SECOND
  CONSUMER of the split+node_gaps knot-feed spelling (knot
  multiplicity stays the recorded escalation; the spelling serves).
- Canonical momwire spelling for E1-family anchors = the knot feed.

## Round-4 results (the SEAM route — one card file, both engines;
## user question 2026-08-28)

- `python -m momwire.eznec <deck> <printout>` serves the IDENTICAL card
  files, buried detached radials included (results/seam/):
  * E2 fan h=0.25 x1: seam 100.32+20.31j vs engine 100.08+20.09j —
    **0.33 Ω (0.3 %) with zero hand-translation**; ref 100.77+19.59j
    vs 100.00+17.73j (2.0 Ω at x1, both ladders still moving).
  * E1 ref (|Z|≈980): seam 23.03−968.19j vs engine −983.49 — the seam's
    EX mapping is a THIRD feed convention, ~15 Ω on the opposite side
    of the delta feed. Consistent with ΔZ ≈ −jωC·Z² throughout.
- **momwire#703 FILED**: seam should adopt the knot-feed spelling for
  EX (measured spelling ladder in the issue) — or at least document
  the Z² scaling. Second consumer of the #449 split+node_gaps
  spelling, noted against its knot-multiplicity escalation record.

## Round-5 results (probe_e4_empymod.py — the three-instrument
## adjudication: ATTRIBUTION SEALED)

- **momwire ≡ empymod on the below-ground illumination of this exact
  geometry: worst residual 0.6 %, median 0.5 %**, over 8 points
  (x ∈ {1.0, 2.5} × depth ∈ {0.15, 0.5, 1.0, 2.0}), after ONE global
  α = −1.0056 (the fill's sign convention + 0.6 % scale). Same ⟨f,E⟩
  functional on both sides; momwire's side harvested through the
  PRODUCTION cross fill (probe-wire trick, zero convention risk);
  empymod per the phase-0 harness conventions verbatim.
- **Depth-decay profiles identical to 3 decimals** (x=1.0:
  1/.679/.422/.207 both; x=2.5: 1/.887/.736/.492 both).
- **The engine's below-ground E_x is qualitatively wrong**: x=1.0
  flattens at depth (1/.602/.326/.286); x=2.5 NON-MONOTONIC
  (1/.601/.198/.398 — rises going deeper). Printed NE tables only.
  The fifth-surface defect, exhibited deck-specifically.
- Caveat, recorded: E4's momwire/empymod source current fed at
  arclength 4.3333, the engine's NE deck at its node 20 (4.4444) —
  a 0.11 m source difference that cannot produce non-monotonic
  observer-depth behavior; the seal stands on the shapes.
- **VERDICT: the panel's buried-coupling disagreement is the engine's
  below-ground field defect — measured, no longer inferred.** The
  sequel post's G3 attribution is publishable.

## ERRATUM DISCOVERED THIS SESSION (#703 review cascade — see the
## momwire#703 builder report + session record): EX 4,tag,k feeds the
## FAR NODE of segment k (arc k·h from the wire start) — confirmed by
## node reconstruction on the crossing AND anchor captures (N7 =
## 0.9999998) and by an engine-vs-momwire feed-position overlay sweep
## (agree ~1 Ω at every matched arc). The banked "EX 4,1,7 ↔ arclength
## 4.3333" equivalence is off by h/2: at the corrected feed the #567
## M-only misses collapse 12.91 → 3.47 (lone) / 17.16 → 4.98 (fan).
## E1/E3 panel conclusions need re-derivation at matched feed; the
## #567 record needs a correction (awaiting Steve's call on scope).

## Next steps (not run this session)

1. Deck-specific empymod illumination check (third instrument on THIS
   geometry) to tighten the attribution for the post.
2. Panel axes for the post: σ ladder, radial count 1→8, depth ladder
   on the fan.
3. Bank ref+elevated decks as SAME-CONVENTION anchors + gates in
   momwire (capture-script ritual, G-rows; gating legitimate — same
   convention) via a delegated PR.
4. The sequel post: implemented-and-compared panel + the depth-ladder
   attribution + the #567 proof for why detached-contact is excluded.

## Round-6 results (probe_e5_matched.py — the E1/E2 RE-DERIVATION at
## matched feed, post-#706; 2026-08-28 evening; results/probe-e5.json.
## SUPERSEDES round 1's raw table, round 2's raw table, and round 3's
## raw-gap numbers; the Δ-instrument conclusions of rounds 1–2 are
## CONFIRMED, not just presumed feed-independent)

Corrected frame: E1 feeds the 4.6667 NODE on both sides (`EX 4,1,7m` —
integral at EVERY multiplier now, engine laddered x1/x3/x5/x8; momwire
knot split 4.6667/5.3333 = 7d/8d uniform-h segments, d1–d3, plus the
point feed d1/d2 for the spelling-spread record). E2 re-meshed 22m
segments so the CENTER is a node (`EX 4,1,11m`; the old 21m family's
engine feed drifted 10.5+0.5/m per rung), momwire [22d] fed at 10.5.

- **E1 raw, converged-vs-converged (Richardson tails, engine p≈0.65,
  momwire p≈0.48): gaps 0.26–1.17 Ω on |Z|≈960 = 0.03–0.12 %.**
  Round 3's "~0.5–1 Ω converged" magnitude survives, now honestly
  derived — but its 0.099 single-rung number and its two-error frame
  are void. The momwire point feed sits ~26 Ω on the OTHER side of the
  engine (feed-region convention, the Z² law): knot feed = canonical
  for the high-Z family, confirmed in the corrected frame.
- **E2 raw, converged: ref 0.19–0.22 Ω, lone 0.29–0.44, fan 1.13–1.53
  on ~95 Ω decks — the residual gap ORDERS BY RADIAL COUNT**: what
  remains in the raw resonant numbers IS the buried-coupling
  disagreement, visible without any Δ instrument.
- **Δ instrument at matched feed (deepest rungs): engine/momwire
  coupling ratio 2.05–3.62 (E1), 2.79–5.15 (E2)** — the rounds-1/2
  coupling finding CONFIRMED in the corrected frame; direction
  unchanged (engine's radial effect too big, X-dominant; momwire's ΔR
  slightly negative where the engine's is positive). E4's attribution
  (momwire ≡ empymod 0.5 % below ground; engine NE non-monotonic)
  stands as the mechanism.
- Case-study numbers come from THIS round (results/probe-e5.json),
  nothing from rounds 1–3.
