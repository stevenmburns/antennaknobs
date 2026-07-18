# 2026-07-18 — Anchoring the quad convergence anomaly (issue #408)

## TL;DR

The 2026-07-16 corpus benchmark left one open question: on the cubical-quad
loop, the NEC-family engines (PyNEC, Sinusoidal) climbed past 136 Ω and kept
rising while the B-spline bases plateaued at ~130 Ω — *different* values, and
which was correct was unresolved. The new `--converge` tool
(`scripts/bench_converge.py`, issue #408 part 2) with its `nec2c` **value
anchor** settles it:

- **They converge to the *same* value (~130 Ω).** The B-splines were right.
- **NEC's climb to 138.8 Ω was a feed-modeling artifact** of `quad.py`, not a
  basis-value disagreement and not a property of closed loops. The quad feeds
  its driver through a **fixed 1-segment gap** (0.1 m) that does *not* refine
  with the mesh; as `nominal_nsegs` grows, that feed segment becomes ~2× larger
  than its shrinking loop-side neighbours, and NEC's delta-gap driving-point R
  drifts upward with that segment-length discontinuity. The B-spline basis is
  insensitive to it and plateaus at the true value.
- **The "closed loops favour the higher-order basis" hypothesis does NOT
  generalise.** A single square loop (`diamond_loop`) and a triangle
  (`delta_loop`) — both meshed with a feed edge that refines with the mesh —
  converge to a single value across *all five* methods (PyNEC, nec2c,
  Sinusoidal, BSpline d=1, d=2); the B-splines merely reach it at a coarser
  mesh. The quad was the lone outlier, and its outlier status is a meshing bug.

Follow-up filed: **quad.py's feed segment should refine with the mesh** (like
`delta_loop`/`diamond_loop` already do). The contingent "make B-spline the cheap
accurate loop engine" product issue (#408 part 3) is **not** pursued — its
premise (B-spline reaches the *same* answer with 2–6× fewer segments) held only
on the quad *because of the bug*; on cleanly-meshed loops the rate advantage is
a modest ~2–3×, not enough to justify per-basis `nominal_nsegs` scaling.

## Tool

`scripts/bench_converge.py` — a sibling of `bench_nec_corpus.py` reusing its
subprocess / peak-RSS / thread-policy harness. For each parameterized design it
sweeps `nominal_nsegs` over a ladder and solves with all four engines, and with
`--anchor-nec2c` also solves each mesh with `nec2c` on the matched-dimension
`export_nec` deck (a faithful text twin of what PyNEC builds — so nec2c anchors
the *value* the curve approaches, not just a fixed geometry).

```
python scripts/bench_converge.py --designs loops.quad \
  --nseg-ladder 7 11 15 21 31 45 61 85 121 161 201 --anchor-nec2c
```

`nseg_to_converge` only counts a mesh **coarser than the finest** as a
convergence point (the finest trivially matches itself), so "not settled"
honestly flags a curve still moving at the finest mesh instead of reporting a
false plateau.

## The quad anchor (feed 0, free space, R + jX in Ω)

| N | Σseg | PyNEC | Sinusoidal | BSpline d=1 | BSpline d=2 | **nec2c** |
|--:|--:|--:|--:|--:|--:|--:|
| 7   | 56   | 115.7 −0.4j | 115.8 −0.4j | 127.5 −2.9j | 130.4 −1.3j | 115.7 −0.4j |
| 15  | 124  | 124.9 −0.5j | 125.0 −0.5j | 129.5 −1.5j | 130.1 −1.0j | 124.9 −0.5j |
| 31  | 256  | 131.2 −0.5j | 131.2 −0.5j | 129.9 −1.2j | 130.0 −0.9j | 131.1 −0.6j |
| 61  | 507  | 135.1 −0.6j | 135.2 −0.6j | 130.0 −1.2j | 130.0 −0.9j | 135.1 −0.6j |
| 85  | 705  | 136.2 −0.6j | 136.3 −0.6j | 130.0 −1.1j | 130.0 −0.9j | 136.2 −0.6j |
| 121 | 1001 | 137.4 −0.6j | 137.5 −0.6j | 130.0 −1.1j | 130.0 −0.9j | 137.4 −0.6j |
| 161 | 1330 | 138.2 −0.6j | 138.3 −0.6j | 130.0 −1.1j | 130.0 −0.9j | 138.2 −0.6j |
| 201 | 1662 | **138.8 −0.6j** | **138.8 −0.6j** | **130.0 −1.1j** | **130.0 −0.9j** | **138.7 −0.6j** |

Two facts jump out:

1. **PyNEC, Sinusoidal and nec2c agree bit-for-bit at every mesh** (ΔΓ ≤ 0.0003
   throughout). Two *independent* NEC-2 kernels (nec2++ inside PyNEC, and the C
   port nec2c) plus momwire's sinusoidal basis all trace the identical curve —
   so the climb is not a PyNEC bug; it is what the NEC-family delta-gap model
   *does* on this geometry.
2. **The NEC curve is still climbing at N=201** (+0.6 Ω over the last doubling)
   and has not turned back toward 130. On its own this looked like NEC
   converging slowly to a *different, higher* value than the B-splines.

## What actually distinguishes the quad — the feed

