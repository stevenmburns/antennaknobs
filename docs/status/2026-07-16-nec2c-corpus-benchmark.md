# 2026-07-16 — nec2c corpus benchmark + solver convergence (xnec2c decks, 4 engines)

## Goal

Benchmark antennaknobs' engines against the canonical NEC2 kernel on a broad
corpus of *real* decks, not hand-built designs. For every `.nec` file in the
xnec2c examples corpus:

1. translate it through `nec_import.parse_nec` (with `network=True`),
2. solve the translated geometry with **PyNEC, Sinusoidal, BSpline d=1,
   BSpline d=2**, and
3. compare driving-point impedance to **`nec2c` run on the original deck**.

Then, following the corpus finding that the B-spline bases sit well off nec2c
at the decks' native segmentation, a **segment-refinement convergence sweep** on
two parameterized designs tests whether the higher-order basis simply needs a
different mesh density.

Tooling set up this session: `nec2c` 1.3 (KJ7LNW fork) built and on `PATH`
(`~/.local/bin/nec2c`); xnec2c examples at `~/antennas/xnec2c/examples` (82
decks).

**Stack (re-run):** the tables below are the **momwire 0.14.0 + pynec-accel
1.7.5** re-run, with `--allow-wire-intersections` (nec2++'s intersection
validator off, issue #409). Two changes vs the original 0.13.0 / post2 pass:
momwire 0.14.0 fixes the ground-junction end conditions for wires touching the
ground plane, and pynec-accel 1.7.5 wraps `set_intersection_check`. Together
they eliminate **every engine error** — all 76 referenced decks now solve on all
four engines (the original pass had 6 PyNEC geometry rejections plus momwire's
`buoy`/`k9ay`/sommerfeld-cliff ground raises).

## Script

`scripts/bench_nec_corpus.py` —
`.venv/bin/python scripts/bench_nec_corpus.py --out results.json`.

Engines: `pynec` PyNECEngine · `sin` SinusoidalSolver · `bs1`/`bs2`
BSplineSolver degree 1/2. Each solve runs in its own **subprocess** for a clean
`getrusage` peak RSS and crash isolation; runtime is the engine
construct+`impedance()` wall-clock.

**Ground is matched on both sides.** `nec_import` reduces ground to a bool, so
the script parses the GN/GD cards itself and maps them to the shared engine
`ground=` spec:

| deck card | engine spec | NEC model |
|---|---|---|
| `GN 1` | `"pec"` | perfect ground |
| `GN 0 … eps sig` | `("finite-fast", eps, sig)` | gn 0, reflection-coefficient |
| `GN 2 … eps sig` | `("finite", eps, sig)` | gn 2, Sommerfeld/Norton |
| none / `GN -1` | `"free"` | free space |

A radial screen (`nradl>0`), a second medium (cliff), or a `GD` card can't be
represented by either engine; those decks still solve with the medium-1 ground
(best effort) but are flagged **`g`** and excluded from the accuracy rollup.
LD/TL/NT cards antennaknobs can express become `Load`/`TL`/`TwoPort` branches
via `build_network`; a card it can't express exactly (frequency-dependent
reactance, complex-Y network, distributed RLC) is flagged **`n`** and excluded.

**Concurrency mirrors `web/server.py`:** BLAS and OpenMP pools both pinned to
the physical-core count via `threadpool_limits` at runtime, with
`OMP_WAIT_POLICY=PASSIVE` / `GOMP_SPINCOUNT=0` exported before the numeric stack
loads. Subprocesses are dispatched **serially** (one solve, all cores) — exactly
as the server handles one request at a time. This run: **4 physical cores**.

`nec2c` output is parsed regardless of exit code, distinguishing a NaN solve, a
faulty/unsupported card (e.g. the xnec2c-only `ZO`), and a timeout. Impedance is
read at the frequency nec2c actually used for its first ANTENNA INPUT PARAMETERS
block (robust to sweep direction).

## Coverage

82 decks → **76 with a usable nec2c reference**. 6 excluded:

