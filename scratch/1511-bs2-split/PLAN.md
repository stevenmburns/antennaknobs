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
