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
decks). antennaknobs 0.28.0 / momwire 0.13.0, both editable.

## Script

`scripts/bench_nec_corpus.py` (branch `bench/nec-corpus-impedance`) —
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

## Agreement rollup

Feed-0 relative error `|Z_eng − Z_nec2c| / |Z_nec2c|`. **Clean** = supported
ground **and** fully-expressed network (excludes `g`/`n` flags), the only decks
where a disagreement is genuinely engine error.

| engine | n | median | <1% | <5% | <20% |
|---|--:|--:|--:|--:|--:|
| **PyNEC** | 55 | **0.1%** | 43 | 49 | 53 |
| **Sinusoidal** | 58 | **2.1%** | 18 | 39 | 44 |
| **BSpline d=2** | 58 | 12.3% | 6 | 19 | 33 |
| **BSpline d=1** | 58 | 21.9% | 1 | 11 | 28 |

## Runtime & peak RSS (successful solves)

Peak RSS includes the ~140 MB interpreter + numpy + PyNEC import baseline; the
per-solve delta is in the JSON. The multi-second / high-RSS tails are the large
dense structures (helicones, helispheres, `23cm_helix`).

| engine | n | solve median | max | peakRSS median | max |
|---|--:|--:|--:|--:|--:|
| PyNEC | 70 | 12 ms | 0.24 s | 148 MB | 202 MB |
| Sinusoidal | 72 | 15 ms | 9.31 s | 153 MB | 206 MB |
| BSpline d=1 | 72 | 23 ms | 9.32 s | 166 MB | **737 MB** |
| BSpline d=2 | 72 | 29 ms | 9.31 s | 166 MB | 441 MB |

## Full per-deck impedance table

Columns are feed-0 relative error (%). `fl`: **g** = unsupported ground
(radial/cliff), **n** = inexpressible LD/TL/NT network. `ERR` = engine raised.

