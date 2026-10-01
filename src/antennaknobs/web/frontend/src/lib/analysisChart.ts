// The analysis chart (AK#1757, sweep-framework step 5 units 2 and 3): one
// chart that owns its analysis picker, Run, a dwell switch and the live
// point, and draws whatever it picked — a knob sweep (R/X against the knob,
// the old Z-vs-parameter view, or its trail on the Smith chart, the old
// "param sweep" switch) or a frequency sweep (on the Swr, S11 or Smith view,
// the old standalone views) — in place. A new chart is a frequency sweep of
// the design's own band on the Smith chart: the workbench's first view, as
// the standalone Smith view with the freq-sweep switch on was (unit 3).
// A pattern (step 7 unit 3) is a third kind: no sweep, one solve per cell,
// drawn as the analysis's cuts or its metrics table.
//
// This module is the chart's STATE and the pure rules over it, React-free:
// what a pick sets, what the dwell switch defaults to, which range a
// frequency chart sweeps, and what each of its two runners is asked to run
// (`chartRunInputs`). The session holds one AnalysisChartState per chart and
// hands each chart's run inputs to that chart's runners, so a second, third
// or fourth chart (unit 4) is another state plus another pair of runners.
//
// Session-only by ruling (Steve, 2026-09-28): nothing here is ever written
// to the browser's storage or to settings.toml. Only the design's .py file
// is remembered between sessions.

import type {
  AnalysisWorkbench,
  FrequencyView,
  FrequencyWorkbench,
  HoldRun,
  KnobView,
  MetricSpec,
  PatternViewSpec,
  PatternWorkbench,
} from "./analyses";
import { frequencyPick } from "./analyses";
import { type ChartCross, FOLLOW_ACTIVE, type ListedCross, NOTHING_LISTED } from "./chartCells";
import {
  DEFAULT_DENSITY_SPEC,
  DENSITY,
  type ParamSweepRequest,
  type ParamSweepSpec,
  RX_AUTO,
  type RxAxisChoice,
  sameSpec,
} from "./paramSweep";
import type { RunOnPickKind } from "./settings";
import type { SweepRange } from "./sweep";
import type { SweepAxes } from "./sweepAxis";

export type ChartKind = "knob" | "frequency" | "pattern";

/** A knob sweep's views: R/X against the knob, the trail on the Smith
 *  chart, or the numbers (Table, step 5 unit 5). A frequency sweep's are
 *  FrequencyView (Swr, S11, Smith, and R/X against frequency and the Table
 *  since unit 5). */
export type { KnobView };
/** The views every knob sweep can draw; a picked analysis with a MetricPlot
 *  adds "Metric" (AK#1828, `chartViews`). */
export const KNOB_VIEWS: readonly KnobView[] = ["Rx", "Smith", "Table"];
/** A held knob sweep's views (AK#1757 step 6): the knob sweep's, and the
 *  held knobs against the swept one. */
export const HELD_VIEWS: readonly KnobView[] = [...KNOB_VIEWS, "Knobs"];
/** Every frequency view, in the order a new chart offers them. Any frequency
 *  sweep can be drawn on all of them (they are projections of one Z(f), or
 *  its numbers), so an analysis's own views only lead the list: R/X and the
 *  Table are offered on every frequency sweep, not only one that lists them
 *  (step 5 unit 5), as Swr / S11 / Smith always were. */
export const FREQUENCY_VIEWS: readonly FrequencyView[] = ["Smith", "Swr", "S11", "Rx", "Table"];
/** A pattern's view on the chart, by its place among the analysis's views
 *  (AK#1757 step 7): two elevation cuts at different bearings are two
 *  views, so a view is not named by its kind alone. */
export type PatternViewId = `pattern:${number}`;
export type ChartView = KnobView | FrequencyView | PatternViewId;

/** What a chart showing a pattern holds of its own: the analysis's views,
 *  in its order, and the one on screen (an index into them). */
export type PatternChartState = { views: PatternViewSpec[]; view: number };

/** A pattern view's words, as the chart's view menu names it. */
export function patternViewLabel(v: PatternViewSpec): string {
  if (v.view === "Elevation") return `Elevation @ ${v.az}° az`;
  if (v.view === "Azimuth") return `Azimuth @ ${v.el}° el`;
  return "Table";
}

/** An analysis's views first, then the rest of the frequency views. */
export function frequencyViews(named: readonly FrequencyView[]): FrequencyView[] {
  return [...named, ...FREQUENCY_VIEWS.filter((v) => !named.includes(v))];
}

