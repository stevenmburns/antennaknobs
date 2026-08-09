# 2026-08-09 — ArrayBlock vs H-matrix vs dense on a growing phased array

## TL;DR

`scripts/bench_arrayblock_lattice.py` grows one shape family — an N×N square
lattice of identical centre-fed half-wave dipoles, 9 segments each, 0.6 λ
pitch, free space, 14 MHz — and asks each of the three B-spline solve paths for
the same 2×2 short-circuit admittance. One fresh subprocess per rung (clean
`getrusage` peak RSS, 8 GB `RLIMIT_AS`), BLAS/OpenMP pinned to the physical
core count, strictly serial, one rung at a time.

**The dense wall is 32×32 (1024 elements, 9216 bases) on an 8 GB budget.**
Estimated live footprint 15.2 GB; a confirming run under the cap died with
`MemoryError` exactly as predicted. The largest dense rung that fits is 24×24,
and it costs **8.0 s and 5277 MB**. The same rung on `arrayblock` costs
**0.77 s and 137 MB** — 10.4× the speed and 38.6× less resident memory, and
the memory ratio is the conservative reading, because 91 MB of both figures is
the interpreter's import floor. Against the *solve's own* allocation it is
5186 MB vs 46 MB, **113×**.

Past the wall `arrayblock` keeps going on a laptop. At **48×48 — 2304
elements, 20736 bases, a dense fill that would need ~77 GB — it answers in
2.99 s and 272 MB.**

Three findings worth stating plainly:

- **`arrayblock` overtakes dense at 8×8 (64 elements) and never looks back.**
  3.1× at 8×8, 4.5× at 16×16, 10.4× at 24×24. Below that the dense fill is
  genuinely the cheaper tool and the FFT bookkeeping does not pay for itself.
- **`hmatrix` never beats dense anywhere dense runs** — 0.10×–0.31× the speed
  across the whole ladder. Its value on this geometry is not speed, it is
  *survival*: it is still solving at 48×48 (157.6 s, 1963 MB) where dense
  wants 77 GB. On a same-shape lattice, the generic hierarchical solve is the
  fallback, not the answer; `arrayblock` is 52.7× faster than it at 48×48.
- **`arrayblock`'s cost is linear in element count over this range.** 8×8 →
  48×48 is 36× the elements and 37× the wall clock (0.08 s → 2.99 s); memory
  above the floor tracks at a flat ~0.080 MB per element (46 MB at 576
  elements, 181 MB at 2304). Dense memory is exactly quadratic in bases, which
  is what puts the wall where it is.

Agreement holds everywhere: worst measured relative error **3.0e-06**
(`hmatrix` vs dense) and **3.5e-06** (`arrayblock`, vs dense while dense ran
and vs `hmatrix` beyond), against a 1e-04 bound.

## Method

```
python scripts/bench_arrayblock_lattice.py --out lattice_bench.json
```

Defaults as committed: sizes 4, 6, 8, 12, 16, 24, 32, 48; 9 segments per
dipole; 0.6 λ pitch; 14 MHz; free space; 8 GB per-rung `RLIMIT_AS`; 600 s
per-rung timeout.

Each rung is one `compute_y_matrix()` in its own fresh interpreter:
`OMP_WAIT_POLICY=PASSIVE`, `GOMP_SPINCOUNT=0` set before the scientific stack
loads, BLAS/OpenMP = physical cores, serial dispatch. Wall clock is
`perf_counter()` around `compute_y_matrix()` alone — geometry construction is
outside it. Peak RSS is `ru_maxrss` for the whole worker, so it **includes**
the ~91 MB import baseline.

**Mesh.** 9 segments per half-wave dipole, odd so a segment centre lands on the
feed point. The portal's engaged-path test
(`test_the_lattice_fft_path_engages_and_the_shim_still_agrees`) uses the
3-segment minimum, which is right for a test — the FFT gate is about lattice
bookkeeping, not mesh size — but a benchmark quoting cost per element needs a
mesh someone would actually model with. 9 is the catalog's own habit for a
resonant half-wave element.