- `10-20m-moxon` — nec2c's own solve returned NaN (all these decks also carry
  the xnec2c-only `ZO` card; stripping it clears the exit-255 but not the NaN).
- `2m_yagi_SY_parametric`, `5el_yagi_SY_parametric` — 4nec2 symbolic vars (SY).
- `ex4_current_source_sq_loop` — EX type 4 current source (not a voltage feed).
- `gray_hoverman` (SM multi-patch), `satellite` (SP surface patch).

## Metric — reflection-coefficient distance (issue #407)

Engines are scored by **ΔΓ = |Γ_eng − Γ_nec2c|**, where Γ = (Z − Z₀)/(Z + Z₀)
at Z₀ = 50 Ω. For any passive antenna R ≥ 0, so Z + Z₀ has real part ≥ Z₀ > 0 —
Γ is never singular and |Γ| ≤ 1, making ΔΓ bounded on [0, 2]. This replaces the
relative-|Z| error `|ΔZ|/|Z_ref|`, which blew up wherever |Z| passed near a
zero/pole of the impedance function (near-open / near-short), producing rows
that read as 100s of % but were artifacts. ΔΓ is also the quantity SWR / match
quality derive from — the error a user actually experiences. Raw complex
impedances stay in the JSON, so relative-|Z| is still derivable.

## Agreement rollup

Feed-0 ΔΓ. **Clean** = supported ground **and** fully-expressed network
(excludes `g`/`n` flags), the only decks where a disagreement is genuinely
engine error. Buckets are the *indistinguishable* / *matched-system-equivalent*
/ *same-ballpark* tiers.

| engine | n | median | <0.01 | <0.05 | <0.2 |
|---|--:|--:|--:|--:|--:|
| **PyNEC** | 61 | **0.0003** | 51 | 58 | 59 |
| **Sinusoidal** | 61 | **0.0051** | 41 | 56 | 58 |
| **BSpline d=2** | 61 | 0.0408 | 15 | 35 | 50 |
| **BSpline d=1** | 61 | 0.0647 | 6 | 24 | 49 |

`n` rose from 55/58 to a uniform **61** because the ground-connected verticals
and the six geometry-rejected decks now solve cleanly on every engine and count
as clean. Every engine improved: Sinusoidal's median halved (0.0092 → 0.0051)
and its `<0.01` bucket jumped 30 → 41, almost entirely from momwire 0.14.0's
ground fix (see headlines).

## Runtime & peak RSS (successful solves)

Peak RSS includes the ~140 MB interpreter + numpy + PyNEC import baseline; the
per-solve delta is in the JSON. The multi-second / high-RSS tails are the large
dense structures (helicones, helispheres, `23cm_helix`).

| engine | n | solve median | max | peakRSS median | max |
|---|--:|--:|--:|--:|--:|
| PyNEC | 76 | 11 ms | 0.21 s | 144 MB | 203 MB |
| Sinusoidal | 76 | 17 ms | 12.16 s | 158 MB | 207 MB |
| BSpline d=1 | 76 | 25 ms | 12.18 s | 182 MB | **738 MB** |
| BSpline d=2 | 76 | 31 ms | 12.22 s | 167 MB | 442 MB |

All four engines now report **n = 76** (every referenced deck solved); the
original pass had 70–72 because of the engine errors now eliminated.

## Full per-deck table

Columns are feed-0 **ΔΓ** (0 = identical, ≤2 = bounded). `fl`: **g** =
unsupported ground (radial/cliff), **n** = inexpressible LD/TL/NT network. No
cell is `ERR`/`GEO` any more — with momwire 0.14.0 and pynec-accel 1.7.5's
intersection check off, every engine solves every referenced deck (issue #409
resolved; the `g`/`n` flags still mark not-apples-to-apples rows).

