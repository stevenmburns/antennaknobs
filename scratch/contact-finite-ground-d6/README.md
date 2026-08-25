# contact-finite-ground-d6 — is the contact gap a basis defect?

Evidence for momwire#603 U5 / the D6 decision in
`momwire/docs/design/contact-over-finite-ground.md` §7.

## The question

`RazorSolver` refuses ground contact over a finite ground; `BSplineSolver`
serves it. §7's D6 asks whether razor needs the capability at all, and the
study's §3.5 supplies the reason to hesitate: momwire's ground-induced shift
`δ = Z(soil) − Z(PEC)` sits up to **3.3 Ω** from the licensed binary's on
poor soil, *opening* with mesh and then saturating — a difference of limits.
Stage 2 killed all three candidate explanations and left a hypothesis.

If razor were given contact and landed in the same gap, we would ship an
engine claiming to be the NEC-5 twin while diverging from NEC-5 on exactly
the capability the twin claim is sold on. That is the real argument against
Stage 3 — not D6's, which reasons from a world in which razor was not yet a
shipping executable.

## What this measures

Razor's basis is the **tent** basis, which is exactly
`BSplineSolver(degree=1)`. Both degrees are Galerkin, so running d=1 beside
d=2 on the study's own contact monopole isolates the **basis**:

```
soil        N |  |diff| d=1 (tent)   |diff| d=2   spread
poor       11 |              2.912        2.915    0.003
poor       21 |              3.141        3.151    0.010
poor       41 |              3.262        3.269    0.007
average    11 |              0.679        0.672    0.007
average    21 |              0.958        0.963    0.005
average    41 |              1.158        1.163    0.005
```

**0.01 Ω of spread on a 3.3 Ω gap — 0.3 %.** The tent basis and the
quadratic land on top of each other. The d=2 column reproduces §3.5's
recorded table exactly, which is the harness's own check.

## What follows, and what does not

**Follows:** the gap is not a property of the basis, so razor's basis is not
what is wrong at contact. It belongs to the trunk's ground handling, which
razor shares through `_potential_ground.PotentialGround`. This agrees with
§4.3 from the code side: *"the defect is a missing term in the row's
potential reference, not a wrong basis function."*

**Does not follow:** d=1 shares razor's basis but not its **testing** — it is
Galerkin, razor is razor-blade path testing. Nothing here says whether
razor's testing lands better or worse at contact. That is §5.5's spike, and
it is still the open question.

Which cuts both ways. Razor is NEC-5's own scheme. If restoring §4.3's
plane-reference term — `(1 − w_Φ)·M0(plane)`, identically zero at PEC — puts
razor **on** the binary where both B-spline degrees sit 3.3 Ω away, that does
not merely serve five decks: it localizes a gap currently unexplained across
the whole finite-ground contact row, for both trunks.

## Running it

```
NEC5_EXE=~/antennas/NEC5-downloads/nec5-linux/nec5cl \
    python scratch/contact-finite-ground-d6/degree_columns.py
```

Only the binary's printed impedance is read. Nothing about the engine's
internals is quoted or inferred. Citation: NEC-5 (LLNL-CODE-746721).
