# momwire#524 phase 0 — shared capture spec

One spec so the nec5cl captures, the empymod harness, and the prototype are
point-comparable. Conventions: SI units, e^{+jωt}, air above (z > 0), ground
below (z < 0). Target frequency band HF; heavy processes ≤8GB.

## Soils

| id | eps_r | sigma (S/m) | note |
| --- | --- | --- | --- |
| A | 13 | 0.005 | target soil, loss tangent ≈ 0.99 at 7 MHz |
| B | 20 | 0.03 | "good" ground, higher loss |
| C | 5 | 0.001 | leaning toward the risky high-eps/low-loss corner — contour stressor; treat oracle cautiously here |

Frequencies: 7 MHz and 21 MHz.
NEVER use fresh water (eps 80 / sigma 0.001) — documented oracle-broken regime.

## Probe decks (anchors, from the 2026-08-21 capability audit; soil A, 7 MHz)

All: monopole GW 1,15,0.,0.,10.,0.,0.,0.,.001 fed EX 4,1,7 (crossing deck: EX 4,2,7),
GN 0,0,0,0,13.,.005, GE 1,-1 (as probed; if the engine objects for buried
wires, record that and what worked).

1. `lone-radial`: monopole + one radial GW 2,10,0.,0.,0.,5.,0.,-0.15,.001
   → anchor Z = 92.13 − j70.14 Ω (reproduce stock before anything else; if it
   does not reproduce, vary plausibly — e.g. sloping first segment — and
   record what did).
2. `four-radial`: monopole + radials to (±5,0,−0.15) and (0,±5,−0.15), 10 seg
   each → anchor 89.985 − j71.401 Ω.
3. `crossing`: GW 1,4,0.,0.,-2.,0.,0.,0.,.001 + GW 2,15,0.,0.,0.,0.,0.,10.,.001
   → anchor 74.761 − j57.730 Ω.

Convergence ladders per deck: segment-count multipliers ×1, ×2, ×4 (and ×8 if
runtime permits) applied to every wire, keeping the fed segment centered.

## Buried dipoles for NE grids

- `bhd10`: horizontal dipole along x, length 10 m centered at origin, 21
  segments, radius 1 mm, fed center (EX 4,1,11), at depth d.
- `bhd1`: same but length 1 m, 11 segments, fed EX 4,1,6 — the near-point-dipole
  case for kernel-level comparison.
- `bvd1`: vertical dipole z from −(d+1.0) to −d, 11 segments, fed EX 4,1,6.
  (For bvd1 use d ≥ 0.05 so the top end stays below the interface.)

Depth ladder: d ∈ {0.02, 0.05, 0.10, 0.15} m (bvd1: {0.05, 0.10, 0.15}).
Full matrix at soil A / 7 MHz. Soils B, C and 21 MHz: at d = 0.05 and 0.15
only, bhd10 + bhd1.

## Observation grids (identical everywhere)

- `T-line` (transmitted, below→above): y=0, z=+1.0 m, x = 2..30 m step 2.
- `T-vert` (vertical ladder): x=10, y=0, z ∈ {0.1, 0.3, 1, 3, 10} m.
- `M-line` (in-medium, below/below): y=0, z=−0.5 m, x = 1..10 m step 1.
- All offsets ≥ 1 mm horizontal (empymod Hankel floor).

nec5cl: NE card grids over those points; capture the FULL out.txt (segment
current tables included — the prototype convolves point-dipole kernels over
the engine's own printed currents to isolate the Green's function).

## A/B rule (every nec5cl capture, no exceptions)

Run stock, then re-run with `EZParam.txt` in the run cwd containing exactly:

    EZ5 0,0,0,-1.,-1.

(disables the buried-buried asymptotic-branch workaround). Record both
outputs; per-capture spread = the oracle's own uncertainty. If spread is
identically zero across all captures, that is itself a finding (the
asymptotic branch never fires in these decks) — then run the positive
control: `bhd10` pair, second identical parasitic dipole at x-offset 130 m
(beyond the ~3 λ₀ table range at 7 MHz), record whether the toggle moves
anything there.

## Output layout

scratch/524-phase0/
  oracle/<capture-id>/deck.nec, out_stock.txt, out_ezoff.txt
  oracle/captures.json   (id → {deck, Z_stock, Z_ezoff, NE tables parsed, spread})
  oracle/SUMMARY.md
  empymod/harness.py, results.json, SUMMARY.md
  proto/ (later)

empymod results.json: for each (soil, freq, source in {HED, VED} × depth,
obs set) the complex E components (Ex, Ey, Ez) at the grid points, source =
UNIT point dipole at the fed-segment center depth. Record the exact empymod
call (function, ab, signs) per entry. empymod is run, never transcribed.
