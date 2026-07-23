# Basis-census re-run + the fan-feed mechanism (issue #484 close-out)

**Date:** 2026-07-22
**Tool:** `scripts/bench_basis_convergence.py`, now Δ/a-headroom-clamped
(ladder N = 21/61/161/321/641 for every design, rungs past
`bench_delta_a_headroom.n_max` recorded as skipped; free space, seg-cap
4000, RLIMIT 6 GB). Raw rows: `bench_out/basis-census-2026-07-22.jsonl`.

## Why a re-run

The 2026-07-20 census carried three recorded debts: the folded/fandipole
rows predated the #496 Δ/a builder fixes, fat-conductor designs' fine
rungs ran below the thin-wire floor (the headroom caveat from PR #498),
and the 641 rung existed only as a hand top-up on the no-mutual class.
All three are paid here — plus one new fix this run flushed out
(twoband_fan below).

## Headline — 92 designs

**72 mutual-limit, 19 no-mutual-limit, 1 incomplete** (elt_whip, over
the seg cap at every rung). Was 66 / 24 / 1 of 91 on 2026-07-20.

| | sin | bs2 |
|---|--:|--:|
| within 2 % of Z\* at N = 21 | 40/72 | **58/72 (81 %)** |
| conv@N ratio sin/bs2 | median 1.0× (50/72 tie) | max **15.3×** |

The default-mesh decision (bs2 @ N=15 in slot A) survives the re-run
unchanged: four out of five scorable designs are converged out of the box.

### Who moved into the scored class, and why

| design | now | why it moved |
|---|---|---|
| folded_invvee | Z\* 222.9−30.3j, sin conv@**21**, agree 0.0 % | #496 Δ/a fix — the 2026-07-20 census's worst row (515 % apart @321) is now the *cleanest*: both bases flat and identical through N=641 |
| folded_invvee_balun | 46.7−4.2j, conv@21 both | inherits the same fix |
| folded_invveearray | 191.8−8.1j, conv@21 both | same |
| beams.owa_yagi | 47.5+1.4j, agree 1.2 % @61 | headroom clamp — its ladder now stops at N\_max=92 instead of solving garbage rungs below the Δ/a floor; the "owa_yagi meshing decision" resolves itself |
| wire.zepp | 2.6+16.3j, agree 0.1 % | #485 distributed port + the full 641 rung for both bases |
| wire.sterba_tl | 77.4−29.8j, agree 0.0 % @61 | #485 pins retired — the unpinned ports converge to the basis-agreed value |

## twoband_fan_dipole: the census's "4b" drift was one more fixed-count wire

The unexplained monotonic drift (sin 55.7 → **67.0** Ω up the ladder,
bs2 flat at 56.9) turned out to be the `inverted_l_tmatch` class-1
pattern hiding in a Δ/a-clean file: the four feed-split links carried a
**hard-coded 5 segments** while the arms refined past them, leaving the
split junctions ever more graded. (Δ/a audits can't catch this — the
links never get short relative to their *radius*, only coarse relative
to their *junction partners*.) Fixed: links now refine at arm density
(floor 5, so the default N=21 mesh is byte-identical). Ladder, free
space:

| N | sin stock | pynec stock | sin fixed | bs2 |
|--:|--|--|--|--|
| 161 | 55.7−7.5j | 55.7−7.3j | 54.1−7.2j | 56.9−7.7j |
| 321 | **63.4**−8.6j | **63.4**−8.5j | 55.8−7.4j | 56.9−7.5j |
| 641 | **67.0**−9.0j | **67.0**−9.1j | 55.1−7.0j | 56.9−7.4j |

PyNEC tracks sin to 0.05 Ω throughout — the drift was never
implementation-specific. Regression test pins N=321
(`tests/test_delta_a_lint.py`).

## The residue is junction fan degree — spacing is refuted

With the builder defects gone, three discriminators pin what remains of
the fan-feed class (full tables in the #484 thread; probes were ladder
solves on modified builders):

1. **Spacing sweep** (twoband's re-tuned s01…s07 variants, element
   planes 0.14 m → 1.0 m apart, fixed builder): sin↔bs2 gap flat at
   ~3–5 % with **no trend in s**. The close-parallel-wire lore (NEC-2
   aligned-segments rule, Cebik's seg-length ≈ spacing practice) does
   not explain this class — 4a killed it for the folded family, this
   kills it for the fan family.
2. **Fan-degree scan** (fandipole's `n_bands` 1→5, junction degree
   2→6): the one-element control converges clean (gap 3 % @321); every
   multi-element variant *diverges with refinement*, fine-mesh sin R
   falling monotonically with degree — 62.6 / 48.8 / 45.8 / 44.7 /
   **42.2** Ω against a bs2 that never moves from ~60.3.
3. **bs1 third opinion**: d=1 triangle Galerkin — independent of both
   sin collocation and d=2 — lands on bs2 to **0.1 %** and is flat from
   N=21. Two independent Galerkin families mutually agreed vs two
   collocation implementations drifting in lockstep: the Galerkin value
   is the credible limit, and the sin/NEC family is ~30 % low on R for
   a five-element fan at fine mesh. bs1's immunity despite its C⁰
   junctions also sharpens the mechanism: **Galerkin Z-stationarity is
   the protective property** (collocation takes junction-charge error
   at first order in Z; a shared feed junction multiplies the error
   sites by the fan degree), not the C¹ continuity previously credited.

`multiband.fandipole` (29.8 % apart) and `multiband.trap_fan_dipole`
(25.9 %) therefore stay in the no-mutual list *by mechanism*, not by
mystery — read them on the B-spline bases. trap_fan adds one open
sub-question: its 1-seg trap wires (deliberate lumped-element ports)
also grade against refining neighbours, so its number mixes both
effects.

## The remaining no-mutual 19, by class

- **Junction-topology-heavy, X-dominated gaps (8):** the hentenna /
  hourglass families + their arrays and slants (22–43 % apart, almost
  entirely reactance), specialty.bowtie (5.4 %). All are T/X-junction
  geometries — *consistent with* the junction-collocation mechanism but
  not yet degree-scanned; the natural next probe if anyone needs these
  at fine mesh. discone (15 %, an apex fan of degree 8+) likely the
  same story.
- **4b structural (2):** fandipole, trap_fan_dipole (diagnosed above).
- **Deliberate exemptions (2):** terminated_longwire (#459 near-open
  feed — its pin is the validated model), helix (mesh is a design knob).
- **Unexplained moderate (1):** beams.moxon (14.3 % @321; bent-corner
  geometry, Δ/a healthy at that rung).
- **The ≤4 % tail (6):** twoband_fan (3.3 % — its junction-degree-3
  residue), inverted_l_tmatch, short_dipole_loaded, hexbeam,
  hexbeam_5band, jpole. All slow-closing; none moving away.

## Implications

1. The #484 arc is complete: 4a (Δ/a builder defects) fixed and linted,
   4b (fan-feed drift) fixed where it was a builder defect and
   *diagnosed as a family-level collocation limitation* where it
   wasn't. The convergence guide's class-4 section now states the
   mechanism and the prescription (trust the B-spline bases on fan-fed
   multiband geometry).
2. **Wild-corpus caveat, extended:** nec2c is not an independent
   referee on fan-fed decks at fine mesh — it shares the collocation
   family's junction error, exactly as it shared #448's class. At
   catalog-default meshes the error is a few percent.
3. The census tool now enforces the headroom clamp by construction, so
   no future run can quietly score sub-floor rungs.
