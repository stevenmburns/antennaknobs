# antennaknobs#1516 — refinement ladders on the four bs2-outlier designs

**Measure only.** Registered 2026-09-15 before any ladder solve. §6 discloses
exactly what had already been solved when the bars in §5 were written.

## 1. The question

The catalog study (`scratch/catalog-razor-nec5-bs2`) found four designs where
razor-2p agrees with a real NEC-5 binary to 0.09–2.0 % while bs2 differs from
both by 16–50 %:

| design | ground | razor vs NEC-5 | bs2 vs NEC-5 |
|---|---|---:|---:|
| `loops.skyloop_lmatch` | free | 0.12 % | **49.62 %** |
| `verticals.rectangle` | free | 0.51 % | **34.29 %** |
| `dipoles.koch_dipole` | free | 0.09 % | **30.06 %** |
| `verticals.four_square` | free (port 1) | 0.26 % | **22.11 %** |
| `verticals.four_square` | somm (port 0) | 2.00 % | **16.11 %** |

Three explanations are on the table for each design, and they are
distinguishable by how the gap behaves under mesh refinement:

* **deck difference** — the engines are not solving the same structure. Settled
  in step 1, before any ladder, and it would make the ladder meaningless.
* **convergence** — one side is unconverged at the default mesh. The gap then
  SHRINKS as the mesh refines. Sub-cases: *bs2 unconverged* (bs2 moves toward
  the tent pair) or *tent pair unconverged* (razor and NEC-5 both move toward
  bs2, together).
* **formulation** — a stable gap that refinement does not close.
* **unexplained** — anything else, said plainly rather than rounded to one of
  the above.

## 2. Setup

| axis | value |
|---|---|
| antennaknobs | `main` at `cc87956fd` (`6e63a763b` + two docs commits; no `src/`, no pointer move) |
| momwire | submodule pointer `1ca8725`, `MOMWIRE_REQUIRE_ACCEL=1` |
| NEC-5 | `nec5cl-3b75639` via `NEC5_EXE`, run as an opaque binary |
| grounds | free space on all four; **plus Sommerfeld `("finite", 13.0, 0.005)` on `four_square`**, whose 2.0 % razor row was the Sommerfeld one |
| threads | `OMP_NUM_THREADS = OPENBLAS_NUM_THREADS = MKL_NUM_THREADS = 4` |
| dispatch | one worker subprocess at a time, `RLIMIT_AS` 40 GB, 300 s timeout |

Engine spellings unchanged from the catalog run:

```python
bs2 = MomwireEngine(b, solver=BSplineSolver, solver_kwargs={"degree": 2}, ground=G)
razor = MomwireEngine(
    b, solver=RazorSolver, solver_kwargs={"nec5_quadrature": True}, ground=G
)
nec5 = NEC5Engine(b, ground=G)
```

## 3. Step 1 — deck equivalence, before any ladder

Per design × engine × rung, recorded: per-wire segment counts as the engine
actually meshes them, total segments, `fed_segments()`, the network as each
engine receives it, the ground model, and the smallest Δ/a anywhere in the mesh.
Every difference is named.

`loops.skyloop_lmatch` carries an **L-match** — a 0.87 µH series inductor at
Q_L 200 into a 60.01 pF shunt, driving virtual port `in` and feeding
`PortOnWire('feed')`. It is applied by antennaknobs' own network reduction on
the antenna Y, identically for all three engines: it is NOT written into the
NEC-5 deck, which carries no `NT`/`LD` line for it. So it cannot be a deck
difference — but it can be an **amplifier**, and the bare-feed control in §6
measures how much.

## 4. Step 2 — the ladders

`nominal_nsegs` at **×1 = 21, ×2 = 42, ×4 = 84, ×8 = 168**, all three engines,
plus a **served-mesh rung at `nominal_nsegs = 40`** — which is exactly what
`razor-2p`'s `default_n_per_wire=40` becomes in the web adapter
(`adapter.py:1876` assigns `n_per_wire` straight to `builder.nominal_nsegs`) and
is the density the app's razor tab uses. The catalog run's razor was at ×1, not
there. All three engines run the 40 rung so it is self-contained.

