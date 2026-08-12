# 2026-08-12 — NEC connection tolerance: the momwire lanes solved broken graphs (momwire#302)

## The finding

momwire#302's larger half (`delta-loop-15m.nec`, bs2 ΔΓ 0.256) turned
out to be an **importer bug that has silently depressed every momwire
census column in the program's history** — not a solver defect.

NEC engines connect segment ends that coincide within a tolerance
(nec2c `conect()`: L1 separation ≤ 1e-3 × the connecting segment's own
length; nec2++ and NEC-5 behave alike). antennaknobs' engines junction
wire ENDS on (near-)exact coordinate matches instead
(`flat_wires_to_polylines` quantizes at 1e-6 m absolute,
`_junction_cuts` at 1e-9 m). A deck whose corners sit microscopically
apart therefore imported as a **broken electrical graph for the momwire
lanes only** — current pinned to zero at every unmatched end — while
nec2c (raw deck), nec2++ and NEC-5 all re-apply NEC's own tolerance
downstream of the translation and solved the antenna the author meant.

The failure class is real and systematic: **GM-rotated copies of
6-significant-digit card coordinates land ~1 µm off the endpoints they
must join.** The qantenna delta loop's corners sit 1.1 µm apart — just
past the 1e-6 grid — so every momwire basis solved three broken
triangles: X wrong by 90–150 Ω across the whole 20–22.5 MHz band and
**no loop resonance anywhere**, while pynec/nec2c/NEC-5 on identical
geometry agree on 21.2 MHz, R = 25.9 to three digits. After connecting
the corners, bs2 reads 35.22−143.55j at 20 MHz vs nec2c's 35.47−143.66j
(ΔΓ 0.256 → 0.038).

## The fix

`parse_nec` now snaps NEC-connected wire ends onto exact shared
coordinates (`_snap_nec_connections`): endpoint clusters under the
per-pair NEC tolerance union-find to a canonical member, then remaining
ends snap onto other wires' interior segment boundaries (the same
`a + (b−a)·(k/n)` formula `_junction_cuts` matches bitwise). L1 norm as
in nec2c; per-pair MINIMUM segment length — the conservative
intersection of nec2c's asymmetric per-end rule, so nothing any NEC
build would leave open gets connected. Gaps wider than the tolerance
stay untouched. Pinned by three importer tests (GM-rotated corners,
end-onto-interior-boundary, wider-gap-stays-open).

## Census impact (bs2 lane re-run, 126 rewrite-affected wild decks)

Corpus scan: 126/3214 parseable wild decks get endpoint rewrites, but
most are sign-of-zero/last-bit canonicalizations with zero electrical
effect — **22 wild decks (plus 7 of 79 xnec2c example decks, including
the shakedown's inverted cones, tower, airplane and helix decks) have
real (> 1 nm) moves**. Artifact: `scratch/nec-connection-snap-rerun.jsonl`
(all 126 re-solved, nec2c references re-run).

Paired against the phase-5 rows (105 decks with nec2c references):

- median bs2 ΔΓ **0.144 → 0.072**; ΔΓ > 0.2 tail 46 → 39;
  improved 14 / worsened 3 / unchanged 88 (the no-op rewrites).
- Headline repairs: `40m V doglegs BUILT` **0.887 → 0.030**, the cebik
  tutorial family 0.26–0.29 → 0.004–0.05, `delta-loop-15m`
  0.256 → 0.038, the NearFld/car objects 0.161 → 0.093.
- The 3 "worsened" decks (`tower` 0.96 → 1.05, `helicalAntenna`
  0.37 → 0.61, `Ship1` 0.089 → 0.098) are **honest reconnections**:
  every snapped end passes nec2c's own connection criterion, so nec2c
  was already solving the connected structure — the broken momwire graph
  had been closer by luck. All were outliers before; they stay flagged.
- The g1ojs magloop family is bit-unchanged (its rewrites were
  canonicalization no-ops) — the EK addendum's kernel-sensitivity
  reading stands.

## momwire#302 disposition

- `delta-loop-15m`: **importer bug, fixed here** — bs2 lands within
  1 Ω of the three-engine consensus across the band.
- `dual_band_stacked_moxon_146_444_50mm_only146driven`: **pathological
  near-short, no defect anywhere** — at 146 MHz every engine converges
  to Z ≈ 0 (bs2 ×4 mesh: 0.000+0.02j; NEC-5's own doubled mesh:
  0.000−0.0001j). The recorded ΔΓ 1.42 compared coarse-mesh reads
  scattered around |Γ| ≈ 1; NEC-5's +4.8j "extrapolation" is itself an
  artifact of a sign-crossing Richardson pair. Same class as
  `excessive_gain.nec` in the phase-5 verdict.

After momwire#300 (instrument radius mismatch) and #302 (importer
connection tolerance + a near-short), the five-phase #872 hunt's
momwire-suspect pile stands at **zero decks**.
