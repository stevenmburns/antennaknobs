# AK#1455: grade `elevated_buried_counterpoise`'s radiator from the feed

Registered 2026-09-15, **before any run**. Branch
`fix/1455-ebc-graded-radiator`, off main a9c49416f.

A gate failure is a stop and a report. A missed prediction is reported as a miss
and is not re-registered.

## What the issue asks

- **Grade the radiator from the feed,** as `buried_radial_vertical` grades its
  rise and radiator.
  - **Adjacent segments within 2×.** `graded_wire`'s growth-4 recipe gives 2.4 m
    middle segments on this radiator.
  - **The fed segment at a matched size,** with the feed staying middle-of-wire.
- **The gate.** NEC-5's R moves < 1 % across nominal_nsegs 21 / 42 / 84 at the
  new default, and momwire stays within its current pins.
- **Then re-pin** whatever pins this design.

## The design, fixed here

- **The schedule is the one antennaknobs#1454 measured**
  (`scratch/1443-counterpoise/step2_source.graded_schedule`), promoted to
  `wire_catalog.doubling_graded_wire`:
  - panels double in length from 2·h0, along the radiator from its feed end;
  - each panel's segment is min(max_h, max(h0, panel start / 2)). So adjacent
    segments differ by at most 2×, and none exceeds max_h.
  - **One guard is added to AK#1454's function.** A last panel shorter than its
    own segment is merged into the panel before it. Without that, a short tail
    at some other knob setting would put a step larger than 2× beside it. At the
    default geometry the guard does not engage, and G2 asserts the schedule
    there equals AK#1454's.
- **h0 = 25 mm.** The fed wire is the house 50 mm gap, which NEC-5 meshes as two
  25 mm segments. momwire's odd port meets the radiator's first 25 mm segment
  with its single 50 mm fed segment, a 2× step.
- **max_h is the design's own radiator segment** at that nominal_nsegs: the
  radiator's length over `segs_for(length, λ_design / 4)`. That is 500.3 mm at
  21, 250.2 mm at 42 and 125.1 mm at 84, so nominal_nsegs refines the far panel
  exactly as it refined the whole radiator before.
- **Unchanged:**
  - the fed wire (50 mm, `ex`, the gap in the middle of that wire);
  - the buried screen and the knobs;
  - the docstring's first line, which the catalog page is generated from.
- **`GradedSegments`' scope freeze.** This is the second consumer its note
  anticipates, with an issue (AK#1455) and a measurement (AK#1454) before it.
- **What users see.**
  - **Engines.** momwire and NEC-5 are the only engines that serve this design,
    and both take a graded wire: momwire as polyline vertices, NEC-5 as one GW
    card per panel. pynec and nec2 already refuse it as buried.
  - **The NEC-2 deck export already refuses it.** Its refusal sentence changes
    from the buried-wire one to the graded-mesh one, as
    `buried_radial_vertical`'s already reads; both point at the NEC-5 download.

## Gates and predictions

**The harness.** `ladder.py`, measuring the design at its defaults (soil 13 /
0.005, 7.1 MHz).
- **Scope.** Both engines, the stock ports, nominal_nsegs 21 / 42 / 84.
- **Two radiators:** the graded default, and the stock radiator (the design as it
  was, rebuilt for comparison).
- **NEC-5:** `nec5cl-x13-static` (sha256 7ebf343d…), the binary AK#1454 used.
- **momwire:** antennaknobs' pointer, 0.55.0 (1ca8725), the tree CI tests against.

| id | what | bar | prediction |
|---|---|---|---|
| **G1** | NEC-5 R across nominal_nsegs 21 / 42 / 84 on the graded default: (max − min) / R(84) | < 1 % | ≤ 0.5 %. AK#1454's graded radiator read 0.26 % with a 6.25 mm source. |
| **G2** | The graded mesh at 21 / 42 / 84, from the built wires, no solve:<br>• adjacent radiator segments within 2×;<br>• no segment above that nominal_nsegs' stock radiator segment;<br>• the first radiator segment 25 mm;<br>• the cap equal to the stock radiator's own segment;<br>• (fracs, counts) equal to AK#1454's `graded_schedule` at the defaults;<br>• the fed wire unchanged (50 mm, `ex`, momwire's feed at arclength 25 mm). | all | passes |
| **G3** | momwire's pins | no test, fixture or public page pins this design's impedance. That was checked across `tests/`, `docs/` (outside dated status records) and `site/`, so momwire's movement is reported, not gated. | momwire R on the graded default moves ≤ 0.3 % across 21 / 42 / 84 |
| **C1** (context) | NEC-5 R across 21 / 42 / 84 on the stock radiator | reported | moves by more than 3 %. The census read 30.643 → 29.417 from 21 to 42. |

## Order

1. Commit this registration.
2. Implement the helper, the design change and the tests.
3. G2, geometry only.
4. The ladder: G1, G3 and C1.
5. Lint, and the antennaknobs tests with momwire at the pointer.
6. Open the PR, unmerged.