**Pitch and feeds.** 0.6 λ sits inside the usual 0.5–0.7 λ broadside-array
window and keeps the elements genuinely coupled. Two feeds on every rung —
element 0 (a corner) and the central element — so Y is 2×2 and the agreement
column checks a corner-to-interior mutual, not only self terms. The feed set is
declared identically on all three solvers; the measured quantity has to be the
same quantity.

**Engaged path, asserted.** Every `arrayblock` rung is constructed with
`require_lattice_fft=True`, so a rung that failed to meet the FFT gate (P ≥ 16,
one block-shape class, a regular lattice) would raise `LatticeFFTUnavailable`
naming the unmet gate and be recorded as a failed rung rather than silently
degrading to the parent H-matrix and being credited to the wrong path. All
eight rungs engaged; `solver_diag()` reports
`operator=LatticeArrayBlock, lattice_fft=True, n_shapes=1` on each.

**Column closure.** A rung that caps, times out, or is skipped closes its
column — larger sizes are not probed. The dense column closes at 32×32 by
estimate.

## Machine

| | |
| --- | --- |
| CPU | Intel Core i7-8550U @ 1.80 GHz — 4 physical cores, 8 threads |
| RAM | 15.3 GiB |
| OS | Linux 7.0.0-28-generic |
| Python | 3.14.5 |
| numpy / scipy | 2.5.0 / 1.18.0 |
| antennaknobs | 0.46.0 |
| momwire | 0.23.0 (submodule `c67d238`) |
| thread policy | BLAS = OpenMP = 4, `OMP_WAIT_POLICY=PASSIVE`, `GOMP_SPINCOUNT=0` |

This is a 2017 mobile quad-core, not a workstation. **Absolute times drift with
hardware; the ratios between the three paths, and the position of the dense
wall relative to the memory budget, are the portable findings.**

## The ladder

`rel err` is max|ΔY| / max|Y_ref|, referenced to dense while dense ran and to
`hmatrix` beyond it.

| grid | elements | n_basis | solver | wall s | peak RSS MB | rel err | status |
|---|---|---|---|---|---|---|---|
| 4×4 | 16 | 144 | dense | 0.01 | 93 | — | ok |
| 4×4 | 16 | 144 | hmatrix | 0.11 | 91 | 2.82e-07 | ok |
| 4×4 | 16 | 144 | arrayblock | 0.02 | 91 | 1.53e-10 | ok |
| 6×6 | 36 | 324 | dense | 0.04 | 111 | — | ok |
| 6×6 | 36 | 324 | hmatrix | 0.38 | 95 | 9.33e-07 | ok |
| 6×6 | 36 | 324 | arrayblock | 0.04 | 92 | 5.97e-10 | ok |
| 8×8 | 64 | 576 | dense | 0.25 | 157 | — | ok |
| 8×8 | 64 | 576 | hmatrix | 1.25 | 102 | 2.40e-06 | ok |
| 8×8 | 64 | 576 | arrayblock | 0.08 | 95 | 7.72e-08 | ok |
| 12×12 | 144 | 1296 | dense | 0.44 | 423 | — | ok |
| 12×12 | 144 | 1296 | hmatrix | 3.19 | 132 | 2.88e-06 | ok |
| 12×12 | 144 | 1296 | arrayblock | 0.18 | 103 | 6.91e-07 | ok |
| 16×16 | 256 | 2304 | dense | 1.25 | 1122 | — | ok |
| 16×16 | 256 | 2304 | hmatrix | 9.36 | 184 | 3.02e-06 | ok |
| 16×16 | 256 | 2304 | arrayblock | 0.28 | 111 | 9.93e-08 | ok |
| 24×24 | 576 | 5184 | dense | 7.99 | 5277 | — | ok |
| 24×24 | 576 | 5184 | hmatrix | 26.18 | 363 | 1.12e-06 | ok |
| 24×24 | 576 | 5184 | arrayblock | 0.77 | 137 | 1.08e-07 | ok |
| **32×32** | **1024** | **9216** | **dense** | **—** | **—** | **—** | **skipped (est 15.19 GB > 8 GB cap)** |
| 32×32 | 1024 | 9216 | hmatrix | 73.94 | 724 | — | ok |
| 32×32 | 1024 | 9216 | arrayblock | 1.29 | 173 | 3.52e-06 | ok |
| 48×48 | 2304 | 20736 | dense | — | — | — | skipped (column closed) |
| 48×48 | 2304 | 20736 | hmatrix | 157.64 | 1963 | — | ok |
| 48×48 | 2304 | 20736 | arrayblock | 2.99 | 272 | 6.99e-07 | ok |

