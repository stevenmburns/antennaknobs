# Correcting comment for momwire#518 — POSTED 2026-08-21
# https://github.com/stevenmburns/momwire/issues/518#issuecomment-5370684239

---

**Correction: the ~2 % bias reported here is OVERTURNED. It was a geometry bug in the ladder script, not a solver defect. The B-spline family is clean on this model.**

The overnight ladder's `run_bspline` split wire 1 at the feed to spell the series gap as a node-gap port — which shifted every subsequent wire's index by one — and then re-indexed only three of the six junction entries. Two consequences, both accepted silently by `BSplineSolver` (it validates index range and `"start"`/`"end"` spelling, never geometric coincidence — filed as #522):

1. **Wire 6 (the 20 m stub closing the loop to the vertical's base) ended up in no junction group** → both ends zeroed as free ends → a 1-segment wire with zero dofs → electrically absent.
2. Two junction groups tied wire ends 60–100 m apart (KCL between non-coincident points).

At 500 Hz the answer is set by which conductors carry charge, so the observable effect is exactly "geometry minus the stub." The razor/NEC-5 rows were immune: razor auto-detects junctions from coordinates (its k=1 refusal of the 1-segment stub proves its model *had* wire 6), and `nec5cl` consumed the actual deck.

**Verification, four ways** (repro: `ladder_geometry_postmortem.py` in the session archive alongside `referee2.py`):

- Re-running the script's exact junction list reproduces the recorded `results.json` bs rows **to all ten stored digits** (e.g. bs1 k=1: 1.0681224372).
- A cleanly-built no-stub model reproduces the recorded ladder at every rung to ≤ 0.05 % — the "family limit" ≈ −377.7 kΩ is the stub-less geometry's correct answer.
- The **same spelling with the junction list fixed** converges onto the referee: bs1 −370.73, bs2 −370.65 kΩ at 496 segments; bs2 at Roy's own 31-segment mesh gives −370.90 kΩ ≡ the seam's own printed 1.0910 A source current (which contradicted this issue's ladder all along). Loop currents land on NEC-5's (0.5101 vs 0.5100 A at ×16).
- The **electrostatic referee re-run on the stub-less geometry certifies the "biased" number**: C_gap = 841.6 pF → −378.2 kΩ. Both families were right — about different structures.

Two independent checks also close the theory side: a from-scratch tent-doublet Galerkin discretization of this model (mean-tested Φ rows, doublet charge, reduced kernel) converges to −370.7 kΩ, and a point-vs-mean testing knob on the referee is a null (+0.013 %). There is no capacitance bias in the Galerkin scalar term to enrich away.

Why the probes upthread misled: a wrong-geometry model is a *well-posed different problem* — it converges cleanly, first-order, mesh-flat, to a limit 2 % away, and no kernel/enrichment knob can touch it. The EK null and enrichment null were inevitable; "bs1 sits with bs2" was the shared geometry builder, not the shared testing scheme.

Status changes:

- The suspected locus (smooth-spline charge at terminations), the proposed end/junction charge enrichment, and the "fix shape" discussion are withdrawn — there is nothing to fix in the basis family here.
- The **N4PC Loop deviation (3,758–4,309 Ω, captures 0081–0084) is un-attributed again**: it came from the seam corpus sweep on real decks (no hand-built junction lists involved) and needs its own investigation. Anti-resonance slope magnifies small errors of *any* origin; do not assume a charge-representation cause.
- #449 (the bs2 taper stall) is unaffected — its evidence is independent and its bs1-escapes signature is different.
- Hardening follow-up: #522 (junction coincidence validation — would have made this a loud `ValueError` at construction).

Net for the record: on W7EL's model, NEC-5, razor, bs1, bs2 and the electrostatic referee all agree at the −370.5 kΩ limit; only the NEC-2 scheme diverges. Closing as not-a-defect once reviewed.

🤖 Generated with [Claude Code](https://claude.com/claude-code)

https://claude.ai/code/session_0163HVuvMSt5iYuA7gfTQWRT