`delta_loop` and `diamond_loop` feed their driven edge as
`build_path([T, S], n_seg1, 1+0j)` with `n_seg1 = max(3, nominal_nsegs // 7)`
— the feed edge is **subdivided and scales with the mesh**, so the feed segment
length stays commensurate with its neighbours as N grows.

`quad.py` instead splits the driver bottom into `BL→C0`, a **fixed 1-segment
gap** `(C0, C1, 1, 1+0j)` of length `2·eps = 0.1 m`, and `C1→BR`. The flanking
wires use `segs_for(...)` and refine with N; the feed segment never does. At
N=201 the loop-side segments are ~0.05 m while the feed segment is still 0.1 m —
a 2× segment-length discontinuity sitting right on the source. NEC's delta-gap
(applied-field) driving-point impedance is well known to drift with the feed
segment length and with abrupt neighbouring segment-length changes; that drift
is the entire 115→139 climb.

## The decisive test — refine the feed, the anomaly vanishes

Rebuilding the quad with the driver bottom fed as one refined edge (segments
scale with the mesh, exactly like the two working loops) — **keeping the
parasitic reflector**, so 2-element coupling is unchanged:

| N | Sinusoidal | BSpline d=2 | nec2c |
|--:|--:|--:|--:|
| 7   | 130.6 +0.6j | 130.5 +0.5j | 130.6 +0.6j |
| 31  | 130.0 −0.6j | 130.1 −0.6j | 130.0 −0.6j |
| 61  | 130.0 −0.8j | 130.0 −0.9j | 129.9 −0.9j |
| 121 | 130.0 −0.9j | 130.0 −1.0j | 129.9 −1.0j |
| 201 | 129.9 −1.0j | 130.0 −1.0j | 129.9 −1.0j |

The NEC climb is **gone**: Sinusoidal and nec2c now agree with the B-splines at
~130 Ω from the coarsest mesh. That the reflector was retained isolates the
cause to the feed alone. **~130 Ω is the true driving-point R of this quad**;
NEC's 138.8-and-rising was the fixed-feed artifact, and the B-splines were
insensitive to it and correct all along.

## Does it generalise? The other loops + the yagi control

Full anchor sweeps (N 7…201, all four engines + nec2c) on the remaining designs:

| design | converged value (all 5 methods) | B-spline vs nec2c @ N=201 | Bs2 settles | NEC settles |
|---|--:|--:|--:|--:|
| `delta_loop` (triangle) | 110.5 +43.5j | ΔΓ 0.001 (rel 0.2%) | N≥7 | N≥15 |
| `diamond_loop` (square) | 220.9 +58.3j | ΔΓ 0.0002 (rel 0.1%) | N≥7 | N≥21 |
| `beams.yagi` (control) | 34.7 −35.8j | ΔΓ 0.0007 (rel 0.1%) | N≥21 | N≥21 |
| `quad` (**buggy feed**) | 130 (Bs) vs 138.8-rising (NEC) | ΔΓ 0.026 (rel 6.3%) | N≥7 | not settled |

`delta_loop`, `diamond_loop` and the yagi all converge to a **single** value on
every method — a single square loop (`diamond_loop`, 4 corners) converges
cleanly, so "4 corners of a square loop" is *not* the culprit. The B-splines do
reach the converged value at a somewhat coarser mesh (N≥7 vs N≥15–21) — a real
but modest ~2–3× rate edge — and on `delta_loop` NEC even *overshoots* to
111.2 Ω at N=45 before settling back to 110.5, more evidence that the NEC-family
mesh dependence near a fed loop edge is a numerical transient, not a march
toward a different answer.

## Consequences

- **The corpus rollup's B-spline "loop error" is largely a red herring for the
  quad specifically.** The `20m_quad.nec` corpus deck is an external deck with
  its own author-chosen mesh, so it isn't the same object, but the mechanism —
  a fed loop edge whose feed segment is coarse relative to its neighbours —
  applies to any loop deck with a short fixed feed gap.
- **Sinusoidal remains the most NEC-faithful momwire basis** (it *is* the NEC
  curve, artifact and all). The takeaway is not "prefer B-spline on loops" but
  "on loops, mesh the *feed edge* to refine with the rest of the structure."
- **No per-basis `nominal_nsegs` scaling.** The dramatic 6× quad advantage that
  motivated #408 part 3 was the bug; the honest advantage on well-meshed loops
  is ~2–3× and does not warrant basis-dependent mesh recommendations or a
  rework of the #382 cost model.

## Follow-ups

- **`quad.py` feed should refine with the mesh** (filed as a bug). The one-line
  shape of the fix: feed the driver bottom as a single `segs_for`-scaled edge
  (`(BL, BR, ns, 1+0j)`), matching `delta_loop`/`diamond_loop`. Impact at the
  default mesh (N=21) is ~1 Ω (128.9 → 130.1); the divergence only grows at the
  fine meshes the workbench convergence slider can reach, where today the quad
  reports a drifting, mesh-dependent impedance.
- The 2026-07-16 doc's convergence-sweep caveat ("converged value is each
  engine's own finest mesh, not an independent reference") is now retired for
  the quad: nec2c on the matched deck is that independent reference, and it
  agrees with the B-splines once the feed is meshed correctly.
