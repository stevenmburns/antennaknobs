# AK#1520: what drives bs2's near-end whole-wire vs split residual

Registered 2026-09-15, **before any solve**. Branch
`scratch/1520-near-end-residual`, off main cc87956; momwire at the pointer,
1ca8725 (0.55.0). Measure only, no PR.

A missed prediction is reported as a miss and is not re-registered.

## The question

In the split study's k3 case, bs2 on the whole wire (A) and on #1511's split
(B) differ by about 0.1 % of \|Z\|, beside the 50 Ω load at 0.04. The
difference does not shrink with n: 0.047 / 0.223 / 0.146 Ω at n = 41 / 81 /
161. What drives it?

- the guard's end piece;
- the junction next to the load's piece;
- the load;
- bs2 near a load at a wire end;
- or it is unexplained.

## A premise correction, from the split study's own records, before any solve

**At n = 41, 81 and 161 the guard did not fire at 0.04.**
- The guard needs b ≤ h. At b = 0.04 that is n ≤ 25.
- `partb_rows.jsonl`, copied from `scratch/1511-bs2-split-study`, shows what the
  split study built:
  - **n = 10 and 21:** the load's fed piece is [0, 0.08], running to the wire
    end.
  - **n = 41, 81 and 161:** the load sits on a middle piece
    [0.0267, 0.0533], of 1 / 3 / 5 segments, behind an end filler [0, 0.0267],
    of 1 / 2 / 4 segments.
- #1520's reading, that "the guard runs its fed piece to the end", holds only at
  n ≤ 25.

**Consequences for the runs.**
- "Guard disabled" (B′) builds exactly B at every n here, so it cannot make the
  residual vanish.
- The guard's end piece is tested instead by **Bg**, the guard forced so the
  0.04 piece runs to the wire end at every n.

**A lead from the same records, to be tested and not assumed.** The residual
tracks the cut ratio beside the 0.04 piece: 1.13 at n = 41, 1.50 at 81 and 1.25
at 161.
- It also tracks the load's segment length against the whole wire's segment:
  1.09 / 0.72 / 0.86.
- So two causes fit so far:
  - **the junction:** a bs2 artefact at a ratio step;
  - **the load's local discretisation:** physical, seen by any engine that
    meshes that geometry.
- The centre engines separate them (Q8).

## The setup

- **Geometry:** the k3 deck, a dipole from (0, −5.25, 10) to (0, 5.25, 10),
  radius 1 mm, 14.2 MHz, in free space.
- **Ports:** the feed at 0.31, a 50 Ω load at 0.77, and the end port at 0.04.
- **Ladder:** n = 41, 81, 161 and 321.
- **Harness:** `study_1520.py`, which uses `study.py`, copied from the split
  study at 4bcf7b2. Its `split_pieces(guard="rule")` is asserted equal to the
  split study's `split_b` at n = 10–321.

### Geometries

- **A:** the whole wire, each port at its exact arclength.
  - On bs2 it is meshed at the authored count exactly, with antennaknobs'
    positioned-port re-count and parity bump suppressed.
  - On sinusoidal and PyNEC it is antennaknobs main's own whole-wire placement.
    No count puts 0.04 on a segment centre, so they snap. The rows are labelled,
    with their offsets.
- **B:** the split rule as the split study built it.
- **Bp (B′):** the guard disabled.
- **Bg:** the guard forced. An end limit is b whenever b is within the port's
  other limits, so the 0.04 piece is [0, 0.08] at every n.

### Cases

The 0.31 feed and the 0.77 load are in every case.