Total sweep wall clock: **300.6 s** for 21 solved rungs. Highest peak RSS
anywhere in the sweep: **5277 MB** (dense, 24×24) — comfortably inside the
8 GB cap, which was never the binding constraint on a rung that ran.

## Ratios — the portable part

Dense cost ÷ accelerator cost. Above 1.00× the accelerator wins.

| grid | elements | hmatrix wall | hmatrix RSS | arrayblock wall | arrayblock RSS |
|---|---|---|---|---|---|
| 4×4 | 16 | 0.13× | 1.02× | 0.63× | 1.03× |
| 6×6 | 36 | 0.10× | 1.18× | 0.90× | 1.20× |
| 8×8 | 64 | 0.20× | 1.54× | **3.09×** | 1.66× |
| 12×12 | 144 | 0.14× | 3.21× | 2.47× | 4.11× |
| 16×16 | 256 | 0.13× | 6.11× | 4.47× | 10.13× |
| 24×24 | 576 | 0.31× | 14.54× | **10.41×** | **38.59×** |

Beyond the dense wall, `arrayblock` against `hmatrix`:

| grid | elements | wall | peak RSS |
|---|---|---|---|
| 32×32 | 1024 | 57.3× faster | 4.2× leaner |
| 48×48 | 2304 | 52.7× faster | 7.2× leaner |

### Above the memory floor

The RSS column includes a ~91 MB interpreter + numpy + momwire import baseline,
which flatters the accelerators' *ratios* downward at small sizes and upward
nowhere. Subtracting it gives each path's own allocation:

| grid | dense | hmatrix | arrayblock |
|---|---|---|---|
| 12×12 | 332 MB | 41 MB | 12 MB |
| 16×16 | 1031 MB | 93 MB | 20 MB |
| 24×24 | 5186 MB | 272 MB | 46 MB |
| 32×32 | (15.2 GB est) | 633 MB | 82 MB |
| 48×48 | (76.9 GB est) | 1872 MB | 181 MB |

Dense is 113× `arrayblock`'s own allocation at 24×24. `arrayblock` holds a flat
~0.080 MB per element across the whole ladder.

## The dense wall, and what the estimate got wrong

The script refuses a dense rung whose estimated live footprint exceeds the cap
rather than discovering the cap the hard way, so the estimator has to be right.
The obvious arithmetic — Z is n²·16 bytes, and the LU holds a working copy —
says 2.2×. **That is wrong by a factor of five.** Measured peak RSS above the
import floor, divided by n²·16:

| n_basis | Z itself | RSS above floor | factor |
|---|---|---|---|
| 1296 | 26.9 MB | 332 MB | 12.3× |
| 2304 | 85.0 MB | 1031 MB | 12.1× |
| 5184 | 430.3 MB | 5186 MB | 12.1× |

The batched C++ assembly materialises a per-pair quadrature gather before it
reduces to Z, and *that*, not the matrix, sets the peak. The factor is flat
across a 4× span in n_basis, so it extrapolates; `DENSE_FOOTPRINT_FACTOR = 12.0`
in the script is this measurement, and the comment says so.

At 32×32 it predicts 15.19 GB against an 8 GB cap. Confirmed with one direct
run of the worker, bypassing the estimate:

