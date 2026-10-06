// A design's analyses in the workbench (AK#1757, sweep-framework steps 3-4):
// what POST /analyses serves, and how a runnable one becomes the
// Z-vs-parameter view's spec (a knob sweep) or the frequency sweep's range,
// charts and SWR axis (a frequency sweep), or a pattern's cuts and table
// (step 7). React-free, so the mapping is
// tested alone.

import type {
  CrossKind,
  DesignCross,
  KnobValue,
  ListedCell,
  ListedCross,
  PlaneCross,
  ScalarKnob,
  StateCross,
  StepCross,
} from "./chartCells";
import { parseKept, type KeptRun } from "./keptRun";
import { DENSITY, paramValues, type ParamSweepSpec } from "./paramSweep";
import type { SweepRangeSpec } from "./params";
import { specRange, type SweepRange } from "./sweep";
import {
  RECIPROCAL,
  RHO,
  SWR_THRESHOLD_MAX,
  SWR_THRESHOLD_MIN,
  type SweepAxisChoice,
} from "./sweepAxis";

/** The views a knob analysis draws here, by the server's names: R/X against
 *  the knob, its Smith trail, the numbers (AK#1757 step 5 unit 5), and a
 *  metric against the knob (AK#1828, `an.MetricPlot`), and a held sweep's
 *  knobs against the knob (AK#1757 step 6). */
export type KnobView = "Rx" | "Smith" | "Table" | "Metric" | "Knobs";

/** A MetricPlot as /analyses serves it (AK#1828): the metric's name and
 *  unit, the cell its curves are drawn relative to (null: none) and the unit
 *  of that difference, and the metric as data, which /param_sweep reads off
 *  each point's solve. */
export type MetricSpec = {
  name: string;
  unit: string;
  relativeTo: string | null;
  relativeUnit: string;
  spec: unknown;
};

/** A knob analysis's hold (AK#1757 step 6), as /analyses serves it: the
 *  optimizer's objective, the knobs it re-solves at every point (resolved on
 *  the tab's design) with their bounds (their ui_params min/max), its Z0
 *  (null: the session's), warm start, and `spec`, the hold as data, which
 *  each curve's /param_sweep sends back for the server to resolve on that
 *  curve's own design. Opaque here. */
export type HoldRun = {
  objective: string;
  knobs: string[];
  bounds: Record<string, [number, number]>;
  z0: number | null;
  warmStart: boolean;
  spec: unknown;
};

/** A knob sweep: `param` and `values` are what /param_sweep takes (the same
 *  ladder `antennaknobs analyze` sweeps). `views` are the ones the analysis
 *  lists that the chart draws, in its order (absent from an older server). */
export type KnobWorkbench = {
  runs: true;
  kind: "knob";
  param: string;
  values: number[];
  log: boolean;
  views?: KnobView[];
  /** Its MetricPlot, when it has one (AK#1828). */
  metric?: MetricSpec | null;
  /** The hold at every point (step 6), or absent / null: none. */
  hold?: HoldRun | null;
  note: string | null;
} & Listed;

/** The engine and ground specs the analysis lists (its cross, else its one
 *  engine or ground), or null where it names none: the analysis chart's
 *  preselection (lib/chartCells.ts, AK#1757 step 5 unit 4). And its other
 *  crosses (unit 4b): the order its crosses are written in, its planes,
 *  designs and family, each null where it has none. Optional: an older
 *  server serves none of them, and the chart then draws the active slot. */
export type Listed = {
  engines?: string[] | null;
  grounds?: string[] | null;
  axes?: CrossKind[];
  planes?: PlaneCross[] | null;
  designs?: DesignCross[] | null;
  states?: StateCross[] | null;
  cells?: ListedCell[] | null;
  step?: StepCross | null;
};

/** The views a frequency analysis draws here, by the server's names: R/X
 *  against frequency and the table since step 5 unit 5. */
export type FrequencyView = "Swr" | "S11" | "Smith" | "Rx" | "Table";

