# Catalog: razor-2p vs NEC-5 vs bs2

**Registered 2026-09-15, BEFORE the sweep.** The predictions in §4 were written
down and committed before any of the 103 designs was solved by the harness. What
*had* been solved by hand while wiring the lanes up is disclosed in §5 — four
designs, and the bars below are set loosely enough that those four do not decide
any of them.

## 1. The question

`razor-2p` is momwire's NEC-5 *formulation twin*: a tent basis tested by NEC-5's
own razor-blade (mixed-potential path) rule, with `nec5_quadrature=True` binding
the two-point ∫A·dl evaluation NEC-5 uses. If that claim is true, razor should
track a real NEC-5 binary across the whole catalog far more closely than momwire's
own default B-spline degree-2 lane does. Nobody has measured it across the catalog.

So: for every built-in design, at its own defaults, solve the driving-point
impedance three ways and publish the distributions of

* `rel|ΔZ|` razor vs NEC-5  — **the headline**
* `rel|ΔZ|` bs2   vs NEC-5
* `rel|ΔZ|` bs2   vs razor

with `rel|ΔZ| = |Z_a − Z_b| / |Z_ref|` per port, `Z_ref` being the
second-named engine.

## 2. What is held fixed

| axis | value |
|---|---|
| antennaknobs | `main` at `6e63a763b` |
| momwire | submodule pointer `1ca8725`, built with `MOMWIRE_REQUIRE_ACCEL=1` |
| NEC-5 | `nec5cl-3b75639`, run as an opaque binary via `NEC5_EXE` |
| designs | all 103 `family.name` built-ins, `nominal_nsegs` at the framework default (21) |
| frequency | each design's own default |
| grounds | `free` and `somm` = `("finite", 13.0, 0.005)`, the app's `DEFAULT_GROUND` |
| threads | `OMP_NUM_THREADS = OPENBLAS_NUM_THREADS = MKL_NUM_THREADS = 4` |
| dispatch | one worker subprocess at a time, `RLIMIT_AS` 40 GB, 300 s timeout |

Engine spellings, exactly:

```python
bs2 = MomwireEngine(b, solver=BSplineSolver, solver_kwargs={"degree": 2}, ground=G)
razor = MomwireEngine(
    b, solver=RazorSolver, solver_kwargs={"nec5_quadrature": True}, ground=G
)
nec5 = NEC5Engine(b, ground=G)
```

`razor-2p`'s served option `extended_kernel` stays at its solver default
(`False`), which is what "at defaults" means here.

**`fast` (reflection-coefficient finite ground) is deliberately NOT run.**
momwire's portal writes `GN 0` for it and NEC-5 reads `GN 0` as Sommerfeld, so a
`fast` row would compare two different *physics*, not two formulations. That is
a confound this study declines to import rather than one it has to label.

## 3. The three known confounds — LABELLED, NOT FIXED

1. **Parity coercion changes the mesh.** `RazorSolver` and NEC-5 both declare
   `segment_parity="even"`; `BSplineSolver(degree=2)` declares `"odd"`. At
   `nominal_nsegs=21` the razor/NEC-5 pair therefore meshes the feed wire even
   and bs2 meshes it odd, and the house 50 mm gap wire becomes **two 25 mm
   segments with a source on the shared knot** for razor/NEC-5 and **one 50 mm
   segment with a mid-segment delta gap** for bs2. A near-open driving point is
   sensitive to exactly that. So any bs2-vs-{razor,NEC-5} number below is a
   basis difference *and* a feed-model difference, and this study cannot separate
   them. `fed_segments()` is recorded per row so the reader can see which rows
   carry it.
2. **Razor is mesh-hungry and is not being given its own default mesh.** The web
   roster serves `razor-2p` at `default_n_per_wire=40`, roughly double bs2's 21,
   because razor needs ~16× the mesh of bspline for the same self-convergence on
   the reference ladder. Running it at the design's `nominal_nsegs` is what keeps
   the mesh comparable to NEC-5's — which is the point — but it means razor here
   is NOT at the density the app would give it, and neither razor nor NEC-5 is
   claimed to be mesh-converged. A razor-vs-NEC-5 *agreement* is therefore
   evidence about the formulation; a razor-vs-bs2 *disagreement* is not evidence
   about which is closer to the truth.