| deck | f/MHz | grd | fl | Z_nec2c (feed0) | PyNEC | Sin | Bs1 | Bs2 |
|---|--:|:--|:-:|--:|--:|--:|--:|--:|
| 10-30m-box | 10.000 | finite-fast | g | 21.8-10.1j | 1.3402 | 1.3402 | 0.4279 | 0.4275 |
| 10-30m_MultiBand_Vertical | 7.000 | pec |  | 7.3-146.8j | 0.0009 | 0.0017 | 0.0023 | 0.0005 |
| 10-30m_bipyramid | 10.000 | finite-fast | g | 13.9+4.5j | 1.5320 | 1.5320 | 0.3335 | 0.3323 |
| 10-30m_inv_cone | 10.000 | pec |  | 19.2+24.8j | 0.0000 | 0.0068 | 0.3191 | 0.3192 |
| 10-30m_sphere | 10.000 | finite-fast | g | 20.1-0.5j | 1.4084 | 1.4084 | 0.4709 | 0.4707 |
| 10-40m_windom | 3.000 | finite-fast | g | 7.8-11485.0j | 0.0722 | 0.0722 | 0.8589 | 0.8590 |
| 10-80m_Classic_Windom-optimized | 3.000 | finite-fast | g | 118.3-10573.0j | 0.0397 | 0.0397 | 0.1117 | 0.1122 |
| 10-80m_G5RV | 3.000 | finite |  | 3.5-90.5j | 0.0001 | 0.0001 | 0.0152 | 0.0056 |
| 10-80m_Inverted-L | 3.000 | finite-fast | g | 11.4-164.0j | 0.5575 | 0.5575 | 0.0427 | 0.0429 |
| 10-80m_windom | 3.000 | finite-fast | g | 91.6-11134.0j | 0.0374 | 0.0374 | 0.1237 | 0.1241 |
| 137MHz_broadside_Yagi | 130.000 | free |  | 29.8-35.3j | 0.0002 | 0.0088 | 0.0532 | 0.0269 |
| 137MHz_turnstile | 135.000 | free |  | 34.6+6.2j | 0.0017 | 0.0167 | 0.0643 | 0.0309 |
| 137MHz_turnstile_sloped | 130.000 | free |  | 66.8-7.4j | 0.0011 | 0.0023 | 0.0233 | 0.0163 |
| 137Mhz-QFHA1 | 130.000 | free |  | 396.5+1098.9j | 0.0000 | 0.0015 | 0.0555 | 0.0428 |
| 137Mhz-QFHA2 | 130.000 | free |  | 2.7-274.3j | 0.0000 | 0.0140 | 0.0750 | 0.0850 |
| 137Mhz-QFHA3 | 135.000 | free |  | 16.0+18.3j | 0.0047 | 0.0044 | 0.0548 | 0.0520 |
| 137Mhz_xpol_omni | 110.000 | free |  | 28.0-39.2j | 0.0035 | 0.0034 | 0.2582 | 0.2380 |
| 13cm_Yagi | 2000.000 | free |  | 9.4-86.1j | 0.0001 | 0.0012 | 0.0565 | 0.0057 |
| 13cm_corner_reflector | 2000.000 | free |  | 59.3-33.7j | 0.0001 | 0.0044 | 0.0957 | 0.0411 |
| 13cm_helix+screen | 2300.000 | free |  | 126.3-27.9j | 0.0394 | 0.0314 | 0.6858 | 0.4885 |
| 15m_delta-loop | 20.000 | free |  | 37.2-133.6j | 0.0383 | 0.2723 | 0.2755 | 0.2556 |
| 1MHz_3x_helicone | 0.900 | pec |  | 49.3-399.8j | 0.0005 | 0.0005 | 0.0266 | 0.0239 |
| 1MHz_3x_helisphere | 0.900 | pec |  | 52.5-413.1j | 0.0000 | 0.0001 | 0.0146 | 0.0123 |
| 1MHz_4x_helisphere | 0.980 | pec |  | 96.5-234.8j | 0.0410 | 0.0410 | 0.1570 | 0.1590 |
| 1MHz_helivert | 0.980 | pec |  | 2.9-14.1j | 0.0003 | 0.0040 | 0.0161 | 0.0114 |
| 1MHz_tower | 0.980 | pec |  | 68.5-136.1j | 0.4249 | 0.8026 | 0.9544 | 0.9558 |
| 20-40m_ground_plane | 6.000 | pec |  | 41.4-214.4j | 0.0000 | 0.0007 | 0.0016 | 0.0007 |
| 20-40m_vert_circ_cliff | 6.000 | finite-fast | g | 48.7-196.1j | 0.3034 | 0.3034 | 0.0144 | 0.0138 |
| 20-40m_vert_linear_cliff | 6.000 | finite-fast | g | 48.7-196.1j | 0.3034 | 0.3034 | 0.0144 | 0.0138 |
| 20-40m_vert_sommerfeld_cliff | 6.000 | finite | g | 74.6-199.9j | 0.0027 | 0.0008 | 0.0345 | 0.0349 |
| 20m_car_ant | 13.000 | free |  | 28.0-57.2j | 0.0014 | 0.0085 | 0.0723 | 0.0766 |
| 20m_dipole_NT_50ohm | 14.000 | free | n | 38.9-3.2j | 1.1243 | 1.1243 | 1.1242 | 1.1243 |
| 20m_quad | 13.600 | free |  | 31.9-149.4j | 0.0397 | 0.0398 | 0.0426 | 0.0412 |
| 23cm_helix+radials | 1200.000 | free |  | 43.4-71.6j | 0.0185 | 0.0202 | 0.2239 | 0.0912 |
| 23cm_helix+screen | 1200.000 | free |  | 162.2-93.6j | 0.0159 | 0.0168 | 0.2890 | 0.2168 |
| 2m-5el-rhcp-ARISS-KJ7NLL | 299.800 | free |  | 88.5-185.4j | 0.0043 | 0.0056 | 0.0710 | 0.0775 |
| 2m_1to4l-gp_on_pole | 140.000 | free |  | 27.8-20.2j | 0.0034 | 0.0148 | 0.1248 | 0.1064 |
| 2m_1to4l-horiz_gp_on_pole | 140.000 | free |  | 11.9-39.5j | 0.0052 | 0.0194 | 0.0314 | 0.0288 |
| 2m_5to8l-gp_on_pole | 140.000 | free |  | 75.5-72.0j | 0.0001 | 0.0051 | 0.1968 | 0.1098 |
| 2m_EME_ant | 144.000 | free |  | 27.2-146.0j | 0.0001 | 0.0090 | 0.0106 | 0.0068 |
| 2m_Lindenblad | 120.000 | free |  | 14.2+29.8j | 0.0001 | 0.0034 | 0.0503 | 0.0205 |
| 2m_bigwheel | 144.000 | free |  | 20.8-0.9j | 0.0001 | 0.0002 | 0.1592 | 0.1596 |
| 2m_extended_Xpol_yagi-2-optimized | 142.000 | free |  | 28.7+14.0j | 0.0003 | 0.0093 | 0.1555 | 0.0316 |
| 2m_extended_Xpol_yagi-2 | 142.000 | free |  | 33.4-138.4j | 0.0001 | 0.0065 | 0.1416 | 0.0618 |
| 2m_extended_Xpol_yagi | 144.000 | free |  | 64.2-229.2j | 0.0001 | 0.0028 | 0.0195 | 0.0036 |
| 2m_extended_yagi-optimized | 140.000 | free |  | 113.3-398.7j | 0.0000 | 0.0010 | 0.0248 | 0.0059 |
| 2m_extended_yagi | 140.000 | free |  | 50.7-205.8j | 0.0001 | 0.0034 | 0.0173 | 0.0025 |
| 2m_halo_stack | 140.000 | free |  | 15.2-276.4j | 0.0001 | 0.0055 | 0.0277 | 0.0113 |
| 2m_sqr_halo | 140.000 | free |  | 18.7+166.6j | 0.0011 | 0.0119 | 0.0184 | 0.0025 |
| 2m_sqr_halo_stack | 140.000 | free |  | 15.6-172.9j | 0.0010 | 0.0131 | 0.0289 | 0.0217 |
| 2m_xpol_omni | 120.000 | free |  | 28.1-29.0j | 0.0033 | 0.0033 | 0.2680 | 0.2512 |
| 2m_xpol_omni_stack | 140.000 | free |  | 34.8-18.8j | 0.0062 | 0.0050 | 0.0147 | 0.0108 |
| 2m_yagi | 140.000 | free |  | 28.8-13.2j | 0.0001 | 0.0309 | 0.0790 | 0.0408 |
| 2m_yagi_stack | 140.000 | free |  | 29.9-12.2j | 0.0001 | 0.0281 | 0.0724 | 0.0373 |
| 30-80m_inv_L | 3.000 | pec |  | 31.4+31.1j | 0.0007 | 0.0006 | 0.0016 | 0.0006 |
| 35-55MHz_logper | 35.000 | free |  | 45.0-1.3j | 0.0000 | 0.0008 | 0.0009 | 0.0005 |
| 40-80m_Inv_L | 3.000 | finite-fast | g | 24.9-497.6j | 0.1309 | 0.1309 | 0.0036 | 0.0036 |
| 40m-moxon | 6.800 | finite |  | 3.0-8.8j | 0.0002 | 0.0010 | 0.0037 | 0.0065 |
| 6-17m_bipyramid | 14.000 | pec |  | 7.0-16.6j | 0.0016 | 0.0017 | 0.2331 | 0.2326 |
| 6-20m_fan | 14.000 | pec |  | 12.3-0.4j | 0.0001 | 0.0008 | 0.2323 | 0.2321 |
| 6-20m_inv_cone | 14.000 | pec |  | 14.4+9.2j | 0.0000 | 0.0051 | 0.2335 | 0.2342 |
| 6-40m_5B4AZ-optimized | 7.000 | finite |  | 0.0-90243.0j | 0.6262 | 0.6264 | 0.6311 | 0.6279 |
| 6-40m_Classic_Windom-optimized | 7.000 | finite-fast | g | 160.8-4703.6j | 0.0441 | 0.0441 | 0.2673 | 0.2673 |
| 6m_big-square_stack | 45.000 | finite-fast |  | 7.5+11.1j | 0.0091 | 0.0064 | 0.0869 | 0.0963 |
| 6m_bigwheel-stack | 45.000 | finite-fast |  | 12.9+21.2j | 0.0001 | 0.0000 | 0.1205 | 0.1196 |
| 6m_horizomni | 45.000 | free |  | 18.9-275.6j | 0.0001 | 0.0018 | 0.0140 | 0.0077 |
| 70cm-5el-rhcp-KJ7NLL | 299.800 | free |  | 123.6-338.9j | 0.0029 | 0.0044 | 0.0423 | 0.0451 |
| 70cm_collinear | 420.000 | free |  | 107.8-340.6j | 0.0118 | 0.0127 | 0.0931 | 0.0311 |
| 80m_zepp | 3.000 | finite |  | 0.6-115.2j | 0.0000 | 0.0003 | 0.0647 | 0.0288 |
| T12m-H24m | 1.000 | finite-fast | g | 6.8-327.1j | 0.1837 | 0.1837 | 0.0018 | 0.0024 |
| T20m-H18m | 1.000 | finite-fast | g | 4.5-277.9j | 0.2516 | 0.2516 | 0.0099 | 0.0093 |
| airplane | 5.000 | free |  | 68.5-91.1j | 0.0001 | 0.0160 | 0.1188 | 0.1265 |
| buoy | 10.000 | finite |  | 3.8-259.8j | 0.0000 | 0.0028 | 0.0349 | 0.0086 |
| ex2_current_slope_disc_dipole | 200.000 | free |  | 26.6-632.1j | 0.0061 | 0.0061 | 0.0021 | 0.0025 |
| k9ay_5b4az | 1.800 | finite |  | 492.6+66.2j | 0.0012 | 0.0584 | 0.0773 | 0.0765 |
| k9ay_orig | 1.800 | finite |  | 960.8+81.2j | 0.0838 | 0.0837 | 0.0899 | 0.0892 |

