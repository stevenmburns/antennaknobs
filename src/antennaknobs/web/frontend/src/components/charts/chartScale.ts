import { createContext, useContext, useMemo } from "react";
import { useIsMobile } from "../hooks";

// The canvas charts' one size knob (AK#1757 unit 6, AK#1807). Steve's laptop
// review: at 100 % browser zoom on a 13" laptop the charts' text and marks
// were too small, and 125 % read right. The page's `--text-*` scale cannot
// reach a canvas, so the charts take a scale of their own:
//
//   - `--chart-scale` in styles.css: 1.25 on a laptop or desktop, 1 on a
//     phone (the phone's sizes were tuned by hand in units 3-4 and stay).
//     The DOM laid over a chart (its legend, chip, axis buttons) reads the
//     same property in calc().
//   - `useChartScale()` reads it ONCE per chart and breakpoint (not per
//     frame) and a chart draws in a logical square of `size / k` px under a
//     `k` transform (`fitChartCanvas`). So every fixed-px thing the chart
//     draws — the type ramp below, line widths, marker radii, margins, the
//     offsets that sit text beside a tick — grows by k together, while
//     anything drawn as a fraction of the side (the Smith disc, a polar
//     plot's rings, the plot box) keeps the chart's full size. That is what
//     browser zoom does to the canvas, without the rest of the page.
//
// A thumbnail pins k = 1 (ChartScaleContext): it draws at the rail's column
// width and is then shrunk, so a larger ramp only crowds a miniature that is
// a button, not a chart to read.

/** The chart type ramp, in logical px (× the chart scale on screen). */
export const CHART_TYPE = {
  /** Tick labels, value boxes, reference-line and grid labels. */
  tick: 9,
  /** Axis titles, captions, status lines. */
  label: 10,
  /** Readouts: the Z∞ line, a peak or summary value. */
  readout: 10,
} as const;

export type ChartTypeRole = keyof typeof CHART_TYPE;

const MONO = "ui-monospace, monospace";

/** The canvas font for a role: what every chart's `ctx.font` is set to. */
export const CHART_FONT: Record<ChartTypeRole, string> = {
  tick: `${CHART_TYPE.tick}px ${MONO}`,
  label: `${CHART_TYPE.label}px ${MONO}`,
  readout: `${CHART_TYPE.readout}px ${MONO}`,
};

/** A canvas font at `px` px, for a canvas whose text size is computed: the
 *  antenna view (CurrentCanvas), which is not on the chart scale — it
 *  already sizes its labels from its own canvas (its `s`, thumbnail to
 *  stage) and has a camera zoom of its own. */
export function chartFontPx(px: number): string {
  return `${px}px ${MONO}`;
}

export const CHART_SCALE_VAR = "--chart-scale";

/** The scale the stylesheet sets, read from `el` (default: the root). No
 *  stylesheet (jsdom) or a nonsense value reads as 1, the unscaled chart. */
export function readChartScale(el: Element = document.documentElement): number {
  const raw = getComputedStyle(el).getPropertyValue(CHART_SCALE_VAR).trim();
  const k = Number.parseFloat(raw);
  return Number.isFinite(k) && k >= 0.5 && k <= 3 ? k : 1;
}

/** A pinned scale for a subtree: the thumbnail strip gives 1. Null (the
 *  default) means "read the stylesheet". */
export const ChartScaleContext = createContext<number | null>(null);

/** The chart scale for this chart: 1 on a phone whatever the stylesheet
 *  says (the phone's hand-tuned sizes are the contract), else the pinned
 *  scale or `--chart-scale`, read once per breakpoint change. */
export function useChartScale(): number {
  const pinned = useContext(ChartScaleContext);
  const { isMobile } = useIsMobile();
  const read = useMemo(() => (isMobile ? 1 : readChartScale()), [isMobile]);
  return isMobile ? 1 : (pinned ?? read);
}

/** Size a chart's canvas to `size` CSS px (at the device's pixel ratio) and
 *  set the transform so it draws in a logical square of `size / k` px.
 *  Returns that logical side: the chart's drawing and hit-testing use it
 *  wherever they used `size`, and pointer offsets are divided by k. */
export function fitChartCanvas(
  canvas: HTMLCanvasElement,
  ctx: CanvasRenderingContext2D,
  size: number,
  k: number,
): number {
  const dpr = window.devicePixelRatio || 1;
  canvas.width = Math.floor(size * dpr);
  canvas.height = Math.floor(size * dpr);
  canvas.style.width = `${size}px`;
  canvas.style.height = `${size}px`;
  ctx.setTransform(dpr * k, 0, 0, dpr * k, 0, 0);
  return size / k;
}
