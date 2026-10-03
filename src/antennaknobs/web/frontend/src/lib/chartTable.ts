// The analysis chart's Table view (AK#1757, sweep-framework step 5 unit 5):
// the numbers `antennaknobs analyze` prints for an analysis's `Table` view,
// as one table. React-free, so the columns and the formatting are tested
// against the CLI's printed table alone.
//
// The CLI prints one block per curve (analysis_run._print_frequency_table,
// _print_sweep_table, and sweep._print_convergence_table for a density
// ladder); the chart prints one row per x value and one column group per
// curve, so the curves of a multi-curve chart read side by side. The
// columns and the number formats are the CLI's:
//   - a frequency sweep: MHz (%.6g), then per curve R (%.3f), X (%+.3f) and
//     SWR against the session's Z0 (%.3f, (1 + |Γ|)/(1 − |Γ|), sweep.swr_of);
//   - a knob sweep: the knob (%.6g), then R and X;
//   - a density ladder: nominal_N, then per curve N_ach, R, X and |ΔΓ|
//     against that curve's finest rung (%.4f);
//   - a knob sweep with a MetricPlot (AK#1867): after R and X, the metric
//     and, relative to a reference, the difference from it, as the CLI's
//     metric table prints them (analysis_run._print_metric_table, %.3f,
//     "—" where there is no value).
// Curves whose x values differ (a design cell on its own band, a refined
// frequency sweep) share the rows they have in common, and a cell a curve
// has no point at is left blank.

import { DENSITY } from "./paramSweep";
import { fileSafe } from "./sweepPins";

export type TableKind = "frequency" | "knob" | "density";

/** One curve: its legend label, its x values and Z at port 0 (index
 *  aligned), and for a density ladder the achieved segment counts. */
export type TableCurve = {
  label: string;
  xs: readonly number[];
  re: readonly number[];
  im: readonly number[];
  nAch?: readonly number[];
  /** A held knob sweep (AK#1757 step 6): each held knob's value at every
   *  x (index aligned), a column of its own after R and X, as the CLI's
   *  held table prints them; and the points the hold did not reach, each a
   *  row reading "gap" and its reason, never a value. */
  held?: Readonly<Record<string, readonly number[]>>;
  gaps?: readonly { value: number; reason: string }[];
  /** A MetricPlot's metric at every x and, on a relative plot, its
   *  difference from the curve's reference (index aligned; null: none). */
  metric?: readonly (number | null)[];
  relative?: readonly (number | null)[];
};

/** A knob table's metric columns (AK#1867): the metric's heading and, on a
 *  relative plot, the difference's. */
export type MetricColumns = { metric: string; relative: string | null };

export type ChartTableData = {
  kind: TableKind;
  /** The x column's heading, as the CLI prints it. */
  xName: string;
  /** Each curve's label and its column names, in order. */
  groups: { label: string; columns: string[] }[];
  /** One row per x value, ascending: the x cell, then every group's cells
   *  ("" where that curve has no point at this x). */
  rows: string[][];
};

/** Python's `%.<prec>g`: `prec` significant digits, trailing zeros dropped,
 *  exponent form below 1e-4 or at 10^prec and above (`e+NN`). */
export function formatG(v: number, prec = 6): string {
  if (Number.isNaN(v)) return "nan";
  if (!Number.isFinite(v)) return v > 0 ? "inf" : "-inf";
  if (v === 0) return Object.is(v, -0) ? "-0" : "0";
  const [mant, expText] = v.toExponential(prec - 1).split("e");
  const exp = Number(expText);
  const strip = (s: string) => (s.includes(".") ? s.replace(/0+$/, "").replace(/\.$/, "") : s);
  if (exp < -4 || exp >= prec) {
    const e = Math.abs(exp);
    return `${strip(mant)}e${exp < 0 ? "-" : "+"}${e < 10 ? `0${e}` : e}`;
  }
  return strip(v.toFixed(prec - 1 - exp));
}

/** Python's `%.<digits>f`, with `inf` / `nan` spelled as Python does. */
export function formatF(v: number, digits: number, plus = false): string {
  if (Number.isNaN(v)) return "nan";
  if (!Number.isFinite(v)) return v > 0 ? `${plus ? "+" : ""}inf` : "-inf";
  const s = v.toFixed(digits);
  return plus && !s.startsWith("-") ? `+${s}` : s;
}

/** SWR against `z0`, the CLI's formula (sweep.swr_of): (1 + |Γ|)/(1 − |Γ|),
 *  infinite at |Γ| = 1. */
export function swrAt(re: number, im: number, z0: number): number {
  const gamma = gammaOf(re, im, z0);
  const rho = Math.hypot(gamma.re, gamma.im);
  return (1 + rho) / (1 - rho);
}

function gammaOf(re: number, im: number, z0: number): { re: number; im: number } {
  // (z − z0)/(z + z0), complex.
  const nr = re - z0;
  const dr = re + z0;
  const den = dr * dr + im * im;
  return { re: (nr * dr + im * im) / den, im: (im * dr - nr * im) / den };
}

/** The x column's heading: MHz, the knob, or the CLI's `nominal_N` for the
 *  density ladder. */
export function tableXName(kind: TableKind, param: string): string {
  if (kind === "frequency") return "MHz";
  if (kind === "density") return param === DENSITY ? "nominal_N" : param;
  return param;
}

const COLUMNS: Record<TableKind, string[]> = {
  frequency: ["R (Ω)", "X (Ω)", "SWR"],
  knob: ["R (Ω)", "X (Ω)"],
  density: ["N_ach", "R (Ω)", "X (Ω)", "|ΔΓ|"],
};

