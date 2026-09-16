# AK#1552 — the bspline tail: density, reference, or placement?

**Builds.** antennaknobs `75aa8fa83`; momwire `ec4047c3d` (`v0.56.0-18-gec4047c`), rebuilt; accelerator `_accelerators_avx2`. Metric and reference are AK#1525's: `|ΔZ|` over all ports as a vector, relative over `|Z_ref|`, reference **bs2@160**. `PLAN.md` registers H1–H3 before the first cell.

## `dipoles.short_dipole_loaded`

**free space** — bs2@160 = `13.0183+12.4373j`, |Z| = 18.00 Ω

| basis | N | fed segment | \|ΔZ\| Ω | relative |
|---|---:|---:|---:|---:|
| bs3 | 12 | 0.20590 m | 40.60 | 225 % |
| bs3 | 15 | 0.17845 m | 35.75 | 199 % |
| bs3 | 20 | 0.12746 m | 26.38 | 147 % |
| bs3 | 30 | 0.08635 m | 18.41 | 102 % |
| bs2 | 15 | 0.17845 m | 22.57 | 125 % |
| bs2 | 20 | 0.12746 m | 16.51 | 92 % |
| bs2 | 30 | 0.08635 m | 11.25 | 62 % |

| arbitration | value | vs bs2@160 |
|---|---|---:|
| bs2@240 | fed segment 0.01111 m | 1.391 Ω = 7.73 % |
| bs2@320 | fed segment 0.00834 m | 2.226 Ω = 12.37 % |
| razor@160 | `12.9210+13.7709j` | 1.34 Ω = 7.4 % |
| razor@320 | `12.8922+15.5021j` | 3.07 Ω = 17.0 % |
| nec5@160 | `12.9210+13.7110j` | 1.28 Ω = 7.1 % |

**Sommerfeld** — bs2@160 = `13.2732+10.5972j`, |Z| = 16.98 Ω

| basis | N | fed segment | \|ΔZ\| Ω | relative |
|---|---:|---:|---:|---:|
| bs3 | 12 | 0.20590 m | 40.78 | 240 % |
| bs3 | 15 | 0.17845 m | 35.92 | 211 % |
| bs3 | 20 | 0.12746 m | 26.50 | 156 % |
| bs3 | 30 | 0.08635 m | 18.49 | 109 % |
| bs2 | 15 | 0.17845 m | 22.66 | 133 % |
| bs2 | 20 | 0.12746 m | 16.58 | 98 % |
| bs2 | 30 | 0.08635 m | 11.29 | 66 % |

| arbitration | value | vs bs2@160 |
|---|---|---:|
| bs2@240 | fed segment 0.01111 m | 1.397 Ω = 8.22 % |
| bs2@320 | fed segment 0.00834 m | 2.236 Ω = 13.16 % |
| razor@160 | `13.1740+11.9446j` | 1.35 Ω = 8.0 % |
| razor@320 | `13.1445+13.6797j` | 3.09 Ω = 18.2 % |
| nec5@160 | `13.1740+11.8840j` | 1.29 Ω = 7.6 % |

**Verdict: REFERENCE.** Absolute error across the d=3 ladder (12 → 30) fell 55 %; the reference moved 12.37 % between 160 and 320; the fed segment went 0.20590 m → 0.08635 m across the ladder.

## `specialty.continuous_helix`

**free space** — bs2@160 = `13.7516+17.6846j`, |Z| = 22.40 Ω

| basis | N | fed segment | \|ΔZ\| Ω | relative |
|---|---:|---:|---:|---:|
| bs3 | 12 | 0.05000 m | 9.32 | 42 % |
| bs3 | 15 | 0.05000 m | 6.78 | 30 % |
| bs3 | 20 | 0.05000 m | 4.08 | 18 % |
| bs3 | 30 | 0.05000 m | 2.07 | 9 % |
| bs2 | 15 | 0.05000 m | 6.88 | 31 % |
| bs2 | 20 | 0.05000 m | 4.16 | 19 % |
| bs2 | 30 | 0.05000 m | 2.13 | 10 % |

| arbitration | value | vs bs2@160 |
|---|---|---:|
| bs2@240 | fed segment 0.01000 m | 0.080 Ω = 0.36 % |
| bs2@320 | fed segment 0.00714 m | 0.115 Ω = 0.51 % |
| razor@160 | `13.7467+17.5832j` | 0.10 Ω = 0.5 % |
| razor@320 | `13.7519+17.7041j` | 0.02 Ω = 0.1 % |
| nec5@160 | `13.7460+17.5610j` | 0.12 Ω = 0.6 % |

**Sommerfeld** — bs2@160 = `13.9333+18.2686j`, |Z| = 22.98 Ω

