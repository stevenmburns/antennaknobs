# 2026-08-12 — NEC-5 convergence-character census (#872 phase 2)

## Goal

The issue's phase-2 questions, answered on a stratified 13-design catalog
sample: (a) do the engines' extrapolated limits Z∞ agree within
formulation bars, and (b) what mesh (or extrapolation pair) NEC-5 needs
for census-grade answers.

Instrument: `scripts/bench_nec5_convergence.py` — nec5/bs2/sin up the
Δ-halving ladder N = 21/41/81/161 (free space), Richardson per series
(observed order p, Z∞), pairwise ΔΓ between limits (agree bar 0.02,
census-grade bar 0.01). nec5 rides `bench_converge.solve_design` as just
another engine key — its knot source is the same feed class as bs1's tent
basis (both `segment_parity="even"`), per the phase-1 framing; no NEC-5
special-casing anywhere. Artifact: `scratch/nec5-convergence-phase2.json`
(+ `.log` report).

## (a) Z∞ agreement — 9/13 designs agree three ways

Nine designs (quad, delta_loop, bisquare, folded_invvee, yagi, moxon,
invvee, ocf_dipole, bruce) agree pairwise to ΔΓ ≤ 0.009 — most to
≤ 0.001. Once the feed model is controlled and the ladders extrapolated,
NEC-5 and the momwire bases measure the same physics across loops,
folded elements, beams, curtains and asymmetric feeds.

Notably `dipoles.invvee` (the catalog's bridge-feed idiom) agrees
nec5-bs2 to 0.0014 — consistent with momwire#300's bound that short
fixed-length bridges (≪ λ) carry only a small residual of the
1-seg-bridge X anomaly.

The four splits are all diagnostic:

| design | worst pair | reading |
|---|---|---|
| specialty.hentenna | bs2-sin 0.068 | **The motivating question, answered**: nec5 and bs2 agree (0.0116) at 43.1+38.5j / 43.4+39.7j; sin sits at +32.9j X — the #484 sin instability, now arbitrated by an independent formulation in bs2's favor. bs2 was converged-to-the-right-place. |
| multiband.fandipole | sin 0.83–0.84 | sin's "limit" (5.1+2.5j, order 0.21) is the #484 fan-feed divergence, spectacularly. nec5-bs2 = 0.035, slightly over bar with bs2 order 0.66 and not yet census-grade at N=161 — needs finer rungs, but the two are approaching each other. |
| verticals.jpole | bs2-sin 0.022 | nec5-bs2 agree (0.0038); sin non-contracting (close-parallel stub — #484-adjacent class). |
| dipoles.short_dipole_loaded | nec5-sin 0.025 | No engine census-grade by N=161 (orders 0.54–0.70); the loaded short dipole converges slowly everywhere, so all three extrapolations carry error. Finer-ladder candidate, not a formulation split. |

## (b) What NEC-5 needs

Observed orders: 0.54–1.74, median ≈ 0.85 — the O(1/N)-class knot-source
march is universal, as phase 1 predicted. Single-mesh NEC-5 is
census-grade (ΔΓ < 0.01 vs its own limit) at N=21 on only 5/13 designs;
on 4/13 not even N=161 suffices (hentenna, moxon, fandipole,
short_dipole_loaded). **The phase-1 recipe is therefore confirmed as
necessary, not optional: census-grade NEC-5 rows are Richardson pairs.**
bs2 by contrast is census-grade at N=21 on 8/13.

Practical guidance for phases 3–5: run NEC-5 at (N, 2N) = (81, 161)-class
pairs and extrapolate; NEC-5 solves are binary-cheap (the whole 13-design
× 4-rung ladder cost seconds of solver time via the capture cache), so
the extra rung is free compared to any momwire column.

## Also landed

- `bench_converge.solve_design` grows the `nec5` dispatch branch
  (capture-dir via `$NEC5_CAPTURE_DIR`), so every existing ladder
  instrument can now run NEC-5.
- Live-gated dispatch test in `tests/test_bench_nec5_lane.py`.

## Next (#872)

- Phase 3: ground ladders — height sweep over Sommerfeld + the
  momwire#291 contact geometries with NEC-5 as arbiter.
- Finer-ladder follow-ups: fandipole (close the nec5-bs2 0.035 gap) and
  short_dipole_loaded (get any engine census-grade).
- The hentenna/fan verdicts feed #484's record: sin's instability is now
  three-way confirmed with an independent-formulation arbiter.
