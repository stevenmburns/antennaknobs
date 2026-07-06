---
title: The solver & accuracy
description: The momwire MoM engine — its basis functions, accelerated solvers, which one to pick, and how results are cross-validated.
---

antennaknobs solves antennas with **momwire**, an in-house method-of-moments
(MoM) engine for wire structures, with an optional NEC-2 backend for
cross-checking.

## Basis functions

momwire offers three current-expansion bases in one engine — uncommon among free
tools, where basis quality is usually a paid feature:

- **triangular** (piecewise-linear "tent") — the default,
- **sinusoidal** — a NEC-2-style three-term basis, useful as a cross-validator,
- **B-spline** — a degree-1/2 Galerkin basis.

Plus two **accelerated** solvers for large problems:

- **`hmatrix`** — ACA / hierarchical-matrix, sub-quadratic on large single-wire
  structures,
- **`arrayblock`** — element-aware block-low-rank, near-linear on arrays of
  identical / few-shape elements.

## Which solver should I use?

The choice turns on two axes — total problem size, and single-structure vs.
array geometry. From the [solver-selection
benchmark](https://github.com/stevenmburns/antennaknobs) (10 designs × 7
engines):

| Antenna class | Use | Why |
| --- | --- | --- |
| Single elements, small loops, beams, multiband dipoles | **`sinusoidal`** or **PyNEC** | the dense solve is milliseconds; the accelerators' setup is pure overhead here |
| Large single-wire structures (rhombic, long-wires, big loops) | **`hmatrix`** (ACA) | sub-quadratic scaling — the only solver that beats PyNEC on `rhombic` at high segmentation |
| Arrays of identical / few-shape elements (loop/bowtie arrays, LPDA) | **`arrayblock`** | 6–11× faster than PyNEC on large arrays; near-linear scaling |

:::caution
`arrayblock` / `hmatrix` only win at moderate-to-high segment counts on their
target geometries — below ~N=40 they're slower than a dense solve even there. Don't
reach for them on small problems.
:::

### What the numbers show

- **ACA earns its place on `rhombic`** — fastest engine at high segmentation
  (~3.9 s at N=81), beating PyNEC and every dense basis, scaling ~2×/step where
  dense solvers go ~5×/step.
- **ArrayBlock dominates arrays** — `lpda`: ~1.2 s vs PyNEC's **13.4 s** (11×);
  `bowtiearray2x4`: ~1.9 s vs 11.4 s (6×).
- **PyNEC is a great fast reference, but not universally fast** — it wins on
  single/few-element designs (often <100 ms), yet blows up on the log-periodic
  (13 s). "Use PyNEC as the reference" holds for small designs, not arrays.
- **Among dense bases, `sinusoidal` stays fastest** on small/medium single
  structures; `triangular` is the slowest dense basis.

## Segments & convergence

Method-of-moments discretizes each wire into **segments**, and the solve builds
one **basis function** per segment. The **segments / wire (N)** control in the
workbench sets the nominal count; antennaknobs scales it per wire by length, so a
long radiator gets proportionally more segments than a short stub. The total
basis-function count — the sum across every wire — is the **dimension of the
impedance matrix** the solver fills and factors.

That matrix is what sets both accuracy and cost:

- **Too few segments** and the current distribution is under-resolved — the
  feed-point impedance hasn't *converged* and your SWR/resonance readings are
  off, sometimes by a lot near a sharp feature.
- **More segments** refine the answer, but the dense solvers form an **N×N**
  matrix: memory grows as **N²** and fill/factor cost as **N²–N³**. Past the
  point where the impedance stops moving, the extra segments only cost time.

### Finding "enough" — the convergence sweep

The workbench's **convergence sweep** re-solves the current antenna across a
range of N and plots the resulting feed-point impedance R + jX against N. Read it
like any convergence study: the curve drops steeply at small N, then **flattens**
("the knee"). The smallest N past the knee is your sweet spot — converged, but no
slower than it needs to be. If the curve never settles, the geometry may have a
feature (a tight bend, a very short feed gap) that needs finer local
segmentation, or a different basis.

A quick rule of thumb: the dense bases want **enough segments per
half-wavelength** to resolve the sinusoidal current — a couple of dozen across a
half-wave element is typical. The convergence sweep turns that rule into an
answer you can see for *your* antenna.

### The size cap

Because the dense matrix grows as N², a runaway segment count (or a big array)
can allocate hundreds of megabytes and stall a solve. The hosted instance
therefore **caps the total segment count** and rejects oversized solves with a
clear message rather than melting the shared box. The cap is engine-aware: the
compressed **`arrayblock`** / **`hmatrix`** engines skip the dense matrix
(ACA / H-matrix), so they're allowed a much higher count — which is exactly why
they exist for large arrays. The cap is **off by default** and enforced only on
the shared hosted instance — a local `pip install` is uncapped; the toggle and
the limits are env-configurable (see `docs/deploy.md`).

## Accuracy & validation

- A NEC-2 reference engine (`pynec-accel`) runs alongside momwire, so any design
  can be solved two ways and compared — a built-in sanity check most tools lack.
- The repo carries the benchmark above plus per-design solver comparisons.

### Honest limitations

In the spirit of not overselling: momwire wires are currently PEC (no conductor
loss — the NEC path with `ld_card` covers lossy elements), and finite-ground
impedance on the triangular/sinusoidal bases folds to the PEC image. The
B-spline family solves finite grounds with the reflection-coefficient model
(validated within ~2 Ω of NEC over 0.1–0.5λ heights), and the NEC path offers
full Sommerfeld–Norton — the reference for very low antennas (below ~0.1λ) —
so real-ground results cross-check across two independent engines.

<!-- TODO: embed the benchmark plots once generated, and a parity/differentiator
     table vs PyNEC / 4nec2 / EZNEC / AN-SOF from the market-research doc. -->