## Headlines

- **Every referenced deck now solves on every engine — zero errors.** The
  original pass had 6 PyNEC geometry rejections and 3 momwire ground raises
  (`buoy`, `k9ay_5b4az`, `k9ay_orig`, plus the sommerfeld cliff). pynec-accel
  1.7.5's `set_intersection_check(False)` and momwire 0.14.0's ground-junction
  fix clear all of them: 76/76 decks × 4 engines, no `ERR`/`GEO` anywhere.
- **momwire's ground weak spot is largely fixed (0.14.0).** This was *the*
  actionable gap in the original pass — ground-mounted verticals/monopoles
  diverged to a near-total reflection-phase gap. They now track nec2c:
  Sinusoidal ΔΓ on `1MHz_helivert` **1.82 → 0.004**, `6-20m_fan` **1.60 →
  0.001**, `6-17m_bipyramid` **1.68 → 0.002**, `10-30m_inv_cone` **1.37 →
  0.007**, `30-80m_inv_L` **1.15 → 0.001**, `20-40m_ground_plane` **0.41 →
  0.001**, the helicones/helispheres **0.20–0.34 → 0.000–0.04**; and `buoy` /
  `k9ay_*`, which used to raise `requires every wire strictly above ground_z`,
  now solve at ΔΓ 0.003 / 0.06 / 0.08. Sinusoidal's overall median halved
  (0.0092 → 0.0051). The B-spline bases share the ground code and improved in
  lockstep (PEC verticals ~1.6 → ~0.23; the ~0.23 residual is the basis-
  convergence gap, not ground). **One PEC deck regressed:** `1MHz_tower`
  (guy-wires meeting the ground plane) went Sinusoidal 0.55 → 0.80 — the lone
  remaining ground outlier, worth a look.
