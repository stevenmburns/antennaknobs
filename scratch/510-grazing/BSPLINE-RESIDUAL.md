# bspline's grazing residual — characterised, not fixed

2026-08-25, after the razor fix landed on
`fix/510-grazing-quadrature-keying`. This is a **separate defect** from #510's
and wants its own issue.

## Why it is separate

#510's cause is razor's remainder source-quadrature order. With that keyed,
razor-nec5 on 0033 at the captured height **converges in mesh**:

| N/wire | 5 | 9 | 15 | 25 | 41 |
|---|---|---|---|---|---|
| razor-nec5 err% (fixed) | 1.46 | 0.90 | 0.94 | 0.94 | 0.80 |
| razor-nec5 err% (before) | 175.88 | 158.64 | 358.73 | 703.13 | 276.32 |

bspline does not, and raising the same knob does not rescue it.

## 1. It is not the quadrature order

0033 at h/λ = 1.09e-4, bspline, error vs the licensed binary:

| N/wire | PEC (`GN 1`) | `GN 0` n_qp=3 | n_qp=48 | n_qp=192 |
|---|---|---|---|---|
| 5 | 24.17 % | 435.18 | 25.70 | **13.97** |
| 9 | 12.34 % | 188.20 | 25.45 | 29.09 |
| 15 | 6.64 % | 46.77 | 47.92 | 48.68 |
| 25 | 3.42 % | 68.91 | 83.57 | **83.60** |

At N = 25 the keying rule asks for ~89 points and 192 is *over*-resolved — and
the answer is still 83.6 % out. Order is not the variable.

## 2. Its PEC control converges; its finite-ground answer diverges

The `GN 1` column converges normally with refinement (24.17 → 3.42 %), so the
basis, the mesh and the junction are fine. The `GN 0` column **gets worse with
refinement** at every order.

## 3. …but its ground-correction entries are RIGHT

The reference-free band test (round 7's instrument): |ΔZ|/|PEC image| in the
near-diagonal band must tend to |2/(ε̃+1)| = **0.0392**. On the one-wire
reproducer, bspline:

| N | n_qp | band 0 | band 1 | band 2 |
|---|---|---|---|---|
| 5 | 96 | 0.0389 | 0.0415 | 0.0392 |
| 9 | 96 | 0.0389 | 0.0402 | 0.0390 |
| 15 | 96 | 0.0389 | 0.0398 | 0.0391 |
| 25 | 96 | 0.0390 | 0.0396 | 0.0392 |

Essentially exact at every mesh, and fine from N = 9 even at n_qp = 3.

## The finding

> **bspline's ground-correction matrix entries are correct, its perfect-ground
> answer converges, and its finite-ground answer still diverges with mesh
> refinement at grazing.**

Entries right + answer wrong is a different defect class from razor's, and it
points away from the ground terms themselves.

## Where to start

- **Test the one-wire reproducer vs 0033 under refinement.** All the mesh
  divergence above is measured on 0033, which has a five-wire junction; the
  band test that came out clean is on the single wire. If the single wire
  converges and 0033 does not, the junction is implicated — and note razor's
  fix made razor fine on 0033 *including* the junction.
- refl-coef also fails to converge here (75 → 87 → 86 → 38 %), but it is
  outside its documented 0.1–0.5 λ window at grazing, so its absolute error is
  not admissible evidence. It is worth re-running only as a *relative* trend.
- The band test does not check the far entries or the block's overall scale —
  only the near-diagonal ratio. Widening it is cheap.

## Release consequence

bspline is the seam's **default** basis and one of #593's two shipped
executables. Until this is fixed, **0033/0034 are still served wrongly by
default**, and the standing "both serve or don't serve" ruling is unmet — so
the option-E *Honest limits* row is back on the table for this release rather
than off it.