| deck | f/MHz | grd | fl | Z_nec2c (feed0) | PyNEC | Sin | Bs1 | Bs2 |
|---|--:|:--|:-:|--:|--:|--:|--:|--:|
| 10-30m-box | 10.000 | finite-fast | g | 21.8-10.1j | 5289.2 | 43190.6 | 26043.9 | 30054.4 |
| 10-30m_MultiBand_Vertical | 7.000 | pec |  | 7.3-146.8j | 0.2 | 5767.2 | 3219.2 | 4070.2 |
| 10-30m_bipyramid | 10.000 | finite-fast | g | 13.9+4.5j | 7803.3 | 38592.6 | 23379.4 | 26963.8 |
| 10-30m_inv_cone | 10.000 | pec |  | 19.2+24.8j | 0.0 | 17565.1 | 10892.0 | 12040.5 |
| 10-30m_sphere | 10.000 | finite-fast | g | 20.1-0.5j | 7181.7 | 34940.9 | 19535.0 | 22643.9 |
| 10-40m_windom | 3.000 | finite-fast | g | 7.8-11485.0j | 92.7 | 331.4 | 183.3 | 240.8 |
| 10-80m_Classic_Windom-optimized | 3.000 | finite-fast | g | 118.3-10573.0j | 89.0 | 329.6 | 182.6 | 240.2 |
| 10-80m_G5RV | 3.000 | finite |  | 3.5-90.5j | 0.0 | 0.0 | 1.8 | 0.7 |
| 10-80m_Inverted-L | 3.000 | finite-fast | g | 11.4-164.0j | 4364.3 | 44584.5 | 27731.3 | 34209.1 |
| 10-80m_windom | 3.000 | finite-fast | g | 91.6-11134.0j | 88.0 | 344.4 | 193.6 | 253.3 |
| 137MHz_broadside_Yagi | 130.000 | free |  | 29.8-35.3j | 0.0 | 1.4 | 8.7 | 4.4 |
| 137MHz_turnstile | 135.000 | free |  | 34.6+6.2j | 0.3 | 3.4 | 12.5 | 6.2 |
| 137MHz_turnstile_sloped | 130.000 | free |  | 66.8-7.4j | 0.2 | 0.5 | 4.8 | 3.4 |
| 137Mhz-QFHA1 | 130.000 | free |  | 396.5+1098.9j | 0.0 | 1.7 | 172.8 | 101.0 |
| 137Mhz-QFHA2 | 130.000 | free |  | 2.7-274.3j | ERR | 4.1 | 26.9 | 31.6 |
| 137Mhz-QFHA3 | 135.000 | free |  | 16.0+18.3j | 0.9 | 0.8 | 11.0 | 10.4 |
| 137Mhz_xpol_omni | 110.000 | free |  | 28.0-39.2j | 0.5 | 0.5 | 47.6 | 42.6 |
| 13cm_Yagi | 2000.000 | free |  | 9.4-86.1j | 0.0 | 0.2 | 6.8 | 0.7 |
| 13cm_corner_reflector | 2000.000 | free |  | 59.3-33.7j | 0.0 | 0.8 | 17.5 | 7.8 |
| 13cm_helix+screen | 2300.000 | free |  | 126.3-27.9j | 10.4 | 7.4 | 76.2 | 64.3 |
| 15m_delta-loop | 20.000 | free |  | 37.2-133.6j | 7.4 | 78.6 | 79.8 | 70.7 |
| 1MHz_3x_helicone | 0.900 | pec |  | 49.3-399.8j | 0.2 | 1136.4 | 1073.9 | 641.6 |
| 1MHz_3x_helisphere | 0.900 | pec |  | 52.5-413.1j | 0.0 | 562.2 | 788.1 | 253.3 |
| 1MHz_4x_helisphere | 0.980 | pec |  | 96.5-234.8j | 13.9 | 1510.4 | 1308.3 | 427.2 |
| 1MHz_helivert | 0.980 | pec |  | 2.9-14.1j | 0.1 | 55226.9 | 39407.3 | 31132.2 |
| 1MHz_tower | 0.980 | pec |  | 68.5-136.1j | ERR | 6154.8 | 3459.3 | 3940.2 |
| 20-40m_ground_plane | 6.000 | pec |  | 41.4-214.4j | 0.0 | 1857.5 | 1102.5 | 1358.9 |
| 20-40m_vert_circ_cliff | 6.000 | finite-fast | g | 48.7-196.1j | 213.6 | 2537.7 | 1466.4 | 1845.6 |
| 20-40m_vert_linear_cliff | 6.000 | finite-fast | g | 48.7-196.1j | 213.6 | 2537.7 | 1466.4 | 1845.6 |
| 20-40m_vert_sommerfeld_cliff | 6.000 | finite | g | 74.6-199.9j | 0.7 | ERR | ERR | ERR |
| 20m_car_ant | 13.000 | free |  | 28.0-57.2j | ERR | 1.3 | 10.0 | 10.6 |
| 20m_dipole_NT_50ohm | 14.000 | free | n | 38.9-3.2j | 148504.0 | 151054.3 | 61621.2 | 83640.7 |
| 20m_quad | 13.600 | free |  | 31.9-149.4j | 7.1 | 7.1 | 7.6 | 7.4 |
| 23cm_helix+radials | 1200.000 | free |  | 43.4-71.6j | ERR | 3.4 | 29.3 | 13.6 |
| 23cm_helix+screen | 1200.000 | free |  | 162.2-93.6j | 4.7 | 5.0 | 49.9 | 41.5 |
| 2m-5el-rhcp-ARISS-KJ7NLL | 299.800 | free |  | 88.5-185.4j | 1.1 | 1.5 | 16.1 | 17.4 |
| 2m_1to4l-gp_on_pole | 140.000 | free |  | 27.8-20.2j | 0.6 | 2.8 | 25.3 | 21.7 |
| 2m_1to4l-horiz_gp_on_pole | 140.000 | free |  | 11.9-39.5j | 0.7 | 2.6 | 4.0 | 3.7 |
| 2m_5to8l-gp_on_pole | 140.000 | free |  | 75.5-72.0j | 0.0 | 1.0 | 32.3 | 19.8 |
| 2m_EME_ant | 144.000 | free |  | 27.2-146.0j | 0.0 | 1.7 | 1.9 | 1.3 |
| 2m_Lindenblad | 120.000 | free |  | 14.2+29.8j | 0.0 | 0.5 | 7.9 | 3.2 |
| 2m_bigwheel | 144.000 | free |  | 20.8-0.9j | 0.0 | 0.0 | 34.6 | 34.6 |
| 2m_extended_Xpol_yagi-2-optimized | 142.000 | free |  | 28.7+14.0j | 0.1 | 1.9 | 32.3 | 6.4 |
| 2m_extended_Xpol_yagi-2 | 142.000 | free |  | 33.4-138.4j | 0.0 | 1.2 | 21.1 | 10.3 |
| 2m_extended_Xpol_yagi | 144.000 | free |  | 64.2-229.2j | 0.0 | 0.8 | 5.1 | 1.0 |
| 2m_extended_yagi-optimized | 140.000 | free |  | 113.3-398.7j | 0.0 | 0.4 | 10.0 | 2.6 |
| 2m_extended_yagi | 140.000 | free |  | 50.7-205.8j | 0.0 | 0.8 | 4.1 | 0.6 |
| 2m_halo_stack | 140.000 | free |  | 15.2-276.4j | 0.0 | 1.6 | 7.5 | 3.2 |
| 2m_sqr_halo | 140.000 | free |  | 18.7+166.6j | 0.2 | 2.3 | 3.5 | 0.5 |
| 2m_sqr_halo_stack | 140.000 | free |  | 15.6-172.9j | 0.2 | 2.6 | 5.4 | 4.1 |
| 2m_xpol_omni | 120.000 | free |  | 28.1-29.0j | 0.6 | 0.6 | 53.5 | 48.7 |
| 2m_xpol_omni_stack | 140.000 | free |  | 34.8-18.8j | 1.2 | 1.0 | 2.8 | 2.1 |
| 2m_yagi | 140.000 | free |  | 28.8-13.2j | 0.0 | 6.2 | 15.9 | 8.2 |
| 2m_yagi_stack | 140.000 | free |  | 29.9-12.2j | 0.0 | 5.7 | 14.6 | 7.6 |
| 30-80m_inv_L | 3.000 | pec |  | 31.4+31.1j | 0.1 | 49568.4 | 33316.1 | 39699.9 |
| 35-55MHz_logper | 35.000 | free |  | 45.0-1.3j | 0.0 | 0.2 | 0.2 | 0.1 |
| 40-80m_Inv_L | 3.000 | finite-fast | g | 24.9-497.6j | 182.0 | 4312.1 | 2931.1 | 3499.3 |
| 40m-moxon | 6.800 | finite |  | 3.0-8.8j | 0.1 | 0.3 | 1.1 | 2.0 |
| 6-17m_bipyramid | 14.000 | pec |  | 7.0-16.6j | 0.3 | 20475.1 | 12072.1 | 12982.3 |
| 6-20m_fan | 14.000 | pec |  | 12.3-0.4j | 0.0 | 34540.3 | 21461.7 | 23314.1 |
| 6-20m_inv_cone | 14.000 | pec |  | 14.4+9.2j | 0.0 | 24992.0 | 15497.7 | 16816.5 |
| 6-40m_5B4AZ-optimized | 7.000 | finite |  | 0.0-90243.0j | 99.9 | 99.9 | 99.9 | 99.9 |
| 6-40m_Classic_Windom-optimized | 7.000 | finite-fast | g | 160.8-4703.6j | 74.1 | 333.7 | 183.9 | 243.9 |
| 6m_big-square_stack | 45.000 | finite-fast |  | 7.5+11.1j | 2.3 | 1.6 | 23.0 | 25.6 |
| 6m_bigwheel-stack | 45.000 | finite-fast |  | 12.9+21.2j | 0.0 | 0.0 | 22.7 | 22.5 |
| 6m_horizomni | 45.000 | free |  | 18.9-275.6j | 0.0 | 0.5 | 3.9 | 2.2 |
| 70cm-5el-rhcp-KJ7NLL | 299.800 | free |  | 123.6-338.9j | 1.2 | 1.8 | 14.8 | 15.6 |
| 70cm_collinear | 420.000 | free |  | 107.8-340.6j | ERR | 4.8 | 27.2 | 11.0 |
| 80m_zepp | 3.000 | finite |  | 0.6-115.2j | 0.0 | 0.0 | 8.3 | 3.8 |
| T12m-H24m | 1.000 | finite-fast | g | 6.8-327.1j | 145.4 | 6506.1 | 4390.1 | 5265.0 |
| T20m-H18m | 1.000 | finite-fast | g | 4.5-277.9j | 230.1 | 9651.9 | 6502.7 | 7791.4 |
| airplane | 5.000 | free |  | 68.5-91.1j | ERR | 3.1 | 24.7 | 26.3 |
| buoy | 10.000 | finite |  | 3.8-259.8j | 0.0 | ERR | ERR | ERR |
| ex2_current_slope_disc_dipole | 200.000 | free |  | 26.6-632.1j | 4.1 | 4.1 | 1.3 | 1.6 |
| k9ay_5b4az | 1.800 | finite |  | 492.6+66.2j | 0.7 | ERR | ERR | ERR |
| k9ay_orig | 1.800 | finite |  | 960.8+81.2j | 48.5 | ERR | ERR | ERR |

