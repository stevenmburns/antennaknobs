# Sweep framework: the 2-D map in the workbench (design note)

Status: **draft for Steve's review, 2026-10-05.** Inventory, cost, options
and a recommendation per axis. No code. The questions at the end are
numbered and each takes a line.

Code citations are to `main` at `72f7477f8` (v0.97.1). Frontend paths are
under `src/antennaknobs/web/frontend/src/`; everything else is under
`src/antennaknobs/`. Timings are from Skylake (`192.168.1.172`), a fresh
clone of that commit, momwire from PyPI.

## 1. Inventory

### What the CLI map computes

- **The spec.** A map is an `an.Analysis` whose `sweep` is a pair of
  `Sweep`s (`analyses.py:1199`), drawn by `an.Map()` (`analyses.py:495`):
  "|Γ| on the session's z0 over (x, y), with the `Ref` lines as contours of
  R and X". Sweeping one knob on both axes is refused
  (`analyses.py:1735`). A map draws `Map` and `Table` only; a curve view
  on a pair is refused by name (`analysis_run.py:135-144`).
- **The grid.** Each axis is `knob_xs` (`analysis_run.py:623`): the spec's
  values, else `gen_xs` over the spec's or the knob's own range, with
  `DEFAULT_POINTS = 11` when no count is given (`analyses.py:64`). So a
  map with no counts is 11 × 11 = 121 solves. A frequency axis goes
  through `frequency_xs` instead (`analysis_run.py:660`).
- **The solve.** `solve_map` (`analysis_run.py:925`): for each y, set y on
  the cell's builder and run x's own line solve (`_solve_line`,
  `analysis_run.py:914`). For a knob x that is `sweep._solve_at`
  (`sweep.py:1141`), one build and solve per point. Z is
  `(len(ys), len(xs))`, port 0. Solves per map = nx · ny, per cell.
- **Crosses.** A map multiplies with crosses like any analysis: one grid per
  cell, one panel per cell, at most 3 panels a row (`_run_map`,
  `analysis_run.py:1601`; `_map_figure`, `analysis_run.py:1678`). The curve
  cap (`CURVE_CAP = 6`, `analyses.py:61`) bounds the panels.
- **The drawing.** `pcolormesh` of |Γ| = |(Z − z0)/(Z + z0)|, shading
  "nearest", `viridis_r`, fixed 0..1 (`analysis_run.py:1697`).
- **The contours** (`map_contours`, `analysis_run.py:1669`): X = each
  `Ref.x` (black, solid) and R = each `Ref.r` (orange/red/magenta/pink,
  dashed). With no `Ref`, X = 0 and R = z0. A level the grid never
  crosses is kept in the legend as "(not reached)", not dropped.
  `Ref.swr` is not drawn on a map.
- **The text.** One line per cell: the grid's least |Γ|, its SWR, where,
  and Z there. It is the best grid node, "not an optimum between cells"
  (`best_cell_line`, `analysis_run.py:1640`). The `Table` view prints every
  node, y outer, x inner. `--csv` refuses a map (`analysis_run.py:960`).

**`dipoles.invvee`'s "tuning map"** (`designs/dipoles/invvee.py:117,140`):
length_factor 0.90..1.06 × 33 by angle_deg 0..60 × 25, `Ref(r=(50, 75),
x=(0,))`, no cross. So **825 solves, one panel, three contours** (X = 0,
R = 50, R = 75). Measured: least |Γ| 0.0235 (SWR 1.05) at length_factor
0.975, angle 30°, Z = 50.96 − j2.17.

### What the workbench does today when the map is picked

Nothing runs. The map is greyed in the picker with its reason:

- `/analyses` serves `{runs: False, why}` (`web/analyses_offer.py:684-693`)
  because `gaps` appends `"a two-sweep map: not in the workbench yet
  (sweep-framework step 5)"` for any two-sweep analysis
  (`web/analyses_offer.py:231`; `_VIEW_STEP = {an.Map: 5}` at `:157`).
- `runOnPickKind` returns null for anything that does not run
  (`lib/analysisChart.ts:274-276`), so a pick starts nothing.
- `"map"` is a valid `[workbench.run_on_pick]` key, default false
  (`web/settings.py:163`; `lib/settings.ts:68`), so a file can say it now.
  The gear menu leaves its switch out on purpose: "a switch for it would
  do nothing; a save passes the file's value through"
  (`components/session/SessionGearMenu.tsx:19-22`).

### What the workbench has that a map can reuse