- **base:** the 0.04 port carries its 50 Ω load (the split study's k3).
- **moved:** the end load at 0.10 instead.
- **noload:** no port at 0.04. A is the wire with two ports, and B keeps base's
  pieces with the 0.04 piece unnamed. This is the geometry alone.
- **short:** the 0.04 port carries a 0 Ω load.

### Engines

- **bs2:** every case, on A, B, Bp and Bg.
- **Sinusoidal and PyNEC:** base on A, B, Bp and Bg; noload on A and B.
- **NEC-2 (`nec2c`):** base and noload, on B.

## Facts from the mesh-only probe, before any solve (`mesh.jsonl`)

- **B and Bp are identical,** pieces and meshed segments, at n = 41, 81, 161 and
  321.
- **The cut ratios beside the 0.04 piece:**
  - **B:** 1.00 and 1.13 at n = 41; 1.50 and 1.42 at 81; 1.25 and 1.18 at 161;
    1.00 and 1.05 at 321.
  - **Bg,** after its [0, 0.08] piece: 1.15 / 1.09 / 1.02 / 1.02.
  - **moved B,** beside its [0.0667, 0.1333] piece: 1.00–1.12 at n = 41, then
    1.00–1.07, 1.00–1.02 and 1.00–1.03.
- **A** meshes exactly n on every engine.
- **noload B's segments** equal base B's.

## The measures

- **The residual:** r(case, G; n) = \|Z_bs2(case, G; n) − Z_bs2(case, A; n)\|.
- **The step:** step_A(n) = \|Z_bs2(base, A; n) − Z_bs2(base, A; next n)\|.
- **The load effect** on an engine and a geometry:
  L_e,G(n) = Z_e(base, G; n) − Z_e(noload, G; n).

## Predictions

| id | what | bar | prediction |
|---|---|---|---|
| **Q1** | The split study reproduces | bs2 base A and B at n = 41, 81 and 161 equal `partb_rows.jsonl`'s k3 rows to within 1e-9 relative | hit |
| **Q2** | The guard is not active at n ≥ 41 | Z of base Bp equals Z of base B to within 1e-12 relative, at every n | hit |
| **Q3** | The residual follows the cut ratio beside the load | r(base, B) is largest at n = 81, and r at n = 41 and at 321 are each ≤ 0.5 × r(base, B; 81) | hit |
| **Q4** | The guard's end piece carries no residual | r(base, Bg; n) ≤ 0.5 × r(base, B; 81) at n = 81, 161 and 321 | hit |
| **Q5** | Away from the end, the residual goes | r(moved, B; n) ≤ 0.5 × r(base, B; 81) at n = 81, 161 and 321 | hit |
| **Q6** | The geometry alone does not produce it | r(noload, B; n) ≤ 0.5 × r(base, B; n) at n = 81 and 161 | hit |
| **Q7** | A 0 Ω port behaves like no port | r(short, B; n) ≤ 0.5 × r(base, B; n) at n = 81 and 161 | hit |
| **Q8** | The centre engines see the load's effect as bs2 does on B | for PyNEC, sinusoidal and NEC-2 at n = 81 and 161: \|L_e,B − L_bs2,B\| < \|L_e,B − L_bs2,A\| | hit |
| **Q9** | No growth with refinement | r(base, B; 321) ≤ 0.5 × r(base, B; 81) | hit |

## The verdict rule, applied by `analyze_1520.py` as written

1. **"The guard's end piece"** if Q4 misses.
2. **Otherwise, "the load at the end"** if Q5 misses: the residual survives with
   the load 0.10 in.
3. **Otherwise, "the junction (mesh next to the piece), with or without the
   load"** if Q6 or Q7 misses: the geometry alone produces it.
4. **Otherwise, if Q3 hits:**
   - **"the load's local discretisation (every engine sees it)"** if Q8 hits;
   - **"the junction beside the load (bs2-specific)"** if Q8 misses.
5. **Otherwise, "unexplained".**

## Order

1. Commit this registration, with `study_1520.py`, `study.py`,
   `partb_rows.jsonl`, `mesh.jsonl` and `analyze_1520.py`, and push.
2. The solves (`rows.jsonl`), under `systemd-run` with MemoryMax=24G.
3. `analyze_1520.py` writes `README.md`, and the report follows.

## Amendment 1, registered after the analysis above and before any amendment solve

**Why.**
- **The registered rule does not fit.** Q4, Q5, Q6, Q7 and Q8 all miss. So the
  rule's first branch, "the guard's end piece", fires on a pattern it was not
  built for: every variant keeps the residual. That output stands as the
  registered one, and is not re-spelled.
- **Where the residual is not.** From the recorded tables:
  - It is the same with or without the 0.04 load: noload reads 0.043 / 0.218 /
    0.144 / 0.0026 Ω against base's 0.047 / 0.223 / 0.146 / 0.0027 Ω at n = 41 /
    81 / 161 / 321.
  - It is the same with a 0 Ω short, with the load at 0.10 (0.20 / 0.26 / 0.16 /
    0.007 Ω) and with the forced guard (0.10 / 0.22 / 0.14 / 0.007 Ω).
  - The 0.04 load's own effect agrees between A and B to 0.003–0.005 Ω.
- **When it vanishes.** It collapses at n = 321 in every variant.
  - On A, the feed at 0.31 sits at ξ = frac(0.31 · n) = 0.71 / 0.11 / 0.91 /
    0.51 within its segment at n = 41 / 81 / 161 / 321. B always feeds a segment
    centre.
  - Part D found that bs2's Z ripples with the feed's ξ. The ripple is largest
    near a knot, about 0.2 Ω peak-to-peak at N = 81 on this deck's k2, and its
    shape matches the residual's pattern here.

**Hypothesis H.** The residual is the whole wire's feed position within its
segment (Part D's ripple), and nothing at 0.04. This hypothesis came from the
data above. The runs below test it with bars set before they are solved.

**New geometries** (bs2 only, the base case, n = 41 / 81 / 161 / 321, at the
authored count):
- **AF:** only the feed is split. It takes its piece from the rule, with the
  feed at the middle, and both loads stay at their exact arclengths on the
  unsplit runs.
- **AL:** only the loads are split, with their pieces from the rule. The feed
  stays at its exact arclength on its run.

**Predictions:**

| id | what | bar | prediction |
|---|---|---|---|
| **E1** | splitting the feed alone reproduces B | \|Z_AF − Z_B\| ≤ 0.25 · r(base, B; n) at n = 81 and 161 | hit |
| **E2** | splitting the loads alone leaves A unchanged | \|Z_AL − Z_A\| ≤ 0.25 · r(base, B; n) at n = 81 and 161 | hit |
| **E3** | the feed split carries the residual | \|Z_AF − Z_A\| ≥ 0.75 · r(base, B; n) at n = 81 and 161 | hit |

**If E1–E3 all hit,** the cause is the feed's position within its segment on
the whole wire (Part D's ripple), which the split removes. The 0.04 end, the
guard and the load are not it. **Any other outcome** leaves the residual
unexplained by these candidates.

**Records:** `rows_e.jsonl`, from `study_1520.py --extra`.