/** A frequency sweep (step 4). `range` is the span and grid the server
 *  resolved (`frequency_range`) when it is absolute — the analysis's own or
 *  the design's; null when it is the band policy, which is relative to this
 *  session's band and so is ours to place. `points` is the analysis's own
 *  count. `freqs` is its explicit frequency list (`Sweep(values=...)`), the
 *  MHz `antennaknobs analyze` sweeps, in its order, or null for a range
 *  (step 5 unit 5); `range` then spans it. `swr` is the Swr view's scale
 *  and the threshold line. */
export type FrequencyWorkbench = {
  runs: true;
  kind: "frequency";
  range: SweepRangeSpec | null;
  level: string;
  points: number | null;
  freqs?: number[] | null;
  views: FrequencyView[];
  swr: { scale: "auto" | "reciprocal" | "rho" | null; threshold: number | null };
  note: string | null;
} & Listed;

/** A pattern's views (AK#1757 step 7), as /analyses serves them: an
 *  elevation cut through azimuth `az`, an azimuth cut at elevation `el`
 *  (whole degrees, the far-field grid's), or the metrics table. */
export type PatternViewSpec =
  | { view: "Elevation"; az: number }
  | { view: "Azimuth"; el: number }
  | { view: "PatternTable" };

/** A pattern (AK#1757 step 7): no sweep, one solve per cell at its
 *  measurement frequency (`freq`, the tab's design's; a state may set its
 *  own), drawn by its `views` in the analysis's order. Each cell is one
 *  POST /pattern_cell. */
export type PatternWorkbench = {
  runs: true;
  kind: "pattern";
  views: PatternViewSpec[];
  freq: number | null;
  note: string | null;
} & Listed;

/** How the workbench runs an analysis, or the reason it cannot yet. */
export type AnalysisWorkbench =
  | KnobWorkbench
  | FrequencyWorkbench
  | PatternWorkbench
  | { runs: false; why: string };

/** A study (AK#1757 step 7): an analysis over several designs, from a
 *  module-level `build_studies()`. `source` is where it is declared (a
 *  catalog study file's `family.name` under `studies/`, a user file's path
 *  under the studies folder, or, for a Builder's method study, its design);
 *  `name` its own, short, name. */
export type StudyTag = { source: string; name: string };

/** One of the design's analyses, as /analyses serves it. A study's `name`
 *  is its full `source:name`, unique beside the design's own analyses (the
 *  picker tells entries apart by name); `study` says it is one. */
export type AnalysisEntry = {
  name: string;
  /** One line: what is swept, over what, into how many curves. */
  summary: string;
  /** The analysis as the Python that constructs it (`an.to_code`). */
  code: string;
  problems: string[];
  workbench: AnalysisWorkbench;
  study?: StudyTag | null;
  /** The heading it is listed under (AK#1907, `analyses.group_of`): its
   *  `group=`, else "General". Absent from an older server: no headings. */
  group?: string;
  /** A kept multi-band optimize run (AK#1906, served as a study): picking
   *  it jumps to it rather than drawing a chart, so its `workbench` is the
   *  inert "runs: false" and this is what it holds (lib/keptRun.ts). */
  kept?: KeptRun;
  /** The analysis as data (`analyses.to_data`), which "copy as analysis"
   *  and "keep as study" send back (AK#1757 step 7 unit 4); opaque here. */
  spec?: unknown;
};

/** What a picker shows for an entry: a study's short name (the Studies
 *  group already says it is one), else the analysis's name. */
export const entryLabel = (a: AnalysisEntry): string => a.study?.name ?? a.name;

/** A list this long or shorter shows no group headings (AK#1907): the
 *  server's `analyses.GROUPS_FROM` less one, which the CLI's listing uses. */
export const GROUPS_AFTER = 3;

/** `entries` under their headings (AK#1907): `[{group, entries}]`, the
 *  groups in the order the list first names them and each group's entries in
 *  list order (the server serves them so already, `analyses.offered`). One
 *  group with a null heading when the design's own list
 *  (`listed`, its analyses whether or not they run here) is `GROUPS_AFTER`
 *  long or shorter, or names one group only: a heading there is noise. */
