# Feed-drift census — issue #459

**Date:** 2026-07-20
**Tool:** `scripts/bench_feed_drift.py` (PyNEC, free space, ladder N = 21/61/161, seg-cap 3000)

## Question

#459 asks whether the two designs carrying pinned-feed exemptions
(`wire/terminated_longwire`, `wire/sterba_tl`) are the only members of the
"high-Z fixed-feed" class, or whether other catalog designs silently drift under
mesh refinement because their feed sits at a mesh-unstable point (a near-open
delta-gap, or a TL/NT attachment port). #435 made feed segments refine with the
mesh across the catalog; the two exemptions were the drifts *caught* at the
time. The census sweeps all 91 designs to find the ones that weren't.

## Method

Per design, solve the driving-point impedance up an N-ladder and ask two things:
does it still move at the finest mesh (no plateau within 2 % of the finest), and
is the feed at a mesh-unstable point — |Z| > 500 Ω (near a current null) or a
TL/NT/transformer port. Both true ⇒ **suspect**. Free space keeps it cheap; the
delta-gap segment sensitivity is a *local* effect, and a ground spot-check
(below) confirms the drift is ground-independent.

**Validation:** the two known exemptions read CONVERGED — `terminated_longwire`
(|Z| = 5295 Ω, conv@21) and `sterba_tl` (conv@21). Their pins hold the feed
segment fixed, so the ladder is flat; they correctly do *not* re-flag. A
regression that unpinned them would put them back on the suspect list.

## Result — the class is ~10 designs, not 2

**Near-open feeds (high |Z|, same physics as `terminated_longwire`):**

| design | \|Z\| | drift | converges? |
|---|--:|--:|---|
| `arrays.delta_looparray_with_tls` | 16 703 Ω | 100 % | never |
| `wire.lazy_h` | 5 044 Ω | 14.7 % | never |
| `wire.vbeam` | 3 516 Ω | 4.9 % | never |
| `wire.rhombic` | 717 Ω | 3.3 % | @61 (borderline — drops off) |

**TL/NT-port feeds (drift tied to the port attachment, not the feed |Z|):**

| design | \|Z\| | drift (free) | drift (pec) |
|---|--:|--:|--:|
| `verticals.dominator` | 32 Ω | 31.7 % | 30.7 % |
| `verticals.challenger` | 33 Ω | 24.8 % | 23.4 % |
| `wire.zepp` | 23 Ω | 22.2 % | 22.1 % |
| `wire.doublet_ladder_tuner`, `verticals.inverted_l_tmatch`, `loops.skyloop_lmatch`, `wire.efhw_sloper`, `wire.edz`, `broadband.lpda` | — | 6–94 % | (same class) |

The pec column shows the port drift is **not** a free-space artifact — it
persists identically over ground. These want #459's question 2: a
length-normalized TL/NT port stamp so port impedance stops scaling with the port
segment.

**Not this class** (drift from other causes, listed for the record):
`dipoles.short_dipole_loaded` drifts 137 % at |Z| = 17 Ω — a lumped-load
convergence issue, not the feed. `elt_whip` was skipped (benchmark-scale, over
the seg cap); `bowtiearray2x4` skipped its two finer rungs.

## The bs2 basis-extension levers do not (yet) fix it

Two momwire BSpline-d2 features looked like they might make a near-open feed
converge *without* pinning (so the design could refine like everything else):

- `feed_smoothing_factor` (cos² source bump): its width is `α · h_feed_segment`,
  i.e. it **scales with the segment**, so under refinement it shrinks with the
  gap and does not decouple from the mesh. On refined `terminated_longwire` it
  made the drift *worse* (|Z| 4626 → 3673 vs the delta-gap 3809 → 3527).
- `use_singular_enrichment` (extra end basis): raises
  `NotImplementedError` in `compute_y_matrix` — the enrichment path isn't wired
  into the Y-matrix (network) solve the reducer uses.

Both would need momwire work to help here: a *fixed physical* smoothing width
(independent of the segment), or enrichment plumbed through the Y-matrix path.
That is #459 question 1/2 territory (momwire-side), not a builder change.

## Confirmatory pin-test — the heuristic over-flags

The suspect predicate (drift + high-|Z|/port) is *necessary but not sufficient*.
The decisive question is: **does pinning the feed to a fixed-length segment
flatten the ladder?** Re-running each suspect refined-vs-pinned (PyNEC, free
space, feed edges forced to 1 segment):

| design | drift authored | drift pinned | pinning fixes it? |
|---|--:|--:|---|
| `wire.rhombic` | 2.4 % | 0.7 % | yes (but already converged @61) |
| `wire.lazy_h` | 14.7 % | 6.9 % | no — still drifting |
| `wire.vbeam` | 4.9 % | 7.5 % | no — worse |
| `verticals.dominator` | 31.7 % | 31.7 % | no — unchanged |
| `wire.doublet_ladder_tuner` | 44.2 % | 44.2 % | no — unchanged |
| `verticals.challenger`, `wire.zepp`, `inverted_l_tmatch`, `skyloop_lmatch`, `efhw_sloper`, `edz`, `lpda` | 3–94 % | ≈ or worse | no |

**Only `terminated_longwire` is genuinely pin-fixable** (confirmed separately:
pinned ladder flat at ~960 − 5240j, ~1 %). The difference is structural: its fed
edge is a *substantial* 0.3 m segment, so refining it shrinks a real gap and
pinning holds it fixed. The near-open wire antennas (`lazy_h`, `vbeam`) already
have ~1-segment gaps — their drift is the **arms refining at a high-Q operating
point**, not the feed, so pinning is a no-op. The TL/NT-port cluster is unmoved
by feed pinning (`dominator`, `doublet_ladder_tuner` identical), so its drift is
the *port attachment*, not the driven segment.

## Conclusion & recommendation

1. **The fixed-feed exemption class is just the two already pinned**
   (`terminated_longwire`, `sterba_tl`). #459 question 3 answer: **no latent
   pin-fixable members.** No new helper application is warranted; a helper that
   only re-expresses two existing magic-number pins is churn.
2. **The census's other drifters are two *different* phenomena**, not #459's
   fixed-feed class:
   - **Near-open high-Q** (`lazy_h`, `vbeam`, `delta_looparray_with_tls`): the
     whole current distribution is mesh-sensitive at a near-open resonance;
     inherent, not a feed model. Worth its own issue if the workbench slider on
     these needs to read as "converging."
   - **TL/NT-port** (`dominator`, `challenger`, `zepp`, `doublet_ladder_tuner`,
     `inverted_l_tmatch`, `skyloop_lmatch`, `efhw_sloper`, `edz`, `lpda`): drift
     tied to the port attachment, ground-independent, not fixed by pinning →
     #459 question 2 (momwire length-normalized port stamp). Filed separately.
3. The census tool stays as the regression metric — but read it *with* the
   pin-test; the flag is a candidate, not a verdict.