/** Where a new chart starts, from the viewer's preferences: the view a
 *  migrated pin named (Smith by default), and the Swr / S11 scales and SWR
 *  threshold the viewer set. */
export type ChartSeed = { view: FrequencyView; axes: SweepAxes; threshold: number };

/** The dwell switch's default per kind, from settings.toml's [switches]:
 *  `freq_sweep` for a frequency sweep, `convergence_sweep` (the old "param
 *  sweep" switch) for a knob or density sweep. */
export type DwellDefaults = { frequency: boolean; knob: boolean };

/** What a chart showing a frequency analysis holds of its own. */
export type FrequencyChartState = {
  /** The analysis's range, or null: the design's own (its band policy
   *  included, so a band that follows the dial moves the sweep with it). */
  analysisRange: SweepRange | null;
  /** The chart's range edit (from / to on the chart), or null: the
   *  analysis's own. */
  rangeEdit: SweepRange | null;
  /** The views the analysis names, in its order, and the one on screen. */
  views: FrequencyView[];
  view: FrequencyView;
  /** The Swr / S11 charts' scales and the SWR threshold: seeded from the
   *  analysis (and the viewer's preferences where it names none), then the
   *  chart's own. Never written back to the preferences. */
  axes: SweepAxes;
  threshold: number;
  /** The R/X-against-frequency view's ranges and x axis (null: follow the
   *  range's spacing), the knob sweep's R/X controls on this view. Absent:
   *  Auto, and the range's spacing. The chart's own; never stored. */
  rx?: { r: RxAxisChoice; x: RxAxisChoice; xLog: boolean | null };
};

/** A frequency chart's R/X ranges and x axis, as they stand. */
export function frequencyRx(f: FrequencyChartState): {
  r: RxAxisChoice;
  x: RxAxisChoice;
  xLog: boolean | null;
} {
  return f.rx ?? { r: RX_AUTO, x: RX_AUTO, xLog: null };
}

export type AnalysisChartState = {
  kind: ChartKind;
  /** The analysis last picked, and (for a knob one) the spec it set: the
   *  picker names it while the chart still runs that. */
  picked: {
    name: string;
    kind: ChartKind;
    spec: ParamSweepSpec | null;
    /** A knob analysis's MetricPlot (AK#1828): what its "Metric" view
     *  draws and its sweep reads off each point. */
    metric?: MetricSpec | null;
  } | null;
  /** The dwell switch: re-run after the knobs settle. Null until the viewer
   *  flips it, and then the kind's default (`chartDwell`). */
  dwell: boolean | null;
  /** The knob sweep's spec, x axis (null: follow the spec's spacing) and
   *  R / X ranges. Kept while the chart shows a frequency analysis, so a
   *  knob pick after one starts from where it was. */
  knob: {
    spec: ParamSweepSpec;
    xLog: boolean | null;
    axes: { r: RxAxisChoice; x: RxAxisChoice };
    view: KnobView;
    /** The picked analysis's hold (AK#1757 step 6), or absent / null: a
     *  plain knob sweep. It runs for as long as the chart runs that pick
     *  (`chartHold`). */
    hold?: HoldRun | null;
  };
  /** Null only while the chart has never held a frequency sweep, which a new
   *  chart always has (initialChart). */
  frequency: FrequencyChartState | null;
  /** The picked pattern's views and the one on screen (AK#1757 step 7);
   *  absent until a pattern is picked, and kept across a later pick of
   *  another kind like the other kinds' own state. */
  pattern?: PatternChartState | null;
  /** The solver slots and ground slots the chart compares (unit 4,
   *  lib/chartCells.ts): null follows the session's active one. The
   *  viewer's, or a pick's preselection; kept across picks and designs,
   *  since it is about the session's slots, not the design. */
  cross: ChartCross;
  /** The engines and grounds the picked analysis lists, which name its
   *  cells (and refuse the ones no slot holds) for as long as the chart
   *  still runs that pick (`chartListed`). */
  listed: ListedCross;
  /** The legend expanded (true) or collapsed to its chip (false); absent
   *  until the viewer flips it, and then collapsed on a phone and open on
   *  a desktop (ChartLegend). */
  legendOpen?: boolean;
};

/** The frequency sweep a new chart shows: the design's own range (the
 *  session's, its range menu edit included), every view, the seed's view
 *  on screen. */