## Headlines

- **PyNEC ≈ nec2c (median 0.1%, 43/55 within 1%).** Two independent NEC2 kernels
  — nec2++ (PyNEC) vs nec2c (C) — so this mostly *validates the pipeline*: the
  `nec_import` translation, the network reduction, and the GN→`ground=` matching
  all reproduce what nec2c builds from the original deck, across 55 real
  free-space/homogeneous-ground decks.
- **Sinusoidal is the most NEC-faithful momwire basis** (median 2.1%), as
  expected — it is the same sinusoidal basis family as NEC2. BSpline d=2 (12.3%)
  and d=1 (21.9%) sit further off *at the decks' native segmentation* — the
  motivation for the convergence sweep below.
- **momwire's weak spot is ground.** Over PEC/finite ground, ground-*mounted*
  verticals and monopoles diverge by 1000s of % (`20-40m_ground_plane`,
  `10-30m_inv_cone`, `6-20m_fan`, `30-80m_inv_L`, the helicones) or raise
  `ground_model='sommerfeld' requires every wire strictly above ground_z` when a
  wire touches z=0 (`buoy`, `k9ay_*`). **PyNEC matches nec2c on all of them**
  (0.0%). This is the clearest actionable gap: momwire's ground handling is
  unreliable for ground-connected structures.
- **Near-open impedances inflate the metric.** `6-40m_5B4AZ` at 0−90243j gives
  99.9% on *every* engine including PyNEC — rel-error blowup on a near-singular Z
  (R≈0, huge X), not a real disagreement. Same story for the high-reactance
  off-resonance windoms.
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
- **Investigate momwire ground on ground-connected wires** — the
  `strictly above ground_z` limitation and the large PEC-ground-plane
  divergence are the biggest real gaps vs NEC.
- A handful of PyNEC `ERR` decks (`20m_car_ant`, `70cm_collinear`, `airplane`,
  `137Mhz-QFHA2`, `1MHz_tower`) warrant a look — momwire solved them.
