// A multi-band optimize run kept as a study (AK#1906, `an.Optimize`), as the
// workbench lists it: in the analysis picker's Studies group on the tabs of
// the design it names, where picking it JUMPS to it (the knobs at its stored
// answer, its knobs marked with its ranges, its bands and balance set), and
// the band readout offers to run it again from its start. React-free, so the
// rules are tested alone.

import type { OptimizeResult } from "../components/session/VfoPanel";
import type { OptBandRecord } from "../components/session/OptBands";
import type { KnobValue } from "./chartCells";
import {
  defaultKnobOpt,
  knobPath,
  setValueAtPath,
  type KnobOpt,
  type ParamValueBag,
  type SchemaItem,
} from "./params";

export type KeptBand = {
  freq: number;
  objective: string;
  feed: number;
  z0: number | null;
};

export type KeptBandResult = {
  freq: number;
  swrBefore: number | null;
  swrAfter: number | null;
};

/** A kept run as /analyses serves it (`analyses_offer._optimize_run`). */
export type KeptRun = {
  /** The knobs its start sets over the design's (variant's) defaults. */
  state: Record<string, KnobValue>;
  free: { name: string; min: number; max: number }[];
  bands: KeptBand[];
  mode: string;
  meanWeight: number;
  z0: number;
  result: { knobs: Record<string, number>; bands: KeptBandResult[] } | null;
};

const isNum = (v: unknown): v is number => typeof v === "number" && Number.isFinite(v);
const numOrNull = (v: unknown): number | null => (isNum(v) ? v : null);

/** A served `workbench` of kind "optimize" as a kept run, else null. */
export function parseKept(w: unknown): KeptRun | null {
  if (!w || typeof w !== "object") return null;
  const o = w as Record<string, unknown>;
  if (o.runs !== true || o.kind !== "optimize") return null;
  const free = Array.isArray(o.free)
    ? o.free.flatMap((f: unknown) => {
        const r = f as Record<string, unknown> | null;
        return r && typeof r.name === "string" && isNum(r.min) && isNum(r.max)
          ? [{ name: r.name, min: r.min, max: r.max }]
          : [];
      })
    : [];
  const bands = Array.isArray(o.bands)
    ? o.bands.flatMap((b: unknown) => {
        const r = b as Record<string, unknown> | null;
        return r && isNum(r.freq)
          ? [
              {
                freq: r.freq,
                objective: typeof r.objective === "string" ? r.objective : "swr",
                feed: isNum(r.feed) ? r.feed : 0,
                z0: numOrNull(r.z0),
              },
            ]
          : [];
      })
    : [];
  if (free.length === 0 || bands.length === 0) return null;
  const res = o.result as Record<string, unknown> | null | undefined;
  let result: KeptRun["result"] = null;
  if (res && typeof res === "object" && res.knobs && typeof res.knobs === "object") {
    const knobs: Record<string, number> = {};
    for (const [k, v] of Object.entries(res.knobs as Record<string, unknown>)) if (isNum(v)) knobs[k] = v;
    const rows = Array.isArray(res.bands)
      ? res.bands.flatMap((b: unknown) => {
          const r = b as Record<string, unknown> | null;
          return r && isNum(r.freq)
            ? [{ freq: r.freq, swrBefore: numOrNull(r.swr_before), swrAfter: numOrNull(r.swr_after) }]
            : [];
        })
      : [];
    result = { knobs, bands: rows };
  }
  return {
    state: o.state && typeof o.state === "object" ? (o.state as Record<string, KnobValue>) : {},
    free,
    bands,
    mode: typeof o.mode === "string" ? o.mode : "minimax",
    meanWeight: isNum(o.mean_weight) ? o.mean_weight : 0.5,
    z0: isNum(o.z0) ? o.z0 : 50,
    result,
  };
}

/** Why the workbench cannot run ``k`` again itself, or null. Its band run is
 *  the SWR minimax at feed 0 against the session's Z0 (the gear's Bands);
 *  any other form `antennaknobs analyze --study` runs. Jumping to the stored
 *  answer works either way. */
export function keptRunBlocked(k: KeptRun): string | null {
  if (k.mode !== "minimax" || k.bands.some((b) => b.objective !== "swr"))
    return `This run is the ${k.mode} form over ${k.bands[0].objective}; the workbench runs the SWR minimax. \`antennaknobs analyze --study\` runs it again.`;
  if (k.bands.some((b) => b.feed !== 0 || b.z0 !== null))
    return "This run reads a band at another feed or Z0; `antennaknobs analyze --study` runs it again.";
  return null;
}

/** The tab's values at the kept run: its variant's ``defaults``, the start's
 *  knobs over them, and at ``"result"`` every moved knob at its stored
 *  answer (at ``"start"``, where the start left it). */
export function keptValues(
  defaults: ParamValueBag,
  k: KeptRun,
  at: "result" | "start",
): ParamValueBag {
  let bag: ParamValueBag = { ...defaults };
  for (const [name, v] of Object.entries(k.state)) bag[name] = v as ParamValueBag[string];
  if (at === "result" && k.result) {
    for (const [name, v] of Object.entries(k.result.knobs)) {
      bag = setValueAtPath(bag, knobPath(name), v) as ParamValueBag;
    }
  }
  return bag;
}

/** The knob marks a kept run sets: each moved knob marked, over its range;
 *  every other knob as the schema seeds it, unmarked. */
export function keptMarks(k: KeptRun, schema: SchemaItem[]): Record<string, KnobOpt> {
  const out: Record<string, KnobOpt> = {};
  for (const f of k.free) {
    out[f.name] = { ...defaultKnobOpt(schema, f.name), vary: true, optMin: f.min, optMax: f.max };
  }
  return out;
}

/** The stored before/after table in the band result's shape, so the readout
 *  draws it as it draws a run's. Null with no stored result. */
export function keptAsResult(k: KeptRun): OptimizeResult | null {
  if (!k.result) return null;
  const rec = (freq: number, swr: number | null, i: number): OptBandRecord => ({
    index: i,
    freq_mhz: freq,
    objective: "swr",
    feed: 0,
    z0_ohms: k.z0,
    z_re: null,
    z_im: null,
    swr,
    residual: null,
    value: swr,
  });
  const before = k.result.bands.map((b, i) => rec(b.freq, b.swrBefore, i));
  const after = k.result.bands.map((b, i) => rec(b.freq, b.swrAfter, i));
  const worst = (xs: (number | null)[]) =>
    xs.some((x) => x === null) ? null : Math.max(...(xs as number[]));
  const empty = { z_in_re: 0, z_in_im: 0, z0_ohms: k.z0, swr: 0 };
  return {
    objective: "bands",
    params: { ...k.result.knobs },
    objective_before: 0,
    objective_after: 0,
    metrics_before: empty,
    metrics_after: empty,
    n_evals: 0,
    improved: true,
    bands_before: before,
    bands_after: after,
    worst_swr_before: worst(k.result.bands.map((b) => b.swrBefore)),
    worst_swr_after: worst(k.result.bands.map((b) => b.swrAfter)),
  };
}
