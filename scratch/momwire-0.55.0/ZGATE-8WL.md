# momwire 0.55.0: the ~8 λ_m Z gate (registered before any run)

**Steve's decision (relayed by Laptop-builder):** before any antennaknobs
re-pin asserts "served" at about 8 in-medium wavelengths, gate the zero there,
in the shape of U4's PT1.

- momwire under test: main at 925678d48, a scratch worktree built with
  `make build`.
- Tooling: `z_gate_8wl.py`.

## Decks, built the way the app builds them

- **D1135.** `verticals.buried_radial_vertical` with `n_radials` 4, `depth`
  0.15, `length_factor` 1.2 and `radial_factor` 1.5, over soil B
  (`("finite", 20.0, 0.03)`) at 7.1 MHz.
  - The pointer momwire (495b6c951) refuses it at R1 = 37.995 m, which is
    7.97 λ_m.
- **D1131.** The same corner with `depth` 0.5.
  - R1 = 38.007 m, which is 7.98 λ_m.
- **The call.** Both are built with `MomwireEngine(builder, ground=SOIL_B)`,
  which is exactly what the app calls. SG is selected with
  `solver=SinusoidalGalerkinSolver`.

## Spellings, the ladder and the bar

- **shipped.** momwire main as it is: a 4 λ_m cap, with pairs past the cap set
  to zero. It runs at the app's mesh, `nominal_nsegs` 21.
- **extended.** The cap is moved to 9 λ_m, which is past both decks' R1. So
  nothing is zeroed, and the grid is tabulated out to the deck.
  - The shipped grids are evicted first, because of the 1.25ⁿ bucket trap
    (`get_grid_below` caches on the R1 bucket, not on the cap).
- **The ladder.** The extended spelling runs at `nominal_nsegs` 21 and 63.
  - **What that axis refines.** For this design it refines the FAR mesh only;
    the node grading is fixed by the recipe.
  - **Why it fits.** The far mesh is where the zeroed pairs live, and #1131
    measured a 3× far refinement moving the app's answer by ≤ 0.126 Ω.
- **The bar** (PT1's): |Z_ship − Z_ext(21)| ≤ 1e-2 × |Z_ext(63) − Z_ext(21)|.
- **Guards, all read before δ:**
  - the shipped plan reaches past 4 λ_m;
  - the shipped grid stops at the cap;
  - the extended grid is tabulated at or past the plan's R1;
  - δ is not bit-zero.

## G8: the reference's own accuracy

This guard is new, because the extended table runs past anything checked so
far.
- **What was checked before.** The below/below far annulus was gated to 4 λ_m
  (3.6e-5 against 2e-4), and U4's G-Z1 spot-checked [4.03, 4.7] λ_m.
- **Why that is not enough.** Here the extended reference is tabulated to
  9 λ_m, so its accuracy must be checked before it can be used as the
  reference.
- **What G8 checks.**
  - 40 off-node points: R1 ∈ {4.137, 4.613, 5.229, 5.871, 6.407, 7.031, 7.659,
    8.213} λ_m, crossed with θ ∈ {0.331, 0.613, 1.071, 1.931, 3.173}°.
  - At each point, the grid is compared against `iv_surfaces_direct_below`.
  - The θ set covers the decks' past-cap pairs: tip to tip is 0.45° at 0.15 m
    deep and 1.5° at 0.5 m, and the widest cross pairs sit near 3°.
- **The metric.** The worst relative error over the four surfaces.
- **The bar.** 2e-4, the grid's own gate.

## Predictions

| id | prediction | result |
|---|---|---|
| PG8 | **blind:** worst ≤ 2e-4 | |
| PZ8-B1135 | **blind:** bspline HITs at 1e-2 of the step | |
| PZ8-B1131 | **blind:** bspline HITs | |
| PZ8-S1135, PZ8-S1131 | **blind:** SG serves both decks, and both HIT | |

## Reading rules, fixed now

- **If PG8 misses,** the extended reference is not trustworthy that far out.
  The Z gate is not read. Stop and report.
- **If a bspline PZ8 row misses,** stop and report. Steve decides, before any
  tag, whether momwire should refuse past some range.
- **An SG miss** is reported the same way. SG refusing a deck is recorded, and
  does not count as a miss.
- **If G8 and both bspline rows hit,** report the numbers. The antennaknobs
  re-pins that assert "served" at these corners are then backed, and D1131's
  app answer is banked from the shipped `nominal_nsegs` 21 solve.

## Results [2026-09-14]

Registered at 828cc0b6b (05:51:13Z), before any run.

| id | result |
|---|---|
| PG8 | **HIT.** The worst relative error over 40 off-node points (4.14–8.21 λ_m × 0.33–3.17°) is 1.58e-8, on `IphiH` at 4.137 λ_m and 3.17°, against a bar of 2e-4. The extended table is a trustworthy reference out to 9 λ_m at soil B and 7.1 MHz (λ_m = 4.764 m). |
| PZ8-B1135 | **HIT.** δ = 2.66e-4 Ω against the 21 → 63 step of 0.0907 Ω, which is 2.9e-3 of the step and 1.0e-6 of \|Z\|. Z shipped = 99.6467+234.0345j. The plan's R1 is 7.975 λ_m. |
| PZ8-B1131 | **HIT.** δ = 9.35e-5 Ω against a step of 0.0893 Ω, which is 1.0e-3 of the step and 3.4e-7 of \|Z\|. Z shipped = 108.9379+253.9648j. The plan's R1 is 7.977 λ_m. |
| PZ8-S1135 | **HIT.** SG serves the deck: δ = 2.66e-4 Ω against a step of 0.0904 Ω, which is 2.9e-3 of the step. |
| PZ8-S1131 | **HIT.** SG serves the deck: δ = 9.37e-5 Ω against a step of 0.0906 Ω, which is 1.0e-3 of the step. |

Every guard holds on every row:
- the plan reaches past 4 λ_m;
- the shipped grid stops at the cap;
- the extended grid, at 9 λ_m, covers the plan;
- δ is not bit-zero.

**Reading, as registered.** G8 and both bspline rows hit.
- **What that backs.** The antennaknobs re-pins that assert "served" at these
  two corners.
- **What gets banked.** D1131's app answer, from the shipped `nominal_nsegs` 21
  solve: 108.93786519336538+253.96475104686718j. That is bit-identical to what
  the CORNERS `_solve` call returns, and its degree pair is 0.650 Ω.

**Margin.** The bspline rows sit 3.4× and 9.5× under the bar. That lies between
U4's soil-A margin (48×) and its fresh-water margin (2×).
