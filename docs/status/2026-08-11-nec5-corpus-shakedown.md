# 2026-08-11 — NEC-5 census lane shakedown (#872 phase 0)

## Goal

Stand up the instrumentation phase of the NEC-5 corpus comparison (#872):
a `nec5` lane for `scripts/bench_nec_corpus.py` driving `NEC5Engine`, with
dialect scoping (designed refusals counted out-of-scope, not as failures),
a printout capture-and-cache keyed by deck content hash, and per-solve
time logging — then shake it down on the full xnec2c examples corpus
(82 decks) against bs2, scoring both against the nec2c reference.

Landed as PR #874. Sweep artifacts: `scratch/nec5-xnec2c-shakedown.jsonl`
(+ `.log` report) on haswell-server; printout captures (End-User Reports,
LLNL-CODE-746721) under `~/.antennaknobs/nec5-captures` (100 files, 2.9 MB).

## Instrumentation summary

- `--engines ... nec5` dispatches `NEC5Engine` through the same
  fresh-subprocess worker as the momwire engines; opt-in like `sing`,
  never in `DEFAULT_ENGINE_KEYS`. `$NEC5_EXE` is preflighted.
- **Dialect scoping**: `NotImplementedError` (TL/NT branches, ql/qc
  loads, distributed/virtual ports, buried wires, refl-coef ground) plus
  the two hard `ValueError` dialect rules (in-plane wire, near-unity
  eps_r) tag the row `out_of_scope`; a new `scope` error kind reports as
  `OOS` in its own bucket.
- **Capture-and-cache**: `NEC5Engine(capture_dir=...)` stores
  `<sha256[:16]>.nec`/`.out` per run and serves an already-captured deck
  from disk without invoking the binary — re-analysis never re-solves.
  Per-run `{hash, cached, seconds}` lands in the census JSON as
  `nec5_runs`.

## Shakedown results (82 xnec2c decks, nec5 + bs2)

- 78 decks referenced (4 pre-existing skips: one nec2c NaN, EX 4, and two
  surface-patch decks the importer refuses).
- **NEC-5: 50 solved, 28 OOS, 0 real errors.** OOS reasons: 15 refl-coef
  grounds (GN 0 — NEC-5's IPERF 0 is full Sommerfeld; no refl-coef option
  exists), 12 TL decks, 1 admittance-branch (NT) deck.
- Total NEC-5 solver time for the corpus: **5.5 s** (median 58 ms/solve,
  max 0.56 s). Census-scale sweeps are binary-cheap; the cost lives in
  the momwire columns.
- Agreement rollup on clean decks (feed-0 ΔΓ vs nec2c):
  - NEC-5 n=45 median **0.072** (<0.01: 7, <0.05: 19, <0.2: 34)
  - bs2 n=59 median **0.034** (<0.01: 16, <0.05: 36, <0.2: 49)

## Findings

1. **The medians are NOT an accuracy verdict.** The rollup compares each
   engine to *nec2c at the deck's native segmentation*. bs2 sits still by
   these meshes while NEC-5 is mid-walk on its ~O(1/N) approach (the
   hentenna observation that motivated #872) — and NEC-5 feeds segment
   ends where nec2c/momwire feed centers, an O(Δ) systematic on these
   often-coarse decks. Phase 1 (feed-model control) and phase 2
   (convergence character) exist precisely to de-confound this number.
2. **Largest NEC-5-vs-bs2 splits, i.e. the phase-2 candidate pile**:
   `airplane` (ΔΓ 0.51 vs 0.13), `1MHz_helivert` (0.37 vs 0.01),
   `13cm_helix+screen` (0.87 vs 0.52), `70cm-5el-rhcp-KJ7NLL` (0.33 vs
   0.04), and the 2m yagi family (~0.15 vs ~0.04 across all four
   variants — systematic, likely the feed-position delta at 9–11 segment
   driven elements). Both engines agree nec2c is far away on `1MHz_tower`
   (0.93/0.96) — a deck-modelling question, not an engine split.
3. **GN 0 is the big scope hole**: 15/28 OOS. For the wild corpus
   (phase 5) this cohort will be large; the planned mitigation is a
   labeled "Sommerfeld-upgraded" lane (GN 0 → NEC-5 native Sommerfeld,
   flagged not-apples-to-apples) rather than dropping the decks.
4. Zero unclassified engine errors and zero printout-parse failures over
   50 previously unseen real-world decks — the stage-1..5 parsers held.

## Next

- **Phase 1 — feed-model control** (issue #872 marks it FIRST): dipole
  mesh-ladder NEC-5 vs bs2, aligned even-NS decks feeding identical
  physical points, deliverable = the correction recipe phases 2–5 apply.
- Phase-2 sample selection can start from the split pile above plus the
  issue's stratified list (hentenna, loops, multi-junction fans, yagis).
- Decide the GN 0 Sommerfeld-upgraded cohort's plumbing when phase 3
  (ground ladders) lands.
