// Pinned sweeps (AK#1757 item 1, docs/design/sweep-framework-pins.md): a
// frozen snapshot of one analysis-chart curve that never re-solves, drawn
// dashed beside the live curves to answer "how does what I have now compare
// with what I had before I changed something".
//
// React-free, so the rules are tested alone:
//  - a pin holds solved Z at each x (port 0, the chart's curves are port 0
//    too), never pixels: every view the chart has (Smith, SWR, S11, R/X) is a
//    projection of Z, so one pin draws on any of them and survives a view
//    switch;
//  - it carries the Z0 it was taken at, and draws SWR and S11 at that Z0,
//    not the chart's; its label says so when the two differ (ruling 4);
//  - x is its kind (frequency / knob / density) and, for a knob, the knob's
//    name: a chart draws a pin only when its own x is the same kind and name
//    (a knob pin matches BY NAME across designs, ruling 3) and the two ranges
//    overlap, and draws the overlapping part. A pin that cannot draw stays
//    listed with the reason;
//  - one pin per drawn curve (ruling 1); a colour slot of its own out of
//    SWEEP_PIN_COLOR_COUNT (ruling 5), the smallest free one, stored so a
//    delete never shifts another pin's colour (the pattern pins' rule).
//
// Session-only: pins are memory, never settings.toml, never a layout.

import { gammaMagFromZ, vswrFromGammaMag } from "./math";
import { DENSITY, formatParam } from "./paramSweep";

/** The sweep-pin palette (ruling 5): 8, since pinning a full cross makes 6
 *  pins at once. Pattern pins keep their own 4 (palette.ts). */
export const SWEEP_PIN_COLOR_COUNT = 8;

export type PinXKind = "frequency" | "knob" | "density";

/** What a pin (or a chart) sweeps: the kind, the parameter's name (the knob
 *  a knob pin matches on; "frequency" and n_per_wire for the other two),
 *  and how to print it. */
export type SweepPinX = {
  kind: PinXKind;
  name: string;
  label: string;
  unit: string | null;
};

export const FREQUENCY_X: SweepPinX = { kind: "frequency", name: "frequency", label: "f", unit: "MHz" };
export const DENSITY_X: SweepPinX = { kind: "density", name: DENSITY, label: "N", unit: null };

/** A knob's x: its name is what a pin matches on. */
export function knobX(name: string, label: string, unit: string | null): SweepPinX {
  return name === DENSITY ? DENSITY_X : { kind: "knob", name, label, unit };
}

/** One curve, frozen: what `pinsFromCurves` builds and the shell stores. */
export type SweepPinSnapshot = {
  x: SweepPinX;
  /** Ascending, with zRe / zIm aligned: Z at port 0. */
  xs: number[];
  zRe: number[];
  zIm: number[];
  /** The reference the curve was drawn at. */
  z0: number;
  /** The context, as one line: design:variant · engine · ground · the knobs
   *  that differ from the design's defaults · the plane. */
  label: string;
  /** The chart cell it was, as the chart's legend named it ("" on a
   *  one-curve chart). */
  cell: string;
  /** The design it was solved on: the label names it; nothing matches on it. */
  design: string;
};

export type SweepPin = SweepPinSnapshot & {
  id: string;
  /** Show / hide, global (ruling 2): one flag, every chart. */
  enabled: boolean;
  /** Fixed slot in the sweep-pin palette, assigned at pin time. */
  colorIdx: number;
};

/** Colour slots for `n` new pins beside `pins`: each the smallest slot no
 *  pin (existing or earlier in this batch) holds; past the palette, the
 *  pattern pins' wrap (count modulo the palette). */
export function nextColorSlots(pins: readonly Pick<SweepPin, "colorIdx">[], n: number): number[] {
  const used = new Set(pins.map((p) => p.colorIdx));
  const out: number[] = [];
  let count = pins.length;
  for (let k = 0; k < n; k++) {
    let c = 0;
    while (used.has(c) && c < SWEEP_PIN_COLOR_COUNT) c++;
    if (c >= SWEEP_PIN_COLOR_COUNT) c = count % SWEEP_PIN_COLOR_COUNT;
    used.add(c);
    out.push(c);
    count++;
  }
  return out;
}

/** Add snapshots to a pin list: ids from `mint`, colour slots from
 *  nextColorSlots, enabled. */
export function withPins(
  pins: readonly SweepPin[],
  snaps: readonly SweepPinSnapshot[],
  mint: () => string,
): SweepPin[] {
  const slots = nextColorSlots(pins, snaps.length);
  return [...pins, ...snaps.map((s, k) => ({ ...s, id: mint(), enabled: true, colorIdx: slots[k] }))];
}

