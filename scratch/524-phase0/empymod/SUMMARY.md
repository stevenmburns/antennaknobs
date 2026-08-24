# empymod second-oracle harness — momwire#524 phase 0

Generated 2026-08-22 by `harness.py` (empymod 2.6.0, run — never transcribed).
Data: `results.json` (17 matrix cells, 30 observation points × Ex/Ey/Ez each,
per-call metadata inline). Run log: `run.log`. Total runtime 452 s.

## Sign / axis mapping (verified empirically, self-check 1a)

SPEC frame: air z > 0, ground z < 0, e^{+jωt}, η = σ + jωε.
empymod frame: z positive DOWN.

```
x_emp = x_spec,   y_emp = y_spec,   z_emp = -z_spec
depth = [0.0];  layer 0 (z_emp < 0) = air  (res 2e14 Ω·m, eps_r 1)
                layer 1 (z_emp > 0) = soil (res 1/σ,      epermH eps_r)
```

A buried source at SPEC z = −d therefore sits at empymod z = +d (checked:
that side shows soil-like attenuation; see also self-check 2).

Component assembly (ab = <rec dir><src dir>, 1=x 2=y 3=z, empymod frame;
the z→−z reflection is exact for E-from-J, so only z-components/z-sources
flip sign):

| source (SPEC) | Ex_spec | Ey_spec | Ez_spec |
| --- | --- | --- | --- |
| HED along +x | +E(ab=11) | +E(ab=21) | −E(ab=31) |
| VED along +z (up) | −E(ab=13) | −E(ab=23) | +E(ab=33) |

Time convention: empymod output matched the e^{+jωt} analytic Hertzian
dipole (outgoing e^{−jkr}) **without conjugation** — no conjugation applied
anywhere.

VED depths: the SPEC bvd1 wire spans z ∈ [−(d+1), −d] fed at segment 6 of
11, so the point-dipole stand-in sits at the fed-segment center,
z = −(d + 0.5) (i.e. 0.55 / 0.60 / 0.65 m for d = 0.05 / 0.10 / 0.15).
HED cells use z = −d directly (bhd10 and bhd1 share the same point-dipole
stand-in). Unit moment Iℓ = 1 A·m everywhere.

## Numerical method (deviation from "prefer the default Hankel transform")

The default DLF filters (log-spaced, CSEM-oriented) are inaccurate in this
wave-regime problem — benchmarked against the exact analytic fullspace
(forced-layered lossless configuration) they show errors up to ~27 % at the
largest k·r of the matrix, and up to 65 % disagreement with converged quad
on real cells (worst: soil B T-line at 21 MHz). The trouble is the largest
offsets/kr, not the smallest (all horizontal offsets ≥ 1 m).

Adopted instead, for every entry:

- **PRIMARY**: `ht='quad'`, `htarg={a:1e-8, b:300, limit:4000,
  pts_per_dec:600}`, `xdirect=True` (analytic direct term when src and rec
  share a layer, i.e. M-line).
- **Cross-checks recorded per grid in results.json**: same quad at
  pts_per_dec 300 / limit 2000, and default DLF (`key_201_2009`).

Convergence evidence: quad(300) vs quad(600) agree to ≤ 1.6e-2 worst,
2.9e-3 median across all 51 grids (worst cells: soil B — highest loss —
T-line/T-vert at 21 MHz; soil C 7 MHz is ≤ 1.3e-3). In damped in-medium
benchmarks quad and DLF both reach ~1e-6, so the spread numbers above are a
conservative bound on the primary's error. Treat the recorded
`quad_ppd300_vs_primary` spread as the per-grid numerical uncertainty of
this oracle. DLF-vs-primary spreads (median 0.13, max 0.65) are recorded
for the record but reflect DLF's error, not the primary's.

## Self-checks

1. **Free-space recovery** (ground → eps_r 1, σ ~ 5e-15; HED and VED, 5
   points each, 7 MHz, vs independent closed-form Hertzian dipole):
   - (a) ground identical to air (empymod's homogeneous-fullspace path):
     max rel err **1.2e-9** — validates the full sign/axis mapping, both
     source types, and the time convention.
   - (b) ground offset 1 ppm to force the true layered/Hankel path: max rel
     err **6.7e-2** (at x=30 m, k₀r ≈ 4.4). This is the pathological
     fully-LOSSLESS corner — no damping anywhere — and is harder than any
     real cell (real cells always have a lossy soil side); real-cell
     accuracy is bounded by the quad(300)/quad(600) spreads above, ≤ 1.6e-2.
2. **Decay sanity** (soil-A fullspace, 7 MHz, broadside |E|·r over
   r = 12..26 m): fitted slope **−0.2398** vs −1/δ = −0.2382 (δ = 4.1985 m
   from the general lossy formula, matching the SPEC's ≈ 4.2 m) — rel err
   **0.7 %**. (The two-layer M-line itself decays slower than e^{−x/δ} at
   range — the up-over-and-down lateral wave — which is physics, not error.)
3. **Reciprocity** (soil A, 7 MHz, below→above: G_zx(rec air 1 m up, src
   buried 0.1 m at 10 m offset) vs G_xz swapped): rel diff **1.7e-15**.
   Machine-exact — the layered formalism is reciprocal by construction, so
   this validates the ab/layer bookkeeping rather than quadrature accuracy.
4. **Depth continuity** (soil A, 7 MHz, HED, observer T-line x=10 z=+1,
   depths 0.02..0.15 m step 0.01): max adjacent relative step **0.60 %**,
   varying smoothly and monotonically — no jumps across the SPEC ladder.

## Warnings

None. Zero Python warnings from empymod across all primary and cross-check
calls (verified in results.json: every per-call `warnings` list is empty).

## Sanity notes

- Ey is identically 0.0 at every point (all grids lie in the y=0 symmetry
  plane; HED-x is mirror-symmetric, VED axisymmetric) — stored anyway.
- Matrix completeness checked programmatically: all 17 SPEC cells present
  (A/7 MHz: HED d ∈ {0.02,0.05,0.10,0.15} + VED d ∈ {0.05,0.10,0.15};
  A/21, B/7, B/21, C/7, C/21: HED d ∈ {0.05,0.15}), grids 15/5/10 points.
- Soil C (the risky high-eps/low-loss corner) is the *best*-converged soil
  here (quad spread ≤ 6.2e-3 at 21 MHz, ≤ 1.3e-3 at 7 MHz); soil B (highest
  loss) is the worst for the transmitted grids at 21 MHz (1.6e-2).