// Two x values are one row when they agree to this relative tolerance (a
// served frequency and the same frequency from another curve's grid).
const SAME_X = 1e-9;
const sameX = (a: number, b: number) => Math.abs(a - b) <= SAME_X * Math.max(1, Math.abs(a), Math.abs(b));

/** The table for `curves` of a `kind` sweep of `param`, against `z0`. */
export function chartTable(
  kind: TableKind,
  param: string,
  curves: readonly TableCurve[],
  z0: number,
  metric: MetricColumns | null = null,
): ChartTableData {
  const metricCols =
    kind === "knob" && metric ? [metric.metric, ...(metric.relative ? [metric.relative] : [])] : [];
  const metricCell = (v: number | null | undefined) =>
    v === null || v === undefined || !Number.isFinite(v) ? "—" : formatF(v, 3);
  const xs: number[] = [];
  for (const c of curves) for (const x of c.xs) xs.push(x);
  for (const c of curves) for (const g of c.gaps ?? []) xs.push(g.value);
  xs.sort((a, b) => a - b);
  const rowXs: number[] = [];
  for (const x of xs) if (rowXs.length === 0 || !sameX(rowXs[rowXs.length - 1], x)) rowXs.push(x);
  const cells = curves.map((c) => {
    // |ΔΓ| is against the curve's finest rung: its largest x (the CLI's
    // last row, the ladder ascending).
    let finest = -1;
    c.xs.forEach((x, i) => {
      if (finest < 0 || x > c.xs[finest]) finest = i;
    });
    const g0 = finest >= 0 ? gammaOf(c.re[finest], c.im[finest], z0) : null;
    const knobs = kind === "knob" ? Object.keys(c.held ?? {}) : [];
    const width = COLUMNS[kind].length + knobs.length + metricCols.length;
    const metricAt = (i: number) =>
      metricCols.length === 0
        ? []
        : [metricCell(c.metric?.[i]), ...(metric?.relative ? [metricCell(c.relative?.[i])] : [])];
    return (x: number): string[] => {
      const i = c.xs.findIndex((v) => sameX(v, x));
      if (i < 0) {
        const gap = (c.gaps ?? []).find((g) => sameX(g.value, x));
        if (gap && kind === "knob") {
          return ["gap", gap.reason, ...knobs.map(() => ""), ...metricCols.map(() => "")];
        }
        return Array.from({ length: width }, () => "");
      }
      const r = c.re[i];
      const im = c.im[i];
      const rx = [formatF(r, 3), formatF(im, 3, true)];
      if (kind === "frequency") return [...rx, formatF(swrAt(r, im, z0), 3)];
      if (kind === "knob") {
        return [...rx, ...knobs.map((k) => formatG(c.held?.[k]?.[i] ?? Number.NaN, 6)), ...metricAt(i)];
      }
      const g = gammaOf(r, im, z0);
      const dg = g0 ? Math.hypot(g.re - g0.re, g.im - g0.im) : NaN;
      const n = c.nAch?.[i];
      return [n !== undefined ? String(Math.round(n)) : "", ...rx, formatF(dg, 4)];
    };
  });
  const xCell = (x: number) => (kind === "density" ? String(Math.round(x)) : formatG(x, 6));
  return {
    kind,
    xName: tableXName(kind, param),
    groups: curves.map((c) => ({
      label: c.label,
      columns:
        kind === "knob" ? [...COLUMNS[kind], ...Object.keys(c.held ?? {}), ...metricCols] : COLUMNS[kind],
    })),
    rows: rowXs.map((x) => [xCell(x), ...cells.flatMap((cell) => cell(x))]),
  };
}

/** The table as tab-separated text, for the clipboard: a heading row (each
 *  column named "<curve> <column>" when there are several curves, or by
 *  its column alone for one), then the rows. */
export function tableTsv(t: ChartTableData): string {
  const named = t.groups.length > 1 || (t.groups[0]?.label ?? "") !== "";
  const head = [
    t.xName,
    ...t.groups.flatMap((g) => g.columns.map((c) => (named && g.label ? `${g.label} ${c}` : c))),
  ];
  return [head, ...t.rows].map((r) => r.join("\t")).join("\n") + "\n";
}

// RFC 4180: a field with a comma, a quote or a line break is quoted, and its
// quotes doubled.
function csvField(f: string): string {
  return /[",\r\n]/.test(f) ? `"${f.replace(/"/g, '""')}"` : f;
}

/** The same table as comma-separated values: the heading and cells exactly
 *  as tableTsv has them (no further rounding), CSV-quoted, CRLF-free. */
export function tableCsv(t: ChartTableData): string {
  const named = t.groups.length > 1 || (t.groups[0]?.label ?? "") !== "";
  const head = [
    t.xName,
    ...t.groups.flatMap((g) => g.columns.map((c) => (named && g.label ? `${g.label} ${c}` : c))),
  ];
  return [head, ...t.rows].map((r) => r.map(csvField).join(",")).join("\n") + "\n";
}

/** The CSV's file name: `<design>-<what the chart sweeps>.csv`, the sweep
 *  being "frequency", "density" or the knob's name. */
export function tableCsvName(t: ChartTableData, design: string): string {
  const what = t.kind === "knob" ? t.xName : t.kind;
  return `${fileSafe(design) || "table"}-${fileSafe(what) || "sweep"}.csv`;
}
