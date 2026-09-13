# AK#1443: `elevated_buried_counterpoise`'s 31 % in R against NEC-5

Haswell (i7-4770K). Scratch only; no `src/` change in either repo until the
term is named. Plan unit U6 (`docs/plan-buried-scope-closure.md`). Measure-first:
every prediction below is committed before the run that tests it, and every
miss is reported.

## Setup

- antennaknobs `eab1c4ac8` (origin/main). momwire `1dbd384`: origin/main, whose
  `src/` is the v0.54.0 tag `260bd91` that antennaknobs pins, and a superset of
  the census's `ad3cb9f`. Accelerators rebuilt with `make build`.
- NEC-5 reference: `~/nec5-timing/nec5cl-x13-static`, sha256
  `7ebf343d7d01283b83fae8192cd9c6ca434b5befb232065fc12b4d729f06a9f3` — the
  original x13 statically linked. The census used dynamic x13 `2068ae67…`. On
  momwire#1048 the static build printed every one of #1027's 15 banked NEC-5 rows
  identically.
- Decks from `NEC5Engine.deck()`, default variant, soil (13, 0.005), 7.1 MHz.

## Two facts from the decks, checked before anything is registered

**The decks are the census's.** Rebuilt at `eab1c4ac8`: nominal_nsegs 21 gives
sha256 `14239f58d8073ceb…` (239 NEC-5 segments), 42 gives `5c08c0eee924e8fe…`
(472), both equal to AK#1443's.

**The fed segment is not refined by nominal_nsegs, and the two engines are fed
at different ports** — the pattern momwire#1048 found on #1027's rod:

| nominal_nsegs | NEC-5 fed wire (0.50 → 0.55 m) | NEC-5 source | momwire fed wire | momwire source |
|---|---|---|---|---|
| 21 | 2 × 25 mm | `EX 0 1 1 2`, the knot | 1 × 50 mm | gap at arclength 0.025 m, mid-segment |
| 42 | 2 × 25 mm | the knot | 1 × 50 mm | mid-segment |

Doubling nominal_nsegs refines the radiator (21 → 42 segments) and the radials,
not the 50 mm source region. So AK#1443's "not mesh error, or not mostly"
(ΔR/R 31.2 → 31.3 % under ×2) is untested on the source axis. On #1027 that
axis, together with a/Δ, carried the whole disagreement. It is a hypothesis
here, not a finding. And this deck is near-open (|X| ≈ 70 kΩ), which is where a
source region's capacitance is the largest part of |Z|.

**Resolution floor.** NEC-5 prints five significant figures, so its X is
quantised to ±0.5 Ω at 61604 and R to ±0.0005 Ω at 30.643.

## Step 1 — reproduce AK#1443's rows (registered before the run)

The census's own per-cell worker (`scratch/956-census/popa_worker.py`) with its
thread pinning (`OMP/OPENBLAS/MKL_NUM_THREADS=1`), so "bit-identical" means what
the census meant by it.

| id | prediction | verdict |
|---|---|---|
| P1.1 | momwire Z bit-identical to the census at both meshes: 44.5602−73719.3196j (21), 42.7896−72708.6105j (42) — `1dbd384` adds nothing on this deck's path beyond `ad3cb9f` | pending |
| P1.2 | NEC-5 (x13-static) prints the census's Z at both meshes: 30.6430−61604.0000j and 29.4170−61557.0000j | pending |
| P1.3 | ΔR / max\|R\| = 31.2 % and 31.3 %; \|ΔZ\| / max\|Z\| = 16.4 % and 15.3 % | pending |

A miss on P1.1 or P1.2 stops the unit and is reported before anything else.

### Step 1 measured

`scratch/956-census/popa_worker.py`, threads pinned; rows in `step1_rows.jsonl`.
ΔR below is NEC-5 − momwire; the census tabulates momwire − NEC-5.

| nominal_nsegs | momwire (`1dbd384`) | census momwire (all three commits) | NEC-5 (x13-static) | census NEC-5 | ΔR | ΔR / max\|R\| | \|ΔZ\| / max\|Z\| |
|---|---|---|---|---|---|---|---|
| 21 | 44.56018940137673 − 73719.31963777544j | identical | 30.643 − 61604.0j | identical | −13.9172 | 31.2 % | 16.4 % |
| 42 | 42.78958801156905 − 72708.61049930776j | R …1156906, X identical | 29.417 − 61557.0j | identical | −13.3726 | 31.3 % | 15.3 % |