- **PyNEC ≈ nec2c (median ΔΓ 0.0003, 51/61 within 0.01).** Two independent NEC2
  kernels — nec2++ (PyNEC) vs nec2c (C) — so this mostly *validates the
  pipeline*: the `nec_import` translation, network reduction, and GN→`ground=`
  matching all reproduce what nec2c builds. Now over 61 clean decks (was 55),
  including the six formerly geometry-rejected ones, which land on nec2c at ΔΓ
  ≤ 0.019 in free space (`1MHz_tower` 0.42 on PEC ground — still beating momwire).
- **Sinusoidal is the most NEC-faithful momwire basis** (median ΔΓ 0.0051), as
  expected — same sinusoidal basis family as NEC2. BSpline d=2 (0.041) and d=1
  (0.065) sit further off *at the decks' native segmentation* — the motivation
  for the convergence sweep below.
- **The reflection-coefficient metric dissolves the near-open artifacts.**
  `6-40m_5B4AZ` at 0−90243j — which read 99.9% under relative-|Z| on *every*
  engine including PyNEC — is ΔΓ ≈ 0.63 **identical across all four**: a real,
  bounded near-open phase gap shared by every engine (tiny geometry differences
  between the two pipelines near a sharp anti-resonance), not a per-engine defect.
  The off-resonance windoms (previously 88–344%) now sit at ΔΓ ≈ 0.006–0.07.