3. **Neither NEC-5 nor razor is a truth oracle.** `Z_ref` = NEC-5 is a choice of
   denominator, not a claim that NEC-5 is right. Where all three disagree, the
   worst-10 table gives a hypothesis and stops there.

## 4. Predictions — registered before the first sweep solve

Bars are on the **per-port row** population (one row per design × port that both
engines of the pair solved), split by ground where stated.

* **P1 (headline).** Median `rel|ΔZ|` razor-vs-NEC-5 over all rows is **≤ 0.5 %**,
  and **≥ 80 %** of rows are below **2 %**.
* **P2.** Median `rel|ΔZ|` bs2-vs-NEC-5 is **≥ 8×** the median razor-vs-NEC-5.
  (The formulation-twin claim has to buy at least this much, or it buys nothing.)
* **P3.** Median `rel|ΔZ|` bs2-vs-razor is within a factor of **1.5** of the
  median bs2-vs-NEC-5 — i.e. razor sits close enough to NEC-5 that bs2's distance
  to the two is the same distance. P2 and P3 together are the twin claim; P2
  alone could be bs2 being bad rather than razor being good.
* **P4 (coverage, not accuracy).** Razor refuses **strictly more** designs than
  bs2 does, and every razor-only refusal is a junction-port design —
  `MomwireEngine` passes `junction_ports=` to every basis but `RazorSolver`. I
  put the count at **4–20** designs. NEC-5's own refusals are a *different*
  set and are dominated by the GE −1 buried-contact refusal (the ≤ 3 buried
  designs).

Misses get reported as misses, with the number that missed them.

## 5. Disclosure: what was solved before the bars were written

Wiring the three lanes up needed a smoke test. Solved by hand, `nominal_nsegs=21`:

* `dipoles.invvee` free: bs2 `55.109 − 10.088j`, razor `54.675 − 12.990j`,
  NEC-5 `54.672 − 13.027j`.
* `dipoles.invvee`, `beams.yagi`, `verticals.four_square`, `arrays.bowtie4x4`
  at `somm`.

That is 4 designs of 103 and one of the two grounds on three of them. It is why
P1's bar is 0.5 % rather than 0.05 %, and it is the reason P4 exists at all
(razor's junction-port refusal is in the code, not in those four runs). The
sweep re-solves all four through the harness, so their numbers appear in the
tables on the same footing as every other row.

## 6. Output

Branch `scratch/catalog-razor-nec5-bs2`, no PR, no issue comments.

* `run_catalog.py` — the harness (driver + `--worker` subprocess entry point)
* `records.jsonl` — one record per design × engine × ground
* `report.py` — reads the JSONL, writes the tables in `README.md`
* `README.md` — the tables, the verdicts on P1–P4, the worst-10 with hypotheses

## 7. Amendment, after the sweep (2026-09-15)

Appended rather than edited in place, so §4's bars stay as registered.

* Two more files joined §6's list: `probe_jacket.py` / `probe_jacket.txt`, the
  follow-up that identifies what the tail is made of, and `hypotheses.md`, the
  prose the README includes verbatim so that generated file has no hand-edited
  section in it.
* **P4 was two claims and only one of them was scored.** As registered it says
  razor refuses strictly more designs than bs2, 4–20 of them, *and* that every
  razor-only refusal is a junction-port design. The scoring code checked only
  the countable half, which would have reported HIT on a prediction whose stated
  reason was wrong. It is now split into **P4a** (count, HIT) and **P4b**
  (cause, **MISS** — 3 of the 4 are momwire's buried-fill refusal, not junction
  ports).
* **A fourth confound was found, and it dominates the headline's tail.** The
  three designs whose razor-vs-NEC-5 rows exceed 5 % are exactly the three
  catalog designs that default to a PVC-jacketed `wire_type`, and NEC-5 has no
  insulated-wire card, so antennaknobs emulates the jacket with an `LD 2`
  inductance while momwire's lane passes the jacket into the solver. README §7
  has the falsified alternatives and the control that settles it.
