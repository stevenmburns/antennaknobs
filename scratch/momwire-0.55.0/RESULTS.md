# Results: the AK suite against momwire main

The predictions were registered in `PREDICTIONS.md` (1e549017b) before any run.

| id | result |
|---|---|
| Q1 | **HIT.** L1's two named tests fail with `assert not True`: #1135's headline corner and the radial 0.95 threshold are now served. |
| Q2 | **HIT.** `test_the_preflight_agrees_with_the_solve` passes all 10 parametrizations. |
| Q3 | **MISS.** L1 had 3 failed, 4967 passed and 37 skipped. The third failure is `tests/test_below_reach_preflight_contact_1464.py::test_a_wire_strictly_below_is_still_asked`, with "DID NOT RAISE ValueError": the test builds #1135's headline corner and expects the `"below/below"` refusal. The skips are all environment gates: 34 for NEC-5 binaries, 2 deck-faithful, and 1 capability-declared. |
| Q4 | **MISS.** L2 had 1 failed, 34 passed and 1 skipped. The failure is `tests/test_buried_knob_corners_1131.py::test_the_all_knobs_max_corner_refuses_BY_NAME`, again "DID NOT RAISE": the all-knobs-max corner now solves. |

**Attribution.** All four tests pass when run against the pointer momwire
(495b6c951, built in this worktree). There, each deck draws the past-cap range
refusal against soil B's 19.058 m cap:

| deck | R1 at the pointer |
|---|---|
| #1135 headline corner, used by both the #1135 and #1464 tests | 37.995 m (7.97 λ_m) |
| threshold, radial 0.95 | 20.051 m (4.21 λ_m) |
| #1131 all-max corner | 38.007 m (7.98 λ_m) |

So all four failures are U4 behaviour (momwire#1058), and all four are
re-pins. No failure comes from anything else.

**Why the grep missed two of them.** The two misses match `"below/below"` and
the singular "in-medium wavelength", not the plural sentence the registration
searched for.

**Caveat.** Two of these corners sit at about 8 λ_m, twice the 4.76 λ_m span of
the synthetic deck on which U4's Z-level bound was measured. U4's field-level
screen did reach 8 λ_m. Re-pinning those corners as served asserts that the
zero is good there, and U4 did not gate that at the Z level.
