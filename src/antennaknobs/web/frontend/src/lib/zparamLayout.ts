// The Z-vs-parameter view's desktop geometry (components/results/ZParamStage):
// shared by the chart, which draws inside these margins, and the stage, which
// pins the readout just inside them and sizes the chart under the sweep bar.

/** The plot's margins in CSS px: the axis labels and titles live in them. */
export const ZPARAM_PLOT_MARGIN = { l: 46, r: 46, t: 18, b: 30 } as const;

/** px between the sweep bar and the chart (mirrors .zparam-area's gap). */
export const ZPARAM_HEAD_GAP = 6;

/** The chart's side: the square the caller would give it (`size`, the width
 *  bound), less the sweep bar's measured height where the box is too short
 *  for both. Before anything is measured (`boxH` 0: the first frame, or
 *  jsdom) it is `size` less `fallbackHead`. Never below 160. */
export function zparamChartSize(
  size: number,
  boxH: number,
  headH: number,
  fallbackHead: number,
): number {
  if (!(boxH > 0)) return Math.max(160, size - fallbackHead);
  const room = Math.floor(boxH - 16 - headH - ZPARAM_HEAD_GAP);
  return Math.max(160, Math.min(size, room));
}