export function analysisGroups(
  entries: readonly AnalysisEntry[],
  listed: readonly AnalysisEntry[] = entries,
): { group: string | null; entries: AnalysisEntry[] }[] {
  const named = new Set(listed.map((a) => a.group ?? null));
  if (listed.length <= GROUPS_AFTER || named.size < 2 || named.has(null)) {
    return entries.length > 0 ? [{ group: null, entries: [...entries] }] : [];
  }
  const out: { group: string | null; entries: AnalysisEntry[] }[] = [];
  for (const a of entries) {
    const g = a.group ?? null;
    const last = out.find((x) => x.group === g);
    if (last) last.entries.push(a);
    else out.push({ group: g, entries: [a] });
  }
  return out;
}

function parseStudy(v: unknown): StudyTag | null {
  if (!v || typeof v !== "object") return null;
  const o = v as Record<string, unknown>;
  return typeof o.source === "string" && typeof o.name === "string"
    ? { source: o.source, name: o.name }
    : null;
}

const isNum = (v: unknown): v is number => typeof v === "number" && Number.isFinite(v);

/** A served spec list: an array of strings, else null (absent, or junk). */
function specList(v: unknown): string[] | null {
  return Array.isArray(v) && v.every((x) => typeof x === "string") && v.length > 0
    ? (v as string[])
    : null;
}

const CROSS_KINDS: readonly CrossKind[] = [
  "engines",
  "grounds",
  "planes",
  "designs",
  "states",
  "cells",
  "step",
];
const isStr = (v: unknown): v is string => typeof v === "string";
const reason = (v: unknown): string | null => (typeof v === "string" && v ? v : null);

/** A served list of named cells (planes, designs), else null. */
function namedList<T>(v: unknown, one: (o: Record<string, unknown>) => T | null): T[] | null {
  if (!Array.isArray(v) || v.length === 0) return null;
  const out: T[] = [];
  for (const item of v) {
    const t = item && typeof item === "object" ? one(item as Record<string, unknown>) : null;
    if (t === null) return null;
    out.push(t);
  }
  return out;
}

function rangeSpacing(r: unknown): "lin" | "log" | null {
  const sp = r && typeof r === "object" ? (r as Record<string, unknown>).spacing : null;
  return sp === "lin" || sp === "log" ? sp : null;
}

/** A design cell as served (a design cross's, or a state's own). */
function parseDesign(d: Record<string, unknown>): DesignCross | null {
  return isStr(d.name)
    ? {
        name: d.name,
        refused: reason(d.refused),
        param: isStr(d.param) ? d.param : null,
        values:
          Array.isArray(d.values) && d.values.length > 0 && d.values.every(isNum)
            ? (d.values as number[])
            : null,
        spacing: rangeSpacing(d.range),
        freqs:
          Array.isArray(d.freqs) && d.freqs.length > 0 && d.freqs.every((f) => isNum(f) && f > 0)
            ? (d.freqs as number[])
            : null,
        ...(d.reference === true ? { reference: true } : {}),
        ...(d.fixed === true ? { fixed: true } : {}),
      }
    : null;
}

/** A served MetricPlot, else null. */
export function parseMetric(v: unknown): MetricSpec | null {
  if (!v || typeof v !== "object") return null;
  const o = v as Record<string, unknown>;
  if (!isStr(o.name) || !isStr(o.unit) || o.spec === undefined) return null;
  return {
    name: o.name,
    unit: o.unit,
    relativeTo: isStr(o.relative_to) && o.relative_to ? o.relative_to : null,
    relativeUnit: isStr(o.relative_unit) ? o.relative_unit : o.unit,
    spec: o.spec,
  };
}

const isScalarKnob = (v: unknown): v is ScalarKnob =>
  isNum(v) || typeof v === "boolean" || typeof v === "string";

