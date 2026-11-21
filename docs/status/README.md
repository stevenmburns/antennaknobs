# Status reports

Dated records of studies that settled a question: what was measured, on which builds, with the numbers and a rerun command. One file per study, named `YYYY-MM-DD-<topic>.md`, never rewritten after the fact.

**Rules.**

* A study that settles a question gets a report here. Anything measured on a user's own model stays out of this public repo (it goes in the untracked `notes/` as `<date>-<topic>.local.md`); reports here use invented decks and catalog designs.
* When a later study or fix overturns one, the old report gets a first line `**Superseded by** <file> (<why>).` and its row below says so. Old reports are not moved or deleted: other records cite them by path.
* Check this index, and the date of a study against later fixes to what it measured, before quoting one. "not yet reviewed" means nobody has checked that report against later work since this index was started (2026-11-21); review it before relying on it, then mark it current or superseded.

| report | title | status |
|---|---|---|
| [2026-06-14-trap-fan-dipole.md](2026-06-14-trap-fan-dipole.md) | 2026-06-14 — Adding the four-band trapped fan dipole design | not yet reviewed |
| [2026-06-15-engine-solve-time-comparison.md](2026-06-15-engine-solve-time-comparison.md) | 2026-06-15 — engine solve-time comparison (fandipole, trap_fan_dipole) | not yet reviewed |
| [2026-06-15-trap-fan-dipole-convergence.md](2026-06-15-trap-fan-dipole-convergence.md) | 2026-06-15 — trap_fan_dipole adaptive segmentation + cross-engine convergence | not yet reviewed |
| [2026-06-17-bspline-swept-k-batching-plan.md](2026-06-17-bspline-swept-k-batching-plan.md) | BSplinePySim swept-k batching — diagnosis and plan | not yet reviewed |
| [2026-06-20-arrayblock-pec-ground-plan.md](2026-06-20-arrayblock-pec-ground-plan.md) | Plan: extend the array-block fast path to the PEC-ground case | not yet reviewed |
| [2026-06-21-hmatrix-pec-ground-plan.md](2026-06-21-hmatrix-pec-ground-plan.md) | Plan: extend the generic H-matrix (ACA) solver to the PEC-ground case | not yet reviewed |
| [2026-06-25-solver-selection-benchmark.md](2026-06-25-solver-selection-benchmark.md) | 2026-06-25 — solver-selection benchmark (10 designs × 7 engines) | not yet reviewed |
| [2026-07-04-ws-postproc-serialization-profile.md](2026-07-04-ws-postproc-serialization-profile.md) | Profile: /ws phases 3 + 4 decision (post-processing skip + serialization) | not yet reviewed |
| [2026-07-08-ground-model-benchmark.md](2026-07-08-ground-model-benchmark.md) | 2026-07-08 — ground-model benchmark (10 designs × 4 grounds × 6 engines) | not yet reviewed |
| [2026-07-11-station-loss-comparison.md](2026-07-11-station-loss-comparison.md) | 2026-07-11 — station loss comparison: coax-fed inv-vee vs doublet + open-wire + tuner | not yet reviewed |
| [2026-07-12-wire-loading-runtime-study.md](2026-07-12-wire-loading-runtime-study.md) | Wire-loading runtime study: is lossy wire cheap enough to default on? | not yet reviewed |
| [2026-07-15-per-wire-specs-design.md](2026-07-15-per-wire-specs-design.md) | Per-wire sizes and specs (#388): design decisions | not yet reviewed |
| [2026-07-15-single-lane-scheduler-design.md](2026-07-15-single-lane-scheduler-design.md) | Single-lane solve scheduler (#382): design decisions | not yet reviewed |
| [2026-07-16-nec2c-corpus-benchmark.md](2026-07-16-nec2c-corpus-benchmark.md) | 2026-07-16 — nec2c corpus benchmark + solver convergence (xnec2c decks, 4 engines) | not yet reviewed |
| [2026-07-16-wild-corpus-parse-census.md](2026-07-16-wild-corpus-parse-census.md) | 2026-07-16 — wild-corpus parse census (3,146 decks, importer acceptance) | not yet reviewed |
| [2026-07-17-wild-corpus-solve-sweep.md](2026-07-17-wild-corpus-solve-sweep.md) | 2026-07-17 — wild-corpus solve sweep (3,146 decks, 4 engines, bounded) | not yet reviewed |
| [2026-07-18-quad-convergence-anchor.md](2026-07-18-quad-convergence-anchor.md) | 2026-07-18 — Anchoring the quad convergence anomaly (issue #408) | not yet reviewed |
| [2026-07-19-catalog-perf-benchmark.md](2026-07-19-catalog-perf-benchmark.md) | 2026-07-19 — Full-catalog runtime + peak-RSS benchmark (across ground models) | not yet reviewed |
| [2026-07-19-meshing-rebaseline.md](2026-07-19-meshing-rebaseline.md) | Meshing re-baseline: wild corpus + catalog after the segment-parity and segs_for arcs | not yet reviewed |
| [2026-07-19-somm-session-benchmark.md](2026-07-19-somm-session-benchmark.md) | 2026-07-19 — Sommerfeld session benchmark (momwire #159 measured) | not yet reviewed |
| [2026-07-20-basis-convergence-census.md](2026-07-20-basis-convergence-census.md) | Basis-convergence census — sin vs BSpline d=2 (issue #477 follow-up) | not yet reviewed |
| [2026-07-20-feed-drift-census.md](2026-07-20-feed-drift-census.md) | Feed-drift census — issue #459 | not yet reviewed |
| [2026-07-22-basis-census-rerun.md](2026-07-22-basis-census-rerun.md) | Basis-census re-run + the fan-feed mechanism (issue #484 close-out) | not yet reviewed |
| [2026-07-25-enrichment-cluster-probe.md](2026-07-25-enrichment-cluster-probe.md) | Singular-enrichment probe over the #521 junction-residue cluster (issue #565) | not yet reviewed |
| [2026-07-28-simnec-comparison-handoff.md](2026-07-28-simnec-comparison-handoff.md) | Handoff: SimNEC ↔ AntennaKNoBs full-tool comparison — status + next steps | not yet reviewed |
| [2026-08-08-ward-simnec-momwire-notes.md](2026-08-08-ward-simnec-momwire-notes.md) | Notes for Ward: running momwire as SimNEC's NEC engine | not yet reviewed |
| [2026-08-09-arrayblock-lattice-benchmark.md](2026-08-09-arrayblock-lattice-benchmark.md) | 2026-08-09 — ArrayBlock vs H-matrix vs dense on a growing phased array | not yet reviewed |
| [2026-08-09-v047-live-session.md](2026-08-09-v047-live-session.md) | 2026-08-09 — v0.47.0 pre-release live SimNEC session | not yet reviewed |
| [2026-08-11-nec5-corpus-shakedown.md](2026-08-11-nec5-corpus-shakedown.md) | 2026-08-11 — NEC-5 census lane shakedown (#872 phase 0) | not yet reviewed |
| [2026-08-12-leeson-demo.md](2026-08-12-leeson-demo.md) | 2026-08-12 — The Leeson demo: Cebik's tapered dipoles, three ways (#896 phase 1) | not yet reviewed |
| [2026-08-12-nec-connection-snap.md](2026-08-12-nec-connection-snap.md) | 2026-08-12 — NEC connection tolerance: the momwire lanes solved broken graphs (momwire#302) | not yet reviewed |
| [2026-08-12-nec5-convergence-phase2.md](2026-08-12-nec5-convergence-phase2.md) | 2026-08-12 — NEC-5 convergence-character census (#872 phase 2) | not yet reviewed |
| [2026-08-12-nec5-feed-model-phase1.md](2026-08-12-nec5-feed-model-phase1.md) | 2026-08-12 — NEC-5 feed-model control study (#872 phase 1) | not yet reviewed |
| [2026-08-12-nec5-ground-phase3a.md](2026-08-12-nec5-ground-phase3a.md) | 2026-08-12 — Sommerfeld height sweep: the reactance split dissolves (#872 phase 3a) | not yet reviewed |
| [2026-08-12-nec5-pair-extrapolation-why.md](2026-08-12-nec5-pair-extrapolation-why.md) | 2026-08-12 — Why NEC-5 needs Richardson pairs: the harness is exonerated (#890) | not yet reviewed |
| [2026-08-12-nec5-patterns-phase4.md](2026-08-12-nec5-patterns-phase4.md) | 2026-08-12 — Pattern census: NEC-5 vs bs2 across the catalog (#872 phase 4) | not yet reviewed |
| [2026-08-12-nec5-wild-phase5.md](2026-08-12-nec5-wild-phase5.md) | 2026-08-12 — Wild-corpus three-way census: the movers verdict (#872 phase 5) | not yet reviewed |
| [2026-08-14-fandipole-pair1210-validation.md](2026-08-14-fandipole-pair1210-validation.md) | Validation study: the catalog fan dipole (`multiband.fandipole`, `pair_12_10`) | not yet reviewed |
| [2026-08-14-nec5-quadrature-identified.md](2026-08-14-nec5-quadrature-identified.md) | NEC-5's coarse-mesh excess identified: the centroid-trapezoid path rule | not yet reviewed |
| [2026-08-14-nec5-twin-hardening.md](2026-08-14-nec5-twin-hardening.md) | Hardening the NEC-5 identification — and the bs1/bs2 numbers it proves | not yet reviewed |
| [2026-08-16-eznec-nec5-dialect-capture.md](2026-08-16-eznec-nec5-dialect-capture.md) | EZNEC -> NEC-5 capture corpus | not yet reviewed |
| [2026-08-18-4nec2-subengine-capture.md](2026-08-18-4nec2-subengine-capture.md) | 4nec2 → NEC-2/NEC-4 subengine: invocation, dialect, and the intersection | not yet reviewed |
| [2026-08-19-frontend-statement-matrix.md](2026-08-19-frontend-statement-matrix.md) | The frontend statement matrix: everything EZNEC and 4nec2 emit, scored | not yet reviewed |
| [2026-08-20-eznec-nec5-scored-matrix.md](2026-08-20-eznec-nec5-scored-matrix.md) | The EZNEC matrix, scored: NEC-5 dialect statements vs momwire today | not yet reviewed |
| [2026-08-21-nec5-capability-audit.md](2026-08-21-nec5-capability-audit.md) | NEC-5 capability audit: the full dialect vs the seam, feature by feature | not yet reviewed |
| [2026-09-07-wild-corpus-solve-sweep.md](2026-09-07-wild-corpus-solve-sweep.md) | 2026-09-07 — wild-corpus solve sweep (3,146 decks, 5 engines, bounded) | not yet reviewed |
| [2026-09-08-catalog-cost-ladder.md](2026-09-08-catalog-cost-ladder.md) | 2026-09-08 — catalog cost ladder (103 designs × 6 engines × 2 rungs) | not yet reviewed |
| [2026-09-08-razor-vertex-port-measured.md](2026-09-08-razor-vertex-port-measured.md) | 2026-09-08 — razor-2p on vertex-port designs: measured | not yet reviewed |
| [2026-09-08-wild-corpus-parse-census.md](2026-09-08-wild-corpus-parse-census.md) | 2026-09-08 — wild-corpus parse census (3,146 decks, importer acceptance) | not yet reviewed |
| [2026-09-09-catalog-edge-census.md](2026-09-09-catalog-edge-census.md) | Edges per deck, segments per edge — the whole catalog | not yet reviewed |
| [2026-09-09-hmatrix-catalog-residual-census.md](2026-09-09-hmatrix-catalog-residual-census.md) | H-matrix Sommerfeld residual census across the catalog | not yet reviewed |
| [2026-09-09-hmatrix-crossover-ladder.md](2026-09-09-hmatrix-crossover-ladder.md) | 2026-09-09 — H-matrix crossover ladder (206 cells, momwire#977) | not yet reviewed |
| [2026-09-10-blocked-aca-catalog-census.md](2026-09-10-blocked-aca-catalog-census.md) | Blocked ACA row sampling across the catalog: b = 1 against b = 8 | not yet reviewed |
| [2026-09-11-corpus-census-momwire-nec5.md](2026-09-11-corpus-census-momwire-nec5.md) | momwire bs2 against NEC-5 over the public NEC corpus | not yet reviewed |
| [2026-09-15-catalog-razor-nec5-bs2.md](2026-09-15-catalog-razor-nec5-bs2.md) | razor-2p, NEC-5 and momwire bs2 over the antennaknobs catalog | not yet reviewed |
| [2026-11-21-point-gap-ladder-creep.md](2026-11-21-point-gap-ladder-creep.md) | The slow tail of a refinement ladder: a zero-width feed gap, on every engine | current |
