# AK#1469 slice 1 — a NEC-5 knot source on a single wire imports without cutting the wire

Registered before any source change (2026-09-13, Laptop-builder). Branch `feat/1469-feed-position-slice1` from main f77b4fd; momwire submodule at main 1dc1f63.

## Decided (Steve, 2026-09-13)
- **Middle-of-wire feeds stay the antennaknobs standard.**
- **Segment-centre and segment-end addressing is not the interface.** It lives only in NEC deck import/export.
- **The escape hatch is a position along the wire,** an arclength fraction `at`. Engines report any offset between the requested and placed point, and nothing moves silently.
- **Don't cut wires, and don't rejoin them afterwards either.**

## Scope of slice 1
A NEC-5 knot source (EX with I4 = 2, a negative segment, or EX 4) at an INTERIOR knot k of a wire with n segments imports as a feed on the WHOLE authored wire at fraction k/n.
- **Middle knot (k/n = 1/2):** a named whole wire + `PortOnWire`, today's middle-of-wire feed, with no new field. This covers every AC6LA catalog deck, since NEC5Engine writes centre feeds as knot sources.
- **Off-centre knot:** a named whole wire carrying `Wire.at = k/n` + `PortOnWire`.
- **Falls back to today's cut + `PortAtVertex`** when any of these holds:
  - more than one claim on the wire (two sources, or a source plus an `LD`/`TL`/`NT` mark);
  - a junction boundary at that knot (a T-junction knot is a real vertex port);
  - a virtual anchor;
  - a knot at 0 or n (a wire end).

## Per-engine placement of `at = p/q` (lowest terms)
| engine | legal point | count rule | slice 1 |
|---|---|---|---|
| NEC-5 | knot | N a multiple of q (the middle, q = 2, is today's even rule) | `EX tag p·N/q 2` on the whole wire |
| momwire bspline d=2, sinusoidal-Galerkin (point feed) | any arclength | none needed; avoid N with the feed exactly on a knot for d=2 (#449 C1) | feed arclength = at·L, flipped to (1 − at)·L when the walk runs the wire backwards |
| momwire razor, bspline d=1 | knot | N a multiple of q | same |
| momwire sinusoidal, pulse, harrington; PyNEC; NEC-2 | segment centre | the middle is today's odd rule | off-centre `at` REFUSED BY NAME (slice 2 adds the count rule and its advisory) |

Exports (`nec_export`, `nec5_export`, `simnec_export`) inherit each engine's placement, and refusals stay by name. The web feed marker comes from the placed point on every lane.

## Gates (registered predictions)
- **G1, AC6LA round trip.** `dipoles.invvee.default.somm13.nec` imports as 3 wires, with GW 3 whole at 2 segments carrying `PortOnWire('feed')` at the middle. The NEC-5 engine deck writes `GW 3 2 …` and `EX 0 3 1 2`, with no GW 4.
- **G2, off-centre knot.** `GW 1 11 …` with `EX 4 1 6 1` (knot 5 of 11) imports as ONE wire with `at = 5/11`. The NEC-5 deck keeps 11 segments and addresses knot 5, as segment 5 end 2 or an equivalent address.
- **G3, NEC-5 impedance, same geometry.** Printed Z identical to 5 significant figures on AC6LA's deck between today's split spelling and the whole-wire spelling (NEC-5 x13 on this laptop).
- **G4, marker.** The NEC-5 and momwire lanes put AC6LA's feed marker at (0, 0, 7.000) ± 1e-9 m. Today NEC-5 is 2.5 cm off and momwire draws no marker.
- **G5, refusals.** An off-centre `at` refuses by name on PyNEC, NEC-2 and the sinusoidal, pulse and harrington solvers. A middle feed is served everywhere it is today.
- **G6, U2 refinement.** `NecDeck.refined(r)` keeps `at` (k·r/(n·r) = k/n), and `test_a_knot_source_keeps_its_knot` passes unchanged.
- **G7, momwire impedance before/after** on the catalog-nec5 decks that serve both before and after (bspline default). Prediction: |ΔZ|/|Z| ≤ 1e-3 on every deck, because today's C0 node-gap spelling and a C1 whole-wire gap differ only in the feed spelling (probe3b measured ~0.015 Ω on soil, #449). A deck above the bound is a finding to report, not a failure to hide.
- **G8, no regression.** The full fast lane (`pytest`), vitest, ruff and tsc stay green. The expected test change: `test_nec_import_dialects.py::test_interior_knot_splits_the_wire` becomes "keeps the wire whole".

## Known behaviour change, stated up front
Importing a middle knot as a middle-of-wire feed means PyNEC and NEC-2 now SERVE centre-knot NEC-5 decks they refused before, with the count coerced to odd. That is the standard feed, and it follows the decision. AK#1456 (per-engine fed-wire parity) applies to these decks exactly as it does to every catalog middle feed.
