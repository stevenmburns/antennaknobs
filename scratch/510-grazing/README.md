# momwire#510 experiment 1 — the grazing-height floor, measured

2026-08-25. Probe: `momwire/scripts/probe_grazing_height_floor.py` (banked in
its own docstring too). Raw output in `RESULTS-height.txt` /
`RESULTS-segments.txt`, machine-readable in the two `.json`.

## The question

Captures 0033/0034 sit 1.778 cm over `GN 0` average soil at 1.832 MHz —
**h/λ = 1.09e-4** — and every basis answers 176–437 % away from the capture
with the reactance sign flipped, *served silently*. "Wrong at 1.09e-4 λ" is
not actionable. A refusal needs a threshold, a documented limit needs a
number, and a bug needs a signature. All three want the error as a function
of height.

## The instrument

0033 lifted **rigidly** — vertical length, radial length, radius, mesh and the
capture's own `EX 0,1,-1` drive card all bit-identical rung to rung, only the
structure's z translated — compared at every rung against the licensed binary
running the same deck text. Z is genuinely height dependent here, which is why
the reference is the binary at each rung and not the ladder's own flatness.

Two controls, both load-bearing: **`GN 1` perfect ground** at every rung (a
perfect image has no Sommerfeld integral in it), and **both shipped trunks**
(`bspline` degree 2, `razor-nec5`), because #593 ships two executables under a
"both serve or don't serve" ruling.

## Result 1 — the floor is between 1e-2 and 1e-3 λ, and it is in the ground

Error against the binary, per cent of |Z|:

| h/λ | 1e-1 | 3e-2 | 2e-2 | 1e-2 | 7e-3 | 5e-3 | 3e-3 | 2e-3 | 1e-3 | 5e-4 | 2e-4 | 1.09e-4 |
|---|---|---|---|---|---|---|---|---|---|---|---|---|
| razor-nec5, `GN 0` | 0.01 | 0.00 | 0.00 | 0.06 | 0.25 | 0.87 | 3.91 | 10.31 | 44.18 | 230.91 | 239.54 | 171.86 |
| razor-nec5, `GN 1` | 0.00 | 0.00 | 0.00 | 0.00 | 0.00 | 0.00 | 0.00 | 0.00 | 0.00 | 0.01 | 0.01 | 0.00 |
| bspline, `GN 0` | 4.68 | 5.06 | 5.30 | 5.92 | 6.40 | 7.14 | 9.72 | 14.84 | 45.66 | 37.23 | 167.08 | 435.18 |
| bspline, `GN 1` | 4.72 | 5.17 | 5.39 | 5.86 | — | — | 6.87 | — | 8.23 | 10.13 | 15.78 | 24.17 |

**Over a perfect image razor-nec5 holds 0.00 % at every rung down to
1.09e-4 λ.** Same mesh, same five-wire junction of near-horizontal wires, same
drive card, same seam. Only the ground card changes. So the grazing failure is
**not** the mesh, **not** the junction, **not** the drive spelling and **not**
this seam's addressing — which is most of experiment 2 answered by a control
that is stronger than the single-wire version would have been, because it
holds the junction fixed instead of removing it.

Both trunks leave their own baseline at the same place — razor's baseline is
0.00 %, bspline's is the ~5 % basis difference it carries at *every* height,
over PEC too — so **one threshold serves both** and the parity ruling is
satisfiable:

> clean ≥ 1e-2 λ · ~1 % at 5e-3 · ~10 % at 2e-3 · broken ≤ 1e-3

bspline over PEC is its own smaller story: 4.7 % at 1e-1 λ rising to 24 % at
1.09e-4, and that one *does* converge out under refinement (24.23 → 1.75 % at
N=41). Ordinary basis convergence, not the finding.

## Result 2 — the controlling variable is h/λ, not h/Δ

Native height, mesh refined 5 → 41 segments a wire:

| N | 5 | 9 | 15 | 25 | 41 |
|---|---|---|---|---|---|
| h/Δ | 0.0022 | 0.0040 | 0.0067 | 0.0112 | 0.0184 |
| nec5cl | 38.79−49.58j | 40.69−42.16j | 41.30−39.80j | 41.54−38.81j | 41.63−38.36j |
| razor-nec5 err% | 175.88 | 158.64 | 358.73 | 703.13 | 276.32 |
| bspline err% | 437.23 | 189.29 | 47.42 | 68.22 | 217.04 |

The binary converges monotonically. Both trunks **diverge, and erratically**.
N=41 puts h/Δ at 0.0184 — the same h/Δ the height sweep reaches at h/λ = 1e-3,
where razor is 44 % out — yet here it is 276 %. Refining the mesh does not buy
the answer back; it costs more of it.

## Reading

This is a **breakdown signature, not a model gap**. A bounded formulation
error is monotone in the mesh and keeps its sign; this is neither — razor
walks −50j → +113j → −231j → +34j across four adjacent rungs, and the error
grows with the number of unknowns landing in the grazing regime. That is
conditioning, not approximation.

Which settles the standards question the handoff posed: **#510 is D3's
category, not D1's** — refuse, don't pin. And the threshold to refuse at is
now a measured number rather than a guess.

## What this does not yet say

- **Where** in the finite-ground path it breaks (interpolation grid, the
  remainder's near-interface behaviour, the reduced kernel). Experiment 3 —
  the contact-limit check against #624 — is the next lever, and the stub
  ladder is reusable.
- Whether `refl-coef` breaks in the same place. #624 found refl-coef and
  Sommerfeld behaving alike at contact; if they agree here too the remainder
  is exonerated again and the shared machinery is the suspect. The deck route
  cannot ask for refl-coef, so that needs a direct-solver lane.
- Whether the onset moves with soil. Average only, so far.
