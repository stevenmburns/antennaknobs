# The bs2 split-equivalence study for positioned ports (#1511's split rule)

Registered 2026-09-15, **before any solve**. Branch
`scratch/1511-bs2-split-study`, off main 006d60e8e (which includes #1512). No
PR. Measure only.

A missed prediction is reported as a miss and is not re-registered.

## The questions

1. **Does splitting change the physics?** With ports partway along a wire,
   does momwire bs2 (BSplineSolver, degree 2, which feeds the exact arclength)
   give the same answer on the whole wire, ports at their exact positions, as on
   the split geometry the centre-engine rule builds (each port at the middle of
   its own fed piece)? If it does, splitting is physics-neutral: the centre
   engines' split answers and bs2's whole-wire answers compare like for like,
   and bs2 never needs to split.
2. **How big is the snapping error?** momwire's SinusoidalSolver snaps a
   positioned port to its grid on the whole wire and is exact on the split one.
3. **Part C, the knot family.** razor-2p (RazorSolver, `nec5_quadrature=True`)
   on the whole wire, where it snaps to a knot, against the break-at-every-port
   geometry NEC-5 gets on main; and razor-2p against NEC-5 on that geometry.

## The setup

- **Geometry:** a dipole from (0, −5.25, 10) to (0, 5.25, 10), 10.5 m, radius
  1 mm, 14.2 MHz.
- **Ground:** free space. The k = 2 case, and D5, also run over the finite
  ground at 13, 0.005 (Sommerfeld).
- **Cases:**
  - k = 1: feed at 1/3;
  - k = 2: feed at 0.31, with a 50 Ω series load at 0.77;
  - k = 3: feed at 0.31, with 50 Ω loads at 0.77 and 0.04.
- **Ladder:** authored n = 10, 21, 41, 81, 161.
- **Engines:** antennaknobs at 006d60e8e; momwire at the antennaknobs pointer,
  1ca8725 (0.55.0), with `make build` current and the avx2 accelerator
  importing; NEC-5 `nec5cl-x13-static`, sha256 7ebf343d.
- **Harness:** `study.py`. Every geometry is built by hand; #1511's code is not
  used.
- **The measured quantity:** the driving-point Z at the feed, with the loads in
  place.

### The geometries

- **A:** the whole wire, each port a `PortOnWire` at its exact arclength, as
  antennaknobs' momwire engine serves it.
- **A0 (control):** A with antennaknobs' positioned-port re-count (AK#1469)
  suppressed in the harness. The wire keeps its parity count at the authored n.
- **B:** #1511's split rule, as written in `study.split_b`.
  - Limits: g/4 per neighbouring port at gap g, and b/3 for an end port's wire
    end at distance b.
  - The guard: for an end limit b, OTHER is the smallest of that port's
    remaining limits (a neighbour's g/4, or for a lone port the other end's
    b′/3). If b ≤ h and b ≤ OTHER, the limit is b.
  - xᵢ is the smallest limit. The fed piece [uᵢ − xᵢ, uᵢ + xᵢ] takes the odd
    count nearest 2xᵢ/h (at least 1). Fillers take max(1, round(len/h)), and a
    zero-length filler is omitted.
  - Each port is a `PortOnWire` at the middle of its own fed piece.
- **C:** break at every port. The pieces are cut at each uᵢ, with
  max(1, round(len/h)) segments each. Each port is a `PortAtVertex` at the p1
  end of the piece before its cut (#1512's knot rule, generalised to k ports).
- **Ce:** C with every vertex-fed piece authored at an even count (+1 when odd),
  so that razor and NEC-5 mesh identical geometry.
- **D5:** the plain centre-fed wire, no loads. It gives razor-2p against NEC-5
  on one even mesh, their usual centre-fed difference.

### The runs

| engine | geometries |
|---|---|
| momwire bs2 | A, A0, B |
| momwire sinusoidal | A, A0, B |
| momwire razor-2p | A, A0, C, Ce, D5 |
| NEC-5 | C, Ce, D5 |

## Facts from the mesh-only probe, before any solve (`mesh.jsonl`)

**A re-counts the wire on some rungs (AK#1469); A0 does not.** Meshed segments:
- **k = 2:**
  - bs2 and sinusoidal read 50 / 150 / 250 at n = 41 / 81 / 161, against 41 / 81
    / 161 on A0;
  - razor reads 100 / 200 at n = 81 / 161, against 82 / 162.
- **k = 3:** razor reads 100 / 200 at n = 81 / 161. bs2 and sinusoidal never
  re-count, because 0.04 = 1/25 is no segment centre at any count.
- **k = 1:** razor reads 12 / 21 / 81 at n = 10 / 21 / 81, multiples of 3 for
  1/3, against 10 / 22 / 82.

So A's refinement ladder does not step evenly for k = 2, and A0 is the
equal-density control.

**razor and NEC-5 do not mesh C alike.**
- momwire's engine bumps a named vertex-fed piece with an odd count to even for
  razor; NEC-5 exempts a vertex-only wire. For example, k = 1 at n = 10 is
  4 + 7 on razor and 3 + 7 on NEC-5.
- On Ce the two engines' counts are identical at every rung. So razor against
  NEC-5 is judged on Ce, and C is reported.

**B's segment-length ratio at a cut** ranges from 1.00 to 2.00. The 2.00 is
k = 2 at n = 10.

## The measures

- **The refinement step on a geometry G:** step_G(n) = |Z_G(n) − Z_G(next n)|.
  It is defined for n = 10, 21, 41, 81.
- **The split difference:** d(G₁, G₂; n) = |Z_G₁(n) − Z_G₂(n)|, on one engine.
- **The reference:** bs2's Z_A at n = 161, "bs2∞".
- **razor against NEC-5:** r(G; n) = |Z_razor,G(n) − Z_NEC-5,G(n)| /
  |Z_NEC-5,G(n)|. D5(n) is that ratio on the D5 deck.

## Predictions

"The cases" are k1, k2, k3 and k2 over somm13.

| id | what | bar | prediction |
|---|---|---|---|
| **P1** | bs2: splitting against the served whole wire | d(B, A; n) ≤ step_A(n) at n = 21, 41, 81, for every case | hit |
| **P1c** | bs2: splitting against the equal-density whole wire | d(B, A0; n) ≤ step_A0(n) at n = 21, 41, 81, for every case | hit |
| **P2** | bs2's A, A0 and B converge to one limit | d(B, A; 161) ≤ max(step_A(81), step_B(81)) and d(B, A0; 161) ≤ max(step_A0(81), step_B(81)), with d(B, A0; n) falling from n = 41 to 161, for every case | hit |
| **P3** | sinusoidal: snapping costs more than splitting | where sinusoidal's A reports a non-zero snap offset: \|Z_sin,A(n) − bs2∞\| > \|Z_sin,B(n) − bs2∞\| | hit |
| **P3c** | the same on A0, where every port snaps | \|Z_sin,A0(n) − bs2∞\| > \|Z_sin,B(n) − bs2∞\| wherever A0's offset is non-zero | hit |
| **P4** | razor-2p on Ce agrees with NEC-5 on Ce as well as it does centre-fed | r(Ce; n) ≤ 2·D5(n) + 0.001 at every n and case, with D5 over the case's own ground | hit |
| **P4c** | the razor bump on C is a mesh mismatch | where razor's and NEC-5's C counts differ, r(C; n) > 2·D5(n) + 0.001 | hit |
| **P5** | razor: snapping costs more than razor-vs-NEC-5 | where razor's A reports a non-zero snap offset: \|Z_razor,A(n) − Z_razor,Ce(n)\| > \|Z_razor,Ce(n) − Z_NEC-5,Ce(n)\| | hit |
| **P5c** | the same on A0 | \|Z_razor,A0(n) − Z_razor,Ce(n)\| > \|Z_razor,Ce(n) − Z_NEC-5,Ce(n)\| wherever A0's offset is non-zero | hit |
| **P6** | bs2: the re-count itself is benign (k2 and k2 over somm13, the only bs2 re-counts) | \|Z_A(n) − Z_A0(n)\| ≤ step_A0(n) at n = 41, 81 | hit |

The offsets come from antennaknobs' FeedPlacement notes: "… N mm away". A snap
offset "non-zero" means a note was issued.

## The report

- **Per case, per n:** bs2 Z_A, Z_A0 and Z_B; d(B, A), d(B, A0), step_A and
  step_A0; sinusoidal Z_A (with offset), Z_A0 (with offset) and Z_B; razor Z_A,
  Z_A0, Z_C and Z_Ce (with offsets); NEC-5 Z_C and Z_Ce; D5; B's junction
  ratios.
- **Each P** with a hit or a miss.
- **A one-line verdict** on whether bs2 and the split agree.

## Order

1. Commit this registration with `study.py` and `mesh.jsonl`, and push.
2. The solves (`rows.jsonl`), under `systemd-run` with MemoryMax=24G.
3. `README.md` with the tables and the P results.

## Results, 2026-09-15

**Records:**
- `rows.jsonl`: 260 rows, all ok;
- `README.md` and `analysis.json`: the output of `analyze.py`, which was itself
  committed before any result was read (163362c).

**Setup:** momwire 1ca8725 (0.55.0) and NEC-5 7ebf343d. The README's header
prints "momwire ?" because momwire has no `__version__`.

| id | verdict | where it failed |
|---|---|---|
| **P1** | **MISS** (3 of 12) | n = 81 for k2, k3 and k2 over somm13: \|Z_B − Z_A\| 0.122 / 0.223 / 0.086 Ω against steps 0.073 / 0.190 / 0.051 Ω |
| **P1c** | **MISS** (7 of 12) | k2 and k2 over somm13 at n = 21, 41 and 81, and k3 at n = 81 |
| **P2** | **MISS** (2 of 4) | k3: d(B, A0) grows from 0.047 at n = 41 to 0.146 at 161. k2 over somm13: d(B, A0; 161) = 0.136 against a bar of 0.133 |
| **P3** | hit (14) | — |
| **P3c** | hit (20) | — |
| **P4** | hit (20) | — |
| **P4c** | **MISS** (7 of 16) | where razor's bump no longer shows at finer meshes |
| **P5** | hit (9) | — |
| **P5c** | hit (18) | — |
| **P6** | **MISS** (4 of 4) | antennaknobs' re-count moves bs2's k2 by 0.20–0.30 Ω, more than A0's own step |

### Reading, after the analysis (not registered)

**bs2 and the split agree at the level of bs2's own mesh noise on this deck.**
- **The split difference.** \|Z_B − Z_A\| is at most 0.143 % of \|Z\| at
  n ≥ 41 (0.017–0.223 Ω), and 0.3–0.44 % at n = 10 and 21.
- **bs2's own ladder is still moving.** Across the rungs, \|Z_A(21) − Z_A(161)\|
  is 0.50–0.82 Ω, and single steps run 0.05–0.54 Ω, unevenly. So a bar of "no
  more than the step" is a bar at the noise, and it missed wherever a step
  happened to be small.
- **One residual does not shrink.** k3, the only case with a load near the wire
  end (0.04, where the guard fires at n = 10 and 21), reads 0.03 % at n = 41,
  0.14 % at 81 and 0.09 % at 161. The cut ratios next to that load are 1.50 and
  1.42 at n = 81.
- **P1c and P6 miss for the same reason.** On k2, antennaknobs' re-count meshes A
  at 50 / 150 / 250 against A0's 41 / 81 / 161. B, at A0's density, lands nearer
  A than A0.

**Sinusoidal: snapping costs far more than splitting.**
- On A0, where every port snaps by 4–250 mm, Z sits 0.36–2.4 Ω from bs2∞ at
  n = 161, and up to 10 Ω at n = 21.
- The split B converges steadily to bs2∞: from 2.2–2.7 Ω at n = 10 to 0.11–0.18 Ω
  at 161.

**razor-2p and NEC-5.**
- **On Ce they agree to 0.034–0.048 %,** the same as their centre-fed agreement
  on D5 (0.044–0.051 %).
- **The count bump on C.**
  - Its effect is 3.4–4.6 % at n = 10 and 0.45–0.98 % at n = 21.
  - By n = 41 it is 0.04–0.22 %, inside the 2·D5 bar in several instances. That
    is P4c's miss.
- **razor's snapping** (A0 against Ce) costs 0.43–13.8 Ω, always more than razor
  against NEC-5 on Ce.
- **Both knot engines are still 1.4–1.8 Ω from bs2∞ at n = 161.** The knot path
  converges at first order.

**Verdict.**
- **bs2.** The whole wire and #1511's split agree to within 0.15 % of \|Z\| at
  n ≥ 41, which is bs2's own refinement scale on this deck. The registered
  test, a difference no larger than the step at every n ≥ 21, missed in 3 of 12
  instances, and k3 keeps a residual of about 0.1 % that has not shrunk by
  n = 161.
- **The snapping solvers.** Splitting (sinusoidal) and breaking at the port
  (razor-2p) remove a snapping error 2–10× larger. On the break geometry with
  matched counts, razor-2p equals NEC-5 as closely as it does centre-fed.

## Part D: bs2's continuous feed against the old placement, at fixed density (#1519)

Registered 2026-09-15, **before any Part D solve**. Measure only.

**Setup.**
- Same branch; antennaknobs 006d60e8e, momwire 1ca8725.
- The engine is bs2 only.
- The harness is `study_d.py`, and the analysis is `analyze_d.py`, committed with
  this registration.

**Why.** P6 found a difference of 0.20–0.30 Ω between A and A0, and it mixed two
effects: the re-count's denser mesh (41 → 50, 81 → 150) and where the feed sits
within its segment. #1519 stops re-counting bs2's wires, so a positioned port
will sit anywhere inside a segment. Part D holds density fixed and varies only
the feed's position within its segment.

### The paths

- **cont:** #1519's continuous feed. The mesh is exactly the authored count, with
  both antennaknobs' positioned-port re-count and its odd-parity bump
  suppressed, and each port at its exact arclength.
  - Part C's A0 suppressed only the re-count, so an even authored count still
    became odd there. #1519's no-re-mesh gate asks that a positioned-port wire
    keep its authored count, so this path suppresses both.
- **old:** antennaknobs' placement as it stands (the parity bump and the
  re-count), i.e. A.

### The runs

- **D1:** the feed at 0.5, on cont.
  - Even n = 20, 40, 80, 160 put the feed on a knot.
  - Odd n = 21, 41, 81, 161, 321 put it at a segment centre.
- **D2:** k1, the feed at 0.31 with no loads. For base N = 41, 81 and 161:
  - n = N − 5 … N + 5 on both paths;
  - cont at 2N − 1, for the refinement step at N.
- **D3:** D2 for k2 (with the load at 0.77) and for k3 (with loads at 0.77 and
  0.04).
- **D4:** D2 for k2 over finite ground 13 / 0.005, at base N = 81 only.

ξ = frac(u·m) is each port's fractional position within its segment, where m is
the engine's actual count.

### Facts from the mesh-only probe, before any Part D solve (`mesh_d.jsonl`)

- **233 rows, all ok.**
- **cont's count equals the authored n in every row,** even n included.
- **The feed's ξ covers 0.02–0.98,** eleven values per base N.
- **old re-counts k1 and k2** to 50 / 150 / 250 segments at N = 41 / 81 / 161,
  more than 5 % from n. So old is density-matched only on k3: no count puts
  0.04 on a segment centre, so old keeps the parity count, n or n + 1, within
  2.8 %.

### Measures

- **D1:**
  - D1(m) = \|Z_cont(2m) − Z_cont(2m + 1)\|;
  - step_odd(m) = \|Z_cont(2m + 1) − Z_cont(4m + 1)\|.
- **The density trend per base N:** a least-squares fit Z = a + b/n² over the 11
  counts, real and imaginary parts separately.
  - The residual is Z − trend.
  - ptp is the largest pairwise \|resᵢ − resⱼ\|.
- **The refinement step at N:** step(N) = \|Z_cont(N) − Z_cont(2N − 1)\|.

### Predictions

| id | what | bar | prediction |
|---|---|---|---|
| **PD1** | a centre feed on a knot (even) against a segment centre (odd), at matched density | D1(m) ≤ step_odd(m) for m = 20, 40 and 80 | hit |
| **PD2** | the continuous feed is insensitive to its place in the segment | ptp ≤ 0.25 · step(N) **and** ptp ≤ 0.05 % of \|Z_cont(N)\|, for k1, k2 and k3 in free space at N = 41, 81 and 161 | hit |
| **PD3** | the old placement against the new, where density matches | wherever old's count is within ±5 % of n: \|Z_old(n) − Z_cont(n)\| ≤ step(N) | hit (k3 is the only case with instances) |
| **PD4** | finite ground behaves like free space | k2 over somm13 at N = 81 meets both of PD2's bars | hit |
| **PD5** | the placement sensitivity shrinks with refinement | ptp(N = 161) < ptp(N = 41), for k1, k2 and k3 in free space | hit |

- **Reported and not gated:** D1 at m = 10, and each row's residual against every
  port's ξ.
- **Where a PD misses,** the report names the row with the largest \|residual\|
  and its ports' ξ.
- **Changing a bar** after the data is seen is an amendment, and never a re-spell.

## Part D results, 2026-09-15

**Records:**
- `rows_d.jsonl`: 233 rows, all ok;
- `README_D.md` and `analysis_d.json`: the output of `analyze_d.py`, which was
  committed with the registration (4e18e38) before any Part D solve;
- `explore_d.py` and `explore_d.json`: the exploratory attribution below.

| id | verdict | where it failed |
|---|---|---|
| **PD1** | hit (3) | the feed on a knot against a segment centre at matched density: 0.140 / 0.082 / 0.049 Ω at m = 20 / 40 / 80, against steps 0.148 / 0.107 / 0.081 Ω |
| **PD2** | **MISS** (9 of 9) | peak-to-peak 0.286 / 0.168 / 0.106 Ω for k1, 0.439 / 0.254 / 0.161 Ω for k2, and 0.447 / 0.259 / 0.164 Ω for k3, at N = 41 / 81 / 161. The bars are 0.04–0.05 Ω (0.25 × step) and 0.063–0.078 Ω (0.05 % of \|Z\|) |
| **PD3** | **MISS** (6 of 33, all on k3) | even n = 36, 42, 44, 76, 84, 86: \|old − cont\| of 0.20–0.36 Ω against steps of 0.17–0.19 Ω |
| **PD4** | **MISS** | k2 over somm13 at N = 81: peak-to-peak 0.231 Ω against bars of 0.033 and 0.074 Ω |
| **PD5** | hit (3) | — |

### Reading, after the analysis (not registered; `explore_d.py`)

**The feed's own position within its segment drives the misses. The loads' do
not.**
- **The fit.** In every sweep, a fit of the residual on (1, cos 2πξ, sin 2πξ) of
  the feed's ξ explains 99–100 % of it. The loads' ξ explain 0–7 %.
- **The shape.** Z sits below the density trend with the feed near a knot
  (ξ ≈ 0) and above it with the feed near a segment centre (ξ ≈ 0.5). The
  residual is smallest near ξ ≈ 0.25 and 0.75.
- **The size.** The ripple's peak-to-peak is 0.08–0.28 % of \|Z\|, and
  0.7–2.7× bs2's own refinement step at that N.
- **How it shrinks.** For k1 it goes 0.29 → 0.17 → 0.11 Ω from N = 41 to 161,
  about N^−0.7. The refinement step itself shrinks more slowly, 0.21 → 0.17 →
  0.15 Ω.

**D1 is the same effect at its two extremes.** A centre feed moved from a
segment centre (odd n) to a knot (even n) at matched density costs 0.16 % of
\|Z\| at m = 20 and 0.06 % at m = 80, which is the ripple's size.

**PD3's k3 misses are that ripple as well.** On even n, old's parity bump adds a
segment and moves the feed's ξ, so \|old − cont\| mixes a one-segment density
change with a large ξ shift.

**Finite ground (PD4) behaves like free space.** The pattern is identical (99 %
explained by the feed's ξ), at 0.16 % of \|Z\| at N = 81.

**Verdict.**
- **Not insensitive at the registered level.** bs2's continuous feed carries a
  periodic ripple in the feed's position within its segment, peak-to-peak 0.08–
  0.28 % of \|Z\| (0.7–2.7× bs2's own refinement step), and it shrinks with
  refinement.
- **What that means for #1519.** Moving a feed off a segment centre can move Z by
  up to that peak-to-peak. The positioned feed is therefore only as
  placement-stable as bs2's mesh is converged.