/** A curve as the chart holds it, for a snapshot: its x values and Z. */
export type PinnableCurve = {
  xs: readonly number[];
  zRe: readonly number[];
  zIm: readonly number[];
  x: SweepPinX;
  label: string;
  cell: string;
  design: string;
};

/** The chart's curves as pins: one per curve with points (ruling 1), each
 *  sorted by x (a refined frequency sweep lands out of order), taken at
 *  `z0`. A curve with no points pins nothing. */
export function pinsFromCurves(curves: readonly PinnableCurve[], z0: number): SweepPinSnapshot[] {
  const out: SweepPinSnapshot[] = [];
  for (const c of curves) {
    const n = Math.min(c.xs.length, c.zRe.length, c.zIm.length);
    if (n === 0) continue;
    const order = Array.from({ length: n }, (_, i) => i).sort((a, b) => c.xs[a] - c.xs[b]);
    out.push({
      x: c.x,
      xs: order.map((i) => c.xs[i]),
      zRe: order.map((i) => c.zRe[i]),
      zIm: order.map((i) => c.zIm[i]),
      z0,
      label: c.label,
      cell: c.cell,
      design: c.design,
    });
  }
  return out;
}

/** What a chart sweeps, for matching: its x and its range. Null for a view
 *  that draws no curve against an x (the Table). */
export type ChartX = { x: SweepPinX; lo: number; hi: number };

/** Where a pin draws on a chart: the indices of its points inside the
 *  chart's range, or why it cannot draw there. */
export type PinPlacement = { drawable: true; idx: number[] } | { drawable: false; reason: string };

// How a range reads in a reason.
function span(lo: number, hi: number, unit: string | null): string {
  const u = unit ? ` ${unit}` : "";
  return lo === hi ? `${formatParam(lo)}${u}` : `${formatParam(lo)}–${formatParam(hi)}${u}`;
}

/** What an x reads as in a reason: "frequency", "density", or the knob's
 *  name (the name is what matches). */
export function xPhrase(x: SweepPinX): string {
  return x.kind === "knob" ? x.name : x.kind;
}

/** Where `pin` draws on a chart sweeping `chart` (null: a view with no x,
 *  the Table). The same kind and, for a knob, the same name; then the part
 *  of it inside the chart's range, which must hold at least one point. */
export function placePin(pin: Pick<SweepPin, "x" | "xs">, chart: ChartX | null): PinPlacement {
  if (!chart) return { drawable: false, reason: "the Table lists this chart's own curves" };
  const same = pin.x.kind === chart.x.kind && (pin.x.kind !== "knob" || pin.x.name === chart.x.name);
  if (!same) {
    return { drawable: false, reason: `sweeps ${xPhrase(pin.x)}; this chart sweeps ${xPhrase(chart.x)}` };
  }
  const lo = Math.min(chart.lo, chart.hi);
  const hi = Math.max(chart.lo, chart.hi);
  // A hair of tolerance: an edge value that round-trips through a range
  // edit must not fall out on the last digit.
  const tol = 1e-9 * Math.max(1, Math.abs(lo), Math.abs(hi));
  const idx: number[] = [];
  pin.xs.forEach((v, i) => {
    if (v >= lo - tol && v <= hi + tol) idx.push(i);
  });
  if (idx.length === 0) {
    const n = pin.xs.length;
    return {
      drawable: false,
      reason: `sweeps ${span(pin.xs[0], pin.xs[n - 1], pin.x.unit)}; this chart sweeps ${span(lo, hi, chart.x.unit)}`,
    };
  }
  return { drawable: true, idx };
}

/** A pin as a chart draws it: the placed points, its colour and Z0. */
export type PinCurve = {
  id: string;
  color: string;
  label: string;
  xs: number[];
  zRe: number[];
  zIm: number[];
  z0: number;
};

/** The placed part of a pin, as a PinCurve. */
export function pinCurve(pin: SweepPin, idx: readonly number[], color: string): PinCurve {
  return {
    id: pin.id,
    color,
    label: pin.label,
    xs: idx.map((i) => pin.xs[i]),
    zRe: idx.map((i) => pin.zRe[i]),
    zIm: idx.map((i) => pin.zIm[i]),
    z0: pin.z0,
  };
}

/** A value at `x` along ascending `xs`, linear between the two samples that
 *  straddle it; null outside the samples (a pin says nothing there). */
