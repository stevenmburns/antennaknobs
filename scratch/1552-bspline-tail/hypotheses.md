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

## ΔΓ re-cut, 2026-09-16

The same three ladders on **ΔΓ**, no cell re-solved. The verdicts are about *why* a row is far, so they are unchanged by the metric; what changes is how far it looks.

| design | ground | basis | N | rel-Z | ΔΓ (norm) | ΔΓ (max port) |
|---|---|---|---:|---:|---:|---:|
| `dipoles.short_dipole_loaded` | free | bs3 | 12 | 225 % | 0.9001 | 0.9001 |
| `dipoles.short_dipole_loaded` | free | bs3 | 15 | 199 % | 0.8153 | 0.8153 |
| `dipoles.short_dipole_loaded` | free | bs3 | 20 | 147 % | 0.6284 | 0.6284 |
| `dipoles.short_dipole_loaded` | free | bs3 | 30 | 102 % | 0.4486 | 0.4486 |
| `dipoles.short_dipole_loaded` | free | bs2 | 15 | 125 % | 0.5446 | 0.5446 |
| `dipoles.short_dipole_loaded` | free | bs2 | 20 | 92 % | 0.4037 | 0.4037 |
| `dipoles.short_dipole_loaded` | free | bs2 | 30 | 62 % | 0.2763 | 0.2763 |
| `dipoles.short_dipole_loaded` | somm | bs3 | 12 | 240 % | 0.8915 | 0.8915 |
| `dipoles.short_dipole_loaded` | somm | bs3 | 15 | 211 % | 0.8086 | 0.8086 |
| `dipoles.short_dipole_loaded` | somm | bs3 | 20 | 156 % | 0.6252 | 0.6252 |
| `dipoles.short_dipole_loaded` | somm | bs3 | 30 | 109 % | 0.4478 | 0.4478 |
| `dipoles.short_dipole_loaded` | somm | bs2 | 15 | 133 % | 0.5426 | 0.5426 |
| `dipoles.short_dipole_loaded` | somm | bs2 | 20 | 98 % | 0.4034 | 0.4034 |
| `dipoles.short_dipole_loaded` | somm | bs2 | 30 | 66 % | 0.2767 | 0.2767 |
| `specialty.continuous_helix` | free | bs3 | 12 | 42 % | 0.2195 | 0.2195 |
| `specialty.continuous_helix` | free | bs3 | 15 | 30 % | 0.1587 | 0.1587 |
| `specialty.continuous_helix` | free | bs3 | 20 | 18 % | 0.0946 | 0.0946 |
| `specialty.continuous_helix` | free | bs3 | 30 | 9 % | 0.0476 | 0.0476 |
| `specialty.continuous_helix` | free | bs2 | 15 | 31 % | 0.1611 | 0.1611 |
| `specialty.continuous_helix` | free | bs2 | 20 | 19 % | 0.0966 | 0.0966 |
| `specialty.continuous_helix` | free | bs2 | 30 | 10 % | 0.0492 | 0.0492 |
| `specialty.continuous_helix` | somm | bs3 | 12 | 41 % | 0.2174 | 0.2174 |
| `specialty.continuous_helix` | somm | bs3 | 15 | 30 % | 0.1572 | 0.1572 |
| `specialty.continuous_helix` | somm | bs3 | 20 | 18 % | 0.0937 | 0.0937 |
| `specialty.continuous_helix` | somm | bs3 | 30 | 9 % | 0.0471 | 0.0471 |
| `specialty.continuous_helix` | somm | bs2 | 15 | 30 % | 0.1596 | 0.1596 |
| `specialty.continuous_helix` | somm | bs2 | 20 | 18 % | 0.0957 | 0.0957 |
| `specialty.continuous_helix` | somm | bs2 | 30 | 9 % | 0.0487 | 0.0487 |
| `wire.zepp` | free | bs3 | 12 | 31 % | 0.1657 | 0.1657 |
| `wire.zepp` | free | bs3 | 15 | 31 % | 0.1664 | 0.1664 |
| `wire.zepp` | free | bs3 | 20 | 31 % | 0.1670 | 0.1670 |
| `wire.zepp` | free | bs3 | 30 | 31 % | 0.1674 | 0.1674 |
| `wire.zepp` | free | bs2 | 15 | 22 % | 0.1175 | 0.1175 |
| `wire.zepp` | free | bs2 | 20 | 23 % | 0.1219 | 0.1219 |
| `wire.zepp` | free | bs2 | 30 | 24 % | 0.1289 | 0.1289 |
| `wire.zepp` | somm | bs3 | 12 | 31 % | 0.1665 | 0.1665 |
| `wire.zepp` | somm | bs3 | 15 | 31 % | 0.1671 | 0.1671 |
| `wire.zepp` | somm | bs3 | 20 | 31 % | 0.1677 | 0.1677 |
| `wire.zepp` | somm | bs3 | 30 | 31 % | 0.1682 | 0.1682 |
| `wire.zepp` | somm | bs2 | 15 | 22 % | 0.1179 | 0.1179 |
| `wire.zepp` | somm | bs2 | 20 | 22 % | 0.1223 | 0.1223 |
| `wire.zepp` | somm | bs2 | 30 | 24 % | 0.1293 | 0.1293 |

At each design's **served** rung, free space:

| design | basis | relative Z | ΔΓ |
|---|---|---:|---:|
| `dipoles.short_dipole_loaded` | bs2 | 125 % | **0.5446** |
| `dipoles.short_dipole_loaded` | bs3 | 225 % | **0.9001** |
| `specialty.continuous_helix` | bs2 | 31 % | **0.1611** |
| `specialty.continuous_helix` | bs3 | 42 % | **0.2195** |
| `wire.zepp` | bs2 | 22 % | **0.1175** |
| `wire.zepp` | bs3 | 31 % | **0.1657** |

### The verdicts on ΔΓ — one of the three changes

| design | verdict on relative Z | verdict on ΔΓ | ΔΓ fall 12→30 | reference's own ΔΓ at 320 | reference / row |
|---|---|---|---:|---:|---:|
| `dipoles.short_dipole_loaded` | reference | **density** **(changed)** | 50 % | 0.0536 | 0.060 |
| `specialty.continuous_helix` | density | **density** | 78 % | 0.0026 | 0.012 |
| `wire.zepp` | placement | **placement** | -1 % | 0.0118 | 0.071 |