- **nec2c has its own edges.** It rejects the xnec2c-only `ZO` card (exit 255,
  but the impedance block is still valid and now parsed past it) and genuinely
  NaN'd one deck (`10-20m-moxon`).

## Convergence sweep — does the B-spline basis just need a different mesh?

The corpus snapshot uses each deck's native segmentation, which is tuned for
NEC. Hypothesis (SB): **BSpline d=2, being higher-order, converges with *fewer*
segments** than the sinusoidal/pulse bases. Tested with the native convergence
mechanism — `builder.nominal_nsegs = N`, which scales each edge's segment count
by length via `segs_for(length, ref)` — on two existing parameterized designs,
free space, sweeping N ∈ {7,11,15,21,31,45,61,85}.

**yagi** — all four converge to ~34.6 −36j; the difference is *rate*:

| N | PyNEC | Sin | Bs1 | Bs2 |
|--:|--:|--:|--:|--:|
| 15 | 33.26 −35.5j | 33.22 −35.7j | 34.04 −37.8j | 34.41 −36.8j |
| 21 | 33.82 −35.8j | 33.78 −36.0j | 34.21 −37.3j | 34.47 −36.6j |
| 45 | 34.41 −36.0j | 34.37 −36.1j | 34.42 −36.6j | 34.56 −36.2j |
| 85 | 34.59 −35.9j | 34.55 −36.1j | 34.52 −36.3j | 34.61 −36.0j |