/** A state's knob value: a scalar, or a group knob's entries (unit 4), each
 *  a record of scalars. */
const isKnobValue = (v: unknown): v is KnobValue =>
  isScalarKnob(v) ||
  (Array.isArray(v) &&
    v.length > 0 &&
    v.every(
      (e) =>
        !!e && typeof e === "object" && !Array.isArray(e) && Object.values(e).every(isScalarKnob),
    ));

/** A served state's knobs: a record of knob values, else null. */
function knobRecord(v: unknown): Record<string, KnobValue> | null {
  const knobs = v && typeof v === "object" && !Array.isArray(v) ? v : null;
  return knobs && Object.values(knobs).every(isKnobValue) ? (knobs as Record<string, KnobValue>) : null;
}

/** A state as served (AK#1757 step 7): its knobs a flat record of numbers,
 *  booleans or strings; the cell's sweep as a design cell's; `on` one
 *  design cell per design beside a designs cross. */
function parseState(o: Record<string, unknown>): StateCross | null {
  if (!isStr(o.name) || !isStr(o.label)) return null;
  const knobs = knobRecord(o.knobs);
  if (!knobs) return null;
  const cell = parseDesign({ ...o, name: o.name });
  if (!cell) return null;
  const on = o.on === null || o.on === undefined ? null : namedList<DesignCross>(o.on, parseDesign);
  if (o.on !== null && o.on !== undefined && on === null) return null;
  return {
    refused: cell.refused,
    param: cell.param,
    values: cell.values,
    spacing: cell.spacing ?? null,
    freqs: cell.freqs ?? null,
    ...(cell.reference ? { reference: true } : {}),
    ...(cell.fixed ? { fixed: true } : {}),
    name: o.name,
    design: isStr(o.design) ? o.design : null,
    variant: isStr(o.variant) ? o.variant : null,
    knobs,
    label: o.label,
    on,
  };
}

/** A listed cell as served (`cells=`, unit 4): its label, its state or
 *  null, its own specs or null, and its sweep and refusal as a design
 *  cell's. */
function parseCell(o: Record<string, unknown>): ListedCell | null {
  if (!isStr(o.label)) return null;
  const sweep = parseDesign({ ...o, name: o.label });
  if (!sweep) return null;
  const optStr = (v: unknown): string | null | undefined =>
    v === null || v === undefined ? null : isStr(v) && v ? v : undefined;
  const engine = optStr(o.engine);
  const ground = optStr(o.ground);
  const plane = optStr(o.plane);
  if (engine === undefined || ground === undefined || plane === undefined) return null;
  let state: ListedCell["state"] = null;
  if (o.state !== null && o.state !== undefined) {
    const st = o.state as Record<string, unknown>;
    const knobs = knobRecord(st.knobs);
    if (!st || typeof st !== "object" || !isStr(st.name) || !isStr(st.label) || !knobs) return null;
    state = {
      name: st.name,
      design: isStr(st.design) ? st.design : null,
      variant: isStr(st.variant) ? st.variant : null,
      knobs,
      label: st.label,
    };
  }
  const { name: _name, ...rest } = sweep;
  void _name;
  return { ...rest, label: o.label, state, engine, ground, plane };
}

function parseStep(v: unknown): StepCross | null {
  if (!v || typeof v !== "object") return null;
  const o = v as Record<string, unknown>;
  if (!isStr(o.knob) || !Array.isArray(o.values) || !o.values.every(isNum) || o.values.length === 0) {
    return null;
  }
  const labels = Array.isArray(o.labels) && o.labels.every(isStr) ? (o.labels as string[]) : [];
  return {
    knob: o.knob,
    values: o.values as number[],
    labels: labels.length === o.values.length ? labels : [],
  };
}

