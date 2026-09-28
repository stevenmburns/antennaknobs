# How other interfaces handle sweeps, comparison and multiple graphs

The cited source for §2 of `sweep-framework.md`, compiled 2026-09-27. It is
description only and makes no recommendation for antennaknobs. Claims taken
from a search summary rather than the primary page are marked
*(unverified)*.

## A. Antenna and RF modelling tools

**EZNEC** ([v6 manual](https://www.eznec.com/misc/EZNEC_Printable_Manual/6.0/EZW60_User_Manual.pdf))
- The frequency sweep is a dialog: start/stop/step, or a list from a file.
- Sweep results are *file artefacts*. The manual: "calculation results from a
  frequency sweep are available only in the form of the file". The SWR graph
  is fed from `LastZ.txt`.
- Only the 2D pattern plot compares:
  - *Save Trace As* writes a `.PF` snapshot;
  - *Add Trace* overlays saved files in recalled-trace colours;
  - *Remove Trace*;
  - a data box reads the selected trace relative to the primary at the cursor.
- TraceView compares saved traces without recomputing.
- The SWR/impedance display has no overlay, and its scales are fixed.

**AutoEZ** ([ac6la.com/autoez](https://ac6la.com/autoez.html))
- A "variable sweep" is like a frequency sweep, but over geometry variables.
  Its test cases are rows on an Excel sheet.
- A Snapshot button captures a trace for overlay, "very similar to the 'Add
  Trace' feature" of EZNEC. The documented workflow is manual and serial:
  set a value, sweep, snapshot, repeat.
- Snapshots can be saved and recalled
  ([changes](https://ac6la.com/aechanges.html)).

**Zplots** ([ac6la.com/zplots1](https://ac6la.com/zplots1.html))
- Four snapshot slots: 1–2 on the left axis, 3–4 on the right.
- "Snapshot traces persist when you load new data", which makes a
  modelled-vs-measured comparison possible.

**4nec2** ([manual](https://hamwaves.com/antennas/doc/4nec2.rtf.pdf))
- Separate mechanisms: a frequency sweep (F7), a variable "Sweeper" and an
  optimizer (F12).
- One line chart (F5) serves both frequency and a variable on its x axis.
  Spline smoothing "can introduce considerable errors".
- Pattern compare holds up to 5 output files, whose theta/phi steps must
  agree. You can walk through the sweep steps or play them back.
- "Sweeper results are stored in memory only … lost" on shutdown or on a new
  input file.

**MMANA-GAL** ([basic docs](https://www.tcpsas.com/sezioneIV/MMANA-GAL/docs/MmanaGalBasic.pdf))
- Compare superimposes results saved as `.mab` files (binary snapshots).

**SimSmith** ([primer](https://www.tcpsas.com/sezioneIV/SimSmith/docs/SimSmithPrimer.pdf))
- A sweep is a *live recipe*: parameters dragged into a sweep menu, each one
  toggled. Several variables plot every combination.
- Right-clicking a sweep arc sets the parameters to that point, so the curve
  becomes a control.
- A small NormalSweepSize is used while editing; an on-demand
  ExtendedSweepSize reverts on the next edit. The author warns that
  multivariable sweeps can reach hundreds of thousands of points.
- SimNEC's own compare UI was *not verified*; only the SimSmith docs were
  read.

**xnec2c** (local manual, [xnec2c.org](https://www.xnec2c.org/))
- Toggle buttons add stacked frequency graphs. Zr/Zi share one graph with
  left and right axes.
- No overlay compares runs.
- Optimization is pushed outside: it writes CSV/Touchstone files when an
  external program edits the input file.

**Keysight ADS**
- A ParamSweep draws one trace per swept value
  ([docs](https://edadocs.software.keysight.com/display/ads2009U1/Parameter+Sweeps+and+Sweep+Plans)).
- **Tuning Store/Recall**
  ([manual](https://edadownload.software.keysight.com/eedl/ads/2011_01/pdf/optstat.pdf)):
  - *Store* saves the parameter values *and* creates dotted memory traces, with
    a name and a comment.
  - *Recall* restores the parameters, asking "Original vs Current" when the
    tuned set has changed.
  - "Memory traces are frozen. They are not reevaluated."
  - States are deleted when tuning closes.
- A "Trace History" count *(unverified)*.

**Cadence AWR** *(unverified: from search summaries)*
- Swept variables can be plotted as "all traces", or as one trace picked
  with the tuner.
- Graph › Freeze Traces keeps the previous result.

**CST** *(unverified: the primary page refused connection)*
- Every run's 1D results are stored with a Run ID.
- Plots can be Single or Parametric.
- A user reports only 50 curves shown out of about 2,000 runs.

**Patterns (A)**
- Comparison is mostly superposition of file-backed data snapshots.
- ADS alone stores the recipe too, and can recall it.
- Hard caps: 4nec2 holds 5 patterns, Zplots 4 snapshots.
- Compatibility is left to the user: matching steps, fixed scales.
- Sweeps render as a family of curves, with "all vs one selected" modes (AWR,
  CST).
- A live-recipe sweep with a small default size appears in SimSmith.
- Persistence is weak or explicit.

## B. RF and lab instruments

**VNAs (Keysight PNA/ENA/E4990A, R&S ZNB)**
- Channel, trace, window and sheet are separate objects
  ([Keysight](https://helpfiles.keysight.com/csg/m9485a/s0_start/traces_channels_and_windows.htm)).
  - A **channel** holds the stimulus (range, points, power, calibration), shared
    by its traces.
  - **Windows** display up to 24 traces.
  - **Sheets** group windows.
- **Data→Memory**
  ([math](https://helpfiles.keysight.com/csg/pxivna/S4_Collect/Math_Operations.htm)):
  - one memory per trace;
  - display Data, Memory, or both;
  - math Data/Mem, Data−Mem, Data×Mem and Data+Mem, on the complex data before
    formatting, so one memory serves any format;
  - suggested for before/after normalization.
- **Staleness is explicit.**
  - Without interpolation, a memory trace doesn't follow later range changes,
    and changing the point count *invalidates* it.
  - With interpolation, it is interpolated onto the new stimulus.
  - Memory survives Save/Recall.
- **E4990A**: memory holds the data as displayed; there is a Data−Mem mode
  ([docs](https://helpfiles.keysight.com/csg/e4990a/measurement/setting_up_the_display_of_measurement_results/trace-based_comparison_and_calculation.htm)).
- **R&S ZNB**: several memories per trace; memory can be loaded from Touchstone
  ([FAQ](https://www.rohde-schwarz.com/in/faq/loading-an-s-parameter-file-from-a-pc-into-a-memory-trace-faq_78704-30247.html)).
- **Markers**: a reference marker, delta markers, and "coupled markers" across
  traces and windows *(unverified)*.

**Spectrum analyzers** ([FieldFox](https://helpfiles.keysight.com/csg/A_Series_FieldFox_WebHelp/Chapter_7_SA_(Spectrum_Analyzer)_Mode_(Option_233%E2%80%93Mixed_Analyzers).htm))
- Four fixed-colour traces, each with a mode: Clear/Write (live), Max/Min
  Hold (accumulated), Average, View (frozen), or Blank.
- Freezing is a per-trace mode.
- Trace 4 "WILL be overwritten" by some features.

**Oscilloscopes**
- Reference waveforms REF1–4, toggled on and off without deleting
  *(unverified)*.
- Tek's FAQ: save the *setup* along with the reference to recall the
  settings; the waveform alone doesn't carry them
  ([Tek](https://www.tek.com/en/support/faqs/how-do-i-save-and-load-reference-waveform-tds3000c-series-oscilloscope)).
- Infinite persistence is cleared by any settings change *(unverified)*.

**NanoVNA-Saver** ([repo](https://github.com/NanoVNA-Saver/nanovna-saver))
- One reference trace, from the current sweep or a Touchstone file.
- A grid of charts, one quantity per chart.
- Users complain that pastel reference colours are hard to read, and that
  markers move by accident.

**Patterns (B)**
- A few named, fixed-colour slots.
- A pin is a per-trace data snapshot.
- Explicit difference (Data−Mem, delta markers) is first class.
- Explicit staleness rules: invalidate or interpolate, or clear on change.
- The stimulus definition is separate from the quantity and the layout.
- Three holds: live, frozen, accumulated.

## C. Financial charting

**TradingView**
- **Compare** switches to a percent axis from the first visible bar, so the
  baseline moves as you scroll
  ([help](https://www.tradingview.com/support/solutions/43000543053-how-to-use-the-compare-tool/)).
  An **Indexed to 100** scale was added because plain price scales left
  "detached lines"
  ([blog](https://www.tradingview.com/blog/en/indexed-to-100-scale-new-compare-tool-8979/)).
- **Placement**: the same scale, a new scale, or a new pane *(third-party
  guides)*.
- **Pane rules**
  ([docs](https://www.tradingview.com/charting-library-docs/latest/ui_elements/indicators/indicator-placement)):
  - price-range indicators overlay the price, and others get a pane;
  - the user can move or merge panes;
  - "All panes share the same time scale; only price scales vary per pane."
- **Layouts** of 1–16 charts, with sync toggles per dimension (symbol,
  interval, crosshair, time, range) and emoji-marked link groups
  ([sync](https://www.tradingview.com/support/solutions/43000629992-how-to-sync-the-charts-of-my-layout/)).
- **Drawings** attach to the *symbol*. A layout is a URL.

**Bloomberg COMP** compares up to six securities, as a graph or a table
([guide](https://libguides.nypl.org/c.php?g=1084166&p=8025762)).

**Dual axes**
- Stephen Few argues against them: line crossings are salient but
  meaningless
  ([article](https://www.perceptualedge.com/articles/visual_business_intelligence/dual-scaled_axes.pdf)).
- Counterpoints: [Datawrapper](https://blog.datawrapper.de/dualaxis/),
  [Y2Y](https://uncharted.software/assets/WhyTwoYAxes_Y2Y.pdf).

**Patterns (C)**
- The comparand is a live recipe (symbol and range).
- Normalization makes comparison meaningful, with an implicit baseline that
  moves with the view.
- Every series goes to one of three places: the same pane and scale, the
  same pane with a new scale, or a new pane.
- The x axis is shared, and y is per pane.
- Links are per dimension, in named groups.

## D. Exploratory data analysis and scientific plotting

**JMP Prediction Profiler**
([options](https://www.jmp.com/support/help/en/18.1/jmp/prediction-profiler-options.shtml))
- It shows one cell per factor, each the response swept over that factor
  with the others held at the current point.
- Dragging a factor's current-value line re-sweeps every other cell, so the
  interactions show.
- **Remember Settings** accumulates named settings rows, each resettable: a
  store of *recipes*, not curves.
- Link Profilers; a sensitivity indicator; settings exportable as script.

**JMP Graph Builder**: drop zones decide overlay vs Group/Wrap small multiples
*(unverified)*.

**Vega-Lite / Altair**
([composition docs](https://github.com/vega/vega-lite/tree/main/site/docs/composition))
- `layer` shares scales by default, and a dual axis needs an explicit
  `resolve`.
- `facet` shares; `concat` and `repeat` keep independent axes.

**Observable Plot** ([facets](https://observablehq.com/plot/features/facets))
- Facets can draw the other facets' data as background ("super"), a hybrid.

**Grafana**
- A dashboard-wide time range with per-panel overrides.
- **Time comparison** as a shifted query, a recipe, GA 2026-09
  ([news](https://grafana.com/whats-new/2026-09-24-panel-time-settings-and-time-comparison-are-now-generally-available/)).
- A shared crosshair or tooltip
  ([settings](https://grafana.com/docs/grafana/latest/dashboards/build-dashboards/modify-dashboard-settings/)).
- Repeated panels by variable.

**Spotfire**: named markings shared across views, with master/details
drill-down
([docs](https://docs.tibco.com/pub/spotfire/6.5.0/doc/html/vis/vis_what_is_a_details_visualization.htm)).

**Plotly Dash**
- Crossfiltering is wired by hand in callbacks.
- Zoom and legend state reset on every update unless `uirevision` is held
  ([forum](https://community.plotly.com/t/preserving-ui-state-like-zoom-in-dcc-graph-with-uirevision-with-dash/15793)).

**ipywidgets**
([interact](https://ipywidgets.readthedocs.io/en/stable/examples/Using%20Interact.html))
- Recompute cadence is a knob: continuous, on release, or on demand
  (`interact_manual`).
- The output area should have a fixed height, or it flickers.

**MATLAB**
- `hold on` is a mode of the axes
  ([hold](https://www.mathworks.com/help/matlab/ref/hold.html)).
- `linkaxes` links limits by dimension
  ([linkaxes](https://www.mathworks.com/help/matlab/ref/linkaxes.html)).

**Weights & Biases**
([compare](https://docs.wandb.ai/models/runs/compare-runs),
[line plots](https://docs.wandb.ai/models/app/features/panels/line-plot/reference))
- Pin up to 20 runs, in your own workspace view.
- **Set as baseline**: drawn bold, with summary-metric deltas in the runs
  table.
- Eye icons hide without removing.
- 10 runs are shown by default.
- Colour belongs to the run.

**TensorBoard**
([README](https://github.com/tensorflow/tensorboard/blob/master/tensorboard/plugins/metrics/README.md))
- "Pin" pins a *chart card*, not a run.
- Run colours persist.

**One-at-a-time sensitivity**
- Tornado and spider plots assume independence
  ([Eschenbach 1992](https://pubsonline.informs.org/doi/10.1287/inte.22.6.40);
  [spider plots](https://modelassist.epixanalytics.com/display/EA/Spider+plots+-+Advanced+sensitivity+analysis)).
- JMP's profiler is the interactive version, around a movable centre.

**Patterns (D)**
- Composition is a small algebra (layer / facet / concat), each operator with
  a default for sharing scales.
- The comparand varies: runs, remembered settings, time shifts, marked
  subsets.
- "Pin" means different things in different tools.
- There are explicit baselines with deltas.
- Links are named and per dimension.
- Recompute cadence is a named knob.
- Display caps are common.

## E. Design literature

- **Gleicher et al. 2011**, [Visual Comparison for Information Visualization](https://graphics.cs.wisc.edu/Papers/2011/GAWJHR11/paper.pdf).
  - Three building blocks:
    - **juxtaposition**: "simple … but place too much of the comparative burden
      on a viewer's memory";
    - **superposition**: "issues with clutter and scalability", poor past 2 or 3
      when blended;
    - **explicit encoding**: needs the relationship known, and risks
      decontextualization.
  - Hybrids manage the trade-offs.
- **Gleicher 2018**, [Considerations for Visualizing Comparison](https://graphics.cs.wisc.edu/Papers/2018/Gle18/viscomp.pdf).
  - Scan sequentially, select a subset, or summarize.
  - A chosen **reference**, several references, or reference-free designs.
  - Implicit comparison against memory.
- **Tufte**: "Compared to what?"; small multiples enforce comparisons
  ([summary](https://en.wikipedia.org/wiki/Small_multiple)).
- **Wang Baldonado et al. 2000**, [Guidelines for Using Multiple Views](https://courses.ischool.berkeley.edu/i247/f05/readings/Baldonado_MultipleViews_AVI00.pdf).
  - **Parsimony**: "A single view provides a user with a stable context";
    multiple views cost context switching, and coupling views adds complexity.
  - **Consistency**: inconsistent states risk false inferences, unless the
    decoupling is made clear.
  - The authors report a case where parsimony should have won.
- **Shneiderman 1996**, [The Eyes Have It](https://www.cs.umd.edu/~ben/papers/Shneiderman1996eyes.pdf).
  - *History*: "Keep a history of actions to support undo, replay, and
    progressive refinement."
  - *Extract*: save the items, or "save … the settings for the control
    widgets", which is the data-vs-recipe distinction.
- **Heer & Shneiderman 2012**, [Interactive Dynamics](https://idl.cs.washington.edu/files/2012-InteractiveDynamics-CACM.pdf).
  Coordinate, organize, record, annotate *(read via a summary)*.
- **Bret Victor 2011**, [Up and Down the Ladder of Abstraction](https://worrydream.com/LadderOfAbstraction/).
  - "Abstracting over" a parameter shows every value at once, and pointing at
    the abstraction steps down to a concrete value.
  - Two parameters make a heat map, of which each sweep is a slice.

## Cross-cutting design axes

1. **What a pin stores: data, a recipe, or both.**
   - Data only: EZNEC, MMANA, AutoEZ/Zplots, VNA memory, scope REF,
     NanoVNA-Saver, SA View.
   - Recipe only: TradingView compare, Grafana time comparison, JMP Remember,
     SimSmith.
   - Both, with recall: ADS Store/Recall, CST runs, W&B runs.
2. **Staleness.**
   - Explicit invalidate-or-interpolate: VNA.
   - Cleared on change: scope persistence.
   - Frozen with a warning: ADS.
   - Silent: antenna-tool snapshots.
   - Moves with the view: TradingView.
   - Lost on a context change: 4nec2, ADS on close.
3. **Superposition, juxtaposition or explicit difference.**
   - Explicit difference as a first-class mode: VNA Data−Mem, delta markers,
     EZNEC's relative readout, W&B deltas.
   - A single placement switch: JMP zones, TradingView placement, Vega
     layer/facet.
4. **The baseline.**
   - Explicit: W&B, VNA, EZNEC TraceView.
   - Implicit: the first visible bar, the current point, the live trace.
   - None: TensorBoard, CST.
5. **Linked or independent axes and cursors.**
   - Per-operator defaults: Vega.
   - A shared x with y per pane: TradingView.
   - Per-dimension links: MATLAB, TradingView, Grafana.
   - Named groups: TradingView, Spotfire.
   - Coupled markers: VNA.
   - Dual y contested: Few against; Zplots and xnec2c use it.
6. **Where the sweep definition lives.**
   - In a stimulus object shared by traces: the VNA channel.
   - One dialog per sweep type: EZNEC, AutoEZ, 4nec2.
   - One sweep over any parameter, frequency included: SimSmith, 4nec2's line
     chart, ADS.
   - A view over the knob space, where hovering steps down: Victor, JMP,
     SimSmith.
7. **A family of curves or one selected member.** AWR, CST, the AutoEZ spin
   button, 4nec2 playback.
8. **Capacity and colour.**
   - A few fixed slots: instruments 4, Zplots 4, 4nec2 5, NanoVNA-Saver 1.
   - Many runs with a display cap: W&B, CST, PNA.
   - Colour owned by the run or by the slot.
   - Legibility complaints.
9. **Recompute cadence and preserving view state.** ipywidgets, SimSmith's
   two sizes, Plotly `uirevision`.
10. **Scope and persistence.** Per workspace, per URL layout, attached to the
    data identity, file-based, session-only, or across sessions.
11. **Simple built in, or pushed out.** xnec2c's external optimizer, EZNEC's
    `LastZ.txt`, JMP script export, Dash callbacks, Excel in AutoEZ; against
    instruments' fixed trace math and a single reference.
12. **The same word, different objects.**
    - "Pin": a run, a chart card, or a scale.
    - "Hold": an axes mode, accumulation, or a freeze.
    - "Snapshot", "memory", "reference" and "trace" overlap.

## Not verified

- SimNEC's own compare UI.
- AWR Freeze Traces.
- The ADS Trace History count.
- CST's 50-curve cap.
- R&S memory naming.
- The details of Bloomberg's normalized overlays.
- Grafana's comparison styling.
- TradingView's three-way placement menu (seen only in third-party guides).
- Origin and Tableau small multiples (not researched).
