# Re-mesh-first against split-always for positioned ports on PyNEC

Registered 2026-09-15, **before any solve**. Branch
`scratch/remesh-vs-split-pynec`, off main 6e63a76. Measure only, no PR, and not
a release blocker.

A missed prediction is reported as a miss and is not re-registered.

## The question

With ports placed partway along a wire, PyNEC can place them two ways. Which
gives the smoother, better-converged Z as the authored count varies?

- **R, re-mesh first** (antennaknobs main's rule). Re-mesh the whole wire within
  2× when a count puts every port on a segment centre; otherwise split.
- **S, split always.** #1511's centre rule, even when a count would fit.

## The setup

- **Geometry:** the split study's 10.5 m dipole, radius 1 mm, 14.2 MHz.
- **Ground:** free space. k2 also runs over finite ground 13 / 0.005 at N = 81.
- **Engine:** antennaknobs main at 6e63a76, `PyNECEngine`. That includes #1512.
  #1511 has not landed, so on main a wire carrying several ports with no fitting
  count keeps its parity count and snaps each port to the nearest centre.
- **Harness:** `pynec_study.py`. It uses `study.py`, copied from
  `scratch/1511-bs2-split-study` at 4bcf7b2, for the builders and
  `study.split_b`.
- **The paths:**
  - **R:** the whole wire, each port a `PortOnWire` at its position, as main's
    engine serves it.
  - **S:** `study.split_b`, each port at the middle of its own fed piece.
- **Cases:**
  - k1: the feed at 0.31;
  - k2: k1 plus a 50 Ω load at 0.77;
  - k3: k2 plus a 50 Ω load at 0.04.

### The sweeps

- **Windows:** k1, k2 and k3 at N = 41, 81 and 161, over n = N − 5 … N + 5.
  Also k2 over somm13 at N = 81.
- **Transitions (added here):** k1 and k2 over n = 45–55 and 70–80. These are
  where R's re-mesh rule changes, and a window of N ± 5 does not reach them.
- **Steps:** n = 2N − 1 for each base N, on both paths.

## Facts from the mesh-only probe, before any solve (`mesh.jsonl`)

288 rows, no errors.

**R on k1 and k2 re-meshes every window count to one deck.**
- The deck is 50 / 150 / 250 segments at N = 41 / 81 / 161, 9–97 % denser than
  the authored count.
- So within a window, R's Z is constant by construction.

**R's transitions.**
- **k1** goes from the 50-segment whole wire at n = 50 to a two-piece split (52
  segments) at 51. At 74 → 75 it goes from a split (75 segments) to the
  150-segment whole wire.
- **k2** carries two ports. At 50 → 51 it goes from 50 exact to 51 segments with
  both ports snapped, and at 74 → 75 from snapped to 150 exact.

**R on k3** never re-meshes, because 0.04 is no segment centre at any count. It
carries three ports on one wire, so it keeps its parity count and snaps every
port: 35.9, 53.8 and 17.9 mm at n = 41.

**S's total count moves non-monotonically with n,** by 1–3 segments, because
each fed piece rounds to an odd count.

## The measures

- **step_S(N)** = \|Z_S(N) − Z_S(2N − 1)\|. step_R is reported. The transition
  sweeps use step_S(41) for n = 45–55 and step_S(81) for n = 70–80.
- **The jump:** the largest \|Z(n + 1) − Z(n)\| over consecutive counts in a
  sweep, per path.
- **The trend ptp:** the peak-to-peak of the residual after a least-squares fit
  of Z = a + b/n² over the sweep, per path.
- **\|R − S\|:** where R places every port exactly (no snap note), and separately
  where R snapped.

## Predictions

| id | what | bar | prediction |
|---|---|---|---|
| **PS1** | S is smooth | S's jump ≤ step_S(N) in every sweep (windows and transitions) | hit |
| **PS2** | R jumps at its own transitions | R's jump > step_S(N) in every transition sweep (k1 and k2) | hit |
| **PS3** | R and S agree where R is exact | max \|R − S\| ≤ step_S(N) in every sweep that has an exact R row | hit |
| **PS4** | S's residual after the density trend is small | S's trend ptp ≤ 0.25 · step_S(N) in every window | hit |
| **PS5** | R's snapping on k3 costs more than the step | max \|R − S\| where R snapped > step_S(N) on k3 at N = 41 and 81 | hit |

### The decision rule

`analyze.py` applies it as written:

- **Split-always**, if S's jump ≤ step_S in every sweep **and** R's jump > step_S
  in at least one sweep.
- **Keep re-mesh-first**, if R's jump ≤ step_S in every sweep **and** PS3 hits.
- **Otherwise, no clear preference**, reported with the data.

## Order

1. Commit this registration with `pynec_study.py`, `study.py`, `analyze.py` and
   `mesh.jsonl`, and push.
2. The solves (`rows.jsonl`), under `systemd-run` with MemoryMax=24G.
3. `analyze.py` writes `README.md` with the tables, and the report follows.

## Results, 2026-09-15

**Records:**
- `rows.jsonl`: 288 rows, all ok;
- `README.md` and `analysis.json`: the output of `analyze.py`, which was committed
  with the registration (49ff792) before any solve.

| id | verdict | where it failed |
|---|---|---|
| **PS1** | hit (14) | — |
| **PS2** | **MISS** (1 of 4) | k1 at n = 45–55: R's re-mesh-to-split switch at 50 → 51 moves Z by only 0.020 Ω, against step_S 0.366 Ω |
| **PS3** | **MISS** (4 of 11) | k1 and k2 at N = 81, windows and transitions: \|R − S\| of 0.20–0.25 Ω against step_S of 0.19–0.23 Ω |
| **PS4** | **MISS** (5 of 10) | S's trend ptp is 0.058–0.23 Ω against 0.25 · step_S (0.034–0.09 Ω): k1, k2 and k3 at N = 41, k2 at N = 81, and k2 over somm13 |
| **PS5** | hit (2) | — |

**The decision rule: split-always.** S's largest jump is 0.72 × step_S; R's is
38.5 × step_S.

### Reading, after the analysis (not registered)

**Where R jumps, and why.**
- **The largest jumps come from snapping,** which is not the re-mesh itself.
  - Main has no multi-port split (#1511 has not landed), so a wire carrying
    several ports with no fitting count keeps its parity count and snaps them.
  - On k3 at every count, and on k2 between n = 51 and 74, R jumps 3.3–12.8 Ω
    between consecutive counts. It sits 2.4–9.2 Ω from S.
  - #1511 would replace those snaps with splits.
- **The re-mesh has a cost of its own, measured where no snap is involved.**
  - **k1 at n = 74 → 75.** R switches from a 75-segment split to the 150-segment
    whole wire, a 0.248 Ω jump (1.1 × step_S). S never moves more than 0.036 Ω in
    that sweep.
  - **Inside the windows.** R's Z is constant, because it is one re-meshed deck,
    but that deck is 1.1–2× denser than the authored count. Where R is exact,
    \|R − S\| is 0.09–0.25 Ω, and it exceeds the step at N = 81 (150 segments
    against about 80).
  - **The other re-mesh switch** (k1 at 50 → 51) happens to cost only 0.020 Ω.
- **S is smooth at every count.**
  - Its largest jump is 0.01–0.24 Ω (at most 0.72 × step_S).
  - Its residual after the density trend (PS4's miss) is below the step
    everywhere. It comes from the ±1–3 segment wobble of each fed piece's odd
    rounding.

**Recommendation: split-always.** It holds on the registered rule. It still
holds on the evidence that does not depend on #1511: re-mesh-first makes Z
depend on whether a segment count happens to fit, which in this deck means a
jump of about one refinement step at the 74 → 75 switch. The split's worst
wobble stays under three-quarters of a step.