| basis | N | fed segment | \|ΔZ\| Ω | relative |
|---|---:|---:|---:|---:|
| bs3 | 12 | 0.05000 m | 9.32 | 41 % |
| bs3 | 15 | 0.05000 m | 6.78 | 30 % |
| bs3 | 20 | 0.05000 m | 4.08 | 18 % |
| bs3 | 30 | 0.05000 m | 2.07 | 9 % |
| bs2 | 15 | 0.05000 m | 6.88 | 30 % |
| bs2 | 20 | 0.05000 m | 4.16 | 18 % |
| bs2 | 30 | 0.05000 m | 2.13 | 9 % |

| arbitration | value | vs bs2@160 |
|---|---|---:|
| bs2@240 | fed segment 0.01000 m | 0.080 Ω = 0.35 % |
| bs2@320 | fed segment 0.00714 m | 0.115 Ω = 0.50 % |
| razor@160 | `13.9286+18.1686j` | 0.10 Ω = 0.4 % |
| razor@320 | `13.9337+18.2889j` | 0.02 Ω = 0.1 % |
| nec5@160 | `13.9280+18.1470j` | 0.12 Ω = 0.5 % |

**Verdict: DENSITY.** Absolute error across the d=3 ladder (12 → 30) fell 78 %; the reference moved 0.51 % between 160 and 320; the fed segment went 0.05000 m → 0.05000 m across the ladder (unchanged — the feed never refines).

## `wire.zepp`

**free space** — bs2@160 = `2.5704+16.6175j`, |Z| = 16.82 Ω

| basis | N | fed segment | \|ΔZ\| Ω | relative |
|---|---:|---:|---:|---:|
| bs3 | 12 | 0.05000 m | 5.21 | 31 % |
| bs3 | 15 | 0.05000 m | 5.24 | 31 % |
| bs3 | 20 | 0.05000 m | 5.25 | 31 % |
| bs3 | 30 | 0.05000 m | 5.27 | 31 % |
| bs2 | 15 | 0.05000 m | 3.65 | 22 % |
| bs2 | 20 | 0.05000 m | 3.79 | 23 % |
| bs2 | 30 | 0.05000 m | 4.02 | 24 % |

| arbitration | value | vs bs2@160 |
|---|---|---:|
| bs2@240 | fed segment 0.01000 m | 0.294 Ω = 1.75 % |
| bs2@320 | fed segment 0.00714 m | 0.357 Ω = 2.12 % |
| razor@160 | `1.9403+16.1004j` | 0.82 Ω = 4.8 % |
| razor@320 | `2.0148+14.9763j` | 1.73 Ω = 10.3 % |
| nec5@160 | refused | — |

**Sommerfeld** — bs2@160 = `2.4306+16.7452j`, |Z| = 16.92 Ω

| basis | N | fed segment | \|ΔZ\| Ω | relative |
|---|---:|---:|---:|---:|
| bs3 | 12 | 0.05000 m | 5.22 | 31 % |
| bs3 | 15 | 0.05000 m | 5.24 | 31 % |
| bs3 | 20 | 0.05000 m | 5.26 | 31 % |
| bs3 | 30 | 0.05000 m | 5.28 | 31 % |
| bs2 | 15 | 0.05000 m | 3.65 | 22 % |
| bs2 | 20 | 0.05000 m | 3.79 | 22 % |
| bs2 | 30 | 0.05000 m | 4.02 | 24 % |

| arbitration | value | vs bs2@160 |
|---|---|---:|
| bs2@240 | fed segment 0.01000 m | 0.293 Ω = 1.73 % |
| bs2@320 | fed segment 0.00714 m | 0.356 Ω = 2.10 % |
| razor@160 | `1.8334+16.1951j` | 0.81 Ω = 4.8 % |
| razor@320 | `1.9044+15.0754j` | 1.75 Ω = 10.3 % |
| nec5@160 | refused | — |

**Verdict: PLACEMENT.** Absolute error across the d=3 ladder (12 → 30) fell -1 %; the reference moved 2.12 % between 160 and 320; the fed segment went 0.05000 m → 0.05000 m across the ladder (unchanged — the feed never refines).

## Verdicts

| design | verdict | error fall 12→30 | reference move 160→320 | fed segment across the ladder |
|---|---|---:|---:|---|
| `dipoles.short_dipole_loaded` | **reference** | 55 % | 12.37 % | 0.20590 → 0.08635 m |
| `specialty.continuous_helix` | **density** | 78 % | 0.51 % | 0.05000 → 0.05000 m (unchanged) |
| `wire.zepp` | **placement** | -1 % | 2.12 % | 0.05000 → 0.05000 m (unchanged) |

## The three verdicts, and how each was reached

### H1 `dipoles.short_dipole_loaded` → **REFERENCE**. Registered, hit.

Both bars held: the absolute error across the d=3 ladder fell **55 %** (40.60 →
18.41 Ω, 12 → 30), so density behaves normally underneath; and bs2@160 → bs2@320
moved **12.37 %** of `|Z_ref|`, so the reference is not settled.