function ownFrequency(seed: ChartSeed): FrequencyChartState {
  return {
    analysisRange: null,
    rangeEdit: null,
    views: frequencyViews([seed.view]),
    view: seed.view,
    axes: seed.axes,
    threshold: seed.threshold,
  };
}

/** A new chart: the design's own frequency sweep on the seed's view (the
 *  Smith chart unless a migrated pin said otherwise), and a density sweep
 *  on Auto ranges waiting behind it for a knob pick. */
export function initialChart(seed: ChartSeed): AnalysisChartState {
  return {
    kind: "frequency",
    picked: null,
    dwell: null,
    knob: { spec: DEFAULT_DENSITY_SPEC, xLog: null, axes: { r: RX_AUTO, x: RX_AUTO }, view: "Rx" },
    frequency: ownFrequency(seed),
    cross: FOLLOW_ACTIVE,
    listed: NOTHING_LISTED,
  };
}

/** The chart after a design switch: a new chart, which keeps only how the
 *  viewer was looking at it — the frequency view on screen, the Swr / S11
 *  scales and threshold, and a flipped dwell switch. What it computed (the
 *  pick, a knob spec, a range edit) belongs to the old design (Steve,
 *  2026-09-26: a length_factor sweep must not follow him onto the next
 *  design). The switch stays because it IS the old freq-sweep checkbox,
 *  which a design switch never reset. */
export function chartForNewDesign(c: AnalysisChartState, seed: ChartSeed): AnalysisChartState {
  const f = c.frequency;
  const view: FrequencyView =
    c.kind === "frequency" && f ? f.view : c.kind === "knob" && c.knob.view === "Smith" ? "Smith" : seed.view;
  const next = initialChart({
    view,
    axes: f?.axes ?? seed.axes,
    threshold: f?.threshold ?? seed.threshold,
  });
  return {
    ...next,
    dwell: c.dwell,
    cross: c.cross,
    // How the viewer looks at the legend, like the scales, stays.
    ...(c.legendOpen !== undefined ? { legendOpen: c.legendOpen } : {}),
  };
}

/** Back to the design's own frequency sweep (the picker's first entry):
 *  a new chart's, on the frequency view on screen (or the seed's, from a
 *  knob sweep on R/X), with the chart's scales and its dwell switch. */
export function pickOwnFrequency(c: AnalysisChartState, seed: ChartSeed): AnalysisChartState {
  const f = c.frequency;
  const view: FrequencyView =
    c.kind === "frequency" && f ? f.view : c.kind === "knob" && c.knob.view === "Smith" ? "Smith" : seed.view;
  return {
    ...c,
    kind: "frequency",
    picked: null,
    frequency: ownFrequency({ view, axes: f?.axes ?? seed.axes, threshold: f?.threshold ?? seed.threshold }),
  };
}

/** The dwell switch as it stands: the viewer's flip, else the kind's
 *  default from settings.toml (`defaults`; built in, a frequency sweep
 *  follows the knobs, as the freq-sweep checkbox did, and a knob or density
 *  sweep, which rebuilds or re-meshes per point, waits for Run). */
export function chartDwell(c: AnalysisChartState, defaults: DwellDefaults): boolean {
  if (c.dwell !== null) return c.dwell;
  // A held sweep (AK#1757 step 6) is an optimisation at every point: it
  // runs on Run, never by itself after a drag, unless the viewer flips this
  // chart's switch on (the step-5 dwell, per chart, as for any analysis).
  if (chartHold(c)) return false;
  // A pattern is one solve per cell, as cheap as the live solve's: it
  // follows the knobs as a frequency sweep does.
  return c.kind === "knob" ? defaults.knob : defaults.frequency;
}

/** The views the chart can draw what it shows, and the one on screen. */
/** The kind of analysis a pick is, as settings.toml's
 *  [workbench.run_on_pick] names it (AC6LA, QRZ 1003328 #179), from what
 *  /analyses serves: a frequency sweep, a pattern, and a knob sweep split
 *  three ways by what it costs — a held one (an.Hold: an optimisation at
 *  every point), a density ladder (the knob is n_per_wire, DENSITY: the
 *  convergence analysis), else a plain knob sweep. A study is classified by
 *  its own workbench, so it is the kind of analysis it is. Null for one the
 *  workbench cannot run (a two-sweep map today, until step 5 draws it):
 *  there is nothing to start. */
