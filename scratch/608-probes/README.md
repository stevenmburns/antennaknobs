# 608-probes — is razor's one-segment-wire refusal over-broad?

Evidence behind momwire#608. `RazorSolver.__init__` refused every wire with
`sum(npe) < 2`, which cost the EZNEC corpus five captures (0011, 0029, 0030,
0034, 0035). These three probes established that the refusal was over-broad,
and by exactly how much.

Run from the antennaknobs root with the venv active.

## The three cases

A one-segment wire's only possible bases are junction tents, so what matters
is how many of its two ends meet something:

| | ends joined | bases on the wire | verdict |
|---|---|---|---|
| (a) | both | 2 tents = a normal interior segment | **served** |
| (b) | one | 1 tent, like a terminal segment | **served** |
| (c) | neither | none at all — inert | **refused** |

## `probe_one_segment.py` → `RESULTS-probe-one-segment.txt`

Neuters the guard in an off-tree copy of `razor.py` (it is inline in
`__init__`, so it cannot be monkeypatched; the copy must live INSIDE the
package or its relative imports fail) and runs the split identity at the two
knots that produce a one-segment piece.

The finding that settled it: cases (a) and (b) are **exact**, not
approximate. A wire split at a knot is the same linear system with one basis
re-labelled, so a split leaving a one-segment piece reproduces the unsplit
wire to solver precision — measured 6e-15 and 3e-14 relative, including the
reversed spelling and a feed on the piece's own junction knot. The prose the
guard carried ("its two junction tents would overlap on that one segment")
described the two Lagrange bases every interior segment already has.

Case (c) is inert: `rel 0.000e+00` against the same model with the floater
deleted — bit-identical, because the wire carries no unknown. The same
floater at two segments scatters (3.4e-5).

## `classify_decks.py` → `RESULTS-classify-decks.txt`

Classifies every one-segment polyline in all 62 captures, on the mesh razor
is actually handed and by razor's own `_find_junctions` grouping (a 1e-9
first-match — NOT the deck front end's 1e-6 node grid, which is a thousand
times looser and a different algorithm).

**74 one-segment polylines across the five decks; 71 case (a), 3 case (b),
zero case (c).** So narrowing the refusal to (c) costs the corpus nothing,
which is what made the fix a narrowing rather than a trade.

## `nec5_case_c.py` → `RESULTS-nec5-case-c.txt`

razor is the NEC-5 formulation twin, so case (c) was put to the licensed
binary before deciding whether to refuse, warn, or match the sibling. A
dipole, the same dipole with an isolated one-segment wire alongside, and the
same floater at two segments:

```
  no floater           66.6810  -35.6310j   elements=20  unknowns=19
  1-seg floater        66.6810  -35.6310j   elements=21  unknowns=19
  2-seg floater        66.6800  -35.6340j   elements=22  unknowns=20
```

The engine counts the floater as an element and gives it **no unknown**, and
prints the same impedance with and without it. razor's inert behaviour IS the
twin's — the divergence in momwire#608 is only that razor SAYS so instead of
dropping the wire silently. `BSplineSolver` differs from both: a degree-2
spline over one segment keeps one basis, so the floater scatters there.

Only the binary's printed output is read. Nothing about the engine's
internals is quoted or inferred. Citation: NEC-5 (LLNL-CODE-746721).
