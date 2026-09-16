# Plan: closing the buried-wire refusals

Status: **units complete, 2026-09-16.** U1–U7 and U9 are done or closed; U8's
pattern is built in both repos (momwire#1078, #1544), with
the near-field item on momwire#570 the one thing left. Written 2026-09-12, the day the momwire#956
residual closed (momwire#1043, antennaknobs PR #1434 for the derivation,
#1441 for the census) and the corpus census showed that **no public deck is
inside the crossing serve's scope**: eight corpus decks have a wire below the
plane, momwire refuses all eight, NEC-5 solves all eight. The refusals are the
map of what is left. This plan orders them.

**Progress, 2026-09-15.**

| unit | state |
|---|---|
| U1 translator | done: corpus tool 1.10 (AK#1453), and the census page re-rendered on 1.11 (AK#1467) |
| U2 refine path | done: `NecDeck.refined(r)` and `antennaknobs ladder` (AK#1457) |
| U3 `GE −1` crossing | done: momwire#1052, released in momwire 0.55.0, which antennaknobs v0.77.0 ships on |
| U4 below range | done: momwire#1058 serves the remainder past the cap as zero, merged 2026-09-13 with its caveat accepted (fresh water at 28 MHz clears the bound by only 2×; broadside parallel wires more than 4 λ_m apart are unmeasured); records in momwire#1057; released in momwire 0.55.0, which antennaknobs v0.77.0 ships on |
| U5 mixed radii | done: two-radius crossing, momwire#1050, released in momwire 0.55.0, which antennaknobs v0.77.0 ships on |
| U6 counterpoise | closed: AK#1443's verdict; follow-up AK#1455 done (the radiator is graded), AK#1456 open |
| U7 buried rod | closed: momwire#1027, not a physical disagreement; the two engines converge toward the same R along two axes, at different rates |
| U8 far field | **built, both halves** (2026-09-16): momwire#1078 serves `RP` for buried decks on both seams through the transmitted far-zone factors in the shared readout; #1544 places buried currents through the interface in both app readouts and retires #1341's refusal and note. Closed form, not a formulation: the far-zone limit of the transmitted family is the Fresnel-transmitted plane wave. Measured against NEC-5 x13: 0.005 dB shape / 0.03 dB absolute on `buried_dipole`; the buried-radial vertical's honest pattern lands 0.005 dB from NEC-5, having moved −0.19 dB off the imaged readout. Records in momwire `scratch/570-far-field/`. Still open on momwire#570: the NE/NH below/below point reader (phase 3) |
| U9 several crossing nodes | **done and released**: momwire#1065 serves several crossing nodes per deck (momwire#1068 moved two tests it made slow). Released in momwire 0.56.0, which antennaknobs v0.79.0 pins and ships on. Measured: the 8-node LPDA at refine 1 reads 52.09 − 3.18j against NEC-5's 53.07 − 3.54j (2.0 %), and momwire's own far × 3 step on it is 0.0394 Ω; two-node soil-A decks against NEC-5 meet the gate on 16 of 16 readings. The LPDA check (d) stopped at its pre-Z check; the two cebik phased arrays are still refused by name; route 1 is deferred; follow-up momwire#1064 |

Ground rules carried from the #956 arc, which are what made it converge:

- Every unit registers its prediction before the run and reports the miss if
  it misses (Haswell's #1044 shape).
- NEC-5 is the reference *engine*, not the truth: a unit's gate is a Richardson
  ladder on both engines over a deck family, not agreement on one print, and
  a cross-formulation disagreement is a finding, never a re-gate.
- The buried census (`scratch/956-census/`, three momwire columns, Population
  A = the catalog's buried designs, Population B = the corpus's eight) is the
  standing gate: re-run after every unit below. A wholly-buried design that
  moves is a stop.

## The refusals, from the census

| # | refusal (momwire's sentence, abridged) | kind | corpus decks | catalog |
|---|---|---|---|---|
| 1 | translate rewrites `GN 2` → `GN 0`; momwire honours NEC-2's `GN 0` = reflection coefficients (AK#1442) | **tool defect** | 1,104 of 1,105 GN 2 decks; 930 census rows compare two ground models | — |
| 2 | "GE −1 declares the ground plane without the ground-contact current expansion … this engine serves the interpolated (GE 1) contact only" | scope | 6 | — |
| 3 | "ground CONTACT under `refl-coef` is refused" | **decision** (D3, 2026-08; stays) | 6 + 2 once #2 is lifted, 0 once #1 is fixed | — |
| 4 | "below/below pair separation R₁ = 136 m (8.9 in-medium λ), past the 4 in-medium λ the remainder is tabulated to" | range | 3 | — |
| 5 | "crossing serve with per-wire radii: ρ_eff = √(ρ² + a²) regularizes the corner with ONE radius, and a mixed-radius convention is not pinned" (momwire#524 phase 2) | scope | 4 | every real screen: radials thinner than the mast |
| 6 | "RP asks for the far field of a deck with a wire below the plane … the transmitted family's far-zone asymptotics" (momwire#570) | **closed form** (U8) | 1 → 0 | none: every buried design's pattern is served through the interface in the app (#1341) and `RP` prints on both momwire seams (momwire#1078) |
| 7 | `elevated_buried_counterpoise` disagrees with NEC-5 by 27 % in R and 10 % in \|Z\| (+10 Ω R, −7.1 kΩ X on \|Z\| ≈ 61–69 kΩ) on its graded radiator, at nominal_nsegs 21, 42 and 84, with each engine's own fed segment (momwire 1 × 50 mm, NEC-5 2 × 25 mm). Most of it is that fed segment's size: with the fed segments near-matched, the R gap is 2.9 % (31 % at the engines' own sizes, measured on the uniform radiator, AK#1456) | **mostly fed-segment size** (AK#1443, AK#1456) | — | 1 design |
| 8 | AK#1417's gate: no refinement path for an imported deck (every ladder tool is Builder-driven) | tooling | blocks per-deck ladders on all of the above | — |
| 9 | a wholly buried vertical rod reads a constant −1.20 % of R against NEC-5, invariant in depth, conductivity and frequency (momwire#1027) | **open disagreement** | — | every wholly buried fed element |
| 10 | "a deck with N crossing junctions … the crossing serve completes ONE crossing node per deck" (momwire#1054; before it, a bare assert in the fill, AK#1464) | scope | 3 (the lpma3r5 LPDA with 8 nodes; two cebik phased arrays with 3 and 4) | every multi-element buried array |

The four-count in #5 and the six in #2 overlap: the six `GE −1` decks are the
four mixed-radius ones plus the two split slopers, so lifting #2 alone
unblocks nothing until #5 and #4 land. The order below is by value per day,
with the tool items first because every later gate wants them.

## Units

### U1 — fix the translator (AK#1442)

`scripts/nec5_corpus` must pass `GN 2` through as its contract says. Then
re-render the #896 census page so its 930 affected rows compare Sommerfeld
with Sommerfeld, with a dated note. Skylake measured the effect on 120 decks
as small (median |ΔZ|/max 0.099 → 0.091, reactance-sign count unchanged), so
this changes provenance, not the headline. **Hours.** Gate: the re-rendered
page's determinism check and the 120-deck A/B in #1441.

### U2 — the imported-deck refinement path (AK#1417's gate)

A `--refine N` on the corpus tool and the CLI that scales every `GW` count of
an imported deck and re-solves both engines at N / 2N / 4N, printing the
Richardson step sequence. Every unit below wants a ladder on a corpus deck;
today only Builders have one. **2–3 days** (Skylake). Gate: reproduces the
#956 rod ladder's numbers when pointed at the exported rod decks.

### U3 — serve `GE −1` crossing decks (6 decks)

Measured 2026-09-13, before any code, with the licensed x13 build: NEC-5 does
**not** read the six decks the same under `GE −1` and `GE 1`. The impedances
differ by 4.8–35 %. Its user manual makes `GE −1` the flag for buried or
interface-crossing wires and says `GE 1` cannot be used with them. So a
`GE −1` → `GE 1` translation would be wrong, and the six decks are correctly
spelled. (The #1441 census table had published their NEC-5 values under the
`GE 1` rewrite; its data file kept both, and the table is being corrected.)

What momwire refuses is narrower than this unit first assumed. Its NEC-2
reader (momwire#489) refuses `GE −1` whenever any wire end stands in the ground
plane under a ground. In NEC-2 such an end is a free contact whose current goes
to zero, which momwire's contact model does not implement. The check does not
tell a free end from a **crossing junction**, where a wire above and a wire below
meet at z = 0. Every z = 0 node in all six decks is such a junction, with no
free ends. At a junction, `GE −1`'s unmodified current expansion is what
momwire's crossing serve already does.

So the unit is: exempt crossing junctions from the #489 refusal, and keep
refusing free in-plane ends. The free end under `GE −1` (momwire#865 / #597)
stays unserved and is not part of this unit. **Gate:** a `GE −1` crossing deck
solves bit-identically to its `GE 1` twin; #489's grounded quarter-wave free-end
refusal still fires; and the six decks then stop at their declared scope
limits (U4, U5, U8, U9) instead of at the flag. The antennaknobs importer drops the
GE sign altogether, which is its own fix (#1460). Not verified: that NEC-4.2,
the source of the Cebik decks, gives `GE −1` the same buried-wire meaning as
NEC-5. **About 1 day.**

### U4 — the below/below range (3 decks)

The below/below remainder is tabulated to 4 in-medium wavelengths and refuses
beyond. In a lossy medium the remainder carries e^{−Im(k_m)·R}; at soil A the
4 λ_m cap is already ~16 nepers of attenuation. First measure the remainder's
magnitude at the cap against the pair's direct term on the #524 phase-0
prototype (`scratch/524-phase0/proto/buried_proto.py`, regime 2). If it is
below the quadrature floor, serve beyond the cap with the remainder set to
zero and the bound documented in the refusal's place; if not, extend the
table with a coarser far segment. **2–4 days.** Gate: the three decks through
U2's ladder against NEC-5, and the wholly-buried census rows unmoved.

### U5 — the mixed-radius crossing corner (4 decks, and every real screen)

The corner term −σσ′·c1·V(a) is the node's own self-energy at pair distance
ρ_eff = √(ρ² + a²); with two radii meeting at the node there is no pinned
convention for a. This is the unit with the most practical value: real radial
screens use radials thinner than the mast, so today's serve refuses the
common case. Plan: (a) derive the per-pair rule from the same-medium blocks'
own convention (they already use R = √(Δz² + a²) per pair — which member's a,
and what the field form says at a two-radius node); (b) the #956 rod harness
with rise radius ≠ radiator radius as a ladder (three ratios, three lengths),
registered prediction, Richardson on both engines; (c) the four corpus decks
through U2. **1–2 weeks.** Gate: the catalog's BRV at equal radii
bit-identical (no regression), the mixed-radius ladder inside the equal-radius
ladder's residual band.

### U6 — the open counterpoise disagreement (1 design, AK#1443)

`elevated_buried_counterpoise` is a `split` deck (above and below, nothing at
z = 0), so it goes through the transmitted **grid**, not the crossing fill.
|Z| ≈ 70 kΩ is near-open, so a small absolute error in the cross block is a
large relative one. Localise before fixing: the field form on the grid
against the designed tables (probe5's method) on this deck's pairs; the grid's
range and interpolation error at the counterpoise's height/depth; NEC-5's own
ladder. **2–3 days to localise;** the fix depends on what it names.

Graded from the feed (AK#1455), each engine's R holds to 0.3 % across
nominal_nsegs 21–84 while the engines stay 27 % apart in R, so the gap is not
the far mesh. **It is mostly the fed segment's size.** The two engines mesh the
50 mm feed gap differently (one 50 mm segment on momwire, two 25 mm segments on
NEC-5), and at this near-open driving point the impedance follows that size.
With the fed segments near-matched (momwire 7 × 7.1 mm, NEC-5 6 × 8.3 mm), the
engines are 2.9 % apart in R and 0.2 % in B, against 31 % and 16 % at their own
sizes. That was measured on the uniform radiator (AK#1456).

### U7 — the wholly buried rod's −1.20 % of R (momwire#1027)

The last miss on the #956 record: five hits and this one, after momwire#1047.
A centre-fed vertical rod with both ends below z = 0, Richardson-extrapolated
on both engines, reads ΔR/R = −1.20 %. That fraction holds to within 1 % of
itself across 16× in depth, 20× in conductivity and 8× in frequency, and it
moves only with the rod's length: −3.9 % at 0.15 m, −0.27 % at 2.4 m.
momwire's two bases agree on it to five figures, so it is not a basis
artefact. It is not #956's mechanism either. That residual was positive,
grew with length and was absolute; this one is negative, falls with length
and is a fixed fraction of R. The #956 fix did not touch wholly buried decks
(census).

One lead to test first, not a conclusion. At fixed length the frequency sweep
changes L/λ_m several-fold without moving the fraction, so it follows *physical*
length (L/a, or the feed gap's share of L), not electrical length. Localise
in this order, registering a prediction before each run:
(a) the same rod in an infinite medium of the same soil, on both engines. If
the fraction survives with no interface, the Sommerfeld remainder is out of
the path.
(b) The feed-gap axis: gap length and EX spelling at fixed L. The g1b probe
already found a buried-fed drift on this axis in any medium.
(c) L/a at fixed L.
**2–3 days to localise;** the fix depends on what it names. Gate: the
#1027 table re-run on both engines, and the census's wholly buried rows
moving only if this unit says they should.

### U8 — the buried far field (momwire#570)

**Built in both repos, 2026-09-16.** The unit was registered as a 3–5 week
formulation; it is a closed form. The pattern is the coefficient of
e^{−jk_pR}/R in the transmitted field, which is the stationary-phase value of
the below→above Sommerfeld surfaces at λ_s = k_p sinθ, and there the five
surfaces collapse to three angular factors: the Fresnel TE transmission
coefficient, the TM pair on Snell's angle, and a depth leg exp(−j k_mz d).
The lateral wave and the critical-angle structure are O(1/R²) at an observer
in air and are not in a pattern; at θ = 90° every factor vanishes, as the
finite-ground image pattern does. Two derivations (the saddle point of the
AGARD surfaces and reciprocity with the Fresnel coefficients) agree to 1e-14
wherever the saddle spelling is well conditioned; the Fresnel spelling is the
one built, because the saddle spelling loses eight digits at grazing.

- **momwire#1078:** `_far_readout.transmitted_factors` /
  `transmitted_moments`; `_far_moments` splits its elements at the plane
  (above: direct + image from the above elements alone; below: transmitted);
  the buried far-field refusal is gone from `_medium_spec`, the NEC-2 portal
  and the EZNEC seam. Serve matrix for a buried deck: impedance, currents,
  charges and pattern; the near field still refuses by name (phase 3).
- **#1544:** `in_medium.py` owns the transmitted placement;
  `MomwireEngine._evaluate_M_perp` and the web cuts split at the plane and
  build the image from the above elements only (the UTD composer takes the
  transmitted moment as a keyword); #1341's refusal, note and power-share bar
  are gone, `in_medium_moment_fraction` stays as information.

**Measured** (records: momwire `scratch/570-far-field/`, PLAN.md with every
prediction registered before its run and every miss kept):

| gate | result |
|---|---|
| ε̃ = 1 collapse to the free-space moment | 2e-13 (momwire), 7e-16 (app factors) |
| closed form vs momwire's numerical transmitted integrals, extrapolated in 1/R over 40 and 80 λ₀ | 8.6e-6 worst; the raw approach is an exact 1/R law (halving ratios 2.000) |
| adversarial: depth leg flipped / T_v negated | 0.18–0.85 / 2.0, against a 1e-2 bar |
| above-ground readouts | bit-identical to v0.79.0 |
| NEC-5 x13, `buried_dipole` (soil A, 7 MHz), momwire's own currents | shape 0.005 dB, absolute 0.03 dB over the lit hemisphere |
| NEC-5 x13, `buried_radial_vertical` (connected) | the honest pattern moves −0.19 dB off the imaged one (bar 0.46 dB) and lands 0.005 dB from NEC-5; the imaged readout sat 0.18 dB above it |
| empymod 2.6.0 as a far-zone oracle | disqualified: O(1) on its above-soil control with every Hankel transform, so NEC-5 is the independent check |

**Not in this unit:** momwire#570's NE/NH item (the below/below point reader,
phase 3) and its EK-under-a-medium item.

### U9 — more than one crossing node (3 decks, every multi-element buried array)

**Done and released.**
- **Where it landed.** momwire#1065 serves a deck with several crossing nodes,
  and momwire#1068 moved two tests it made slow on macOS.
- **What users get today.** Both are in momwire 0.56.0, which antennaknobs
  v0.79.0 pins and ships on, so a deck with several crossing nodes solves
  instead of being refused by name (momwire#1054). The two cebik phased arrays
  are still refused, on limits of their own.
- **Records:** momwire `scratch/u9-multi-crossing/` (momwire#1063).

**What the fill does now.**
- **The corner.** It was the one term fixed to a single node. It is now
  evaluated for every in-plane end pair, at one node or across two, as
  −σσ′·c1·V(√(ρ² + a²)). Every other term was already evaluated at any
  distance.
- **The grazing floor.** Two crossing nodes put their rises' below/below pairs
  at θ = atan(2·h_node/d), under the old 0.05° floor at any practical spacing.
  - **The new floor is 0.016667°.** The low band starts two cells lower, at its
    own Δθ, with a 24,000-panel tail budget.
  - **Interpolation.** The real-grid interpolation over the new cells reads
    3.9e-9 against a 4.7e-4 bar.
- **Still refused by name:**
  - crossing nodes closer than 1 m (`MIN_CROSSING_NODE_SEPARATION_M`, gated on
    one deck);
  - a two-radius deck with more than one node.

**What is measured.**
- **The ε̃ = 1 collapse.**
  - Two rise-plus-monopole pairs match the free-space two-wire Z to 2.0e-4 Ω,
    at 12 m and at 1 m, on both σσ′ orientations.
  - Without the cross-node corner, Z12 misses by 4.70 Ω.
  - Two of the registered magnitude bands missed low, so the GO was a
    post-hoc ruling, recorded in momwire#1063's `PLAN.md`.
- **The soil-A ladder, at 3 / 5 / 8 / 11 m.**
  - Every rung is served.
  - Z11 approaches the single-node print, 1.02 → 0.33 Ω.
  - Z12 = Z21 to 1.5e-15.
- **Two-node decks against NEC-5.** Soil A, at 3 / 5 / 8 / 11 m, with both
  engines fed at one knot.
  - **The gate.** The full 2 × 2 Z meets the registered gate on all 16
    readings: Z11 and Z12, at two meshes, at every separation.
  - **At the finer mesh,** Z12 is within 0.7 % and Z11 within 1.1 %.
  - **The gate sees the term.** Leaving the cross-node corner out moves Z12 by
    5.5–21.9 Ω.
- **The 8-node lpma3r5 LPDA.**
  - **The reading.** At refine 1 through antennaknobs' multiport route, momwire
    reads 52.09 − 3.18j against NEC-5's 53.07 − 3.54j, 2.0 % of |Z|.
  - **momwire's own far × 3 step** on it is 0.0394 Ω (run on Skylake).
  - **The condition.** antennaknobs' construction-time preflight was stubbed.
    momwire's own scope and serve plan ran unstubbed.

**What did not land.**
- **(d), isolating the corner on the corpus LPDA, stopped at a pre-Z check.**
  The NEC-5 route's reciprocity on the one-node spelling read 2.29 %, against
  1 %.
  - **(d) was ended there.** The full-against-one-node change is mostly the
    ungrounded elements, so it could not isolate the corner.
  - **The two-node decks took its place.**
- **The two cebik phased arrays stay refused by name.** Their walls:
  - pairs grazing past the table;
  - U5's within-side radius spread, on both sides;
  - NT-fed ports.
- **Route 1,** serving past-cap below/below pairs at any θ, is deferred.
- **Refining a served two-node deck's node segments** pushes it back under the
  floor.

**Follow-ups.**
- **momwire#1064, the cold fill.** Decks that reach under 0.1° pay 2.3–2.9× on
  the cold fill; warm solves and memory are unchanged. A fifth θ band would
  confine that cost to decks under 0.05°.
- **Solve cost.** A two-node solve at soil A takes about 30 s.

## Order and size

| order | unit | days | unblocks | state |
|---|---|---|---|---|
| 1 | U1 translator | 0.5 | provenance on 930 census rows | done |
| 2 | U2 refine path | 2–3 | ladders on corpus decks for everything below | done |
| 3 | U3 GE −1 crossing | ~1 | 6 decks reach their real limits (U4/U5/U8/U9) | done; released in momwire 0.55.0 |
| 4 | U4 below range | 2–4 | 3 decks | done; released in momwire 0.55.0 |
| 5 | U5 mixed radii | 5–10 | 4 decks; thin radials on a fat mast | done; released in momwire 0.55.0 |
| 6 | U6 counterpoise | 2–3 (+fix) | 1 design's published number | closed (AK#1443) |
| 7 | U7 buried rod | 2–3 (+fix) | every wholly buried fed element's R | closed (momwire#1027) |
| 8 | U8 far field | 15–25 (took 1: closed form) | every buried pattern | built in both repos (momwire#1078, #1544) |
| 9 | U9 several crossing nodes | 4–6 | 3 decks; every multi-element buried array | done; released in momwire 0.56.0 |

**What remains.**
- **momwire#570's near-field item** (NE/NH for buried decks, phase 3) is the
  last output a buried deck cannot answer; U8's pattern turned "impedance and
  currents only" into a serve with a pattern.
- **Follow-ups from the done units:**
  - **momwire#1064:** U9's extra cold-fill cost, confined to decks under 0.05°
    by a fifth θ band;
  - **AK#1456:** cross-engine comparisons inherit each engine's fed-segment
    size, which matters at near-open feeds (from U6);
  - **momwire#1066:** SinusoidalGalerkin's slope jump across a crossing node
    grows under refinement, while bspline's halves. Nothing gated moves.
- **U9 reached users** in momwire 0.56.0, which antennaknobs v0.79.0 ships
  on.

## What is deliberately not on the plan

- Contact under the reflection-coefficient model (#3): refused by decision
  since the D3 cleanup; the reflection-coefficient ground has no lower medium
  to put a contact end in. U1 removes the decks that hit it by accident.
- The detached-radial convention: both engines refuse it by name; not a
  target.
- A Windows 7 floor (`notes/PY38-FLOOR-AUDIT-2026-09-12.local.md`): 8–12 days
  and the frozen workbench still would not run there.