export function runOnPickKind(w: AnalysisWorkbench): RunOnPickKind | null {
  if (!w.runs) return null;
  if (w.kind === "frequency" || w.kind === "pattern") return w.kind;
  if (w.hold) return "held";
  return w.param === DENSITY ? "convergence" : "knob";
}

/** Whether picking `w` starts it, by the served table. */
export function pickRuns(w: AnalysisWorkbench, runOnPick: Record<RunOnPickKind, boolean>): boolean {
  const kind = runOnPickKind(w);
  return kind !== null && runOnPick[kind];
}

export function chartViews(c: AnalysisChartState): readonly ChartView[] {
  if (c.kind === "pattern") return (c.pattern?.views ?? []).map((_, k) => patternViewId(k));
  if (c.kind === "knob") {
    // A picked MetricPlot adds "Metric" (AK#1828), a picked hold "Knobs"
    // (AK#1757 step 6).
    const base = chartHold(c) ? HELD_VIEWS : KNOB_VIEWS;
    return chartMetric(c) ? [...base, "Metric"] : base;
  }
  return c.frequency?.views ?? FREQUENCY_VIEWS;
}

/** The hold the chart runs (AK#1757 step 6): the picked analysis's, while
 *  the chart still runs that pick (an edit of its range keeps it); null
 *  once the viewer sweeps another knob or picks something else. */
export function chartHold(c: AnalysisChartState): HoldRun | null {
  return c.kind === "knob" && pickedName(c) !== null ? (c.knob.hold ?? null) : null;
}
export function chartView(c: AnalysisChartState): ChartView {
  if (c.kind === "pattern") return patternViewId(c.pattern?.view ?? 0);
  if (c.kind === "knob") {
    // The metric view leaves with the analysis that drew it, and the Knobs
    // view with its hold (step 6): off either, R/X again.
    if (c.knob.view === "Metric" && !chartMetric(c)) return "Rx";
    if (c.knob.view === "Knobs" && !chartHold(c)) return "Rx";
    return c.knob.view;
  }
  return c.frequency?.view ?? "Smith";
}

/** The MetricPlot the chart draws (AK#1828): the picked knob analysis's,
 *  while the chart still runs it; null otherwise. */
export function chartMetric(c: AnalysisChartState): MetricSpec | null {
  if (c.kind !== "knob" || pickedName(c) === null) return null;
  return c.picked?.metric ?? null;
}

const patternViewId = (k: number): PatternViewId => `pattern:${k}`;

/** The pattern view on screen, or null when the chart shows no pattern. */
export function chartPatternView(c: AnalysisChartState): PatternViewSpec | null {
  if (c.kind !== "pattern" || !c.pattern) return null;
  return c.pattern.views[c.pattern.view] ?? c.pattern.views[0] ?? null;
}

/** The chart on another of its views. A view its kind cannot draw is
 *  refused (the same chart back). */
export function setChartView(c: AnalysisChartState, v: ChartView): AnalysisChartState {
  if (!chartViews(c).includes(v)) return c;
  if (c.kind === "pattern") {
    return c.pattern ? { ...c, pattern: { ...c.pattern, view: Number(v.slice("pattern:".length)) } } : c;
  }
  if (c.kind === "knob") return { ...c, knob: { ...c.knob, view: v as KnobView } };
  return c.frequency ? { ...c, frequency: { ...c.frequency, view: v as FrequencyView } } : c;
}

/** The range a frequency chart sweeps: its edit, else the analysis's own,
 *  else the session's (`designRange`: lib/sweep.ts resolveSweepRange, the
 *  design's own with the measurement dial's range-menu edit applied, which
 *  is what the standalone sweep views swept). */
export function chartFrequencyRange(f: FrequencyChartState, designRange: SweepRange): SweepRange {
  return f.rangeEdit ?? f.analysisRange ?? designRange;
}

/** Picking a knob analysis (or the header's own spec): the chart shows that
 *  knob sweep. `views` are the ones the analysis lists (step 5 unit 5): the
 *  view on screen stays when the analysis lists it, else the chart opens
 *  on the analysis's first (a Table-only analysis opens on its table). */
