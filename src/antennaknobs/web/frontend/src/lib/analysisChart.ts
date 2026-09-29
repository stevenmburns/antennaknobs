// The analysis chart (AK#1757, sweep-framework step 5 unit 2): one chart
// that owns its analysis picker, Run, a dwell switch and the live point, and
// draws whatever it picked — a knob sweep (R/X against the knob, the old
// Z-vs-parameter view) or a frequency sweep (its first view: Swr, S11 or
// Smith) — in place.
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
  isDensity,
  type ParamSweepRequest,
  type ParamSweepSpec,
  RX_AUTO,
  type RxAxisChoice,
  sameSpec,
} from "./paramSweep";
import type { SweepRange } from "./sweep";
import type { SweepAxes } from "./sweepAxis";

export type ChartKind = "knob" | "frequency";

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
  knob: { spec: ParamSweepSpec; xLog: boolean | null; axes: { r: RxAxisChoice; x: RxAxisChoice } };
  frequency: FrequencyChartState | null;
};

/** A new chart: the density sweep on Auto ranges, as the Z-vs-parameter
 *  view has always opened. */
export function initialChart(): AnalysisChartState {
  return {
    kind: "knob",
    picked: null,
    dwell: null,
    knob: { spec: DEFAULT_DENSITY_SPEC, xLog: null, axes: { r: RX_AUTO, x: RX_AUTO } },
    frequency: null,
  };
}

/** The dwell switch as it stands. Its defaults are today's behaviour: a
 *  frequency sweep follows the knobs (the freq-sweep switch's meaning), a
 *  density sweep runs by itself as the old convergence sweep did, and a knob
 *  sweep, which rebuilds the design per point, waits for Run. */
export function chartDwell(c: AnalysisChartState): boolean {
  if (c.dwell !== null) return c.dwell;
  return c.kind === "frequency" ? true : isDensity(c.knob.spec.param);
}

/** The range a frequency chart sweeps: its edit, else the analysis's own,
 *  else the design's (`designRange`, lib/sweep.ts designSweepRange). */
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
      views: [...w.views],
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
  const dwell = chartDwell(c);
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
