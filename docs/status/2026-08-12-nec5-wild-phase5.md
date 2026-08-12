# 2026-08-12 — Wild-corpus three-way census: the movers verdict (#872 phase 5)

## Goal

Phase 5 of #872: the 3,146-deck wild corpus through the census lane with
NEC-5 and bs2, scored against nec2c per deck, hunting **outliers that
move between oracles** — the study's highest-value output.

Sweep: `bench_nec_corpus.py --corpus ~/antennas/nec-wild --engines nec5
bs2 --timeout 180 --mem-limit-gb 8`, with the phase-2 recipe now built
into the lane: NEC-5 census rows are Richardson (N, 2N) pairs (native +
doubled-mesh solves, extrapolation reported, raw reads preserved;
`NEC5_PAIR=0` opts out). Artifacts: `scratch/nec5-wild-phase5.jsonl`
(~3,147 rows, 4 MB — untracked on haswell-server, same convention as
the July sweep) and `scratch/nec5-wild-pynec-votes.json` (the
fourth-vote run, committed). The historical July artifact (`bench_out/wild-solve-2026-07-17.jsonl`)
was untracked and is gone; this sweep regenerates the momwire column.

## Sweep totals

- NEC-5 solved 2,314 decks (as pairs; median 0.145 s/solve), 488 OOS
  (designed dialect refusals — TL/NT dominate), 0 unclassified errors.
- Clean-cohort rollup (feed-0 ΔΓ vs nec2c): NEC-5 n=1369 median 0.0215;
  bs2 n=1686 median 0.0080.
- Pair extrapolation vs the native single-mesh read, corpus-wide:
  **helps on 1,480 decks, hurts on 537, neutral 297** — the recipe is
  validated at corpus scale.

## The movers analysis (clean three-way cohort, 1,368 decks)

Classification at the ΔΓ > 0.2 outlier bar:

| class | count | verdict |
|---|---|---|
| bs2 outlier, NEC-5 sides with nec2c (momwire-suspect) | **2** | filed as momwire#302 (dual_band_stacked_moxon ΔΓ 1.42 near-short; delta-loop-15m 0.256) |
| NEC-5 outlier, bs2 sides with nec2c | 10 | **not formulation findings** — pre-asymptotic decks where even the (N, 2N) pair under-resolves (worst: 13el20mwireYagi, whose native→doubled step moves 47 Ω — order-1 extrapolation invalid there), plus one near-short pathological deck (`excessive_gain.nec`). Practical-limits note, not a bug. |
| both off, mutually agreeing | 61 → 47 pynec-voted | see below |

**The fourth vote.** pynec (nec2++) shares *geometry* with nec5/bs2 (the
translated wires) but *formulation* with nec2c — so it discriminates
translation-suspect from formulation-finding. Result: **46/47 decks are
formulation** (pynec agrees with nec2c; the split follows the
formulation, {bs2 + NEC-5} vs {nec2c + nec2++} on identical geometry),
1/47 translation-suspect, 0 ambiguous.

**And 44 of those 46 decks have stepped/multi-radius elements** — the
known NEC-2 stepped-diameter defect (the reason EZNEC ships the Leeson
correction; fixed in NEC-4/NEC-5). The two single-radius members
(capload2el10mYagi-375, Tutorial-2 ch-10/10-3b) are a residual tail.

## The verdict that rewrites the historical census

On stepped-radius decks the nec2c reference is the outlier, not bs2:
historical censuses scored bs2 as "off by 0.2–1.3 ΔΓ vs nec2c" on
exactly these decks, and two independent formulations (momwire's
Galerkin B-splines and NEC-5) now agree against the two NEC-2
implementations. Filed as #885: the census should carry a
stepped-radius flag so those rows read as "reference suspect" (with the
bs2↔nec5 mutual distance as the quality signal there).

Meanwhile the momwire-suspect pile across 1,368 clean three-way decks is
exactly **two decks** (momwire#302) — after five phases of looking, the
formulation-level agreement between momwire and NEC-5 is the story.

## #872 acceptance status

- [x] Census artifacts (JSON) + `docs/status/` writeup per phase
      (0, 1, 2, 3a, 4, 5; 3b deferred to a momwire-level instrument —
      the base-feed spelling needs #291's verbatim setup)
- [x] Phase-2 order/Z∞ table, hentenna included (arbitrated for bs2)
- [x] Feed-model correction recipe documented (and baked into the lane)
- [x] Outlier issues filed with three-way evidence (#885, momwire#302,
      momwire#300 from phase 1; sin's #484 instability three-way
      confirmed in phase 2)

## Addendum (same day): the EK kernel-mismatch closure

momwire's `extended_kernel=` opt-in (#849) was never wired into the
census lanes, so bs2 rows ran the reduced kernel on the 310 EK-carrying
decks while nec2c applied EK — a kernel mismatch pynec never had (#414).
With momwire 0.27.0 serving EK end to end, the lanes now forward
`deck.extended_kernel` and the 310 decks were re-solved (jsonl surgery,
first-run backup at `.pre-ek`).

**Result — honest and mixed**: paired before/after on 309 decks, bs2 ΔΓ
median 0.0380 → 0.0477, improved 41 / worsened 104 / unchanged 164,
worst tail slightly thinner (>0.2: 59 → 57). The movers are dominated by
the g1ojs magloop family and swing BOTH ways by up to ±0.44 (20m/160m
magloops improve up to 0.61 → 0.18; 40m magloops regress up to 0.35 →
0.82). Reading: electrically-tiny fat-conductor loops are
kernel-sensitive to the point that no single-kernel read is
census-grade there — the honest treatment is a kernel-sensitivity flag,
not a kernel preference. Note 4nec2 writes `EK` by default, so many of
the 310 cards are incidental (median deck moved little). The wiring
stays: kernel-for-kernel against the reference is correct methodology
independent of whether it flatters the numbers.
