import { useContext, useEffect, useRef } from "react";
import type { SolveResponse } from "../../lib/api";
import { cutDbiTop, cutDbiToFrac } from "../../lib/refine";
import { ThemeContext } from "../hooks";
import { CHART_FONT, fitChartCanvas, useChartScale } from "./chartScale";
import { cutsRedrawKey, traceFor, useCutTraces } from "./cuts";
import { plotColors } from "./palette";
import { drawDbiRings, type PolarGeom, strokeTrace } from "./polar";
import type { FarFieldCut } from "./types";

// A pattern analysis's cut (AK#1757, sweep-framework step 7 unit 3): one
// trace per cell, in the cell's colour, on the far-field charts' polar grid
// (FarFieldChart's radial map, rings and trace stroke), each trace cut from
// that cell's own solve through the same machinery as the live lobe and the
// pinned ghosts (useCutTraces: the angles the solve shipped with, else
// POST /cuts). The legend beside it names the cells (ChartLegend).

/** One cell as the chart draws it. */
export type PatternCellTrace = {
  key: string;
  label: string;
  color: string;
  result: SolveResponse | null;
  /** Inputs changed since it solved (dwell switch off): drawn dimmed. */
  stale: boolean;
};

export function AnalysisPatternChart({
  cut,
  azElevDeg,
  elevAzDeg,
  cells,
  size,
}: {
  /** "yz": the elevation cut through azimuth `elevAzDeg`; "xy": the
   *  azimuth cut at elevation `azElevDeg`. */
  cut: FarFieldCut;
  azElevDeg: number;
  elevAzDeg: number;
  cells: readonly PatternCellTrace[];
  size: number;
}) {
  const theme = useContext(ThemeContext); // repaint on theme toggle
  const k = useChartScale();
  const canvasRef = useRef<HTMLCanvasElement>(null);
  const traces = useCutTraces(
    cut,
    cells.map((c) => c.result),
    azElevDeg,
    elevAzDeg,
  );
  const tracesKey = cutsRedrawKey(traces);
  const drawn = cells.map((c, i) => ({ cell: c, trace: traceFor(traces[i], cut) }));
  // Which cells draw a trace, for a test to read rather than the pixels.
  const drawnLabels = drawn.filter((d) => d.trace).map((d) => d.cell.label);
  const drawKey = JSON.stringify(
    cells.map((c) => [c.key, c.color, c.stale, c.result?.solve_id ?? null]),
  );

  useEffect(() => {
    const canvas = canvasRef.current;
    if (!canvas) return;
    const ctx = canvas.getContext("2d");
    if (!ctx) return;
    const sz = fitChartCanvas(canvas, ctx, size, k);
    const PC = plotColors();
    ctx.fillStyle = PC.bg;
    ctx.fillRect(0, 0, sz, sz);
    const R = sz / 2 - 14;
    // The radial scale fits the highest lobe of every cell, as the
    // far-field charts fit the live lobe and the pinned ghosts together.
    const peaks = drawn.flatMap((d) => (d.trace ? [d.trace.peakDbi] : []));
    const dbiToFrac = cutDbiToFrac(cutDbiTop(peaks));
    const geom: PolarGeom = { cx: sz / 2, cy: sz / 2, R, dbiToFrac };
    drawDbiRings(ctx, geom, PC);
    ctx.fillStyle = PC.labelDim;
    ctx.font = CHART_FONT.label;
    ctx.fillText(
      cut === "xy" ? `az @ ${azElevDeg}° elev (dBi)` : `elev @ ${elevAzDeg}° az (dBi)`,
      6,
      14,
    );
    for (const { cell, trace } of drawn) {
      if (!trace) continue;
      strokeTrace(ctx, geom, trace.dbi, {
        stroke: cell.color,
        width: cell.stale ? 1 : 1.6,
        ...(cell.stale ? { dash: [4, 3] } : {}),
        anglesDeg: trace.anglesDeg,
      });
    }
    // drawKey and tracesKey stand in for the cells and their traces.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [drawKey, tracesKey, cut, azElevDeg, elevAzDeg, size, k, theme]);

  return (
    <canvas
      ref={canvasRef}
      className="farfield analysis-pattern"
      role="img"
      aria-label={
        cut === "xy"
          ? `Azimuth cut at ${azElevDeg}° elevation`
          : `Elevation cut at ${elevAzDeg}° azimuth`
      }
      data-cut={cut}
      data-traces={JSON.stringify(drawnLabels)}
    />
  );
}
