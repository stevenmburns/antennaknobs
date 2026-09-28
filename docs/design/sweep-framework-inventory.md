# Sweep inventory, with citations (antennaknobs v0.90.0, main @ 201fa89e1)

The cited source for §1 of `sweep-framework.md`. It was taken from the code
on 2026-09-27 and records facts only. Line numbers are as of that commit.

Paths: `PKG` = `src/antennaknobs`, `WEB` = `PKG/web`, `FE` =
`PKG/web/frontend/src`, `DOCS` = `site/src/content/docs/reference`.

## 1. Sweeps

### 1a. Summary

| | Frequency sweep | Freq refinement (#744) | Param sweep, density | Param sweep, knob |
|---|---|---|---|---|
| Endpoint | `POST /sweep` (WEB/server.py:2018) | `/sweep`, body `_refine: true` (FE/components/session/useAnalysisRunners.ts:874-886) | `POST /param_sweep` (server.py:2395); `/converge` is an alias (2424-2447) | same |
| Server path | momwire: batched `sweep_ex.momwire_sweep`, adaptive chunks aimed at `_CHUNK_TARGET_MS=500` (server.py:195, 2180-2263). External engines: per point, `_sweep_at` / `_sweep_at_multifeed` (2092-2166) | same generator | `_param_sweep_stream` (2272-2392). Per point: `request_at(req, param, value)` (WEB/param_sweep.py:84-88), then `_solve_z_only` (server.py:2244-2269) | same |
| Lane kind | `sweep` (2058, 2120, 2213) | `sweep_refine` (2058) | `converge` (2348) | `converge` |
| Lane priority (WEB/lane.py:28-43) | 2 | 3 | 2 | 2 |
| In `SAME_KIND_SUPERSEDES` (lane.py:59-61) | yes | no, so a refinement cannot kill its base (51-58) | yes | yes |
| Runs when | `autoSim && sweepEnabled && sweepResident && active` (useAnalysisRunners.ts:466). `sweepResident` = smith, gamma or vswr pinned or active (FE/components/session/DesignSession.tsx:1366-1368) | tail of a completed base sweep with refine on (useAnalysisRunners.ts:803-810); re-armed when the resident projections grow (522-559) | `(convergeEnabled && convergeResident) \|\| paramViewResident` (567); `auto: true` (DesignSession.tsx:2057) | same, and it must be armed: `auto: false`; `paramSweepArmedRef === paramSweepSig` (useAnalysisRunners.ts:587). Armed by `armParamSweep` or `runParamSweepNow` (1160-1172; DesignSession.tsx:2075-2086, 2581-2590) |
| Dwell | 500 ms (474) | 500 ms (84) | 500 ms (616) | 500 ms |
| x grid | `sweepGrid(resolveSweepRange(...).range, defaultSweepPoints(...))` (742-745; FE/lib/sweep.ts:176-283) | `refineSweepFreqs` (FE/lib/refine.ts:409-429) | `DENSITY_LADDER` [8,12,17,24,34,48,68] (FE/lib/paramSweep.ts:16, 155-176) | lin or geometric; integer knobs rounded and deduplicated (162-175); default is the knob's min..max, else ±20 %, 11 points (118-123) |
| Extras | `fixed_frequency_advisories` (server.py:2074-2076, 2265-2268) | none | Richardson Z* (client, per feed; useAnalysisRunners.ts:1040-1051); `gap_fed_advisory` (server.py:2382-2388; param_sweep.py:146-173) | none (paramSweep.ts:186; param_sweep.py:153) |
| Failed point, server | `{error}`, then the stream ends (server.py:2143-2153, 2224-2237) | same | `{param,value,error}`, then continue (2354-2369) | same |
| Failed point, client | `console.error`; points already landed are kept (useAnalysisRunners.ts:144-147); no refinement follows (123, 784-787) | same | dropped (1025); non-finite Z dropped (1028); an HTTP error shows as the view's refusal note, with "Solve anyway" on a 403 (985-998; DesignSession.tsx:2621-2633) | same |
| Stop / Run | none; phases idle/queued/running/refining (1204-1210) | "refining" | Stop keeps the partial points (1148-1156); Run (1160-1166) | same, plus stale |
| Server cache | `_SWEEP_Z_CACHE`, key (design_key, quantised freq), max 4096 (server.py:1316-1356, 1411-1482) | always read (2065) | none (2244-2269) | none |

### 1b. Signatures and exemptions (useAnalysisRunners.ts)

Exemption lists:

- `DISPLAY_ONLY_EXEMPT` = `az_elev_deg`, `elev_az_deg`, `z0_ohms` (57).
- `IMPEDANCE_ANALYSIS_EXEMPT` adds `terrain` (63).
- `FREQ_SWEEP_EXEMPT` adds `measurement_freq_mhz` (76; #1755; rationale at 65-75).

Signatures:

- Parameter sweep: `solveSignature(req, {exempt:[...IMPEDANCE_ANALYSIS_EXEMPT, param]}) + JSON.stringify([param, values])` (331-334).
- Frequency sweep: `solveSignature(req, {exempt: FREQ_SWEEP_EXEMPT})` (335). The effect deps add `sweepRangeKey` (318) and the enable, residency, slot and approval states (488-511).

Metadata and server blocklist:

- `METADATA_EXEMPT`: FE/lib/solveSignature.ts:387-400.
- The server's `_CACHE_KEY_BLOCKLIST` (server.py:1566-1602) also blocks `_refine`, `reuse_cached_z`, the cut angles and `z0_ohms`.
- `_sweep_design_key` keeps `measurement_freq_mhz` (1411-1422).

Cache reads (`_base_sweep_may_read_cache`, 1424-1446):

- a base sweep reads the cache only with `reuse_cached_z`, on a non-user design, and from the same session;
- the client sets `reuse_cached_z` for non-user designs (useAnalysisRunners.ts:756-758);
- a designs refresh evicts the user-design entries (server.py:1373-1402).

Invalidation:

- The frequency sweep is nulled on every effect run (456-461).
- The parameter sweep is blanked, except that a knob sweep for the same param is kept `stale` (587-605).
- z0 is not a dependency. Refinement reads it per round (271-279, 853-860).
- `_track` (DesignSession.tsx:1241-1248) is in no exemption list and not in the server blocklist.

### 1c. The frequency x grid (FE/lib/sweep.ts)

Range precedence:

1. session edit (176-182);
2. file `sweep_range` (137-141);
3. design `sweep_range`, else `meas_freq_range_mhz` (138-145);
4. `sweep_policy` band or factors (147-161);
5. default ×0.8–×1.25, log (162-171).

A custom measurement band skips 2-3 (137).

Points:

- the range's own density if it has one (232-248);
- else 17 with refine on (`SWEEP_BASE_N`, 354), 21 on Sommerfeld ground, 41 otherwise (185-207);
- capped at 500 (100, 254-267).

The resolved range is the dial's range (DesignSession.tsx:1429-1444, 2143).

### 1d. Refinement (#744)

- **Budgets and tolerance:** 48 in total and 12 per round (sweep.ts:361-368); tolerance 0.003 (refine.ts:62).
- **Planning:** in display space, over the resident vswr/gamma/smith projections, using the drawn domain and the SWR threshold (refine.ts:337-407); x is linear in MHz (330-336).
- **Merge:** `mergeSweepPoints` (sweep.ts:381-417).
- **Settling:** `sweepSettled` is false while refining (useAnalysisRunners.ts:347-356). SweepChart connects its dots only when settled (FE/components/charts/SweepChart.tsx:414-424); Smith uses `refineEnabled && sweepSettled` (FE/components/results/viewRegistry.tsx:274).

### 1e. Other sweep-like jobs

- **Pattern-cut refinement:** `POST /cuts` (server.py:2937), no lane. Budget 120 in total and 40 per round, 400 ms dwell (FE/components/charts/cuts.ts:335-350); on-screen cuts only (536-551).
- **Norm check:** `/norm_check`, lane `norm_check`, not gated on residency (useAnalysisRunners.ts:639-675, 1066-1110).
- **NEC `rp`:** `/pattern`, lane `pattern`, pynec/nec5 only (681-722).
- **`/pattern_metrics`:** lane `pattern_metrics` (server.py:3036; lane.py:47-49).
- **The optimizer:** `/optimize`, outside the lane (server.py:1620-1625). Its per-evaluation Z is a moving dot; no trace is kept (DesignSession.tsx:2650-2652; FE/components/session/useOptimizer.ts:261).
- **Cancel:** `abortInFlight` (useAnalysisRunners.ts:1174-1202); `lane.cancel_all` (lane.py:161-179).

## 2. Views

The view registry is FE/lib/view.ts:44-104; views render through FE/components/results/viewRegistry.tsx:186-359.

| View | Plots | Axes | Controls | Readouts | Feeds |
|---|---|---|---|---|---|
| `vswr` (viewRegistry.tsx:310-325) | SWR(f) and the live marker | 1−1/SWR (default), ρ, presets, custom; no Auto (FE/lib/sweepAxis.ts:21-25, 36-37, 85-131) | y-axis popover (FE/components/charts/SweepRangePopover.tsx:29-40, 100-190); freq-sweep checkbox on desktop (DesignSession.tsx:2797-2802) | threshold, shading, "2:1 BW" (SweepChart.tsx:275-289, 400-406); status and progress (FE/components/charts/sweepStatus.ts:14-26) | one line each |
| `gamma` (291-308) | 20·log10\|Γ\| | Auto (grow-only while live; SweepChart.tsx:62-121, 255), floors, custom | same | same | same |
| `smith` (255-278) | freq locus and markers (FE/components/charts/SmithChart.tsx:385-487); param trail, Z* (599-730); measured (514-578) | zoom/pan (113-121) | FE/components/results/StageOverlays.tsx:261-330 | status (732-741), caption (885-895), Z* summary (870-882) | all |
| `zparam` (330-358) | R and X vs param, Z*, guide, references (FE/components/charts/ZParamChart.tsx:26-38, 101-127) | lin/log (DesignSession.tsx:2093); R and X Auto or fixed (FE/lib/paramSweep.ts:207-254) | FE/components/results/ZParamControls.tsx; DesignSession.tsx:2576-2612; FE/components/charts/ZParamChart.tsx:486-545 | hover (436-445), status (133-145) | port 0 (38) |

- **Pins:** 6 (`PIN_CAP`, FE/components/session/useViewPrefs.ts:39). The grid shows 4 (370-386).
- **Thumbnails** get the same data, and no pins or callbacks (DesignSession.tsx:3014-3049).
- **One dataset each** (useAnalysisRunners.ts:338, 369).
- **The Smith trail** is drawn whenever `paramSweep` is non-null (DesignSession.tsx:2655, 3025; SmithChart.tsx:599). Only ZParamChart dims when stale (ZParamChart.tsx:321-323).
- **Desktop layout:** `ZParamStage` (FE/components/results/ZParamStage.tsx:4-27; FE/lib/zparamLayout.ts).
- **Phone:** carousel (view.ts:134-136); gear-menu switches (FE/components/session/SessionGearMenu.tsx:163-170, 257-305); zparam chart size (DesignSession.tsx:125, 2913-2919).

## 3. Comparison

- **Pattern pins** (FE/components/charts/types.ts:57-70; FE/App.tsx:97-139; PinsContext at DesignSession.tsx:911-920):
  - captures the whole SolveResponse and a label (DesignSession.tsx:1686-1695);
  - 4 colour slots (App.tsx:107-116; FE/components/charts/palette.ts:17);
  - `/pattern_metrics` at pin time (App.tsx:117-119); cuts recomputed from the pinned solve (cuts.ts:236-275, 526-560);
  - memory only (App.tsx:100).
- **Compare table:** FE/components/results/PatternCompareTable.tsx:17-24, 60-70; its live metrics are debounced (DesignSession.tsx:1697-1711).
- **Measured overlay:**
  - data model `MeasuredData` (FE/lib/api.ts:459-465), per session (DesignSession.tsx:892-895);
  - loaded through `POST /measured` (FE/components/session/sessionActions.ts:68-101; server.py:2863);
  - Smith only (SmithChart.tsx:514-578; viewRegistry.tsx:291-325);
  - kept across a design switch, cleared by "clear" (DesignSession.tsx:2240, 2744).
- **Slots:** FE/components/session/useSolverSlots.ts:16-60. `activeSlot` is used at DesignSession.tsx:476, 2436 and 2519 only. There is no cross-slot comparison.
- **Stale knob sweep:** useAnalysisRunners.ts:587-598. The spec resets on a design switch (DesignSession.tsx:860-872).

## 4. Settings and state

- **`[switches]`:** WEB/settings.py:58-68, FE/lib/settings.ts:14-35. Seeded into the session at DesignSession.tsx:846-849 and saved at 1065-1066.
- **`akb.viewPrefs.v1`:** useViewPrefs.ts:41, 65-82, sparse write 233-264. Defaults at sweepAxis.ts:53-55, 90.
- **`antennaknobs.refineEnabled`:** DesignSession.tsx:874-891.
- **Tuning keys (FE/lib/tuning.ts):** sweep.ts:354, 361; cuts.ts:341; refine.ts:62.
- **`akb.optimizerZo.v1`:** FE/lib/zoOverride.ts:25.
- **Session-only state:** DesignSession.tsx:524-529, 854-859, 892-895.
- **Caps:**
  - WEB/cost.py:51, 65, 94-103;
  - sweep.ts:100;
  - paramSweep.ts:18-24.

## 5. The CLI (PKG/cli.py:1239-1527, PKG/sweep.py)

Flags:

- `--engine`, several engines allowed: 1028-1070, 1240.
- `--param`: 1243-1251.
- The range defaults: sweep.py:524-534.
- `--npoints`: cli.py:1262-1269, 1391.
- The chart options: 1270-1376.
- The refusals: `_check_chart_flags` (460-529), 1400-1453, 1427-1432.

The drawing functions:

- **Impedance chart:** `sweep()` (sweep.py:1015-1383). It solves per point, frequency included (1098-1107).
- **Panels and overlay:** `_rx_panels` (212-291) and `_rx_overlay` (429+). Port 0 only, with no measured overlay (1253-1275).
- **`sweep_swr`:** 564-641. It is vectorized only for freq (594-603) and plots reflection as 10·log10|Γ| (610-616).
- **`sweep_gain`** (687-720) and **`sweep_patterns`** (649-684).
- **Density study, `_sweep_convergence`:** 850-1012.
  - the ladder: 756, 759-780;
  - `N_ach`: 783-805;
  - the table: 812-847;
  - Z*: 723-753;
  - plotted against achieved N: 996-1008;
  - its Smith drawing: 937-982.

Related subcommands:

- `compare_patterns`: cli.py:1955.
- `ladder`: 2001.
- `capture`: 1768.
- `fit`: 1635.

## 6. User docs

- **DOCS/web.md:**
  - 91-125: the range precedence;
  - 126+: settings.toml;
  - 218-275: the output stage;
  - ~300-340: pins, layout and residency;
  - 396-434: adaptive resolution;
  - 822+: the lane;
  - 1135-1162: the convergence sweep;
  - 1164-1230: Z vs parameter;
  - 1232-1264: the measured overlay;
  - 1266-1285: sessions;
  - 1287-1357: comparing patterns.
- **DOCS/cli.md:**
  - 80-110: sweeps;
  - 111-158: R/X charts;
  - 217-242: capture;
  - 243-283: the measured overlay;
  - 284+: fit;
  - 420-502: convergence studies;
  - 540-584: comparing engines;
  - 585-600: the refinement ladder.

## 7. Limits and discrepancies

The limits:

- same-kind supersession (lane.py:59-61, 193-197);
- one dataset each (useAnalysisRunners.ts:338, 369);
- sweeps on the active slot only (docs/design/z-vs-param-view.md:72-76, 139-141; DOCS/web.md:1215-1216);
- enum, bool, group and freq-linked knobs can't be swept (paramSweep.ts:94-96; `z-vs-param-view.md:16-21`);
- no parameter-sweep refinement (78-82);
- port 0 only (ZParamChart.tsx:38; sweep.py:867-869, 1253-1275);
- pins for patterns only, in memory (App.tsx:100);
- the measured overlay is per session and Smith-only;
- no Stop/Run on the frequency sweep;
- frequency-sweep refusals go to the console only (useAnalysisRunners.ts:123, 144-147, 784-787);
- the 500-point cap;
- `/optimize` is not lane-scheduled.

Discrepancies: as in `sweep-framework.md` §1.6, with sources:

1. The options note, lines 28-30, against SmithChart.tsx:514-578 and SweepChart.tsx:122-170.
2. The note, line 20, against useAnalysisRunners.ts:1025 and paramSweep.ts:56-85.
3. DesignSession.tsx:2655 and SmithChart.tsx:599, against DOCS/web.md:1153-1161.
4. useAnalysisRunners.ts:76 against server.py:1411-1422.
5. DOCS/cli.md:94-96 against sweep.py:594-596, 1098-1107.
6. sweep.py:752 and DOCS/cli.md:436.
7. DOCS/web.md at about lines 236 and 1255.
8. useViewPrefs.ts:77-79 against sweepAxis.ts:90.
9. sweep.py:610-616 against FE/lib/math.ts:29-32.
10. sweep.py:723-753 against FE/lib/math.ts:34-45.