export function pickKnob(
  c: AnalysisChartState,
  name: string | null,
  spec: ParamSweepSpec,
  views?: readonly KnobView[],
  metric?: MetricSpec | null,
  hold?: HoldRun | null,
): AnalysisChartState {
  const held = name === null ? null : (hold ?? null);
  // The metric view only with a metric to draw (AK#1828), the Knobs view
  // only with a hold (AK#1757 step 6).
  const own = views?.filter((v) => (v !== "Metric" || !!metric) && (v !== "Knobs" || !!held));
  const was =
    (c.knob.view === "Metric" && !metric) || (c.knob.view === "Knobs" && !held) ? "Rx" : c.knob.view;
  // A metric analysis that leads with its MetricPlot opens on it: the view
  // is new with the pick, so staying on the old one would hide it.
  const leads = !!metric && own?.[0] === "Metric";
  const view = leads ? "Metric" : own && own.length > 0 && !own.includes(was) ? own[0] : was;
  return {
    ...c,
    kind: "knob",
    // A null name is a pick of no analysis ("Sweep a knob", the knob menu):
    // it leaves the analysis, so the old pick and its crosses go, and its
    // hold (step 6) with them.
    picked:
      name === null
        ? null
        : { name, kind: "knob", spec, ...(metric ? { metric } : {}) },
    knob: { ...c.knob, spec, xLog: null, view, hold: held },
  };
}

/** Picking a frequency analysis: its range (null when it is the design's
 *  own), its views, its SWR scale and threshold where it names them, else
 *  the viewer's (`prefs`, read here and never written). */
export function pickFrequency(
  c: AnalysisChartState,
  name: string,
  w: FrequencyWorkbench,
  designRange: SweepRange,
  prefs: { axes: SweepAxes; threshold: number },
): AnalysisChartState {
  const pick = frequencyPick(w, designRange);
  return {
    ...c,
    kind: "frequency",
    picked: { name, kind: "frequency", spec: null },
    frequency: {
      analysisRange: pick.range,
      rangeEdit: null,
      views: frequencyViews(w.views),
      view: w.views[0],
      axes: pick.vswr ? { ...prefs.axes, vswr: pick.vswr } : prefs.axes,
      threshold: pick.threshold ?? prefs.threshold,
      // How the viewer set the R/X view's ranges stays, as the knob
      // sweep's does across picks.
      ...(c.frequency?.rx ? { rx: c.frequency.rx } : {}),
    },
  };
}

/** Picking a pattern (AK#1757 step 7): its views, the first on screen. A
 *  pattern has no range of its own to set; each cell is one solve. */
export function pickPattern(c: AnalysisChartState, name: string, w: PatternWorkbench): AnalysisChartState {
  return {
    ...c,
    kind: "pattern",
    picked: { name, kind: "pattern", spec: null },
    pattern: { views: [...w.views], view: 0 },
  };
}

/** A pick's listed engines and grounds, and the slots they preselect
 *  (lib/chartCells.ts preselect): an axis the analysis lists takes the
 *  preselection, one it does not keeps the chart's own. */
export function withListed(
  c: AnalysisChartState,
  listed: ListedCross,
  preselected: ChartCross,
): AnalysisChartState {
  return {
    ...c,
    listed,
    cross: {
      slots: listed.engines ? preselected.slots : c.cross.slots,
      grounds: listed.grounds ? preselected.grounds : c.cross.grounds,
    },
  };
}

/** What the picked analysis lists, while the chart still runs that pick;
 *  nothing once the viewer has moved it off (another pick, a range edit of
 *  a knob sweep), so a refused cell never outlives the analysis that
 *  named it. */
export function chartListed(c: AnalysisChartState): ListedCross {
  return pickedName(c) !== null ? c.listed : NOTHING_LISTED;
}

/** The picked analysis's name while the chart still runs it. A knob
 *  analysis stays picked through an edit of its range, points or spacing
 *  (AK#1757, Steve's phone: 33 → 5 points on "tuning family" dropped the
 *  family); it is left by picking something else or by sweeping another
 *  knob (`knob.spec.param` no longer the pick's). */
export function pickedName(c: AnalysisChartState): string | null {
  const p = c.picked;
  if (!p || p.kind !== c.kind) return null;
  if (p.kind === "frequency" || p.kind === "pattern") return p.name;
  return p.spec && p.spec.param === c.knob.spec.param ? p.name : null;
}

/** A picked analysis whose range the viewer has edited: a knob one's
 *  range, points or spacing, or a frequency one's from / to (an explicit
 *  frequency list edited becomes a range, step 5 unit 5). Still picked (its
 *  crosses stay), no longer its own range. Picking it again, or the chart's
 *  ↺, restores the range. */
