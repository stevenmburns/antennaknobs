# AK#1469 slice 1 — a NEC-5 knot source on a single wire imports without cutting the wire

Registered before any source change (2026-09-13, Laptop-builder). Branch `feat/1469-feed-position-slice1` from main f77b4fd; momwire submodule at main 1dc1f63.

## Decided (Steve, 2026-09-13)
- **Middle-of-wire feeds stay the antennaknobs standard.**
- **Segment-centre and segment-end addressing is not the interface.** It lives only in NEC deck import/export.
- **The escape hatch is a position along the wire,** an arclength fraction `at`. Engines report any offset between the requested and placed point, and nothing moves silently.
- **Don't cut wires, and don't rejoin them afterwards either.**

## Scope of slice 1 (revised before any source change, same day)
The corpus sets the order. 472 of the 476 catalog-nec5 decks carry a MIDDLE knot source: NEC5Engine writes every centre feed as `EX tag n/2 2`. The other 4 source at knot 0, a wire end. The raw corpus has no NEC-5 edge sources at all, so no corpus deck carries an off-centre interior knot. `Wire.at` is therefore deferred to slice 2, where off-centre NEC-2 segment feeds (the #872 cuts, which ARE common) need it anyway. Adding the field once, for both, is less churn than adding it twice.

Slice 1 is therefore:
- **A middle voltage knot source** (interior knot k = n/2) on a wire with no other claim imports as the WHOLE named wire + `PortOnWire`, today's standard middle-of-wire feed. No new field. Every catalog-nec5 deck and AC6LA's deck take this path. It falls back to today's cut + `PortAtVertex` when any of these holds:
  - more than one claim on the wire (a second source, or an `LD`/`TL`/`NT` mark);
  - a junction boundary on the wire (`_junction_cuts`);
  - a virtual anchor;
  - an EX 4 current source (kept on the proven path until an engine check covers `DrivenCurrent` on `PortOnWire`).
- **The feed marker sits at the true source point on every lane:**
  - a `PortOnWire` marker at the named wire's physical middle (the NEC-5 lane drew it at the middle SEGMENT's centre, half a segment off on an even count);
  - a `PortAtVertex` marker at its knot (the NEC-5 lane drew it at the piece's middle; the momwire lane drew none).
- **Unchanged in slice 1:** off-centre interior knots and knots 0/n keep today's cut + `PortAtVertex`. `Wire.at` and its per-engine placement rules are slice 2.

## Gates (registered predictions)
- **G1, AC6LA round trip.** `dipoles.invvee.default.somm13.nec` imports as 3 wires, with GW 3 whole at 2 segments carrying `PortOnWire('feed')`. The NEC-5 engine deck writes `GW 3 2 …` and `EX 0 3 1 2`, with no GW 4.
- **G2, fallbacks unchanged.** An off-centre interior knot (`GW 1 11 …` with `EX 4 1 6 1`, knot 5 of 11) still imports as two pieces + `PortAtVertex`. So does a middle knot on a wire that carries a second claim.
- **G3, NEC-5 impedance.** Printed Z on AC6LA's deck identical to 5 significant figures between today's split spelling and the whole-wire spelling (NEC-5 x13, laptop).
- **G4, marker.** AC6LA's feed marker lands at (0, 0, 7.000) ± 1e-9 m on the NEC-5 and momwire lanes. A `PortAtVertex` fallback's marker lands on its knot on both lanes.
- **G5, refinement.** `NecDeck.refined(r)` keeps a middle knot in the middle (k·r of n·r), and `test_a_knot_source_keeps_its_knot` (off-centre knots, the fallback) passes unchanged.
- **G6, momwire impedance before/after** on the catalog-nec5 decks that serve both before and after (bspline default). Prediction: |ΔZ|/|Z| <= 1e-3 on every such deck. The whole-wire spelling changes the fed wire's count (odd coercion) and swaps a C0 node gap for a C1 mid-segment gap; probe3b measured the spelling at ~0.015 Ω on soil (#449). A deck above the bound is a finding to report, not a failure to hide.
- **G7, no regression.** The fast lane (`pytest`), vitest, ruff and tsc stay green. Expected test changes: `test_nec_import_dialects.py::test_interior_knot_splits_the_wire` for a middle knot, plus new G1/G2/G4 tests.

## Known behaviour change, stated up front
Importing a middle knot as a middle-of-wire feed means PyNEC and NEC-2 now SERVE middle-knot NEC-5 decks they refused before, with the count coerced to odd. That is the standard feed, and it follows the decision. AK#1456 (per-engine fed-wire parity) applies to these decks exactly as it does to every catalog middle feed.

## Outcome (2026-09-13)
- **Hit:** G1, G2, G4, G5. They are pinned in `tests/test_middle_knot_source_1469.py`.
- **G3 hit.** AC6LA's deck prints 48.497 − j11.378 on NEC-5 x13 before and after, and GW 3 goes out whole.
- **G6 MISSED as registered.** 284 of the 466 decks served on both runs move by more than 1e-3. The change scales with the feed impedance: median 7.0e-4 below 100 Ω, 1.5e-3 at 100–300, 4.8e-3 at 300–1000, 2.6e-2 above 1 kΩ, and a worst case of 0.110. AC6LA's invvee decks move 0.034–0.043 Ω. `buried_radial_vertical` on somm13 goes from refused (the cut made an above-side junction) to served at 78.14 + j46.33.
- **Follow-up (post hoc, NOT registered before the run):** which spelling lands closer to the catalog design solved directly? The reference is `native_reference.py`, which builds each design the way the export does. The whole-wire spelling is closer on 112 of 118 decks:
  - |Z| < 300 Ω: 70 of 70, median distance 2.3e-3 → 2.3e-4;
  - |Z| ≥ 300 Ω: 42 of 48, median 3.1e-2 → 6.6e-3.
  So G6's bound was wrong in kind: today's cut spelling was itself further from the design than the bound, and slice 1 moves imports TOWARD the design.
- **Separate finding, not slice 1's:** `wire.rhombic` (~59 %) and `broadband.t2fd` (~38 %) sit far from the native design in BOTH spellings, so the catalog round trip loses something on those two terminated designs.
- **G7:** CI green on the draft PR (build, frontend, ruff, wheel lanes).
