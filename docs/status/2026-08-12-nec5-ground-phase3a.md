# 2026-08-12 — Sommerfeld height sweep: the reactance split dissolves (#872 phase 3a)

## Goal

Phase 3(a) of #872: map the reactance-split curve the pinned 0.048 λ
point sampled — "NEC-5 ~7 Ω from the mutually-agreeing NEC-2 lineage,
resistances matching" — across heights 0.02–1.0 λ over Sommerfeld ground
("finite", 13, 0.005). Instrument: `scripts/bench_nec5_ground.py`;
artifact `scratch/nec5-ground-phase3a.json`.

Setup: 5 m dipole at 28.5 MHz, feed positions exact everywhere (center
knot / center gap of a symmetric dipole); NEC-5 as a Richardson (40, 80)
pair per the phase-2 recipe, with the raw NS=20 read — what the pinned
test actually sampled — recorded beside it; bs2/sin/pynec at N=81; nec2c
NS=81 hand decks.

## Result: there is no reactance-split curve

| h/λ | nec5 raw NS=20 | nec5 extrap | nec2c | bs2 | ΔX vs nec2c | ΔX vs bs2 |
|---|---|---|---|---|---|---|
| 0.02 | 87.99 +1.03j | 89.34 +7.81j | 89.23 +7.94j | 89.30 +7.99j | −0.12 | −0.17 |
| 0.048 | 61.89 −28.75j | 62.81 −21.62j | 62.89 −21.56j | 62.86 −21.52j | −0.06 | −0.10 |
| 0.10 | 51.14 −27.45j | 51.98 −19.92j | 52.05 −19.89j | 52.02 −19.84j | −0.03 | −0.08 |
| 0.30 | 78.83 −31.17j | 80.18 −23.68j | 80.25 −23.58j | 80.24 −23.54j | −0.10 | −0.14 |
| 1.0 | 65.25 −41.95j | 66.34 −34.58j | 66.23 −34.51j | 66.42 −34.46j | −0.07 | −0.12 |

(11 heights total in the artifact; every row looks like these.)

- **Extrapolated NEC-5 agrees with nec2c and bs2 to ≤ 0.17 Ω in X at
  every height** from 0.02 λ to 1.0 λ. NEC-5 never departs the NEC-2
  lineage over Sommerfeld ground; the phase-3 question "where and how
  fast does it depart" has the empty answer.
- **The documented 7 Ω split was 100% the knot-source mesh march.** The
  raw NS=20 column sits a uniform ~7.0–7.5 Ω low in X (and ~1 Ω in R)
  at *all* heights — height-independence is exactly the signature of a
  feed-model term rather than close-ground physics. The prior-data-point
  framing in #872 ("genuine formulation difference in the close-ground
  interaction") is retired.
- sin and pynec agree throughout as well (artifact); nec2c wobbles
  ~0.75 Ω in R at 0.5–0.75 λ against the other four — noted, within
  historical nec2c scatter.

`test_live_low_height_sommerfeld_documented_gap` now pins both halves:
the raw NS=20 march (the trap a single-mesh comparison falls into,
stable and reproducible) AND its extrapolated resolution (|ΔX| < 1.5 Ω
against momwire at the same point).

## Consequences for the study

- The phase-1/2 recipe (aligned feeds + Richardson pairs) holds over
  Sommerfeld ground unchanged — close ground does not break the
  extrapolation order.
- Every "NEC-5 vs X" number in earlier #825/#872 threads taken at a
  single mesh should be re-read with the ~7 Ω/NS=20-class march in mind.

## Deferred: phase 3(b), the contact-geometry extensions

The momwire#291 extensions (radius ladder, slant contact, 3-wire star)
are deliberately not in this instrument yet: a faithful base-fed
ground-contact spelling per engine is exactly where feed-model artifacts
breed (the momwire#300 bridge lesson — antennaknobs' catalog base-feed
idiom puts the gap eps/2 above the contact NEC-5 feeds exactly), so it
needs its own carefully-oracled setup at the momwire level, matching
#291's spelling verbatim.
