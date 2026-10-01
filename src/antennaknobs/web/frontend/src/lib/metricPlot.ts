// A metric against the swept knob (AK#1828, sweep-framework step 8,
// `an.MetricPlot`): each cell's curve, read off its knob sweep's points (the
// server reads the metric off each point's own solve, /param_sweep with
// `metric`), and, when the analysis names a reference cell, each curve less
// that cell's. React-free, so the pairing and the arithmetic are tested alone.
//
// The rules are the CLI's (`analysis_run.references`):
//  - a curve's reference is the cell the MetricPlot's `relative_to` names
//    (/analyses marks it `reference`); when it names several (one per
//    engine, say), the one that matches the curve on slot, ground, plane and
//    family step;
//  - a FIXED reference is solved once at its own setting (its sweep is its
//    one value of the swept knob) and drawn flat across the others' x;
//  - a difference is taken at the same x, never interpolated: a point the
//    reference has no value at has no difference.

import type { ParamSweepData } from "./paramSweep";

/** One drawn cell as the metric plot pairs it. */
export type MetricCell = {
  key: string;
  label: string;
  color: string;
  reference: boolean;
  fixed: boolean;
  /** What a reference must match when several are named. */
  slot: string | null;
  ground: string | null;
  plane?: string;
  step?: { knob: string; value: number };
};

/** One curve as the chart draws it: `xs` and `ys` (null where there is no
 *  value), a fixed reference as a flat `level` instead. */
export type MetricSeries = {
  key: string;
  label: string;
  color: string;
  xs: number[];
  ys: (number | null)[];
  fixed: boolean;
  /** A fixed reference's one value (the difference from itself, 0, when
   *  drawn relative). */
  level: number | null;
  stale: boolean;
  /** Why the server could not read the metric, when it could not. */
  error: string | null;
};

const sameCell = (a: MetricCell, b: MetricCell) =>
  a.slot === b.slot &&
  a.ground === b.ground &&
  a.plane === b.plane &&
  a.step?.knob === b.step?.knob &&
  a.step?.value === b.step?.value;

/** Each cell's reference: its index among `cells`, or null (none named, or
 *  none matching it). */
export function metricReferences(cells: readonly MetricCell[]): (number | null)[] {
  const named = cells.map((c, k) => (c.reference ? k : -1)).filter((k) => k >= 0);
  return cells.map((c) => {
    if (named.length === 0) return null;
    if (named.length === 1) return named[0];
    const same = named.filter((k) => sameCell(cells[k], c));
    return same.length === 1 ? same[0] : null;
  });
}

function valueAt(d: ParamSweepData | null, x: number): number | null {
  if (!d?.metric) return null;
  const i = d.values.findIndex((v) => v === x);
  const v = i >= 0 ? d.metric[i] : null;
  return v === undefined || v === null || !Number.isFinite(v) ? null : v;
}

/** The curves a metric plot draws: absolute values, or, `relative`, each
 *  less its reference at the same x (a fixed reference's one value at every
 *  x). `data[k]` is cell k's sweep. */
export function metricSeries(
  cells: readonly MetricCell[],
  data: readonly (ParamSweepData | null)[],
  relative: boolean,
): MetricSeries[] {
  const refs = relative ? metricReferences(cells) : cells.map(() => null);
  const fixedValue = (k: number): number | null => {
    const d = data[k];
    const v = d?.metric?.[0];
    return v === undefined || v === null || !Number.isFinite(v) ? null : v;
  };
  return cells.map((c, k) => {
    const d = data[k] ?? null;
    const base = {
      key: c.key,
      label: c.label,
      color: c.color,
      stale: !!d?.stale,
      error: d?.metric_error ?? null,
    };
    if (c.fixed) {
      const own = fixedValue(k);
      const r = refs[k];
      const level =
        own === null
          ? null
          : r === null
            ? relative
              ? null
              : own
            : r === k
              ? 0
              : cells[r].fixed && fixedValue(r) !== null
                ? own - (fixedValue(r) as number)
                : null;
      return { ...base, xs: [], ys: [], fixed: true, level };
    }
    const xs = d ? d.values.slice() : [];
    const ys = xs.map((x, i) => {
      const v = d?.metric?.[i];
      if (v === undefined || v === null || !Number.isFinite(v)) return null;
      if (!relative) return v;
      const r = refs[k];
      if (r === null) return null;
      const ref = cells[r].fixed ? fixedValue(r) : valueAt(data[r] ?? null, x);
      return ref === null ? null : v - ref;
    });
    return { ...base, xs, ys, fixed: false, level: null };
  });
}

/** The y range every curve and flat line spans, padded a little, or null
 *  when there is nothing to draw. */
export function metricRange(series: readonly MetricSeries[]): { lo: number; hi: number } | null {
  const ys: number[] = [];
  for (const s of series) {
    if (s.fixed) {
      if (s.level !== null) ys.push(s.level);
    } else {
      for (const y of s.ys) if (y !== null) ys.push(y);
    }
  }
  if (ys.length === 0) return null;
  let lo = Math.min(...ys);
  let hi = Math.max(...ys);
  if (hi - lo < 1e-9) {
    lo -= 0.5;
    hi += 0.5;
  }
  const pad = (hi - lo) * 0.06;
  return { lo: lo - pad, hi: hi + pad };
}

/** The x range every non-fixed curve spans, or null. */
export function metricSpan(series: readonly MetricSeries[]): { lo: number; hi: number } | null {
  const xs = series.flatMap((s) => (s.fixed ? [] : s.xs));
  if (xs.length === 0) return null;
  return { lo: Math.min(...xs), hi: Math.max(...xs) };
}
