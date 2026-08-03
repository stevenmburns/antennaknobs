import type { ConvergeData, MeasuredData, SolveResponse, SweepData } from "../../lib/api";
import type { Projection, View } from "../../lib/view";
import { CurrentCanvas } from "../charts/CurrentCanvas";
import { FarFieldChart } from "../charts/FarFieldChart";
import { SmithChart } from "../charts/SmithChart";
import type { PatternData, PinnedPattern } from "../charts/types";
import { SchematicPanel } from "./SchematicPanel";

export function ViewPanel({
  view,
  size,
  fill,
  result,
  preview,
  sweep,
  converge,
  measured,
  pattern,
  pinnedPatterns,
  measFreqMhz,
  sweepRunning,
  convergeRunning,
  azElevDeg,
  elevAzDeg,
  cameraProjection,
  showHeatmap,
  showEnvelope,
  showWireLabels = false,
  showFeedNames = true,
  multiFeed,
  fineNorm,
  schematicSvg = null,
  schematicUnavailable = false,
}: {
  view: View;
  size: number;
  fill: boolean;
  result: SolveResponse | null;
  preview: SolveResponse | null;
  sweep: SweepData | null;
  converge: ConvergeData | null;
  measured: MeasuredData | null;
  pattern: PatternData | null;
  pinnedPatterns: PinnedPattern[];
  measFreqMhz: number;
  sweepRunning: boolean;
  convergeRunning: boolean;
  azElevDeg: number;
  elevAzDeg: number;
  cameraProjection: Projection;
  showHeatmap: boolean;
  showEnvelope: boolean;
  showWireLabels?: boolean;
  showFeedNames?: boolean;
  multiFeed: boolean;
  fineNorm?: number | null;
  schematicSvg?: string | null;
  schematicUnavailable?: boolean;
}) {
  if (view === "antenna") {
    // Fall back to the geometry-only preview while the real solve is in
    // flight, but with the current heatmap/waveform overlays forced off —
    // the preview has no currents, so only the bare wires + feed are drawn.
    const showingPreview = !result && !!preview;
    return (
      <div className={fill ? "antenna-fill" : "antenna-thumb"}
           style={fill ? undefined : { width: size, height: size }}>
        <CurrentCanvas
          result={result ?? preview}
          projection={cameraProjection}
          showHeatmap={showingPreview ? false : showHeatmap}
          showEnvelope={showingPreview ? false : showEnvelope}
          showWireLabels={showWireLabels}
          showFeedNames={showFeedNames}
          interactive={fill}
        />
      </div>
    );
  }
  if (view === "azimuth") {
    return (
      <FarFieldChart
        result={result}
        pattern={pattern}
        pinned={pinnedPatterns}
        size={size}
        cut="xy"
        azElevDeg={azElevDeg}
        elevAzDeg={elevAzDeg}
        fineNorm={fineNorm}
      />
    );
  }
  if (view === "elevation") {
    return (
      <FarFieldChart
        result={result}
        pattern={pattern}
        pinned={pinnedPatterns}
        size={size}
        cut="yz"
        azElevDeg={azElevDeg}
        elevAzDeg={elevAzDeg}
        fineNorm={fineNorm}
      />
    );
  }
  if (view === "schematic") {
    return (
      <SchematicPanel
        svg={schematicSvg}
        unavailable={schematicUnavailable}
        size={size}
        fill={fill}
      />
    );
  }
  return (
    <SmithChart
      r={result?.z_in_re ?? 0}
      x={result?.z_in_im ?? 0}
      z0={result?.z0_ohms ?? 50}
      size={size}
      sweep={sweep}
      converge={converge}
      measured={measured}
      measFreqMhz={measFreqMhz}
      running={sweepRunning}
      convergeRunning={convergeRunning}
      feeds={result?.feeds}
      multiFeed={multiFeed}
    />
  );
}
