// The analysis chart (AK#1757, sweep-framework step 5 units 2 and 3): one
// chart that owns its analysis picker, Run, a dwell switch and the live
// point, and draws whatever it picked — a knob sweep (R/X against the knob,
// the old Z-vs-parameter view, or its trail on the Smith chart, the old
// "param sweep" switch) or a frequency sweep (on the Swr, S11 or Smith view,
// the old standalone views) — in place. A new chart is a frequency sweep of
// the design's own band on the Smith chart: the workbench's first view, as
// the standalone Smith view with the freq-sweep switch on was (unit 3).
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

import type { FrequencyView, FrequencyWorkbench } from "./analyses";
import { frequencyPick } from "./analyses";
import {
  DEFAULT_DENSITY_SPEC,
  type ParamSweepRequest,
  type ParamSweepSpec,
  RX_AUTO,
  type RxAxisChoice,
  sameSpec,
} from "./paramSweep";
import type { SweepRange } from "./sweep";
import type { SweepAxes } from "./sweepAxis";

export type ChartKind = "knob" | "frequency";

/** A knob sweep's views: R/X against the knob, or the trail on the Smith
 *  chart. A frequency sweep's are FrequencyView (Swr, S11, Smith). */
export type KnobView = "Rx" | "Smith";
export const KNOB_VIEWS: readonly KnobView[] = ["Rx", "Smith"];
/** Every frequency view, in the order a new chart offers them. Any frequency
 *  sweep can be drawn on all three (they are projections of one Z(f)), so an
 *  analysis's own views only lead the list. */
export const FREQUENCY_VIEWS: readonly FrequencyView[] = ["Smith", "Swr", "S11"];
export type ChartView = KnobView | FrequencyView;

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
};

export type AnalysisChartState = {
  kind: ChartKind;
  /** The analysis last picked, and (for a knob one) the spec it set: the
   *  picker names it while the chart still runs that. */
  picked: { name: string; kind: ChartKind; spec: ParamSweepSpec | null } | null;
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
  };
  /** Null only while the chart has never held a frequency sweep, which a new
   *  chart always has (initialChart). */
  frequency: FrequencyChartState | null;
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
  return { ...next, dwell: c.dwell };
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
  return c.kind === "frequency" ? defaults.frequency : defaults.knob;
}

/** The views the chart can draw what it shows, and the one on screen. */
export function chartViews(c: AnalysisChartState): readonly ChartView[] {
  return c.kind === "knob" ? KNOB_VIEWS : (c.frequency?.views ?? FREQUENCY_VIEWS);
}
export function chartView(c: AnalysisChartState): ChartView {
  return c.kind === "knob" ? c.knob.view : (c.frequency?.view ?? "Smith");
}

/** The chart on another of its views. A view its kind cannot draw is
 *  refused (the same chart back). */
export function setChartView(c: AnalysisChartState, v: ChartView): AnalysisChartState {
  if (!chartViews(c).includes(v)) return c;
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
 *  knob sweep. */
export function pickKnob(
  c: AnalysisChartState,
  name: string | null,
  spec: ParamSweepSpec,
): AnalysisChartState {
  return {
    ...c,
    kind: "knob",
    picked: name === null ? c.picked : { name, kind: "knob", spec },
    knob: { ...c.knob, spec, xLog: null },
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
    },
  };
}

/** The picked analysis's name while the chart still runs what it set. */
export function pickedName(c: AnalysisChartState): string | null {
  const p = c.picked;
  if (!p || p.kind !== c.kind) return null;
  if (p.kind === "frequency") return p.name;
  return p.spec && sameSpec(p.spec, c.knob.spec) ? p.name : null;
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
} {
  const dwell = chartDwell(c, env.dwellDefaults);
  const f = c.kind === "frequency" ? c.frequency : null;
  const shown = env.resident && f !== null;
  return {
    param: {
      req: { param: c.knob.spec.param, values: env.values, label: env.label, auto: dwell },
      wanted: env.resident && c.kind === "knob",
    },
    freq: {
      range: f ? chartFrequencyRange(f, env.designRange) : env.designRange,
      wanted: shown,
      auto: dwell,
      views: {
        vswr: shown && f.view === "Swr",
        gamma: shown && f.view === "S11",
        smith: shown && f.view === "Smith",
      },
    },
  };
}

/** A range edit from the chart's from / to: the same spacing and step (or
 *  count), new ends. Null when the ends are not a range. */
export function editRange(r: SweepRange, lo: number, hi: number): SweepRange | null {
  if (!(Number.isFinite(lo) && Number.isFinite(hi) && lo > 0 && hi > lo)) return null;
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