export function valueAt(xs: readonly number[], ys: readonly number[], x: number): number | null {
  const n = Math.min(xs.length, ys.length);
  if (n === 0 || x < xs[0] || x > xs[n - 1]) return null;
  for (let i = 1; i < n; i++) {
    if (x <= xs[i]) {
      const t = xs[i] === xs[i - 1] ? 0 : (x - xs[i - 1]) / (xs[i] - xs[i - 1]);
      return ys[i - 1] + t * (ys[i] - ys[i - 1]);
    }
  }
  return ys[n - 1];
}

/** A pin's Z at `x` (interpolated in R and X), or null outside it. */
export function pinZAt(p: Pick<PinCurve, "xs" | "zRe" | "zIm">, x: number): { re: number; im: number } | null {
  const re = valueAt(p.xs, p.zRe, x);
  const im = valueAt(p.xs, p.zIm, x);
  return re === null || im === null ? null : { re, im };
}

/** The SWR a Z reads at `z0`. */
export function swrAt(re: number, im: number, z0: number): number {
  return vswrFromGammaMag(gammaMagFromZ(re, im, z0));
}

/** The label's Z0 note (ruling 4): "Z0 50 Ω" when the pin's reference is
 *  not the chart's, else null. */
export function z0Note(pinZ0: number, chartZ0: number): string | null {
  return Math.abs(pinZ0 - chartZ0) <= 1e-9 * Math.max(1, chartZ0) ? null : `Z0 ${formatParam(pinZ0)} Ω`;
}

/** The context label (the design note's "invvee:dipole · NEC-5 ·
 *  Sommerfeld 13/0.005 · height 9.5"): the design and its variant (a
 *  design's only "default" variant is left unsaid), the engine, the
 *  ground, each knob that differs from the design's defaults, the plane. */
export function pinLabel(ctx: {
  design: string;
  variant: string | null;
  engine: string;
  ground: string;
  knobs: readonly (readonly [string, number | boolean | string])[];
  plane: string | null;
}): string {
  const design = ctx.variant && ctx.variant !== "default" ? `${ctx.design}:${ctx.variant}` : ctx.design;
  const knobs = ctx.knobs.map(([k, v]) => `${k} ${typeof v === "number" ? formatParam(v) : String(v)}`);
  return [design, ctx.engine, ctx.ground, ...knobs, ...(ctx.plane ? [`plane ${ctx.plane}`] : [])]
    .filter((s) => s !== "")
    .join(" · ");
}

/** The scalar knobs whose value differs from the default, in the values'
 *  order, leaving out `skip` (the knob the chart sweeps, which varies along
 *  x). Group knobs (arrays) are left out: they have no one-word value. */
export function changedKnobs(
  values: Record<string, unknown>,
  defaults: Record<string, unknown>,
  skip: string | null,
): [string, number | boolean | string][] {
  const out: [string, number | boolean | string][] = [];
  for (const [k, v] of Object.entries(values)) {
    if (k === skip) continue;
    if (typeof v !== "number" && typeof v !== "boolean" && typeof v !== "string") continue;
    const d = defaults[k];
    const same =
      typeof v === "number" && typeof d === "number"
        ? Math.abs(v - d) <= 1e-9 * Math.max(1, Math.abs(d))
        : v === d;
    if (!same) out.push([k, v]);
  }
  return out;
}

// A CSV field: quoted when it holds a comma, quote or newline.
function field(s: string): string {
  return /[",\n]/.test(s) ? `"${s.replace(/"/g, '""')}"` : s;
}

/** The pin as CSV: two comment lines (the context and the Z0), then x, R,
 *  X and the SWR at the pin's own Z0, one row per point. */
export function pinCsv(pin: SweepPinSnapshot): string {
  const xHead = pin.x.kind === "frequency" ? "freq_mhz" : pin.x.name;
  const lines = [
    `# ${pin.label}${pin.cell ? ` (${pin.cell})` : ""}`,
    `# Z0 ${formatParam(pin.z0)} ohm`,
    [xHead, "r_ohm", "x_ohm", `swr_z0_${formatParam(pin.z0)}`].map(field).join(","),
  ];
  for (let i = 0; i < pin.xs.length; i++) {
    lines.push(
      [pin.xs[i], pin.zRe[i], pin.zIm[i], swrAt(pin.zRe[i], pin.zIm[i], pin.z0)]
        .map((v) => String(Number(v.toPrecision(10))))
        .join(","),
    );
  }
  return lines.join("\n") + "\n";
}

/** A file name for the pin's CSV: the design and what it sweeps. */
export function pinCsvName(pin: SweepPinSnapshot, id: string): string {
  const safe = (s: string) => s.replace(/[^A-Za-z0-9_.-]+/g, "_");
  return `${safe(pin.design) || "pin"}-${safe(xPhrase(pin.x))}-${safe(id)}.csv`;
}
