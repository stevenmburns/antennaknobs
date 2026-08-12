# 2026-08-12 — Pattern census: NEC-5 vs bs2 across the catalog (#872 phase 4)

## Goal

Phase 4 of #872: `pattern_metrics` (peak dBi, takeoff, azimuth, F/B,
beamwidths) across the built-in catalog, nec5 vs bs2, flagging
|Δpeak| > 0.5 dB or |Δtakeoff| > 2°. Instrument:
`scripts/bench_nec5_patterns.py`; artifact
`scratch/nec5-patterns-phase4.json`.

Setup: free space, shared 1° upper-hemisphere grid, single mesh
(nominal_nsegs = 81 under a 3000-segment cap, else the design default) —
patterns are global functionals, far less mesh-sensitive than the feed
impedance the knot-source march lives in. RMS dB is computed over the
co-illuminated grid (both engines within 30 dB of peak). The takeoff
flag is gated on RMS > 0.1 dB: on a broad flat lobe the argmax twitches
degrees between engines whose patterns match to milli-dB (free-space
dipoles showed ±5–77° takeoff "differences" at RMS 0.003).

## Result: 73 compared, 0 errors, essentially perfect agreement

- **|Δpeak| median 0.003 dB, max 0.166 dB** (verticals.elt_whip, a
  loaded whip, RMS 1.13 — the largest shape difference in the catalog
  and still far under the flag bar).
- **RMS dB median 0.006.** Beams with real shape structure (moxon, yagi,
  owa_yagi, four_square) sit at RMS 0.4–0.6 with Δpeak ≤ 0.04 dB and
  ΔF/B ≤ 1.7 dB.
- **Zero designs cross the 0.5 dB peak flag.** One marginal takeoff
  flag: beams.hexbeam (Δtakeoff 4°, RMS 0.102 — just over the shape
  gate, Δpeak 0.03 dB). Read as a broad-lobe peak location wobble with
  mild shape difference, not a physics split; recorded, not escalated.
- 26 designs OOS, all designed refusals (TL/NT/TwoPort/Transformer/
  BalancedLine/FloatingBalun branches — network dialect NEC-5's stage
  1–5 engine deliberately does not stamp).

## Reading

The pattern story is closed: whatever residual formulation character
distinguishes NEC-5's knot sources and momwire's Galerkin bases at the
feed point, it does not reach the radiated field at catalog scale. This
matches the engine's own cross-check (0.01 dB RMS on the invvee) and
means phase-5 outlier hunting can concentrate on impedance, using
patterns only as a cheap sanity column.

## Next

- Phase 5: the wild-corpus subset — Z census with extrapolated-pair
  NEC-5 rows, cross-referenced against the historical nec2c census;
  outliers that MOVE between oracles are the findings.
- Phase 3(b) (momwire#291 contact extensions) still deferred to a
  momwire-level instrument with a verbatim base-feed spelling.