export function pickedEdited(c: AnalysisChartState): boolean {
  const p = c.picked;
  if (pickedName(c) === null || !p) return false;
  // A pattern has no range to edit.
  if (p.kind === "pattern") return false;
  if (p.kind === "frequency") return !!c.frequency?.rangeEdit;
  return !!p.spec && !sameSpec(p.spec, c.knob.spec);
}

/** What a chart asks of its two runners this render.
 *
 *  `param` is the knob sweep's request (its `auto` is the dwell switch) and
 *  whether the chart wants it run; `freq` is the frequency sweep's range,
 *  whether it is wanted, its `auto`, and the projections refinement should
 *  judge (only the view on screen). A runner whose kind the chart is not
 *  showing is not wanted, so it runs nothing. */
export function chartRunInputs(
  c: AnalysisChartState,
  env: {
    resident: boolean;
    dwellDefaults: DwellDefaults;
    designRange: SweepRange;
    /** The knob sweep's values (paramLadder) and display name. */
    values: number[];
    label: string;
  },
): {
  param: { req: ParamSweepRequest; wanted: boolean };
  freq: {
    range: SweepRange;
    wanted: boolean;
    auto: boolean;
    views: { vswr: boolean; gamma: boolean; smith: boolean };
  };
  /** A pattern's one solve per cell (AK#1757 step 7), and the cut angles
   *  its solve ships with: the chart's first elevation cut's bearing and
   *  first azimuth cut's elevation (another view re-cuts off the same
   *  solve, as a cut dial does). */
  pattern: { wanted: boolean; auto: boolean; elevAzDeg: number; azElevDeg: number };
} {
  const dwell = chartDwell(c, env.dwellDefaults);
  const metric = chartMetric(c);
  const f = c.kind === "frequency" ? c.frequency : null;
  const shown = env.resident && f !== null;
  const pv = c.kind === "pattern" ? (c.pattern?.views ?? []) : [];
  const el = pv.find((v) => v.view === "Elevation");
  const az = pv.find((v) => v.view === "Azimuth");
  return {
    pattern: {
      wanted: env.resident && c.kind === "pattern" && pv.length > 0,
      auto: dwell,
      elevAzDeg: el?.view === "Elevation" ? el.az : 0,
      azElevDeg: az?.view === "Azimuth" ? az.el : 15,
    },
    param: {
      req: {
        param: c.knob.spec.param,
        values: env.values,
        label: env.label,
        auto: dwell,
        // Read off every point while the chart can show it (AK#1828), so
        // flipping to the Metric view needs no second sweep.
        ...(metric ? { metric: metric.spec } : {}),
        // A held pick's hold rides with every curve's request (step 6).
        ...(chartHold(c) ? { hold: chartHold(c) } : {}),
      },
      wanted: env.resident && c.kind === "knob",
    },
    freq: {
      range: f ? chartFrequencyRange(f, env.designRange) : env.designRange,
      wanted: shown,
      auto: dwell,
      // R/X against frequency judges refinement on the Smith projection,
      // which is Z itself; the Table judges none (it lists the points
      // swept, and refinement would only add rows between them).
      views: {
        vswr: shown && f.view === "Swr",
        gamma: shown && f.view === "S11",
        smith: shown && (f.view === "Smith" || f.view === "Rx"),
      },
    },
  };
}

/** A range edit from the chart's from / to: the same spacing and step (or
 *  count), new ends. An explicit frequency list (step 5 unit 5) becomes a
 *  linear range over the new ends with as many points as the list had: an
 *  edit of the ends is a range. Null when the ends are not a range. */
export function editRange(r: SweepRange, lo: number, hi: number): SweepRange | null {
  if (!(Number.isFinite(lo) && Number.isFinite(hi) && lo > 0 && hi > lo)) return null;
  if (r.freqs) {
    const n = r.freqs.length;
    return n >= 2 ? { lo, hi, spacing: "lin", step: (hi - lo) / (n - 1) } : { lo, hi, spacing: "lin" };
  }
  return { ...r, lo, hi };
}

/** The chart header's data attributes: its kind, dwell switch and pick, for
 *  a test to read rather than the pixels. */
export function chartDataAttrs(kind: ChartKind, dwell: boolean, picked: string | null) {
  return {
    "data-chart-kind": kind,
    "data-dwell": dwell ? "1" : "0",
    "data-analysis": picked ?? "",
  };
}
