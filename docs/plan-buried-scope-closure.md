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
| 7 | `elevated_buried_counterpoise` disagrees with NEC-5 by ~20 % (14 Ω R, ~12 kΩ X on \|Z\| ≈ 70 kΩ), at both meshes and all three momwire commits | **open disagreement** (issue being filed) | — | 1 design |
| 8 | AK#1417's gate: no refinement path for an imported deck (every ladder tool is Builder-driven) | tooling | blocks per-deck ladders on all of the above | — |

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

### U3 — serve `GE −1` (6 decks)

NEC's `GE −1` is a ground plane with **no** current interpolation at a contact
end: the wire ends *at* the plane rather than continuing into its image (the
#151 continuation model is `GE 1`). momwire serves only the interpolated form.
This is momwire#865 ("wire IN the ground plane — the z = 0 limit of the buried
family") and #597 ("solvers still disagree about a lone wire end resting in
the ground plane") under one name. First a 20-minute measurement: NEC-5's own
print on the six decks under `GE −1` and under `GE 1` — if the engine reads
them the same, the unit is a translation (`GE −1` → served as `GE 1` with a
note); if not, it is the z → 0⁻ limit of the buried family as an end
condition, derived against the #524 phase-0 kit and gated on the six decks
through U2's ladder. **1 day if the former, 3–5 days if the latter.**

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

### U6 — the open counterpoise disagreement (1 design)

`elevated_buried_counterpoise` is a `split` deck (above and below, nothing at
z = 0), so it goes through the transmitted **grid**, not the crossing fill.
|Z| ≈ 70 kΩ is near-open, so a small absolute error in the cross block is a
large relative one. Localise before fixing: the field form on the grid
against the designed tables (probe5's method) on this deck's pairs; the grid's
range and interpolation error at the counterpoise's height/depth; NEC-5's own
ladder. **2–3 days to localise;** the fix depends on what it names.

### U7 — the buried far field (momwire#570)

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
| 3 | U3 GE −1 | 1–5 | 6 decks (with U4/U5) |
| 4 | U4 below range | 2–4 | 3 decks |
| 5 | U5 mixed radii | 5–10 | 4 decks; thin radials on a fat mast |
| 6 | U6 counterpoise | 2–3 (+fix) | 1 design's published number |
| 7 | U7 far field | 15–25 | every buried pattern |

About 6–10 weeks of session time end to end, U7 alone being a third of it.
U1–U4 are the cheap half and clear the corpus population that the census
cannot exercise today; U5 is the one users will meet first; U7 is the one that
turns "impedance and currents only" into a complete buried serve.

## What is deliberately not on the plan

- Contact under the reflection-coefficient model (#3): refused by decision
  since the D3 cleanup; the reflection-coefficient ground has no lower medium
  to put a contact end in. U1 removes the decks that hit it by accident.
- The detached-radial convention: both engines refuse it by name; not a
  target.
- A Windows 7 floor (`notes/PY38-FLOOR-AUDIT-2026-09-12.local.md`): 8–12 days
  and the frozen workbench still would not run there.
