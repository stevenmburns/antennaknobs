# NEC-5's coarse-mesh excess identified: the centroid-trapezoid path rule

**2026-08-14** · instrument `scripts/bench_tri_razor.py` (path-rule variants)
· artifact `scratch/tri-razor-ladders.json` (`razor_trap2` lane) · follows
the momwire#309/#311 formulation-twin arc

## The question

The RazorSolver twin shares NEC-5's O(1/N) walk and limit, but NEC-5
carried extra coarse-mesh excess: twin-vs-NEC-5 gaps of −0.43−5.34j Ω at
N=12, decaying as an almost pure **C/N² term** (gapX·N² ≈ −769/−765/−764/
−771 for N=12/16/24/32 on the free-space ByDipole1 wire; the drift past
N=48 is NEC-5's 0.001 Ω print precision). A clean second-order term with
our lane at converged quadrature says: a low-order local rule in NEC-5's
fill, not formulation.

## The kill table

Four candidate rules for the testing-path integral ∫A·dl (all with exact
inner potential integrals; gaps are variant − converged-razor, X in Ω):

| rule | X gap @ N=12 | gapX·N² band | verdict |
| --- | --- | --- | --- |
| target (NEC-5 − razor) | −5.340 | −764…−771 | — |
| **trap2** — A at the two path-end centroids, trapezoid | **−5.303** | **−694…−764** | **matches** |
| trap3 — centroids + knot, composite trapezoid | −0.532 | −77…−113 | killed |
| mid2 — half-path midpoints | +0.222 | +32…+51 | killed (wrong sign) |
| 1pt — h·A(knot) | +4.254 | +468…+613 | killed (wrong sign; the unit-1 finding) |

## The result

`razor_impedance(n, path_rule="trap2")` — every potential evaluated ONLY
at the two element centroids bounding the testing path, ∫A·dl by two-point
trapezoid — matches NEC-5 across the whole N=12…100 ladder to a
**constant −0.0036 −0.0371j Ω** (spread under 0.001 Ω, i.e. flat to
NEC-5's print precision). The pair-walk signature becomes identical to the
third decimal: X(2N)−X(N) = +8.500/+3.160/+1.409 vs NEC-5's
+8.500/+3.160/+1.408, ratios 2.69/2.24 on both.

So NEC-5's wire fill is, in full: tent basis, razor-blade testing, with
**all potentials evaluated at element centroids** — which is the literal
reading of the manual's "path integrals of the electric field between
centroids of connected elements" (§1). The twin's earlier residual came
from us doing the path integral *better* than the scheme itself does; the
classic mixed-potential idiom evaluates A and Φ at the centroids only.
Identified black-box from printouts + the public manual; no NEC-5 source
consulted.

What remains is a **constant** −0.004−0.037j Ω — N-independent, so a
limit-level kernel nuance (e.g. surface-vs-axis evaluation detail), 0.04 Ω,
below anything the census quotes.

## Consequences

- The momwire#890 story is now complete at three levels: the walk is the
  razor-blade testing rule (momwire#309); the coarse-rung excess is the
  centroid-trapezoid quadrature (this note); the remaining residual is a
  0.04 Ω constant. The (N, 2N) census pair recipe stands unchanged — extrapolation
  removes the first-order term regardless of the h² coefficient.
- A `nec5_quadrature=True` mode on momwire's RazorSolver (swap the T1 path
  rule to trap2) would reproduce NEC-5 rung-for-rung to 0.04 Ω, making the
  twin-vs-NEC-5 documentation exhibits exact — filed as a momwire
  follow-up. Deliberately NOT a step toward productizing an NEC-5
  substitute: the mode exists so the census rationale is demonstrable, and
  the real binary remains the only oracle that can testify.