function parseListed(o: Record<string, unknown>): Required<ListedCross> {
  return {
    engines: specList(o.engines),
    grounds: specList(o.grounds),
    axes: Array.isArray(o.axes)
      ? o.axes.filter((k): k is CrossKind => CROSS_KINDS.includes(k as CrossKind))
      : [],
    planes: namedList<PlaneCross>(o.planes, (p) =>
      isStr(p.name) ? { name: p.name, refused: reason(p.refused) } : null,
    ),
    designs: namedList<DesignCross>(o.designs, parseDesign),
    states: namedList<StateCross>(o.states, parseState),
    cells: namedList<ListedCell>(o.cells, parseCell),
    step: parseStep(o.step),
  };
}

const FREQUENCY_VIEWS: readonly FrequencyView[] = ["Swr", "S11", "Smith", "Rx", "Table"];
const KNOB_VIEWS: readonly KnobView[] = ["Rx", "Smith", "Table", "Metric", "Knobs"];

/** A served hold, else null (absent, or junk: the analysis then runs as a
 *  plain knob sweep would be wrong, so a malformed one is dropped with the
 *  whole entry by the caller). */
function parseHold(v: unknown): HoldRun | null | undefined {
  if (v === null || v === undefined) return null;
  if (typeof v !== "object") return undefined;
  const o = v as Record<string, unknown>;
  if (typeof o.objective !== "string" || !Array.isArray(o.knobs) || !o.knobs.every(isStr)) {
    return undefined;
  }
  if (o.knobs.length === 0 || o.spec === undefined || o.spec === null) return undefined;
  const bounds: Record<string, [number, number]> = {};
  const b = (o.bounds ?? {}) as Record<string, unknown>;
  for (const k of o.knobs as string[]) {
    const pair = b[k];
    if (Array.isArray(pair) && pair.length === 2 && isNum(pair[0]) && isNum(pair[1])) {
      bounds[k] = [pair[0], pair[1]];
    }
  }
  return {
    objective: o.objective,
    knobs: o.knobs as string[],
    bounds,
    z0: isNum(o.z0) ? o.z0 : null,
    warmStart: o.warm_start !== false,
    spec: o.spec,
  };
}

/** A served frequency list: positive numbers, at least one, else null. */
function freqList(v: unknown): number[] | null {
  return Array.isArray(v) && v.length > 0 && v.every((f) => isNum(f) && f > 0)
    ? (v as number[])
    : null;
}

function parseRange(r: unknown): SweepRangeSpec | null | undefined {
  if (r === null) return null;
  if (!r || typeof r !== "object") return undefined;
  const o = r as Record<string, unknown>;
  if (!isNum(o.lo) || !isNum(o.hi) || !(o.hi > o.lo) || !(o.lo > 0)) return undefined;
  if (o.spacing !== "lin" && o.spacing !== "log") return undefined;
  return {
    lo: o.lo,
    hi: o.hi,
    spacing: o.spacing,
    ...(isNum(o.step) ? { step: o.step } : {}),
    ...(isNum(o.points) ? { points: o.points } : {}),
    source: o.source === "file" ? "file" : "design",
  };
}

function parseFrequency(o: Record<string, unknown>, note: string | null): AnalysisWorkbench | null {
  const range = parseRange(o.range);
  if (range === undefined || !Array.isArray(o.views)) return null;
  const views = o.views.filter((v): v is FrequencyView =>
    FREQUENCY_VIEWS.includes(v as FrequencyView),
  );
  if (views.length === 0) return null;
  const swr = (o.swr ?? {}) as Record<string, unknown>;
  const scale =
    swr.scale === "auto" || swr.scale === "reciprocal" || swr.scale === "rho" ? swr.scale : null;
  return {
    runs: true,
    kind: "frequency",
    range,
    level: typeof o.level === "string" ? o.level : "",
    points: isNum(o.points) && o.points >= 2 ? Math.round(o.points) : null,
    freqs: freqList(o.freqs),
    views,
    swr: { scale, threshold: isNum(swr.threshold) ? swr.threshold : null },
    ...parseListed(o),
    note,
  };
}

/** A served pattern view, else null (an unknown view, or an angle that is
 *  no whole number of degrees). */