- **`/param_sweep`** streams one NDJSON record per value of one knob, at the
  request's other fields (`web/server.py:2772-2909`). Each point takes its
  own lane turn, checks disconnect, and reports a failed point without
  ending the sweep. Admission is once per request, by point count
  (`web/server.py:2803`).
- **The lane.** One per session, priority-ordered: the live solve (0)
  always goes before a sweep point (2) (`web/lane.py:28-40`). A turn
  carrying a generation older than the lane's is superseded; a gen-less
  turn is not (`web/lane.py:162-180`). Cancel stops everything
  (`web/lane.py:182`). Named streams (`"sweep:c1r2"`) let several runs of
  one kind coexist (`web/lane.py:69-77`).
- **The client runner** (`components/session/useParamSweep.ts`): 500 ms
  dwell (`:155`), Stop keeps the partial curve, a change of inputs keeps
  the old curve dimmed as stale, a dropped stream is re-asked up to twice
  (`PARAM_SWEEP_REISSUES`, `:56`), **from the start**. The request carries
  `_gen` (`:205`). Its signature exempts the swept knob
  (`components/session/useAnalysisRunners.ts:94`), so dragging that knob
  does not stale the curve.
- **A chart holds six fixed runner pairs**, one per curve
  (`CELL_RUNNERS = 6`, `components/session/useChartCells.ts:54`). A map's
  25 rows do not fit that shape.
- **Every chart is hand-drawn on a canvas**; the frontend has no chart
  library (only react and react-dom in `package.json`). There is no
  contour code and no sequential colour map; the nearest is the current
  heat ramp (`components/charts/palette.ts:170`).
- **Phones** use the rail layout, one view at a time
  (`components/session/DesignSession.tsx:1269`).

## 2. Cost

### Solves per map

| design | grid | solves | per point (Skylake) | one map |
|---|---|---|---|---|
| dipoles.invvee, its tuning map | 33 × 25 | 825 | 5.5 ms CLI; 6–8.5 ms via `/param_sweep` | 4.5 s CLI solve (6.7 s wall); ~5–7 s served |
| dipoles.invvee, a default pair | 11 × 11 | 121 | same | < 1 s |
| beams.moxon, default pair | 11 × 11 | 121 | 0.02 s | ~2.4 s |
| beams.yagi, default pair | 11 × 11 | 121 | 0.11 s | ~13 s |
| verticals.buried_radial_vertical, default pair | 11 × 11 | 121 | 0.61 s | ~74 s |
| arrays.bowtie4x4, default pair | 11 × 11 | 121 | 1.19 s | ~2.4 min |
| the last two at the tuning map's 33 × 25 | | 825 | | 8.4 min; 16 min |

The invvee row is single-threaded (`OMP_NUM_THREADS=1`), 825 points. The
other per-point times are 3-point `/param_sweep` runs through FastAPI's
TestClient at default threading on an 8-core box, so treat them as ±50 %.
The hosted box was not measured.

### Hosted admission

- `MAX_SWEEP_POINTS = 500`, checked once per request against its point
  count (`web/cost.py:52,130`). **Invvee's own tuning map (825) is over
  it.** Served as one request it is refused hosted; served as 25 row
  requests of 33 each, every row passes and the 500 cap bounds nothing.
- The 60 s budget is per solve turn **and only for an opened deck**
  (`web/decks.py:164`; `_deck_turn`, `web/server.py:1977`). An opened deck's
  map takes the server-wide deck slot once per point, so another visitor's
  deck can interleave between points, and none of its points can exceed
  60 s. A catalog design's map has no time bound at all today.
- Precedent for a wall-time bound on a batch: one multi-band optimize run
  is capped at `MAX_OPT_SECONDS = 120` hosted and answers with the best so
  far (`web/cost.py:58`; `web/server.py:4480`).

### Streaming, partial drawing, cancel

- A per-point stream gives a partial grid for free: a cell paints when its
  record lands.
- Disconnect stops the server at the next point (`web/server.py:2816`), so
  Stop and closing the chart both work as they do for a knob sweep.
- **Trap:** a turn carrying `_gen` is superseded by any newer live solve
  (`web/lane.py:162-180`). Dragging x or y is exempt from the signature,
  so the client keeps the run, but the server ends the stream at the next
  point, and today's runner re-asks it from the start. On a 1-second map
  that is invisible. On an 8-minute map it means a drag throws the work
  away.

## 3. Options

### (a) Where the grid is computed and how it streams

1. **Client rows over `/param_sweep`.** One request per y, with y set as a
   request field. No server change. But admission sees 33, never 825
   (above). The chart sequences 25 streams outside the six runner pairs.
   Resuming a dropped row is per row. Frequency on x would mean `/sweep`
   per row instead, a different endpoint with its own chunking and
   refinement.