```
python scripts/bench_arrayblock_lattice.py --worker dense 32 9 0.6 14.0 8.0
{"error": "MemoryError: exceeded 8 GB cap", "error_kind": "capped"}
```

Note what kind of wall this is: **memory, not time.** Extrapolating the dense
time curve (P^1.58 over 8×8 → 24×24) puts a 32×32 dense solve at roughly 20 s,
well inside the 600 s timeout. It is the quadratic fill that ends the column,
which is why the accelerators exist.

## Agreement

| column | worst rel err | at | reference | bound |
|---|---|---|---|---|
| hmatrix | 3.02e-06 | 16×16 | dense | 1e-04 |
| arrayblock | 3.52e-06 | 32×32 | hmatrix | 1e-04 |

Both are ~30× inside the bound. `arrayblock` against dense specifically is
tighter still — worst 6.91e-07 at 12×12, and 1.5e-10 at 4×4 — which is the
expected shape: the lattice-FFT path is an exact reorganisation of the same
operator, so its deviation from dense is convolution round-off, whereas
`hmatrix` carries a genuine ACA truncation. The 3.52e-06 on the `arrayblock`
row at 32×32 is measured against `hmatrix`, so it is mostly `hmatrix`'s error,
not `arrayblock`'s.

## Caveats

- **Memory floor.** Every RSS figure includes the ~91 MB import baseline. The
  "above the floor" table exists so the per-path allocation is recoverable.
- **Cold process, one fill.** Each number is a first-and-only
  `compute_y_matrix()` — fill, factor, one back-substitution per port. A warm
  second solve at another frequency is not measured. This is a fill story, and
  fill dominates; a swept-frequency comparison would be a different benchmark
  and would likely favour the accelerators further, since they amortise their
  setup. Future work, deliberately out of scope here.
- **Free space only.** Ground would confound the scaling comparison. All three
  paths ride their accelerated route on ground already, which is a separate
  question the #830-era notes cover.
- **Ratios, not absolutes.** See the machine table. A workstation moves every
  wall-clock number and moves the dense wall too — the wall is set by the
  memory budget, so a 64 GB box pushes it out about one rung and a half.
- **One geometry family.** Identical elements on a regular lattice is the best
  case for `arrayblock` by construction. That is the point — it is Ward's case
  — but the 8×8 crossover is specific to this family and this mesh, not a
  universal number.

## Ward-quotable summary

On a plain 2017 quad-core laptop, a 24×24 array of half-wave dipoles — 576
elements, 5184 unknowns — takes 8.0 seconds and 5.3 GB of RAM to solve with a
conventional dense fill, and a 32×32 array cannot be solved at all inside an
8 GB budget: it needs about 15 GB. With `--basis arrayblock` the same 24×24
array answers in 0.77 seconds and 137 MB, and the 32×32 that dense cannot reach
takes 1.3 seconds and 173 MB. A 48×48 array — 2304 elements, 20736 unknowns,
where the dense matrix alone is 6.9 GB and the dense solve around it needs an
estimated 77 GB — solves in 3.0 seconds and 272 MB.
The answers agree with the dense solve to within a few parts in 10⁶ relative
wherever dense can still be run, so nothing is being traded away for the speed: it is
the same physics and the same operator, reorganised as an FFT convolution over
the element grid. The generic hierarchical solver (`--basis hmatrix`) also
survives past the dense wall, but on a repeated-element lattice it is roughly
50× slower than `arrayblock` and should be regarded as the fallback for decks
with no repeated structure.

## Reproducing

```
python scripts/bench_arrayblock_lattice.py --out lattice_bench.json
python scripts/bench_arrayblock_lattice.py --sizes 4 8 16 --solvers arrayblock
# the dense-wall confirmation (bypasses the estimate skip, keeps the cap):
python scripts/bench_arrayblock_lattice.py --worker dense 32 9 0.6 14.0 8.0
```

Manual-only. The benchmark is a script, never wired into CI, per the repo test
policy (no per-design certs in CI; PR #392 precedent).