| id | verdict |
|---|---|
| P1.1 | **MISSED, by one unit in the last place — a cross-machine ULP, not examined further.** The #1441 census ran on Skylake; between `ad3cb9f` and `1dbd384` momwire gained only the skill doc, the version bump and scratch, no `src/` change; the house rule is never to pin cross-machine bit equality. Bit-identical at nominal_nsegs 21 (R and X) and in X at 42; R at 42 is 42.78958801156905 against the census's …906 on all three of its commits (1.7e-16 relative). The cause (the `1dbd384` source against `ad3cb9f`, or today's rebuild of the accelerators) is not examined. Reported before step 2 runs, as the stop rule requires; it is immaterial at every scale this unit reads |
| P1.2 | **HIT** — NEC-5's printed Z identical at both meshes, x13-static against the census's dynamic x13 |
| P1.3 | **HIT** — 31.2 % / 31.3 % in R, 16.4 % / 15.3 % in \|Z\| |

### The mesh at the source, both census decks

| tag | wire | nominal_nsegs 21 | nominal_nsegs 42 |
|---|---|---|---|
| 1 | fed wire, z 0.50 → 0.55 m | 2 × 25.00 mm (momwire: 1 × 50 mm) | 2 × 25.00 mm (momwire: 1 × 50 mm) |
| 2 | radiator, 10.506 m | 21 × 500.29 mm | 42 × 250.14 mm |
| 3–6 | radials at z = −0.15 m, 6.334 m each | 54 × 117.29 mm | 107 × 59.19 mm |