2. **A `/map` endpoint, one stream per map, one record per point.** It
   takes the solve request and the two axes, `{x: {param, values}, y:
   {param, values}}`. It is admitted once at nx · ny, and streams
   `{i, j, z_re, z_im, n_seg}` y outer, x inner (the CLI's table order),
   then `{done}`. The per-point body is `_param_sweep_stream`'s loop,
   extracted and shared, so the point solve is the same function.
   `/analyses` serves the axes' values from `knob_xs`, the one place both
   tools read, as it does for a knob sweep.
3. **One request per point.** 825 HTTP round trips and admissions. No
   advantage over 2.
4. **Reuse the chart's runner pairs.** Six runners for 25 rows means the
   chart re-arms them in turns. That bends a structure built for curves.

**Generation.** (i) Map points are gen-less, like a compare-table row: a
drag never supersedes them, and only disconnect, Stop or Cancel stops them.
(ii) Keep `_gen` and have the client resume from the first missing point.
The two do not exclude each other.

**Recommendation: 2, with (i) and resume.** One admission tells the truth
about cost. One stream is one runner. The point solve is shared code, so
the oracle holds by construction. Gen-less points mean dragging x or y only
moves the marker. Any other input change makes the client abort the
stream, so the server still stops. Resume means `/map` takes a `from` flat
index, and a dropped stream continues where it stopped.

**Hosted admission options:**
- (h1) hold maps to `MAX_SWEEP_POINTS`, so invvee's map is greyed hosted;
- (h2) a map cap of its own (proposed 1000 points) **plus** a wall-time
  budget like optimize's 120 s, past which the map stops, keeps what it
  drew, and says so;
- (h3) the budget alone.

**Recommendation: (h2).** Invvee's map should run hosted: about 6 s on
Skylake, so well inside 120 s even on a box 2–3× slower. A
bowtie4x4-class map stops at about 100 of 121 points and says so.

**Solve order:** (o1) rows, y outer (the CLI's order); (o2) coarse first:
every 4th node, then every 2nd, then the rest. Values are independent of
order (each point is its own build). (o2) shows the whole map's shape
early and makes a budget cut leave a coarse full map rather than half a
map. It costs a fill rule for unsolved cells. **Recommendation: (o1)
first**; (o2) as a later unit if the budget cuts prove common.

### (b) The drawing

- **Heatmap.** Canvas, one rectangle per node centred on it (the CLI's
  "nearest" shading), so a cell is a solve, not an interpolation. An
  unsolved node is the chart background, so a partial map reads as
  partial.
- **Colour quantity.**
  - |Γ| on z0, 0..1: the CLI's, and exactly the Swr view's ρ scale.
  - 1 − 1/SWR: the Swr view's 1–∞ scale.
  - SWR clipped at some value: rejected, because it needs an arbitrary
    top.

  Both kept choices reuse the Swr scale names (`an.Swr(scale=...)`:
  "rho", "reciprocal"). Z is z0-free, so a z0 change re-colours without
  re-solving. **Recommendation:** |Γ| by default, with the reciprocal
  scale as the chart's alternative.
- **Colour map.** (1) `viridis_r`, as the CLI draws it: perceptually
  uniform, reads in both themes, and colour-blind safe. (2) The current
  heat ramp: on-brand, but not uniform, so equal steps of |Γ| do not look
  equal. **Recommendation: (1)**, as a fixed table of about 16 stops in
  `palette.ts`, so the CLI and the workbench show the same picture.
- **Contours.** The CLI's rule, exactly: `Ref.x` solid in the foreground
  colour, `Ref.r` dashed in a cycling palette, X = 0 and R = z0 when no
  `Ref`, and "(not reached)" in the legend. Marching squares with linear
  interpolation (about 100 lines of TS), redrawn as rows land.
  `matplotlib`'s contour is the same algorithm (contourpy), so the
  vertices can be checked against it.
- **The live marker** at the current (x, y) knob values: a ring, filled
  with the live solve's |Γ| colour. Off the grid's span, it is a clamped
  arrow at the edge, as the knob chart does for an off-span live value.
- **Hover readout:** the nearest node's x, y, R, X, SWR and |Γ|, with no
  interpolation, matching `best_cell_line`'s rule.
- **The legend line:** the CLI's "least |Γ| … at …" for the grid as drawn
  so far.
- **Click to set the knobs.**
  - (k1) never: hover only;
  - (k2) a click selects a node, and its readout has a "set knobs here"
    button;
  - (k3) a click sets both knobs.

  Setting knobs writes inputs from the right side. The optimizer already
  does that, but by an explicit act. **Recommendation: (k2).** It is an
  explicit act, and it is the obvious next step after reading the map
  ("tune to here, then optimise").

### (c) The controls on the chart

- Two **axis range editors**, x and y, each the knob chart's own (lo, hi,
  points, spacing). An edit marks the pick edited and ↺ restores it, as
  `pickedEdited` does for a knob sweep (`lib/analysisChart.ts:472-480`).
- A **cost line** beside Run: "825 solves · ~6 s", from the points and the
  live solve's own time. Over the hosted cap, Run is disabled and the line
  says why.
- **Quantity:** |Γ| / 1 − 1/SWR (above).
- **Engine and ground.** The step-5 charts carry slot and ground
  checkboxes. On a map each ticked slot is another whole grid.
  **Recommendation for v1:** one slot and one ground slot, as radios
  defaulting to the active ones. A map with a cross is greyed with its
  reason (see question 9).
- **Not on the chart in v1:** editing the contour levels (they are the
  `.py`'s `Ref`) and swapping axes.

### (d) Dwell and Run

- Run on pick: already a key, default false (`web/settings.py:163`). The
  menu gains the switch when the map draws.
- **Dwell: default off.** The switch stays on the chart, per the step-5
  rule, so a cheap map (invvee: 6 s) can follow the knobs if the viewer
  wants.
- **Dragging x or y** moves the marker and leaves the map current: both
  axes are exempt from its signature, as the swept knob is today.
- **Any other input** (another knob, the slot, the ground, the frequency)
  dims the map as stale ("re-run?"), as a knob sweep does. Changing z0
  re-colours the map without staling it.

### (e) Pins, keep, `to_code`

- **Pins.** A pin is Z along one x (`sweep-framework-pins.md`), and a map
  has no such curve.
  - (p1) No map pins in v1: Pin is disabled with its reason.
  - (p2) A map pin holds the Z grid and draws as dashed contours over a
    live map with the same two knobs. This shows "where X = 0 moved"
    between engines or designs, which is the map's comparison.
  - (p3) Pin a row or column as a knob-sweep pin.

  **Recommendation: (p1) now, (p2) as its own later unit.**
- **Copy as analysis.** Unedited, `to_code` of the served spec already
  works. Edited, `keep.py` refuses today: "only a one-sweep chart has x
  values to keep" (`keep.py:786`). It also writes an edited one-sweep
  range as `values=`, which for a 33-point axis is a 33-number tuple.
  **Recommendation:** extend `_with_values` to take one edit per axis and
  write each as `Sweep(knob, lo, hi, points=, spacing=)`.
- **Keep as study:** no change. The tab's knobs become a state, as for any
  chart.
- **The `Table` view** of a map (825 rows in the CLI). Options: skip it by
  name ("runs without the Table view"), or a grid table. **Recommendation:
  skip it in v1.** Hover is the numbers. A CSV of the grid can come later,
  in the CLI first.

### (f) Phones

- The rail shows one view at a time, full width. On a 360 px phone, 33
  columns are about 10 px each, which reads fine.
- A tap is the hover readout. "Set knobs here" sits in that readout.
- The range editors and the quantity move into the chart's popover, as the
  Swr range does today.
- The legend goes below the plot.
- No pinch zoom in v1.

### What this constrains elsewhere

- **The deck stub (last).** NEC has no two-knob sweep card, and a geometry
  knob cannot be swept in a deck at all, so a map's deck stub is refused by
  name. Nothing here blocks that.
- **Whole-pattern metrics (#1837) and user quantities.** A map of a metric
  (F/B over two knobs) is the obvious next map. Two consequences:
  - `/map` records keep `/param_sweep`'s optional `metric` field shape
    (`web/server.py:2874-2878`), so a metric map is a new view and not a
    new endpoint;
  - the quantity control is a list, not a toggle.
- **Frequency or density as an axis.**
  - A frequency axis in the CLI solves through the vectorized
    `swr_curve`, one build per row. A per-point `/map` would not be that
    path, so it is not bit-identical by construction.
  - A density axis re-meshes per point.

  **Recommendation:** knob × knob only in v1; the others greyed with a
  reason.

## 4. Recommendation and units

**Per axis:**

| axis | choice |
|---|---|
| (a) compute | `/map`: one stream, per-point records, shared point solve, gen-less points, `from` resume |
| hosted | own cap 1000 + 120 s budget, partial kept |
| order | rows (y outer) |
| (b) drawing | canvas, nearest cells, `viridis_r`, \|Γ\| default, CLI contours, marker, hover, click → "set knobs here" |
| (c) controls | x and y range editors, cost line, quantity, one slot + one ground radio |
| (d) dwell | run on pick off; dwell off by default, switchable; x/y drags don't stale |
| (e) keep | copy as analysis writes lo/hi/points per axis; no pins in v1; Table skipped |
| (f) phones | rail, tap = readout, controls in a popover |

**Units (small PRs; CLI-first is already done):**

1. **`/map` and the offer (server only).**
   - Extract `_param_sweep_stream`'s point loop and add `/map` with
     admission (h2) and `from`.
   - `analyses_offer` serves `{runs: True, kind: "map", x: {param, values,
     log}, y: {…}, refs: {r, x}, views}`, with `knob_xs` for both axes.
   - Crosses, frequency and density axes stay greyed, each with its
     reason.
   - **Gate: the oracle.** `/map` on invvee's tuning map equals
     `analysis_run.solve_map` **bit-for-bit**, all 825 nodes, at the same
     ground, density and engine.
     - Feasibility is measured. One 33-point row through `/param_sweep`
       was bit-identical to the CLI's row on Skylake, once both sides had
       the same ground.
     - Trap: the CLI's default ground for this design matched the
       request's `ground: true`. A request with no ground (free space) was
       13 % off. Name the ground on both sides.
     - Also assert the record count is 825, so the gate cannot pass on an
       empty stream.
     - Plus: admission over the cap, the budget cut (`ANTENNAKNOBS_*`
       env), resume from `from`, and disconnect.
2. **The map chart (drawing only, fed a fixture).** `MapChart.tsx`:
   heatmap, `viridis_r` table, marching squares, legend with "(not
   reached)", marker, hover.
   - **Gate:** the contour segments on the invvee grid (a committed
     fixture written by the CLI) match contourpy's vertices to 1e-9 of the
     axis span.
   - Also: the "(not reached)" rule, and the best node equal to
     `best_cell_line`'s.
3. **The runner and the controls.** A `useMapRun` hook (stream, partial
   paint, Stop, resume, stale, x/y exempt). The chart's range editors,
   cost line, quantity and slot radios. The gear menu's map switch.
   - **Gate: a real-app drive on invvee.** Pick "tuning map", Run, and
     watch the grid fill. Drag angle_deg: the marker moves and the map
     stays current. Drag base: the map dims stale.
   - The drawn grid, read through a test hook, equals the CLI's grid
     bit-for-bit.
4. **Set knobs here, and copy as analysis with edited axes.**
   - **Gate:** `keep` round-trips (`eval(to_code(a)) == a`) for an edited
     map.
   - A drive confirms "set knobs here" puts the live solve at that node's
     Z.
5. **Later, each its own unit:** map pins as contours (p2), coarse-first
   order (o2), frequency × knob maps, crosses as panels.

Unit 2 does not depend on unit 1 (it draws a fixture), so the two can be
built in parallel.

## 5. Questions for Steve

1. Compute the grid in a new `/map` endpoint (one stream, admitted once at
   nx · ny), rather than client rows over `/param_sweep`?
2. Hosted: a map cap of its own (1000 points) plus a 120 s wall budget that
   keeps the partial map, rather than `MAX_SWEEP_POINTS` (500), which greys
   invvee's own 825-point map?
3. Solve rows in the CLI's order (y outer) for v1, with coarse-first later
   only if budget cuts are common?
4. Colour by |Γ| on z0 by default (the CLI's; the Swr view's ρ), with
   1 − 1/SWR as the chart's alternative?
5. `viridis_r` in the workbench, as the CLI draws it?
6. Clicking a node: readout plus a "set knobs here" button (k2), rather
   than readout only or set-on-click?
7. Dwell on a map: off by default but switchable, rather than no switch?
8. Dragging the x or y knob moves the marker and leaves the map current
   (gen-less points); any other input dims it stale. Agreed?
9. A map with a cross in the workbench v1: greyed with its reason, rather
   than one panel per cell as the CLI draws?
10. Frequency or density as a map axis in v1: greyed with a reason?
11. Pins: none on a map in v1, with map pins as dashed contours a later
    unit?
12. Copy as analysis for an edited map writes `Sweep(lo, hi, points=)` per
    axis, not `values=`?
13. `Ref.swr` on a map: draw the SWR threshold as a |Γ| contour, in the
    CLI and the workbench together, or leave it off as today?
14. The map's `Table` view in the workbench: skipped by name in v1 (hover
    gives the numbers)?
15. Engine and ground on a map chart: one slot and one ground slot as
    radios, not the checkboxes other charts carry?
