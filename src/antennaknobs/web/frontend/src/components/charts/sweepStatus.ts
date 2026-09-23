// The sweep charts' status line (AK#1682). It used to be a bare "sweeping…"
// that said nothing about how far along a sweep was and nothing at all
// during refinement; now it counts the points that actually landed.
import {
  sweepProgressFraction,
  sweepProgressLabel,
  type SweepProgress,
} from "../../lib/sweep";

/** The text the chart prints bottom-left, or null for none. `progress` wins
 *  over `running` — a refinement pass streams with `running` false (see
 *  useAnalysisRunners), and a caller that has no progress (an older call
 *  site, a test) still gets the old "sweeping…" rather than nothing. */
export function sweepStatusText(
  running: boolean,
  progress: SweepProgress | null | undefined,
): string | null {
  if (progress) return sweepProgressLabel(progress);
  return running ? "sweeping…" : null;
}

/** A 2 px bar along the canvas's bottom edge filled to the base sweep's
 *  received fraction. Refinement draws none: it has no known end, and a bar
 *  that stops at 30 % when the planner concludes would read as a failure. */
export function drawSweepProgressBar(
  ctx: CanvasRenderingContext2D,
  progress: SweepProgress | null | undefined,
  size: number,
  color: string,
): void {
  if (!progress) return;
  const frac = sweepProgressFraction(progress);
  if (frac == null) return;
  ctx.fillStyle = color;
  ctx.globalAlpha = 0.6;
  ctx.fillRect(0, size - 2, size * frac, 2);
  ctx.globalAlpha = 1;
}

/** The data-* attribute value tests read (canvas pixels are invisible to
 *  jsdom), e.g. "base:12/17" or "refine:8/48". Empty when idle. */
export function sweepProgressAttr(
  progress: SweepProgress | null | undefined,
): string {
  if (!progress) return "";
  return progress.phase === "base"
    ? `base:${progress.received}/${progress.planned}`
    : `refine:${progress.received}/${progress.budget}`;
}