function parsePatternView(v: unknown): PatternViewSpec | null {
  if (!v || typeof v !== "object") return null;
  const o = v as Record<string, unknown>;
  const whole = (a: unknown): a is number => isNum(a) && Number.isInteger(a);
  if (o.view === "Elevation" && whole(o.az)) return { view: "Elevation", az: o.az };
  if (o.view === "Azimuth" && whole(o.el)) return { view: "Azimuth", el: o.el };
  if (o.view === "PatternTable") return { view: "PatternTable" };
  return null;
}

function parsePattern(o: Record<string, unknown>, note: string | null): AnalysisWorkbench | null {
  if (!Array.isArray(o.views)) return null;
  const views = o.views.map(parsePatternView).filter((v): v is PatternViewSpec => v !== null);
  if (views.length === 0) return null;
  return {
    runs: true,
    kind: "pattern",
    views,
    freq: isNum(o.freq) && o.freq > 0 ? o.freq : null,
    ...parseListed(o),
    note,
  };
}

function parseWorkbench(w: unknown): AnalysisWorkbench | null {
  if (!w || typeof w !== "object") return null;
  const o = w as Record<string, unknown>;
  if (o.runs === true) {
    const note = typeof o.note === "string" && o.note ? o.note : null;
    if (o.kind === "frequency") return parseFrequency(o, note);
    if (o.kind === "pattern") return parsePattern(o, note);
    if (typeof o.param !== "string" || !Array.isArray(o.values)) return null;
    const values = o.values.filter(isNum);
    if (values.length === 0 || values.length !== o.values.length) return null;
    const hold = parseHold(o.hold);
    if (hold === undefined) return null;
    const views = Array.isArray(o.views)
      ? o.views.filter(
          (v): v is KnobView => KNOB_VIEWS.includes(v as KnobView) && (v !== "Knobs" || hold !== null),
        )
      : [];
    const metric = parseMetric(o.metric);
    // A Metric view with no metric served has nothing to draw.
    const drawn = metric ? views : views.filter((v) => v !== "Metric");
    return {
      runs: true,
      kind: "knob",
      param: o.param,
      values,
      log: o.log === true,
      ...(drawn.length > 0 ? { views: drawn } : {}),
      ...(metric ? { metric } : {}),
      ...(hold ? { hold } : {}),
      ...parseListed(o),
      note,
    };
  }
  return { runs: false, why: typeof o.why === "string" ? o.why : "not runnable here" };
}

/** What a kept optimize run's (inert) workbench says: a chart never runs
 *  it; the picker jumps to it instead. */
export const KEPT_NOT_A_CHART = "a kept optimize run: picking it jumps to its stored answer";

/** /analyses' body as entries; anything malformed is dropped (an older
 *  server, a stub answering `{}`: no analyses, not an error). */
export function parseAnalyses(body: unknown): AnalysisEntry[] {
  const list = (body as { analyses?: unknown } | null)?.analyses;
  if (!Array.isArray(list)) return [];
  const out: AnalysisEntry[] = [];
  for (const item of list) {
    if (!item || typeof item !== "object") continue;
    const o = item as Record<string, unknown>;
    const kept = parseKept(o.workbench);
    const workbench: AnalysisWorkbench | null = kept
      ? { runs: false, why: KEPT_NOT_A_CHART }
      : parseWorkbench(o.workbench);
    if (typeof o.name !== "string" || !workbench) continue;
    out.push({
      name: o.name,
      summary: typeof o.summary === "string" ? o.summary : "",
      code: typeof o.code === "string" ? o.code : "",
      problems: Array.isArray(o.problems)
        ? o.problems.filter((p): p is string => typeof p === "string")
        : [],
      workbench,
      study: parseStudy(o.study),
      ...(typeof o.group === "string" && o.group ? { group: o.group } : {}),
      ...(kept ? { kept } : {}),
      ...(o.spec !== undefined ? { spec: o.spec } : {}),
    });
  }
  return out;
}