The radiator's first segment is **20× NEC-5's fed segment at nominal_nsegs 21
(10× momwire's)** and 10× (5×) at 42. The step sits on the source of a
near-open driving point, and doubling nominal_nsegs halves the jump without
touching the fed wire.

## Step 2 — the source region (registered before the run)

`step2_source.py`, nominal_nsegs 21, F = 1 / 2 / 4 / 8. Ports matched:
momwire's feed parity patched to even, so it shares NEC-5's knot source.
Segment counts and the knot are asserted equal at every rung. The `feed`
ladder's F = 1 NEC-5 deck is asserted to be the census's sha.

- **`feed` ladder**: the fed wire at 2F segments (25 mm / F); radiator and
  radials exactly as the census meshes them. The jump at the source grows with
  F. This measures the fed segment alone.
- **`graded` ladder**: the fed wire at 2F segments, and the radiator graded
  away from it by an explicit schedule. Panels double in length from 2·(25 mm /
  F); each panel's segment is min(500.29 mm, max(25 mm / F, panel start / 2)),
  so adjacent segments differ by at most 2× and none exceeds the census
  radiator segment. `graded_wire`'s growth-4, two-per-panel recipe was not used:
  on this radiator it makes 2.4 m segments in the middle, the confound that
  voided momwire#1048's P2b.3.

| id | prediction | verdict |
|---|---|---|
| P2.1 | **blind**, `feed`: from F = 1 to F = 8 each engine's R moves by more than 1 % of itself, and ΔR / max\|R\| moves by more than 3 pp | pending |
| P2.2 | **blind**, `graded`: \|ΔR\| / max\|R\| is below 20 % at F = 1 (the jump removed) and below 15 % at F = 8 | pending |

Competing outcome, registered with them: P2.2 holding near 31 % means the
source region is not the mechanism on this deck, and the plan's grid probes
(the transmitted grid's field form against designed tables; its range and
interpolation error at this height and depth) come next.

### The admittance reading (raised on review; registered while step 2 was already running)

At a near-open driving point R is a small, ill-conditioned part of Z. So each
ladder is also read as Y = 1/Z = G + jB, with the G fraction next to the R
fraction.

**Timing, stated before any prediction.** Both step-2 ladders were launched
before this reading was asked for. When it was registered, three rows had
already printed: `feed` F = 1 and F = 2, and `graded` F = 1. For those rows,
and for the census rows, the numbers below are computed from Z already in
hand, not predicted. No further ladder output was read before this was
committed.

| row | G momwire (S) | G NEC-5 (S) | ΔG / max\|G\| | B momwire (S) | B NEC-5 (S) | ΔB / max\|B\| | ΔR / max\|R\| |
|---|---|---|---|---|---|---|---|
| census nn 21 (stock ports) | 8.19944e-09 | 8.07446e-09 | -1.52 % | 1.35650e-05 | 1.62327e-05 | +16.43 % | -31.23 % |
| census nn 42 (stock ports) | 8.09406e-09 | 7.76325e-09 | -4.09 % | 1.37535e-05 | 1.62451e-05 | +15.34 % | -31.25 % |
| feed F = 1 (seen) | 8.46821e-09 | 8.07446e-09 | -4.65 % | 1.46459e-05 | 1.62327e-05 | +9.78 % | -22.38 % |
| feed F = 2 (seen) | 8.18399e-09 | 8.41899e-09 | +2.79 % | 1.58087e-05 | 1.70300e-05 | +7.17 % | -11.35 % |
| graded F = 1 (seen) | 8.32540e-09 | 7.39957e-09 | -11.12 % | 1.49398e-05 | 1.62747e-05 | +8.20 % | -25.10 % |

On the census deck the two engines agree in **G to 1.5–4 %** while R differs by
31 %, and **B differs by 15–16 %**. At a near-open R ≈ G / B², so a 16 %
difference in B by itself makes about a 35 % difference in R. The 31 % in R is
mostly the susceptance difference, read through that conditioning. The
susceptance is the source region's and the radiator's capacitance, and it
falls as the port is matched and the fed segment shrinks (16.4 → 9.8 → 7.2 % on
the seen `feed` rows).

| id | prediction (rows not yet seen only) | verdict |
|---|---|---|
| P2.3 | `feed` F = 4 and F = 8: ΔB / max\|B\| below 7.2 % at F = 4 and lower again at F = 8; \|ΔG / max\|G\|\| below 5 % at both | pending |
| P2.4 | `graded` F = 2, 4, 8: ΔB / max\|B\| below 8.2 % at each and falling with F; \|ΔG / max\|G\|\| below 12 % at each | pending |

Informed by the seen rows and flagged as such; P2.1 and P2.2 stand as
registered.

### Step 2 measured

`step2_source.py`, nominal_nsegs 21, ports matched (momwire's segment counts
and knot source asserted equal to NEC-5's at every rung). `feed` F = 1
reproduced the census deck sha. Rows in `step2_feed_nn21.json` and
`step2_graded_nn21.json`. Fractions are (NEC-5 − momwire) / max.

`feed` — the fed segment refined, radiator as the census meshes it (500 mm):

| F | segs | fed seg | momwire Z | NEC-5 Z | ΔR/max\|R\| | \|ΔZ\|/max\|Z\| | ΔG/max\|G\| | ΔB/max\|B\| |
|---|---|---|---|---|---|---|---|---|
| 1 | 239 | 25.000 mm | 39.4782 − 68278.3j | 30.643 − 61604j | −22.38 % | 9.78 % | −4.65 % | +9.78 % |
| 2 | 241 | 12.500 mm | 32.7471 − 63256.3j | 29.029 − 58720j | −11.35 % | 7.17 % | +2.79 % | +7.17 % |
| 4 | 245 | 6.250 mm | 28.9962 − 59097.1j | 27.677 − 56539j | −4.55 % | 4.33 % | +4.11 % | +4.33 % |
| 8 | 253 | 3.125 mm | 26.6950 − 56498.2j | 26.466 − 54775j | −0.86 % | 3.05 % | +5.19 % | +3.05 % |

`graded` — the fed segment refined and the radiator graded away from it:

| F | segs | fed seg | momwire Z | NEC-5 Z | ΔR/max\|R\| | \|ΔZ\|/max\|Z\| | ΔG/max\|G\| | ΔB/max\|B\| |
|---|---|---|---|---|---|---|---|---|
| 1 | 250 | 25.000 mm | 37.3008 − 66935.5j | 27.937 − 61445j | −25.10 % | 8.20 % | −11.12 % | +8.20 % |
| 2 | 254 | 12.500 mm | 32.5729 − 63188.3j | 26.443 − 58562j | −18.82 % | 7.32 % | −5.49 % | +7.32 % |
| 4 | 260 | 6.250 mm | 28.7956 − 59030.4j | 25.231 − 56390j | −12.38 % | 4.47 % | −3.98 % | +4.47 % |
| 8 | 270 | 3.125 mm | 26.5158 − 56436.8j | 24.149 − 54633j | −8.93 % | 3.20 % | −2.81 % | +3.20 % |

| id | verdict |
|---|---|
| P2.1 | **HIT** — momwire's R moves 32 %, NEC-5's 13.6 %, and the R fraction 21.5 pp, from F = 1 to 8 |
| P2.2 | **SPLIT** — −25.10 % at F = 1 misses "< 20 %"; −8.93 % at F = 8 meets "< 15 %" |
| P2.3 | **SPLIT** — ΔB 4.33 % then 3.05 %, below 7.2 % and falling (hit); \|ΔG\| 4.11 % at F = 4 (hit) but 5.19 % at F = 8 (misses "< 5 %" by 0.19 pp) |
| P2.4 | **HIT** — ΔB 7.32 / 4.47 / 3.20 %, below 8.2 % and falling; \|ΔG\| 5.49 / 3.98 / 2.81 %, below 12 % |

(The runs used a `zip(edges[:-1], edges[1:])` spelling that ruff's RUF007
flagged at launch. The committed script uses `itertools.pairwise(edges)`,
which yields the same pairs.)

**What the ladders say, as observations:**

- **Neither engine's census Z is converged on the source axis.** From F = 1 to
  8 on the `feed` ladder, momwire's X moves −68278 → −56498 Ω (17.3 %) and
  NEC-5's −61604 → −54775 Ω (11.1 %). The census compared two stock-mesh
  numbers with the source unrefined on both.
- **B carries \|ΔZ\|, and it converges the same way on both ladders**: 3.05 %
  and 3.20 % at F = 8 whether or not the 20:1 jump is graded away. At a
  near-open, ΔB and ΔX are the same number.
- **G, and R with it, is where the two ladders part.** At F = 8 grading the
  radiator moves the G fraction from +5.2 % to −2.8 % and the R fraction from
  −0.86 % to −8.93 %, while B barely moves. R at this driving point depends on
  the radiator's mesh as well as the source's, and is too ill-conditioned to
  adjudicate a 31 % question on its own.
- **Matching the port is not immaterial here.** At F = 1 it moved momwire's B
  by 8 % (1.3565e-5 → 1.4646e-5 S) and took the R fraction from 31.2 % to
  22.4 %. On #1027's rod the same change moved R by 2e-12, and on
  `buried_radial_vertical` by 4.4e-6. The difference is the near-open: the
  source region's susceptance is most of |Y|.

### P2.5 — do momwire's two port spellings converge to the same Y? (registered before the run)

The `feed` ladder again, with momwire on antennaknobs' own odd-parity port
(no patch). The builder asks for 2F fed segments; the odd coercion makes them
2F + 1 (F = 1 auto-meshes to one), so the gap sits mid-segment as the census
has it. NEC-5 unchanged. The harness asserts that momwire's feed is NOT on a
knot and that its segment count differs from NEC-5's by exactly one. Read in Y
against both NEC-5 and the port-matched momwire of `step2_feed_nn21.json`.

| id | prediction | verdict |
|---|---|---|
| P2.5a | **blind**: the odd- and even-port momwire converge together. Their B differ by less than 1.5 % at F = 8 (8 % at F = 1), shrinking monotonically with F | pending |
| P2.5b | **blind**: their G differ by less than 2 % at F = 8 | pending |
| P2.5c | **blind**: at F = 8 the odd-port momwire's ΔB against NEC-5 is within 1 pp of the matched one's 3.05 % | pending |

Competing outcome, registered with them: B apart by more than 3 % at F = 8 and
not shrinking means the port definition is a genuine modelling choice at a
near-open feed. antennaknobs would then have to declare which port a
cross-engine row uses, and that becomes a finding about the comparison method,
not an engine defect.
