# Plan: closing the buried-wire refusals

Status: **draft for review, 2026-09-12.** Written the day the momwire#956
residual closed (momwire#1043, antennaknobs PR #1434 for the derivation,
#1441 for the census) and the corpus census showed that **no public deck is
inside the crossing serve's scope**: eight corpus decks have a wire below the
plane, momwire refuses all eight, NEC-5 solves all eight. The refusals are the
map of what is left. This plan orders them.

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
| 6 | "RP asks for the far field of a deck with a wire below the plane … the transmitted family's far-zone asymptotics" (momwire#570) | **formulation** | 1 | every buried design's pattern (wholly buried refused; mixed served with a note, #1341) |
| 7 | `elevated_buried_counterpoise` disagrees with NEC-5 by 31 % in R and 16 % in \|Z\| (+14 Ω R, −12 kΩ X on \|Z\| ≈ 62–74 kΩ), at both meshes and all three momwire commits | **open disagreement** (AK#1443) | — | 1 design |
| 8 | AK#1417's gate: no refinement path for an imported deck (every ladder tool is Builder-driven) | tooling | blocks per-deck ladders on all of the above | — |
| 9 | a wholly buried vertical rod reads a constant −1.20 % of R against NEC-5, invariant in depth, conductivity and frequency (momwire#1027) | **open disagreement** | — | every wholly buried fed element |

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
limits (U4, U5, U8) instead of at the flag. The antennaknobs importer drops the
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

The far-zone asymptotics of the transmitted family: stationary phase over the
below→above Sommerfeld integrals, with the lateral wave and the critical-angle
structure the near-zone tables never see. A phase-0-style prototype against
empymod's far field first (the #524 phase-0 shape: verified equations from the
open literature, gates G1–G6, then the kit), then the far-field readout in
both engines and the app's `in_medium` rule (#1341) replacing its refusal and
its 3 dB note with the served answer. Also carries #570's NE/NH item (the
below/below point reader) if the readout contract is settled on the way.
**3–5 weeks**, the only formulation unit here. Gate: the buried dipole's
pattern against empymod and NEC-5; the BRV's pattern moving by less than its
current #1341 note (0.46 dB) says it should.

## Order and size

| order | unit | days | unblocks |
|---|---|---|---|
| 1 | U1 translator | 0.5 | provenance on 930 census rows |
| 2 | U2 refine path | 2–3 | ladders on corpus decks for everything below |
| 3 | U3 GE −1 crossing | ~1 | 6 decks reach their real limits (U4/U5/U8) |
| 4 | U4 below range | 2–4 | 3 decks |
| 5 | U5 mixed radii | 5–10 | 4 decks; thin radials on a fat mast |
| 6 | U6 counterpoise | 2–3 (+fix) | 1 design's published number |
| 7 | U7 buried rod | 2–3 (+fix) | every wholly buried fed element's R |
| 8 | U8 far field | 15–25 | every buried pattern |

About 6–10 weeks of session time end to end, U8 alone being a third of it.
U1–U4 are the cheap half and clear the corpus population that the census
cannot exercise today; U5 is the one users will meet first; U8 is the one that
turns "impedance and currents only" into a complete buried serve.

## What is deliberately not on the plan

- Contact under the reflection-coefficient model (#3): refused by decision
  since the D3 cleanup; the reflection-coefficient ground has no lower medium
  to put a contact end in. U1 removes the decks that hit it by accident.
- The detached-radial convention: both engines refuse it by name; not a
  target.
- A Windows 7 floor (`notes/PY38-FLOOR-AUDIT-2026-09-12.local.md`): 8–12 days
  and the frozen workbench still would not run there.
