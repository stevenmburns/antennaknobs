# bspline's grazing residual — characterised, not fixed

2026-08-25, after the razor fix landed on
`fix/510-grazing-quadrature-keying`. This is a **separate defect** from #510's
and wants its own issue.

> ## MECHANISM FOUND — read this first
>
> Later the same day, momwire#632. **The reading below is half right and the
> half that is wrong is the framing.** Two of its three observations were
> taken on 0033 and the third on the one-wire reproducer, and splitting those
> two decks apart overturns the conclusion.
>
> - **"PEC converges" is 0033's column only.** On the bare grazing wire
>   bspline's PEC control is 998.67 / 458.80 / 195.12 / 112.07 / 73.04 % at
>   n = 4…32, where razor is 0.00 %. 0033's PEC looked healthy because its
>   non-grazing vertical dominates Z and dilutes the radials.
> - **The defect is grazing-keyed with no soil in the deck.** Free space is
>   flat (1.21 % at n = 16 across six decades of height); the PEC column
>   tracks that basis-error baseline to 3e-3 λ and then detonates to 195 %.
>   So it reproduces over a **closed-form image** — no Sommerfeld surface, no
>   interpolation grid, no soil.
> - **Which is exactly why §3's entries looked right.** The band test's
>   denominator is Z(`GN 1`) − Z(`GN -1`), so a broken image term sits in
>   both halves of the ratio and divides out. The reference-free test is
>   **blind to this defect by construction** — the one thing to carry
>   forward, since the arc banked it as the candidate CI gate.
> - **Source:** `_build_J_image_blocks` premises the image on being "always
>   far enough from the original" and integrates every image pair at a fixed
>   `n_qp_pair` (default 4). At grazing a segment's own image is 2h away —
>   3.6 cm under a 2.48 m segment. Same defect *shape* as #510's, different
>   code path.
> - **It takes BOTH orders.** Image order alone plateaus at 152 %, remainder
>   order alone at 306 %, both together reach 0.62 %. §1 below is therefore
>   true as measured and wrong as evidence: it moved one of two broken terms.
>
> Fix obstacle: the C++ off-edge kernel refuses `n_qp > 8` ("scratch buffer
> size"), so the working orders exist only in the numpy fallback. Not a
> mechanical port of #630.

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