`loops.skyloop_lmatch` additionally runs a **bare-feed variant** at every rung —
the same design with the L-match replaced by a bare `Driven(PortOnWire('feed'))`
and nothing else changed — so the network's amplification can be separated from
the antenna's own disagreement.

Recorded per cell: Z at every port, `fed_segments()`, the per-wire segment
counts the engine actually built, total segments, wall time, status.

## 5. Predictions — registered before the first ladder solve

* **P1 (the headline, per design).** bs2 is unconverged rather than
  formulation-different: `rel|ΔZ|(bs2, NEC-5)` at ×8 is **≤ 0.25×** its value at
  ×1, on **all four** designs (free space; four_square scored on port 0).
* **P2.** The tent pair stays locked at every rung: `rel|ΔZ|(razor, NEC-5)`
  ≤ **1 %** at every free-space rung of all four designs, and ≤ **2.5 %** at
  every Sommerfeld rung of `four_square`.
* **P3 (deck equivalence).** At every rung, razor's and NEC-5's per-wire segment
  counts are identical card for card, and bs2's differ **only** on the fed edge
  (its odd parity leaves one segment where the even pair takes two). Bar: zero
  differences anywhere else, on every rung of every design.
* **P4 (the L-match amplifies).** On `skyloop_lmatch` the ratio
  (bs2-vs-NEC-5 gap through the L-match) / (the same gap at the bare feed) stays
  **> 1.2** at every rung, while both shrink under P1.
* **P5 (razor's served mesh earns its keep).**
  `|Z_razor(40) − Z_razor(×8)| ≤ 0.25 × |Z_razor(×1) − Z_razor(×8)|` on all four
  designs in free space.
* **P6 (geometry, not a solve).** The peer's Δ/a risk on `koch_dipole` does not
  materialise: the smallest Δ/a anywhere in any design at any rung stays
  **above 30**, well clear of the regime where a reduced thin-wire kernel stops
  being comparable. This one is computed from geometry alone and was measured
  before the bars were written (§6) — it is registered as a stated expectation
  about the ladder's top rung, not as a discovery.

Misses are reported as misses, with the number that missed them.

## 6. Disclosure: what was already solved when §5 was written

* **The ×1 rung of all four designs, both grounds** — it is the catalog run, and
  it is the table in §1. P1 and P4 are about how the gap MOVES from there, which
  was not known.
* **The bare-feed control on `skyloop_lmatch` at ×1 only**: razor
  265.684 − 190.017j, NEC-5 265.710 − 190.340j, bs2 258.783 − 79.594j — 0.10 %
  and **33.95 %**, against 0.12 % / 49.62 % through the L-match. That is where
  P4's 1.2 bar comes from (the measured ×1 ratio is 1.46), and it is why P4 is
  stated as a floor rather than a number.
* **Δ/a and the mesh sizes at ×1 and ×8**, from geometry with no solve: minimum
  Δ/a is 200.0 at ×1 on three designs (188.0 on `koch_dipole`) and 31.0–31.3 at
  ×8. Hence P6.
* **The engines' ×1 meshes**, also construction-only: razor and NEC-5 agree
  card-for-card (91/91, 88/88, 66/66, 168/168 segments) and bs2 differs only on
  the fed edge. Hence P3, which extends that to every rung.

Nothing above is a ladder rung other than ×1.

## 7. Output

Branch `scratch/1516-ladders`, no PR, no issue comments, no names. NEC-5
conclusions and aggregates only — impedances and timings, never a printout.

* `run_ladders.py` — harness (driver + `--worker`)
* `records.jsonl` — one record per design × variant × ground × rung × engine
* `report.py` — writes every table in `README.md` from the JSONL
* `hypotheses.md` — the per-design verdicts, included verbatim by `report.py`
* `README.md` — deck-equivalence tables, ladder tables, verdicts, P1–P6 scored
