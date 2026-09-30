import type { ParamSweepData, SweepData } from "../../lib/api";
import type { PinCurve } from "../../lib/sweepPins";

/** One more curve on a chart that already draws its own (AK#1757 step 5
 *  unit 4): an analysis chart's second to sixth engine x ground cell, in
 *  its legend colour. A frequency sweep (`sweep`) on the Swr, S11 and Smith
 *  views, or a knob sweep (`paramSweep`) on the R / X plot and the Smith
 *  chart's trail. Feed 0 only: the CLI's curves are Z at port 0 as well. */
export type ExtraCurve = {
  key: string;
  color: string;
  sweep?: SweepData | null;
  /** The sweep's shape is final (issue #866): a line, else dots. */
  settled?: boolean;
  /** Drawn for inputs since changed: dimmed, as the chart's own curve is. */
  stale?: boolean;
  paramSweep?: ParamSweepData | null;
};

export const NO_CURVES: readonly ExtraCurve[] = [];

/** The frequency span every drawn sweep covers, or null: the curves share
 *  one range, but one may land before another. */
export function sweepSpan(
  sweeps: readonly (SweepData | null | undefined)[],
): { lo: number; hi: number } | null {
  let lo = Infinity;
  let hi = -Infinity;
  for (const s of sweeps) {
    if (!s || s.freqs_mhz.length < 2) continue;
    lo = Math.min(lo, s.freqs_mhz[0]);
    hi = Math.max(hi, s.freqs_mhz[s.freqs_mhz.length - 1]);
  }
  return lo < hi ? { lo, hi } : null;
}

/** A curve's points, as data attributes a test reads instead of pixels. */
export function curvesAttr(curves: readonly ExtraCurve[]): string {
  return curves
    .map((c) => `${c.key}:${c.sweep?.freqs_mhz.length ?? c.paramSweep?.values.length ?? 0}`)
    .join(";");
}

export type { PinCurve };
export const NO_PINS: readonly PinCurve[] = [];

/** The pinned sweeps drawn (AK#1757 item 1), "id:points" each, for tests. */
export function pinsAttr(pins: readonly PinCurve[]): string {
  return pins.map((p) => `${p.id}:${p.xs.length}`).join(";");
}