**quad loop** — the dramatic case:

| N | PyNEC | Sin | Bs1 | Bs2 |
|--:|--:|--:|--:|--:|
| 7 | 115.74 −0.4j | 115.77 −0.4j | 127.49 −2.9j | 130.45 −1.3j |
| 15 | 124.93 −0.5j | 124.96 −0.5j | 129.54 −1.5j | 130.15 −1.0j |
| 45 | 133.69 −0.6j | 133.73 −0.5j | 129.95 −1.2j | 130.01 −0.9j |
| 85 | 136.24 −0.6j | 136.28 −0.6j | 129.95 −1.2j | 129.98 −0.9j |

Segments to reach within 2% of that engine's own finest-mesh value:

| design | PyNEC | Sin | Bs1 | Bs2 |
|---|--:|--:|--:|--:|
| yagi | 21 | 21 | 31 | **15** |
| quad | 45 | 45 | 11 | **7** |

- **The hypothesis holds — strongly.** On the quad, **Bs2 is flat by N=7** while
  **PyNEC/Sin are still climbing at N=85** (115→136 Ω, not yet converged): ~6×
  fewer segments to a settled answer. Even on the well-behaved yagi, Bs2
  converges at N=15 vs N=21 for PyNEC/Sin.
- **But they converge to *different* values on the quad.** B-splines settle at
  ~130 Ω; PyNEC/Sin are past 136 Ω and still rising. A quad's driving-point R is
  typically ~120–130 Ω, so the B-spline plateau looks physically sane and the
  pulse/sinusoidal pair appears to be crawling up from below — but this needs an
  independent anchor before asserting which is *correct*. **This reframes the
  corpus rollup:** some of the B-spline "error" is coarse-mesh convergence lag,
  not a fixed basis offset — the decks are meshed for NEC, not for a higher-order
  basis.

## Caveats

- 4-physical-core box; absolute runtimes move with core count. Cross-engine
  ratios should hold.
- Feed-0 only in the rollup; multi-feed decks (5 of the corpus) compare all
  feeds by EX order in the JSON.
- Peak RSS includes the interpreter+numpy+PyNEC import baseline (~140 MB).
- Convergence sweep is a preliminary inline run on two designs; "converged
  value" is each engine's own finest mesh (N=85), **not** an independent
  reference, so it measures convergence *rate*, not correctness.

## Follow-ups

- **Anchor the quad convergence** with a very-fine PyNEC mesh (N≈201) and/or
  nec2c on a matched-dimension quad deck, to settle whether Bs2 converges *faster
  to the same answer* or to a *different* one.
- **Formalize the convergence sweep** into `bench_nec_corpus.py` (a `--converge`
  mode) or a sibling script, reusing the subprocess/RSS/concurrency harness;
  extend to more loops (`delta_loop`, `diamond_loop`) to test whether "closed
  loops favor the higher-order basis" generalizes.
- **momwire ground on ground-connected wires — largely resolved by 0.14.0.**
  The `strictly above ground_z` raises and the large PEC-ground-plane divergence
  are gone (see headlines). Remaining thread: `1MHz_tower` (guy-wires into the
  ground plane) regressed to Sinusoidal ΔΓ 0.80 — the one PEC deck still off, and
  the only ground case now worth chasing.

## PyNEC `ERR` triage (issue #409) — all are nec2++ geometry rejections

