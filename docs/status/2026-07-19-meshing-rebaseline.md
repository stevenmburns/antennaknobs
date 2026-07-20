# Meshing re-baseline: wild corpus + catalog after the segment-parity and segs_for arcs

**Date:** 2026-07-19
**Context:** four merged PRs changed how every antenna is meshed —
fed-only segment-parity coercion (#450 / PR #455), the `segs_for` clip at 1
plus retirement of the `max(3, nominal//7)` idiom (#457 / PR #458), and
mesh-refining feed segments plus catalog-norm density alignment (#435 /
PR #460). This document is the one-churn-event re-baseline both for the
wild-deck corpus and the design catalog, plus the post-#456 reference
repair.

## Wild corpus re-sweep (post-#455)

Full sweep of the 3,146 content-unique wild decks, all four engines vs
pinned vanilla nec2c 1.3.1, same bounds as the 2026-07-17 baseline
(300 s / 8 GB — kept identical so every taxonomy delta is attributable to
the code change, not moved goalposts). Results:
`bench_out/wild-solve-2026-07-18-post455.jsonl` (gitignored). Wall time
~6 h.

Clean-deck agreement rollup (supported ground, fully-expressed network, no
virtualized anchors, verbatim reference), vs the 07-17 baseline:

| engine | median ΔΓ | baseline | ≤ 0.01 | baseline |
|---|--:|--:|--:|--:|
| PyNEC | **0.0001** | 0.0002 | **97.4 %** | 91 % |
| Sinusoidal | **0.0032** | 0.0046 | 69 % | — |
| BSpline d=2 | 0.0082 | 0.0084 | 53 % | — |
| BSpline d=1 | 0.0255 | 0.0251 | 24 % | — |

**No deck class regressed.** The two engines sharing the odd-parity
coercion #455 removed from unfed wires (PyNEC, Sinusoidal) both improved;
the B-spline bases are flat within noise. Deck meshes are now solved with
the deck's own segment counts verbatim — strictly more faithful to the
reference than the old blanket parity bump.

Taxonomy: MEM 4 rows (the known ch-5/5-8 + Parab50 family), GEO = the
known nec2++ intersection-validator class, ERR = known classes
(buried-radial decks, multi-EX-per-segment decks, singular tiny-loop
matrices). Runtime medians 0.03–0.07 s/solve; peaks 67–186 s
(the fat-mesh tail), peak RSS 5.5 GB (bs2 on Parab50) — under the 8 GB
cap everywhere except the four MEM rows.

### Outlier residue: 51 → 12

Clean-deck PyNEC outliers (ΔΓ > 0.2) collapsed from 51 to **12** — the
meshing arc (mostly #455's faithful deck meshes) resolved ~39 of them.
The survivors cluster:

- `salt_ground` (1.12) — extreme ground parameters, known standalone.
- `ch-11/11-4` (0.93) — the #448 PyNEC high-|Z| feed deck; momwire and
  both true NEC-2s agree against nec2++ here.
- `ch-5/5-10`, `5-10a`, `5-6a`, `15-5-*` (0.23–0.54) — Cebik tutorial
  models, untriaged.
- half-square / bobtail-curtain family (0.28–0.40) — high-Z feed
  geometries; plausibly the #459 mesh-stable-feed class.
- `1r8-2-elphased-radials` (0.31) — phased-with-radials, known from the
  first sweep.

### EX 6 + TL reference repair (#456)

The sweep initially recorded 13 decks against the broken EX 6 R_BIG
emulation reference (feed segment shared with a TL → the subtraction
manufactured ≈ −20 kΩ references): the EZNEC-coax family
(DipTL/CardTL/4SQTL ×2 copies), the HFActiveFeed phased decks
(3vertical, BRDZPR10, ZLSPTS10, ZLTROM10), Coax, EDZ_TL, LOGPERTL, and
the G3TXQ broadband hexbeam. After #456 landed (skip the subtraction and
flag `t` when a TL/NT anchors the driven segment), those 13 rows were
deleted and re-run in place (backup:
`wild-solve-2026-07-18-post455.jsonl.pre456`):

| deck | new reference | PyNEC ΔΓ | sin ΔΓ |
|---|--:|--:|--:|
| DipTL / CardTL / 4SQTL (×2 copies) | 27.7−9.3j / 22.6+12.8j / 13.6+4.4j | 0.0001–0.0007 | 0.0004–0.0007 |
| Coax | 27.9−9.0j | 0.0003 | 0.0028 |
| EDZ_TL | 48.2+2.2j | 0.0005 | 0.0029 |
| ZLSPTS10 | 54.0−9.1j | 0.0010 | 0.0099 |
| LOGPERTL | 157.6−43.3j | 0.100 | 0.099 |
| G3TXQ hexbeam | 54.2+6.6j | 0.194 | 0.191 |
| BRDZPR10 | 88.5−11.6j | 0.584 | 0.585 |
| ZLTROM10 | 217.2+15.8j | 0.779 | 0.780 |
| 3vertical | still −18972+258j (feed 0) | 0.43 | 0.43 |

**8 of 13 fully rescued** (ΔΓ ≤ 0.01), two more improved below the
outlier bar. Three HFActiveFeed decks remain, in two distinct classes:

- **3vertical**: none of its three EX 6 feeds shares a TL segment
  (`ex6_tl_shared` empty), yet feed 0's reference still carries a
  −R_BIG-shaped residue — the subtraction assumption fails by a
  *different* mechanism on multi-EX 6-source decks. Needs its own look.
- **BRDZPR10 / ZLTROM10**: the skip fired correctly and the references
  now look sane — the remaining 0.58/0.78 disagreement is *ours*, both
  engines in lockstep: the engine-side composition of an EX 6 current
  source sharing its port with a TL is the suspect (the same shared-port
  situation the reference-side fix just repaired, one layer down).

  **Resolved (#464) — the diagnosis above was wrong; the bug was the
  reference, not the engine.** A driving-point impedance is source-type
  independent (V/I at a port is the same whether you force V or I), and
  nec2c's *own* 1 V voltage drive with the TL intact reports 34.9 + 45.1j
  for BRDZPR10 — matching our engines (33.2 + 44.6j), not the 88.5 − 11.6j
  R_BIG readout. The "R_BIG-invariant ⟹ trustworthy" assumption behind
  #456's skip is false: when the driven segment is also a TL/NT port, NEC
  *bypasses* the series `LD 4 R_BIG` (a 20 kΩ load carrying 222 A at
  R_BIG = 2e4), so the raw readout is a NEC LD-plus-network composition
  artifact, not an impedance. The fix routes single-source EX 6 decks
  through the #463 Y-matrix superposition path (native voltage drives, TL
  intact), which for N = 1 degenerates to one 1 V solve. Both decks now
  land at ΔΓ ≤ 0.0015. Corrected references: **BRDZPR10 34.9 + 45.1j**,
  **ZLTROM10 33.6 + 28.6j**.

## Catalog re-baseline

The catalog A/B was done PR-by-PR rather than as a separate sweep — every
changed design was measured old-vs-new against main at merge time.

**PR #458 (`segs_for` clip + idiom retirement):** 40 designs' meshes
changed (short bridges 3→1/3→2); median |ΔZ| ≈ 1 Ω across 80 solves,
PyNEC and Sinusoidal in lockstep. Ladder-adjudicated movers: fandipole
(21 % — the old meshing never plateaus, and its 5-segment 2 cm bridge
tripped nec2++'s intersection validator at N=41, making convergence
sweeps impossible before), jpole (6 %, closer to converged).

**PR #460 (feed refinement + density alignment):** exactly six designs
changed at default N (verified by full-catalog mesh diff): quad
(+1.9 Ω — to its converged ~130 Ω; ladder flat N=7→201 where it
previously climbed 115.7→138.8 without settling), jpole tap (+3.4 Ω —
now converges, plateau ~69 Ω), trap_dipole (0.5 %), lumped_coupled_pair
(0.2 %), plus sterba/short_dipole_loaded (bit-identical, slider now
functional). ~45 other fed/named-wire sites refine with the mesh at zero
default churn. Ladders also repaired edz and zepp.

**Deliberate exemptions (issue #459):** terminated_longwire's near-open
feed and sterba_tl's TL ports keep pinned segment counts — refining them
demonstrably worsens their ladders (delta-gap divergence at |Z| ≈ 5 kΩ;
TL port stamp sensitivity). In-code comments carry the rationale (grep
"deliberately exempt").

## Open threads

- #448 — PyNEC high-|Z| feeds (11-4 back in the outlier list; possibly
  the same physics as #459).
- #436 — basis-aware loop meshing (BSpline d=2 converges coarser on
  closed loops).
- #459 — mesh-stable feed model for high-Z feeds / TL ports; would lift
  the two exemptions and possibly resolve #448.
- Remaining 12-outlier triage (above).