/** The view's spec for a runnable analysis: its parameter, the values'
 *  range and count, and the spacing. When the header's own ladder over that
 *  range (paramValues) is not exactly the served values (the density ladder
 *  of a deck's own knob, a geometric ladder that rounds differently), the
 *  spec carries the values themselves, so the view sweeps what the CLI does. */
export function analysisSpec(w: KnobWorkbench, integer: boolean): ParamSweepSpec {
  const spec: ParamSweepSpec = {
    param: w.param,
    lo: Math.min(...w.values),
    hi: Math.max(...w.values),
    points: w.values.length,
    log: w.log,
  };
  const derived = paramValues(spec, integer || w.param === DENSITY);
  const same =
    derived.length === w.values.length && derived.every((v, i) => v === w.values[i]);
  return same ? spec : { ...spec, values: [...w.values] };
}

/** Why a runnable analysis still cannot run in this session's view (its
 *  knob is not one the header can sweep: hidden on this variant, say), or
 *  null when it can. */
export function analysisBlocked(
  w: AnalysisWorkbench,
  sweepable: ReadonlySet<string>,
): string | null {
  if (!w.runs) return w.why;
  // A frequency sweep and a pattern (step 7) sweep no knob of the header's.
  if (w.kind === "frequency" || w.kind === "pattern") return null;
  if (w.param === DENSITY || sweepable.has(w.param)) return null;
  return `${w.param} is not a knob this view can sweep on this variant`;
}

/** An explicit frequency list as the range a chart sweeps: exactly those
 *  frequencies (`exact`: no refinement adds any, as `analyze` adds none),
 *  ascending so the curves draw left to right; `lo`/`hi` are its ends. */
export function listRange(freqs: readonly number[]): SweepRange {
  const sorted = [...freqs].sort((a, b) => a - b);
  return { lo: sorted[0], hi: sorted[sorted.length - 1], spacing: "lin", freqs: sorted, exact: true };
}

/** What picking a frequency analysis sets: the sweep range edit (null: the
 *  design's own range, its band policy included, which `designRange` is),
 *  and the VSWR chart's scale and threshold (null: leave the viewer's). The
 *  view it opens on is the analysis's first (lib/analysisChart.ts). */
export type FrequencyPick = {
  range: SweepRange | null;
  vswr: SweepAxisChoice | null;
  threshold: number | null;
};

function sameRange(a: SweepRange, b: SweepRange): boolean {
  return (
    a.lo === b.lo &&
    a.hi === b.hi &&
    a.spacing === b.spacing &&
    a.step === b.step &&
    a.points === b.points &&
    JSON.stringify(a.freqs ?? null) === JSON.stringify(b.freqs ?? null)
  );
}

/** A frequency analysis as the frequency sweep's settings. The range is the
 *  server's when it served one — cleared back to the design's own when that
 *  is what it is, so the menu says "file"/"design" rather than "session" —
 *  and `designRange` (this session's band policy) when it did not; the
 *  analysis's own point count replaces the range's density. "auto" is the
 *  1–∞ reciprocal scale, as a VSWR Auto reads everywhere else
 *  (`effectiveChoice`). An explicit frequency list is swept exactly
 *  (`listRange`). */
export function frequencyPick(w: FrequencyWorkbench, designRange: SweepRange): FrequencyPick {
  let range = w.range ? specRange(w.range) : designRange;
  if (w.freqs) {
    range = listRange(w.freqs);
  } else if (w.points !== null) {
    range =
      range.spacing === "lin"
        ? { lo: range.lo, hi: range.hi, spacing: "lin", step: (range.hi - range.lo) / (w.points - 1) }
        : { lo: range.lo, hi: range.hi, spacing: "log", points: w.points };
  }
  const t = w.swr.threshold;
  return {
    range: sameRange(range, designRange) ? null : range,
    vswr: w.swr.scale === null ? null : w.swr.scale === "rho" ? RHO : RECIPROCAL,
    threshold:
      t === null ? null : Math.min(SWR_THRESHOLD_MAX, Math.max(SWR_THRESHOLD_MIN, t)),
  };
}