The decks PyNEC raised on — the five in the issue (`20m_car_ant`,
`70cm_collinear`, `airplane`, `137Mhz-QFHA2`, `1MHz_tower`) plus a sixth the
classifier surfaced (`23cm_helix+radials`, below) — are **one root cause, not
several bugs**: nec2++
(the PyNEC kernel) runs a geometry validator inside `geometry_complete()` /
`geo.wire()` that fatally rejects wires passing within a radius-sum of each
other. The NEC-2 Fortran kernel and its faithful C port `nec2c` only *warn*
about this, and momwire's MoM does no such pre-check — so `nec2c` solves every
original deck and all three momwire solvers solve every translation. **The
translated geometry is sound; this is a genuine kernel-wrapper limitation, not
a `nec_import`/`engines/pynec.py` bug.**

The captured exceptions split the one cause into two nec2++ messages:

| deck | nec2++ message | condition |
|---|---|---|
| `20m_car_ant` | `WIRE #3 INTERSECTS WIRE #40` | car-body grid: non-connected wires cross within a radius-sum |
| `1MHz_tower` | `WIRE #1 INTERSECTS WIRE #19` | tower/guy attachment crossing |
| `137Mhz-QFHA2` | `WIRE #16 INTERSECTS WIRE #18` | quadrifilar-helix crossover |
| `70cm_collinear` | `FIRST SEGMENT MIDPOINT OF WIRE #6 INTERSECTS WIRE #1` | short feed-stub segment lands inside the connecting wire's radius |
| `airplane` | `FIRST SEGMENT MIDPOINT OF WIRE #117 INTERSECTS WIRE #116` | dense fuselage/wing grid, junction segment inside neighbour |

Because the classifier keys off the nec2++ message rather than a deck
allow-list, it also caught a **sixth** deck the original triage list missed —
`23cm_helix+radials` (`FIRST SEGMENT MIDPOINT OF WIRE #2 INTERSECTS WIRE #1`,
helix feed meeting the radial screen) — same root cause, same `GEO`
classification.

A geometry sweep (segment-to-segment distance vs sum-of-radii, excluding
shared endpoints) confirms every deck carries wires closer than that threshold
— crossing pairs (`20m_car_ant` 333, `airplane` 23, `1MHz_tower`/`137Mhz-QFHA2`
1–2) and shared-endpoint-too-close pairs where a junction segment sits inside
the neighbour's radius (14–761 per deck). These are real thick-/touching-wire
conditions the thin-wire kernel's separation assumption is uneasy about; nec2++
made the warning fatal, NEC-2/nec2c did not.

**Resolution — two layers.**

*1. Clean classification (default).* `bench_nec_corpus.py` classifies engine
errors: a nec2++ geometry rejection shows as **`GEO`** in the per-deck table
(vs `ERR` for a genuine solve crash), the JSON row carries an `error_kind`
(`"geo"`/`"err"`), and the report prints an `ENGINE ERRORS` section that
separates the documented `GEO` limitation from anything worth investigating. So
a reader sees *why* PyNEC is absent on these rows rather than an opaque `ERR`.

*2. An opt-in that recovers the decks — now shipped.* nec2++'s validator is
toggleable as of **pynec-accel 1.7.5** (on PyPI): the `stevenmburns/necpp`
engine fork gained a public `c_geometry::set_intersection_check(bool)`
(mirroring upstream necpp master), `stevenmburns/python-necpp` wraps it for
Python, `PyNECEngine(..., check_intersections=False)` calls it before
`geometry_complete()`, and `bench_nec_corpus.py --allow-wire-intersections`
sets it per run. **The tables above are that run** — the six decks appear as
ordinary rows, and PyNEC lands right on nec2c (five free-space decks ΔΓ ≤ 0.019,
two ~0; `1MHz_tower` 0.42 on PEC ground, still beating momwire). That confirms
these were **false-positive rejections, not bad geometry**.

The classification (`GEO`, `error_kind`, the `ENGINE ERRORS` section) stays in
the script for **strict runs** — with the default `check_intersections=True`
these six decks still show `GEO` rather than an opaque `ERR`, so a reader of a
strict run sees *why* PyNEC is absent. The engine default remains check-on (a
reasonable guard for hand-built designs); the corpus/acceptance runs pass
`--allow-wire-intersections` to recover every solvable deck.