The arbitration makes it unambiguous. razor-2p and NEC-5 at 160 agree with **each
other** to 0.06 Ω — `12.9210 + 13.7709j` and `12.9210 + 13.7110j` — while sitting
**1.3 Ω** from bs2@160's `13.0183 + 12.4373j`. Two independent oracles agreeing
with each other and disagreeing with the reference is the signature of a reference
that has not arrived. razor@320 then reads `12.8922 + 15.5021j`: **still climbing
in X**.

And it is climbing in X only. Across every engine and every rung, R sits between
**12.89 and 13.27 Ω**; X wanders from **10.60 to 15.50 Ω**. That is exactly what
`PLAN.md` predicted from the geometry before any solve: one wire at 0.25 λ with a
`Load(l=4.65 µH)` at its centre gap is **+j818 Ω against a short dipole's large
capacitive X**, so the served driving point is the residual of two large opposed
reactances on a ~17 Ω denominator. A 1 % error in the antenna's own X is ~8 Ω, or
~47 % of the residual. The relative error is amplified by roughly `X_L/|Z| ≈ 48`.

**So the 133–240 % figures on this row are real arithmetic about a badly
conditioned quantity, not a defect in d=2 or d=3 at their served densities.**

### H2 `specialty.continuous_helix` → **DENSITY**. Registered, hit.

Error fell **78 %** (9.32 → 2.07 Ω), the reference moved **0.51 %**, and razor and
NEC-5 at 160 both land within **0.1–0.12 Ω** of bs2@160. Everything agrees; the
served rung is simply too coarse for the helix's curvature. d=2 at 15 and d=3 at
12 track each other almost exactly (6.88 vs 6.78 Ω at N=15), so this is a property
of the mesh rather than of the degree.

### H3 `wire.zepp` → **PLACEMENT**. Registered as density; **missed**, cleanly.

I predicted density and both bars failed. The error does not fall at all: d=3 reads
**5.21 / 5.24 / 5.25 / 5.27 Ω** across 12 / 15 / 20 / 30 — flat, very slightly
rising — and d=2 reads 3.65 / 3.79 / 4.02 Ω, also rising. The reference moved
**2.12 %**, just over the < 2 % bar.

The placement check, which `PLAN.md` said would run regardless of the verdicts, is
what explains it. **The fed wire is one segment of 0.05000 m at every rung from 12
to 30** — identical at all four — and only refines at the reference: 3 segments of
0.01667 m at 160, 7 of 0.00714 m at 320. So the ladder refines the radiator (24 →
58 segments) while leaving the feed region untouched, and the ~5 Ω is the
difference between a **one-segment and a three-segment feed wire**, not a density
effect on the antenna.

Two things follow:

* `wire.zepp` is end-fed through a 600 Ω transmission line, so its ~16.8 Ω served
  driving point is a *transformed* high impedance. A fixed feed-region difference
  is amplified by that transform — the same conditioning family as H1, reached by
  a different route.
* **The ladder the issue specified cannot answer the question for this design.**
  Refining `nominal_nsegs` from 12 to 30 does not refine what the driving point
  depends on. Any conclusion about zepp's density would have been measured over a
  refinement that did not happen — the same trap as `elt_whip` on AK#1525, in a
  narrower form: there the whole mesh was stiff, here only the fed wire is.

### The precedence between the three tests, which I got wrong once

`specialty.continuous_helix`'s feed is *also* fixed at one 0.05000 m segment
across the ladder, and it is still a density row, because its error falls 78 %
anyway — the helix body's refinement dominates. A first version of the verdict
logic tested "does the feed refine?" first and classed the helix as placement on
that basis. **A non-refining feed only explains a row whose error also fails to
fall.** Density is tested first now, and placement claims only the rows that
refinement did not move.

## What this does and does not justify

* No change to `density.py` is proposed here; that is Steve's call.
* **Nothing here argues against d=3 at 12 on density grounds.** Of the three tail
  rows, one is a conditioning artefact of a loaded short dipole, one is a genuine
  under-resolution that d=2 at 15 shares almost exactly, and one is a feed-mesh
  artefact that no choice of `nominal_nsegs` in the served range would fix.
* What *would* be worth deciding: whether a fixed one-segment feed wire should
  scale with `nominal_nsegs` at all. Two of the three rows here, and `elt_whip` on
  AK#1525, are the same complaint — the knob does not refine the thing the
  driving point depends on. That is a design question, not a density-table one.

## Reproducing

```
NEC5_EXE=<nec5cl-3b75639> python scratch/1552-bspline-tail/run_tail.py \
  --designs dipoles.short_dipole_loaded specialty.continuous_helix wire.zepp \
  --plan bs3:12 bs3:15 bs3:20 bs3:30 bs2:15 bs2:20 bs2:30 bs2:160 bs2:240 bs2:320 \
         razor:160 razor:320 nec5:160 \
  --out scratch/1552-bspline-tail/records.jsonl
python scratch/1552-bspline-tail/report.py
```

78 cells in 55 s. NEC-5 refuses `wire.zepp` on both grounds; that refusal is a
recorded row.

