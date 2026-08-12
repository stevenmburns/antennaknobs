# 2026-08-12 — Why NEC-5 needs Richardson pairs: the harness is exonerated (#890)

## Goal

The #872 study made (N, 2N) pair extrapolation the census-grade NEC-5
recipe without establishing *why* the raw ladder walks ~O(1/N) when bs2
settles at a single mesh. A clean first-order systematic is exactly what
a half-segment harness offset would produce, and the census had already
caught one harness-side idiom artifact this cycle (momwire#300's
1-seg-bridge feed), so #890 demanded the harness-side hypotheses be
discriminated before the walk may be pronounced intrinsic.

Instrument: `scripts/bench_nec5_walk_why.py` (sections A–F); artifact
`scratch/nec5-walk-why-890.json`. Probe decks per the issue's acceptance
set: a thin 5 m dipole in free space at 28.5 MHz (bs2-anchored), the
`specialty.hentenna` phase-2 deck, and the phase-3a 0.048 λ Sommerfeld
dipole over ("finite", 13, 0.005).

## Verdict — hypothesis 4 survived; the march is NEC-5's own

**No harness defect exists.** Source placement, source type, readout
convention, deck geometry and the runner/parser were each given a
discriminating experiment, and every one came back exact or orders of
magnitude too small. The O(1/N) impedance march is intrinsic to NEC-5's
knot-source discretization; the (N, 2N) Richardson pair stays the
permanent census-lane recipe, now with the mechanism question closed.
No phase-3a or phase-5 re-runs are owed (those columns were never
carrying a harness error).

## The kill table

| # | hypothesis | experiment | result | verdict |
|---|---|---|---|---|
| 1a | source-placement: spelling bias into one adjoining segment | end 2 of seg N/2 vs end 1 of seg N/2+1 (same knot, other side), all 3 decks × all rungs | \|ΔZ\| = 0 exactly, 13/13 rungs | **dead** — the gap is knot-symmetric |
| 1b | source-placement: hidden half-segment offset | feed slid one whole segment off-center; \|Z(slide)−Z(base)\|/2 bounds any half-segment term | bound is 9–400× smaller than the walk residual at every rung, and shrinks ~O(Δ²) while the walk shrinks O(Δ) | **dead** — wrong size *and* wrong order |
| 2a | gap construction differs by source type | same knot driven as EX 0 (1 V) and EX 4 (1 A, NEC-5-native), full ladders | Z identical to every printed digit at every rung; identical Richardson orders and Z∞ (ΔZ∞ = 0.0000 Ω) | **dead** — walk is source-type-independent |
| 2b | readout: AIP row's I is a mis-convention current | EX 4 genuineness + asymmetric-feed (0.25L knot) AIP-vs-Wire-Currents cross-check | EX 4's AIP row carries I = 1+0j exactly, V = Z read against a *known* current — and still walks identically; AIP I at an asymmetric feed is NEC-5's own knot current (between the flanking segment centers, matching neither), Z = V/I to print precision (≤4 mΩ) | **dead** — with EX 4 no readout convention is even in play |
| 3 | deck writing: parity coercion compares mismatched geometry | per-wire counts actually solved on the hentenna ladder + bs2 count-sensitivity | coercion shifts ≤1 wire by +1 segment per rung (endpoints untouched by construction); bs2 moves 0.0006 Ω between adjacent census meshes vs NEC-5's 1–6 Ω per-rung walk | **dead** — 3–4 orders too small |
| 4 | intrinsic knot-source discretization | LLNL sample decks (7 shipped models incl. Sommerfeld) through `NEC5Engine._run`, AIP rows vs the shipped reference printouts, both sides read by the engine's own parser | 15/15 AIP rows bit-identical (max \|ΔZ\| = 0) | **survives** — runner + parser reproduce LLNL's published numbers exactly |

## Numbers behind the rows

Walk residual |Z(N) − Z∞| vs the half-segment placement bound
(|Z(slide)−Z(base)|/2), free-space dipole:

| N | walk | placement bound |
|---|---|---|
| 20 | 7.75 Ω | 0.86 Ω |
| 80 | 1.96 Ω | 0.05 Ω |
| 320 | 0.61 Ω | 0.003 Ω |

Same shape on the Sommerfeld deck (7.19 Ω vs 0.79 Ω at N=20) and the
hentenna (1.94 Ω vs 0.005 Ω at N=81). A placement error cannot be two
orders too small *and* decay a full order faster than the thing it is
supposed to explain.

Richardson orders/limits (EX 0 = EX 4 identically): dipole free 0.84 →
67.601−29.560j (bs2 N=321: 67.626−29.522j, <0.07 Ω apart); hentenna
1.42 → 43.127+38.548j (phase-2 bs2: 43.4+39.7j, ΔΓ 0.012-class);
Sommerfeld 0.048 λ 1.00 → 62.799−21.626j (phase-3a nec2c
62.89−21.56j). The limits were never in question — phase 1's aligned
ladder had already matched the all-engines single-wire arbiter — but the
dipole anchor closes the acceptance set.

Sample-deck reproduction detail: all seven shipped models (LP12,
BoxWhip, HLoopBoxPEC, Outback f7/f30 free + Sommerfeld) ran through the
engine's stdin/tempdir protocol and produced ANTENNA INPUT PARAMETERS
rows identical to LLNL's shipped reference printouts to every printed
digit — including the Sommerfeld pair, where the x13 rebuild's known
low-order-digit drift (nec5-linux README) evidently lives outside the
AIP columns.

## What the mechanism is (and where clean-room stops)

The march is first-order in segment length, identical under voltage and
current drive, present with the feed knot pinned on the exact same
physical point every rung, and unchanged by how the row is read — i.e.
it is a property of NEC-5's *solution* in the source region, not of any
boundary we control. That is as far as the Users-Manual-only rule lets
us see (the EULA bars reading the Fortran); the census does not need
more. What matters operationally is measured and now closed: order ≈ 1,
source-type-independent, extrapolates to the right answer.

- Pin added: `test_live_ex0_ex4_identical_impedance` (EX 0 vs EX 4
  digit-identity at fixed mesh) beside the phase-1 knot-identity pin.
- `site/src/content/docs/reference/nec5.md` honest-numbers section now
  names the cause, not just the resolution.

## Residue

- Phase 5's clean-cohort median gap (NEC-5 0.0215 vs bs2 0.0080 ΔΓ,
  both vs nec2c) stands as the honest cost of an order-1 engine even
  with pairs — pre-asymptotic wild decks (the 10 NEC-5-only outliers)
  remain out-of-recipe by nature, not by defect.
- momwire#302 (the two momwire-suspect corpus decks) is the separate
  open thread from #872.
