# 2026-08-12 — The Leeson demo: Cebik's tapered dipoles, three ways (#896 phase 1)

## Goal

Phase 1 of #896: a published stepped-diameter demonstration with known
corrected values — show raw NEC-2 missing by the documented amount, bs2
landing natively, NEC-5 concurring by pair. One sentence: *the correction
table is built into the physics.*

## The published anchor

L.B. Cebik (W4RNL), "Tapering to Perfection" (*Antenna Modeling* #10,
archived at antenna2.github.io/cebik/content/amod/amod10.html): five
14 MHz free-space dipoles with progressively harder diameter tapers, each
with published uncorrected-NEC-2 and Leeson-corrected values. Exact
half-element schedules are in the article (and now in
`scripts/bench_leeson.py`); Cebik's segment counts were NOT published, so
raw-NEC-2 reads match his tables in signature and direction but not to
the ohm (the raw error is segmentation-dependent).

The same article's W6NGZ / WB0DGF / K6STI driven-element cases (with
NEC-4 and MININEC columns) are follow-up material; the K6STI fat-center
element (3.42″ × 8″ center section) is honest-limits material — even
NEC-4 diverges there (thick-wire kernel territory).

## Instrument

`scripts/bench_leeson.py` → `scratch/leeson-cebik.json` (committed).
Decks built from the half-schedules mirrored about the feed (center
section = one wire with odd segment count, feed at the exact center
segment; ~equal segment lengths across sections). Engines per case:

- nec2c raw at 1×/2×/4× density (1× ≈ 0.25 m segments),
- bs2 and the census NEC-5 (N, 2N) pair at 1×/2× (converged by 2×),
- NEC-5 native single-mesh reads preserved alongside the pair.

`build_validation_report.py` consumes the artifact: the five-case table,
the case-5 reactance-vs-mesh figure, and computed spread claims.

## Findings

- **The defect grows with refinement.** Raw nec2c on the extreme taper:
  X = +19.6 Ω at 1× → +22.3 at 2× → +24.4 at 4× (published raw +17.1 at
  Cebik's unstated mesh). Same direction on every stepped case. You
  cannot mesh your way out of the stepped-radius defect — refining makes
  it worse. This is the demo's strongest single fact, and the published
  tables could not show it (single mesh).
- **Formulation-line agreement on the exact geometry**: bs2 ↔ NEC-5 pair
  within 0.81 Ω (worst case) across all five cases and both meshes, with
  no correction applied anywhere.
- **Where the correction points, the physics lands**: bs2 X within
  2.5 Ω of the published corrected value on every taper (corrected X ≈ 0
  = resonance restored; ours sit −0.4 to −2.1).
- **The correction is itself an approximation**: on the extreme taper the
  corrected R (72.1) sits ~4.4 Ω from the exact-geometry consensus
  (76.5) while X agrees — the uniform-substitute element reproduces
  resonance, not the exact R. Two independent formulations solving the
  true geometry is the stronger statement. Worth care in public framing:
  we agree with the correction's *purpose*, we do not treat the
  corrected number as ground truth.
- The uniform control row: all engines and the published value within a
  few tenths of an ohm (nec2c included — the defect is the steps, not
  the taper per se).

## Ties

- #872 phase 5 / #885: 44/46 wild-corpus formulation movers are
  stepped-radius decks — this demo is the mechanism behind the census
  verdict, one deck class down.
- The census `d` flag marks these decks nec2c-reference-suspect; the
  validation page now demonstrates why with a published anchor.
