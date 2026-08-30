# momwire#692 — the deeper-deck density ladder (near axes coarsen too)

Arc opened + SHIPPED 2026-08-27/28 session 12 (same session as #674).
Issue: can the crossing fill's NEAR axes carry the #688 far-density
knobs (q4 / G4 panels / ×4 growth)? Blocked on deep-deck evidence —
every #688 deck was 0.15 m and `_n_qp_buried_field`'s q=6 was measured
on close pairs.

## Probes

- probe1_deep_density_ladder.py — the harness (knobs scoped inside an
  `axis_data` wrapper; near/fine path only) × deck ladder (0.15/0.5/
  1.0 m, base + #674-graded node meshes) × rungs (q4 | panels
  touching-only | combo). RESULT: worst soil |dZ| 7e-4 Ω (D100-g,
  q4-driven); panels-only worst 1e-4; graded ε̃=1 margins unmoved at
  1e-4 class. results/probe1-deep-density-ladder.json.
- probe2_rebank.py — every banked print through the flip: g1
  138.7670−102.9889j (−1e-4 from bank), g2/hub unchanged, fan base
  143.9327−26.2136j (margin 0.2268), n2 142.1923−36.4707j (re-banked),
  n3 142.1919−36.4767j, AK catalog 75.9413+77.2359j @ 3.2 s warm.

## Shipped

momwire PR #695 (branch `692-near-density-default`, closes #692):
`_NEAR_Q/_NEAR_GROWTH/_NEAR_GX/GW` knobs (= far values, separate for
one-line revert), fine path off `_n_qp_buried_field` (grid fills keep
it), docstring notes both sides, FAN_SOIL_A_N2 re-banked, g524_7
message 0.2268. Measurement bank = #692 issue comment. Wall: g1
2.1→1.3 s, fan soil 3.2→2.0 s, AK catalog ~4.5→3.2 s (~1.4×).

## New ritual prints after this flip (supersede the #688-era set)

g1 138.7670−102.9889j · fan base soil 143.9327−26.2136j · fan collapse
margin 0.2268 · n2 fan 142.1923−36.4707j (graded margin 0.0001) · AK
catalog 75.9413+77.2359j (warm ~3.2 s).
