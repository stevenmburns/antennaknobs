// A design's analyses in the workbench (AK#1757, sweep-framework step 3):
// what POST /analyses serves, and how a runnable one becomes the
// Z-vs-parameter view's spec. React-free, so the mapping is tested alone.

import { DENSITY, paramValues, type ParamSweepSpec } from "./paramSweep";

/** How the workbench runs an analysis: `param` and `values` are what
 *  /param_sweep takes (the same ladder `antennaknobs analyze` sweeps), or the
 *  reason it cannot yet. */
export type AnalysisWorkbench =
  | { runs: true; param: string; values: number[]; log: boolean; note: string | null }
  | { runs: false; why: string };

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

function parseWorkbench(w: unknown): AnalysisWorkbench | null {
  if (!w || typeof w !== "object") return null;
  const o = w as Record<string, unknown>;
  if (o.runs === true) {
    if (typeof o.param !== "string" || !Array.isArray(o.values)) return null;
    const values = o.values.filter(isNum);
    if (values.length === 0 || values.length !== o.values.length) return null;
    return {
      runs: true,
      param: o.param,
      values,
      log: o.log === true,
      note: typeof o.note === "string" && o.note ? o.note : null,
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
export function analysisSpec(
  w: Extract<AnalysisWorkbench, { runs: true }>,
  integer: boolean,
): ParamSweepSpec {
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
  if (w.param === DENSITY || sweepable.has(w.param)) return null;
  return `${w.param} is not a knob this view can sweep on this variant`;
}
