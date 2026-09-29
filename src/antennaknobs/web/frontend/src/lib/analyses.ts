// A design's analyses in the workbench (AK#1757, sweep-framework steps 3-4):
// what POST /analyses serves, and how a runnable one becomes the
// Z-vs-parameter view's spec (a knob sweep) or the frequency sweep's range,
// charts and SWR axis (a frequency sweep). React-free, so the mapping is
// tested alone.

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

/** A knob sweep: `param` and `values` are what /param_sweep takes (the same
 *  ladder `antennaknobs analyze` sweeps). */
export type KnobWorkbench = {
  runs: true;
  kind: "knob";
  param: string;
  values: number[];
  log: boolean;
  note: string | null;
} & Listed;

/** The engine and ground specs the analysis lists (its cross, else its one
 *  engine or ground), or null where it names none: the analysis chart's
 *  preselection (lib/chartCells.ts, AK#1757 step 5 unit 4). Optional: an
 *  older server serves neither, and the chart then draws the active slot. */
export type Listed = {
  engines?: string[] | null;
  grounds?: string[] | null;
};

/** The views a frequency analysis draws here, by the server's names. */
export type FrequencyView = "Swr" | "S11" | "Smith";

/** A frequency sweep (step 4). `range` is the span and grid the server
 *  resolved (`frequency_range`) when it is absolute — the analysis's own or
 *  the design's; null when it is the band policy, which is relative to this
 *  session's band and so is ours to place. `points` is the analysis's own
 *  count. `swr` is the Swr view's scale and the threshold line. */
export type FrequencyWorkbench = {
  runs: true;
  kind: "frequency";
  range: SweepRangeSpec | null;
  level: string;
  points: number | null;
  views: FrequencyView[];
  swr: { scale: "auto" | "reciprocal" | "rho" | null; threshold: number | null };
  note: string | null;
} & Listed;

/** How the workbench runs an analysis, or the reason it cannot yet. */
export type AnalysisWorkbench = KnobWorkbench | FrequencyWorkbench | { runs: false; why: string };

/** One of the design's analyses, as /analyses serves it. */
export type AnalysisEntry = {
  name: string;
  /** One line: what is swept, over what, into how many curves. */
  summary: string;
  /** The analysis as the Python that constructs it (`an.to_code`). */
  code: string;
  problems: string[];
  workbench: AnalysisWorkbench;
};

const isNum = (v: unknown): v is number => typeof v === "number" && Number.isFinite(v);

/** A served spec list: an array of strings, else null (absent, or junk). */
function specList(v: unknown): string[] | null {
  return Array.isArray(v) && v.every((x) => typeof x === "string") && v.length > 0
    ? (v as string[])
    : null;
}

function parseListed(o: Record<string, unknown>): { engines: string[] | null; grounds: string[] | null } {
  return { engines: specList(o.engines), grounds: specList(o.grounds) };
}

const FREQUENCY_VIEWS: readonly FrequencyView[] = ["Swr", "S11", "Smith"];

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
    views,
    swr: { scale, threshold: isNum(swr.threshold) ? swr.threshold : null },
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
    if (typeof o.param !== "string" || !Array.isArray(o.values)) return null;
    const values = o.values.filter(isNum);
    if (values.length === 0 || values.length !== o.values.length) return null;
    return {
      runs: true,
      kind: "knob",
      param: o.param,
      values,
      log: o.log === true,
      ...parseListed(o),
      note,
    };
  }
  return { runs: false, why: typeof o.why === "string" ? o.why : "not runnable here" };
}

/** /analyses' body as entries; anything malformed is dropped (an older
 *  server, a stub answering `{}`: no analyses, not an error). */
export function parseAnalyses(body: unknown): AnalysisEntry[] {
  const list = (body as { analyses?: unknown } | null)?.analyses;
  if (!Array.isArray(list)) return [];
  const out: AnalysisEntry[] = [];
  for (const item of list) {
    if (!item || typeof item !== "object") continue;
    const o = item as Record<string, unknown>;
    const workbench = parseWorkbench(o.workbench);
    if (typeof o.name !== "string" || !workbench) continue;
    out.push({
      name: o.name,
      summary: typeof o.summary === "string" ? o.summary : "",
      code: typeof o.code === "string" ? o.code : "",
      problems: Array.isArray(o.problems)
        ? o.problems.filter((p): p is string => typeof p === "string")
        : [],
      workbench,
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
  if (w.kind === "frequency") return null;
  if (w.param === DENSITY || sweepable.has(w.param)) return null;
  return `${w.param} is not a knob this view can sweep on this variant`;
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
    a.points === b.points
  );
}

/** A frequency analysis as the frequency sweep's settings. The range is the
 *  server's when it served one — cleared back to the design's own when that
 *  is what it is, so the menu says "file"/"design" rather than "session" —
 *  and `designRange` (this session's band policy) when it did not; the
 *  analysis's own point count replaces the range's density. "auto" is the
 *  1–∞ reciprocal scale, as a VSWR Auto reads everywhere else
 *  (`effectiveChoice`). */
export function frequencyPick(w: FrequencyWorkbench, designRange: SweepRange): FrequencyPick {
  let range = w.range ? specRange(w.range) : designRange;
  if (w.points !== null) {
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
