# AK#1523 surface option: #1532's coated-wire pair near ground

Registered 2026-09-15, **before any solve** (only a mesh-only probe has run).
Branch `scratch/1523-surface-option`, off AK main 97ca2b6b0. Measurement only:
no PR, and no issue or PR comments.

A missed prediction is reported as a miss and is not re-registered.

## Context

- **What #1532 changed.** It is merged at 97ca2b6b0 and unreleased. Every NEC
  writer now gives a jacketed wire momwire's pair, spelled in one place,
  `engines/_nec_wire.py::nec_wire_material`:
  - the GW radius a′ = a·(b/a)^((εr−1)/εr);
  - `LD 2` = L′ at the conductor radius;
  - `LD 5` conductivity scaled to σ·(a/a′)².
- **What is already checked.** Free space and the default ground on the three
  elevated PVC catalog designs: razor-2p against NEC-5 is 0.06–0.13 % with the
  pair, and 10.7–14.4 % with inductance only.
- **What is not checked,** and is caveat 4 of `scratch/1523-insulated-wire/VERDICT.md`:
  a jacketed wire near or on ground.
- **The catalog's one such deck** is `verticals.buried_radial_vertical:surface`
  (momwire#865):
  - four radials, 0.6 × the radiator's length, lying at z = h;
  - by default h = b, the jacket's outer radius;
  - copper conductors under PVC, with a bare radiator and a 5 cm feed gap;
  - 7.1 MHz.

## Mode and inputs (dev mode)

- **antennaknobs:** main 97ca2b6b0 for every arm except the pre-#1532 control,
  which runs from a detached worktree at e7317cb19 against the same momwire.
- **momwire origin/main** 227491d, built with `make build` and its accelerators
  import-checked.
- **The submodule pointer is never moved or staged.** It stays at 1ca8725 in the
  tree; dev mode supplies momwire through `PYTHONPATH`.
- **Why a separate worktree** (`momwire-wt-1064-main`) rather than the AK root
  checkout's submodule working tree: the root `.venv` installs momwire editable
  from that submodule for the live appserver, so switching it would change what
  the appserver serves. This is the same momwire commit and the same build rule.
- **NEC-5:** `nec5cl-x13-static`, sha256 7ebf343d.
- **Every run** executes under `systemd-run --user -p MemoryMax=24G` with
  `ulimit -v` set to 25 GiB (the box has 32 GB).
- **The records carry both AK SHAs and the momwire SHA,** and the harness
  refuses to run on any other tree.

## The decks

- **surface**, the catalog design:
  - `resolve_variant_params(Builder, "surface")`, overriding `wire_type` and
    `nominal_nsegs` (the framework's auto-mesh density, 21 per quarter-wave by
    default), and `surface_h_m` in Q2;
  - the default ground `("finite", 13, 0.005)`, the design's declared nominal
    soil and its test's ground. Both engines solve it as Sommerfeld; MomwireEngine
    also gets `ground_z=0`.
- **severns**, an AK spelling of the Severns surface deck that momwire's
  `equivalent_radius` docstring cites (momwire#865):
  - N = 16 radials, 33 ft long, at h = 1.6 mm;
  - a = 0.51 mm, b = 0.9 mm, εr = 3, a perfect conductor;
  - a 33.5 ft mast in three wires (a 5 cm feed gap fed at its centre, 2
    segments; then 0.45 m, 2 segments; then the rest, 19 segments);
  - radials at 10 segments each;
  - 7.2 MHz, soil `("finite", 30, 0.020)`.
  - **How it differs from momwire's `BSplineSolver` deck:** the feed is at the
    gap's centre rather than at the knot 5 cm up, and the gap has 2 segments
    instead of 3.
  - **The references:** Severns Table 1 measured 56.1 + 6.2j; momwire's
    docstring gives a′ + L = 49.38 + 14.93j on its own spelling.

## Arms

| arm | engine | treatment |
|---|---|---|
| `nec5` | NEC5Engine at 97ca2b6b0 | the pair (#1532) |
| `nec5_lonly` | NEC5Engine at 97ca2b6b0, with `antennaknobs.engines.nec5.nec_wire_material` monkeypatched to `functools.partial(nec_wire_material, pair=False)` | inductance only |
| `nec5_pre` | NEC5Engine at e7317cb19 | inductance only, as shipped before #1532 |
| `razor` | MomwireEngine, RazorSolver with `nec5_quadrature=True` | the pair (momwire as it is) |
| `bs2` | MomwireEngine, BSplineSolver | the pair |
| `razor_lonly`, `bs2_lonly` | the same, with `momwire._wire_loading.equivalent_radius` returning a | inductance only (context, Q1 only) |

## Cells

| cell | deck | wire | h | nominal_nsegs | arms |
|---|---|---|---|---:|---|
| q1-18-awg-pvc, q1-22-awg-pvc, q1-28-awg-pvc | surface | each PVC wire | b | 21 | all seven |
| m0-18 (the ×2 cell for Q0) | surface | 18-awg-pvc | b | 42 | nec5, razor, bs2 |
| m1-28 (the ×2 cell for Q1) | surface | 28-awg-pvc | b | 42 | nec5, nec5_lonly, razor, bs2 |
| q2-2b, q2-5b, q2-20a | surface | 18-awg-pvc | 2b, 5b, 20a | 21 | nec5, nec5_lonly, nec5_pre, razor, bs2 |
| m2-20a (the ×2 cell for Q2) | surface | 18-awg-pvc | 20a | 42 | nec5, razor, bs2 |
| severns | severns | a 0.51, b 0.9, εr 3 | 1.6 mm | explicit | nec5, nec5_lonly, nec5_pre, razor, bs2 |

**h = b in Q2 is the q1-18-awg-pvc cell.** On 18-awg-pvc (a 0.512 mm,
a′ 0.855 mm, b 1.05 mm):

| h | h/a | h/a′ |
|---|---:|---:|
| b | 2.05 | 1.23 |
| 2b | 4.10 | 2.46 |
| 5b | 10.25 | 6.14 |
| 20a | 20.0 | 11.97 |

NEC-5 arms run first across every cell, so a NEC-5 refusal is seen before any
momwire solve.

## Recorded per row

- **For every row:**
  - the status;
  - a refusal's exception type and full sentence, verbatim;
  - Z;
  - the meshed segment count;
  - every Python warning.
- **NEC-5 rows:** the deck's GW, LD, GE and GN cards, and the printout's
  WARNING and ERROR lines.
- **momwire rows:**
  - the kernel and conductor radii of the solver the engine actually made;
  - the engine's recorded advisories.

## Checks (a failure is a stop and a report)

| id | what | bar |
|---|---|---|
| **K0** | the treatment reached the solve | NEC-5 decks carry the radial GW radius a′ on `nec5` and a on `nec5_lonly` and `nec5_pre`. Each radial has an `LD 5` of σ·(a/a′)² on `nec5` and σ otherwise (none on the PEC Severns deck), and an `LD 2` of L′ on every jacketed arm. The mast and gap carry no LD cards. Deck values are compared at their printed resolution. momwire's kernel radii are a′ (pair) or a (L-only) on the radials and the mast radius elsewhere, to 1e-12 |
| **K1** | the monkeypatch is the pre-#1532 engine | wherever both ran, \|Z_nec5_lonly − Z_nec5_pre\| ≤ 5e-3 Ω |

## Predictions

**Q0: is the surface option served?**

| id | what | bar | prediction |
|---|---|---|---|
| **A0** | NEC-5 serves it | every NEC-5 row, on every cell and arm, is status ok with finite Z and 0 < R < 2000 Ω | hit |
| **A1** | momwire serves it, with its advisory | every momwire row is status ok, with no coated-wire refusal. Every cell with h/a < 20 (the 20a cells excepted, as boundary) has a `SurfaceRadialHeight` advisory on at least one of its momwire rows | hit |

The advisory is claimed per cell, not per row, because a repeat solve of the
same deck can emit nothing (momwire#927) and razor-2p may not emit it at all.
Which solver emitted it is recorded but not graded.

**Q1: does the pair close razor-2p against NEC-5 near ground?** Defined on the
q1 cells at nominal_nsegs 21:

- gap_t = \|Z_nec5,t − Z_razor\| / \|Z_razor\|, with t = pair (`nec5`) or
  L-only (`nec5_lonly`), razor-2p carrying the pair;
- shift_e = \|Z_e,pair − Z_e,Lonly\| / \|Z_e,Lonly\|.

| id | what | bar | prediction |
|---|---|---|---|
| **B1** | the pair moves NEC-5 far more near ground than on a free-space dipole | shift_nec5 ≥ 5 % on every PVC wire | hit |
| **B1o** | and more on thinner wire | shift_nec5 ordered 28 > 22 > 18 | hit |
| **B2a** | the pair still narrows the gap | gap_pair < gap_Lonly on every wire | hit |
| **B2b** | but does not close it the way it does in free space | gap_pair > 0.3 % on every wire | hit |
| **B3** | both engines respond alike to the radius half | \|Z_nec5 − Z_nec5_lonly\| / \|Z_razor − Z_razor_lonly\| ∈ [0.75, 1.25] on every wire | hit |

**Q2: stand-off sensitivity** (18-awg-pvc at h = b, 2b, 5b, 20a; nominal_nsegs
21).

| id | what | bar | prediction |
|---|---|---|---|
| **C1** | the engines come together with height | gap_pair(20a) < gap_pair(b), and gap_pair(20a) ≤ 1 % | hit |
| **C2** | the mechanism hypothesis (low confidence): the separation is NEC-5's reduced-kernel image distance | gap_pair(5b) ≤ gap_pair(b) / 5 | hit |
| **C3** | the class's own sensitivity | from b to 2b, \|ΔZ\| ≥ 5 Ω and ΔX < 0, on each of bs2, razor-2p and `nec5` | hit |
| **C4** | the radius half matters less as the wire rises | shift_nec5(20a) < shift_nec5(b) | hit |

**Mesh:** one ×2 cell per question (m0 against q1-18, m1 against q1-28, m2
against q2-20a).

| id | what | bar | prediction |
|---|---|---|---|
| **M** | agreement is not convergence | on every cell bs2 moves ≤ 1 % of \|Z\| from 21 to 42. razor-2p moves more than bs2 on ≥ 2 of the 3 cells, and so does `nec5` (the #1516 unconverged pair) | hit |

**Severns:**

| id | what | bar | prediction |
|---|---|---|---|
| **S1** | the AK spelling reproduces momwire's own deck | \|Z_bs2 − (49.38 + 14.93j)\| ≤ 5 Ω | hit |
| **S2** | every engine sits in the measurement's envelope | bs2, razor-2p and `nec5` each within 18 Ω of 56.1 + 6.2j in R and in X (the Table-1 ROW_BAR of momwire's `test_surface_radials_865.py`) | hit |
| **S3** | the radius half pulls X down on NEC-5, as momwire#865 measured on bs2 | X_nec5,Lonly > X_nec5 | hit |

## The estimates behind the bars

These come from arithmetic on the deck's own numbers, not from any solve.

- **Why B1 is bigger than free space.** Near ground, a radial's line log is about
  ln(2h/a) ≈ 1.4 (18-awg-pvc at h = b), not about 10 as in free space. The pair
  changes the kernel by ln(a′/a) = (1 − 1/εr) ln(b/a): 0.51, 0.65 and 0.81 on
  18, 22 and 28 AWG.
  - That is about 36 % of the near-ground log, against about 5 % in free space.
  - The screen is a slow-wave line, so the feed impedance moves strongly: the
    banked corners move 21.8 Ω for 1.95 mm of height.
  - The bar is 5 %, and ln(a′/a) orders 28 > 22 > 18.
- **B2b and C2, the image distance.**
  - A thin-wire code that takes the image interaction at √(4h² + a′²) sees the
    line log ln(√(4h² + a′²)/a′).
  - A uniform surface charge averaged over the wire's own surface sees ln(2h/a′)
    exactly, because the image axis lies outside the circle.
  - The two differ by ½ ln(1 + a′²/4h²). On 18-awg-pvc that is 0.077 at h = b
    (8.5 % of the log), 0.020 at 2b, 0.0033 at 5b and 0.0009 at 20a. With the
    bare radius at h = b it is 0.029 (2 %).
  - If the engines differ in that one term, the pair puts NEC-5 farther from
    razor-2p near ground than in free space. The difference then falls about
    25× from b to 5b.
  - I have not established which form either engine uses; C2 is the hypothesis
    that this term is the separator, and it may miss.
- **B3.** Under the same image form the radius-half shifts differ by about 10 %
  (ln(a′/a) against the reduced form's difference, 0.46 against 0.51 on 18 AWG),
  so the band is ±25 %.
- **C3.** momwire's banked corners go from 60.6 + 60.9j at h = b to
  55.1 + 39.8j at 3 mm.
- **S1.** The spelling differences (the feed position, the gap's segment count)
  and momwire's movement since that docstring's commit are allowed 5 Ω.

## The answer rules

1. **K0 or K1 fails:** stop and report.
2. **A0 misses** (NEC-5 refuses): Q1 and Q2 cannot be asked on the refused
   cells. Stop and report with the verbatim sentence.
3. **Q1:**
   - **B2a and B2b hit:** "near ground the pair narrows but does not close
     razor-2p against NEC-5; the near-ground signature is gap_pair". Q2 says
     where it departs.
   - **B2a hits and B2b misses:** "the pair closes the gap near ground as in
     free space".
   - **B2a misses:** "near ground the pair does not narrow the gap: a different
     signature". The sizes are reported.

## Order

1. Commit this registration with the harness, the analysis and the mesh-only
   probe's output, and push.
2. The main tree, NEC-5 arms first, then the momwire arms; then the pre-#1532
   tree.
3. `analyze_surface.py` writes `README.md` and `analysis.json`; the report
   follows.
