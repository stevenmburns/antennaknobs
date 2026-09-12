# probe41 — the AGARD slope ratio, read from the shipped solver

Haswell (i7-4770K), 2026-09-12. Scratch only. The question: is probe31's
slope-ratio "gap" (§6 row 31, §7 adjudicator 1, and momwire
`scratch/956-readjudication/MEASUREMENTS.md`) still a gap after momwire#1043's
W-terms fix?

**No.** On momwire 0.54.0 (`260bd91`) the shipped solver's junction satisfies
the AGARD slope condition I′(0⁺)/I′(0⁻) = 1/ε̃ **in full complex form** to
2–9 × 10⁻⁴ on every rung whose node segment is ≥ 3 mm, with nothing imposing
it. On the pre-fix kernel (`0e72ab4`) the same ratio is 47 % → 102 % → 462 %
off and diverging. The fix is what closed it.

## Why a new probe

Both problems were in the instrument, not the solver:

1. **§6 graded a complex quantity by its magnitude.** Session 6's banked
   `results/probe31-currents.json`, read in complex form against
   1/ε̃ = 0.03894+0.03846j (|0.05473|, +44.6°):

   | rung | slope ratio | \|·\| | phase | \|ratio − 1/ε̃\| / \|1/ε̃\| |
   |---|---|---|---|---|
   | g1 | 0.0431+0.0127j | 0.0450 | +16.4° | 48 % |
   | g2 | 0.0508−0.0161j | 0.0532 | −17.6° | 102 % |

   The magnitudes approach |1/ε̃|; the ratio moves away from it, 60° off in
   phase. "Converging onto AGARD" was a magnitude coincidence.

2. **probe31 reads the ratio through the phase-2 probe composition**, which
   today fails probe29's ε̃ = 1 known answer by 35 % on every commit
   (momwire#1044). Its re-run values (1.223 at g1, 0.0636 / 0.0642 at g2) say
   nothing about the fix either way.

probe41 takes the ratio from `BSplineSolver.compute_impedance()` itself —
`current_slopes` is the exact spline derivative — on probe31's deck, meshed
with probe18's grades plus finer rungs.

## Result

Distance = \|ratio − 1/ε̃\| / \|1/ε̃\|, on the complex values.

| rung | node segment | pre-fix `0e72ab4` | **0.54.0 `260bd91`** | ε̃ = 1 control, 0.54.0 |
|---|---|---|---|---|
| g1 | 50 mm | 47 % | **0.03 %** | 1.5e-4 |
| g2 | 12.5 mm | 102 % | **0.02 %** | 1.3e-5 |
| g3 | 3.1 mm | 462 % | **0.09 %** | 3e-6 |
| g2×2 | 6.25 mm | 191 % | **0.04 %** | < 1e-6 |
| g3×2 | 1.56 mm | — | 0.30 % | < 1e-6 |
| g4 | 0.78 mm | — | 2.4 % | 1.8e-5 |

Continuity, \|I(0⁺) − I(0⁻)\| / \|I(0⁺)\|: pre-fix 1.5e-5 … 1.3e-4; 0.54.0
6.4e-8 … 2.6e-7 (8.2e-6 at g4).

Anchors that this is the right object on both sides:

- 0.54.0 g1 reads **169.7756−82.2800j**, #1044's fixed-kernel record
  (169.7754−82.2803j). Pre-fix g1 reads **138.9609−102.6097j**, #1044's "was"
  row to the digit.
- Pre-fix g2's ratio **0.050758−0.016130j** reproduces session 6's banked
  0.05076−0.01606j to four digits. Session 6's probe31 was reading what the
  pre-fix shipped solver reads, phase included.

## Why it is a measurement and not a construction

- **No constraint row.** `kcl_A` is empty (0 × 32 at g1); each arm keeps its
  own node coefficient. Continuity and the slope condition both come out of the
  fill.
- **The crossing serve ran.** One `cross_complete_block_split` call per solve,
  every rung, counted.
- **The derivative is the derivative.** A one-sided finite difference of the
  current agrees with `current_slopes` to ≤ 5e-6 on every 0.54.0 rung.
- **It can fail.** `--variant` removes one piece of the complete fill (soil A,
  0.54.0). Each cell: distance / continuity deficit / Z.

  | rung | corner0 | selfcomp0 |
  |---|---|---|
  | g1 | 393 % / 1.2 / 52.83−954.36j | 4171 % / 9.8 / 29.28−980.04j |
  | g2 | 3.4 % / 2.0 / 297.71−452.77j | 21841 % / 9.2 / 29.30−980.00j |
  | g3 | 429 % / 8.8 / 26.97−969.41j | 830 % / 12 / 29.21−979.88j |

  Either removal breaks continuity and moves Z by hundreds of ohms. Note
  corner0 at g2: the ratio lands 3.4 % from AGARD while continuity is violated
  by 200 %. **A slope ratio read without its continuity deficit can pass by
  accident.**

## One loose end, not a gap

At g4 the node segment (0.78 mm) is shorter than the wire radius (1 mm). Soil A
drifts to 2.4 % and its continuity to 8e-6, while the ε̃ = 1 control stays at
1.8e-5; g3×2 (1.56 mm) is already at 0.30 %. So the degradation appears only
with ε̃ ≠ 1 and only as the node segment approaches the radius — most likely
the thin-wire treatment running out near the interface. momwire's node advisory
(`warn_coarse_node`, 25 mm bar) warns when the node is too coarse, not too fine.

## What this changes in the record

- **§6 row 31 / §7 adjudicator 1**: "slope-ratio magnitude converging onto
  AGARD" is superseded. On the kernel it was measured on, the ratio did not
  converge; on the corrected kernel it satisfies AGARD at every resolved rung.
- **momwire `scratch/956-readjudication/MEASUREMENTS.md`**: "the fix is
  neutral-to-slightly-adverse on probe31's slope ratio" does not hold on the
  shipped solver. Corrected there.
- **The §7 restate-or-retire question narrows.** Adjudicator 1 is answered on
  the shipped solver, with no need to repair the phase-2 composition first.

## Reproduce

```
# momwire at the commit under test, extension built (`make build`)
P=scratch/524-phase2/proto/probe41_production_slope.py
python $P --ground soilA 1 2 3 4 2x2 3x2
python $P --ground eps1  1 2 3 4 2x2 3x2
python $P --variant corner0   1 2 3
python $P --variant selfcomp0 1 2 3
```

Each solve takes under a second. The probe writes only with `--out`; the banked
runs are `results/probe41-<commit>-<variant>-<ground>.json`.
