# Hardening the NEC-5 identification — and the bs1/bs2 numbers it proves

**2026-08-14** · instrument `scripts/bench_nec5_twin_hardening.py` · artifact
`scratch/nec5-twin-hardening.json` · follows
`2026-08-14-nec5-quadrature-identified.md` · all free space, 14 MHz

Four geometries: the ByDipole1 wire (thin dipole), the same wire at 10 mm
radius (fat), a 90° inverted-V (bend + apex K=2 junction feed), and a
1.13λ square loop (closed topology, four corners). Lanes: NEC-5 (licensed
binary), `RazorSolver(nec5_quadrature=True)` (the identified twin),
RazorSolver default, bs1, bs2 (bs lanes on the non-loop geometries).

## Claim 1 — the identification generalizes

NEC-5 minus the twin, down each ladder (mean ± max deviation):

| geometry | mean residual (Ω) | spread (Ω) | verdict |
| --- | --- | --- | --- |
| dipole | −0.0036−0.0370j | 0.0007 | constant |
| invvee | −0.0027−0.0371j | 0.0005 | constant — bend + junction feed change nothing |
| loop | −0.0108−0.0674j | 0.0060 | constant within print-precision noise |
| fat-dipole | −0.0073−0.0422j | 0.0287 | **drifts with N** — see below |

The quadrature identification holds everywhere: on every geometry the
O(1/N) walk and the h² coarse-mesh excess are fully reproduced, and on
thin wires the residual is a per-geometry constant of a few hundredths of
an ohm. The fat wire sharpens the picture of what the residual IS: at
10 mm radius it grows from −0.029j (N=12) to −0.070j (N=96) — i.e. it
scales with a/h, exactly the signature of a **kernel-evaluation nuance**
(how the code handles the wire surface vs axis as segments approach the
wire thickness), not of any further quadrature difference. Everything
observed stays under 0.07 Ω — below anything the census quotes — and the
thin-wire constancy (spreads of 0.0005–0.006) is the identification's
confirmation across bends, junctions, and loops.

## Claim 2 — what this buys bs1/bs2 (the real story)

N* = total segments a lane needs to sit within 0.5 Ω of its own converged
value (first-order lanes judged against their own Richardson limit):

| geometry | bs2 | bs1 | razor / NEC-5 |
| --- | --- | --- | --- |
| dipole | **12** | 48 | **>96** |
| fat-dipole | **32** | 64 | >96 |
| invvee | **16** | 48 | >96 |

Same tent basis as NEC-5's, Galerkin testing instead of razor-blade: bs1
converges at half the mesh NEC-5 hasn't converged at. Higher-order basis
on top: bs2 is census-grade at 12–32 segments while NEC-5's formulation
is still >0.5 Ω out at 96. In matrix terms an 8× segment factor is 64×
the fill and ~500× the dense-solve work — and NEC-5 additionally needs
the (N, 2N) pair extrapolation (two solves) to quote a converged number
at all, which bs2 does not.

This is the controlled experiment behind the claim: the twin proves the
difference is the formulation (testing rule + basis order), not
implementation quality — the twin IS NEC-5's formulation, in this
codebase, at converged quadrature, and it walks exactly like NEC-5 does.

## Caveats

- Free space only (the twin's domain). The bs-vs-NEC-5 convergence
  comparison over ground is already on the validation page's left panel
  and tells the same story.
- Loop bs lanes not run (BSplineSolver wants an explicit junction spec
  for closed loops; out of scope for this instrument).
- NEC-5 rungs at loop scale carry ~0.005 Ω print-precision noise.
