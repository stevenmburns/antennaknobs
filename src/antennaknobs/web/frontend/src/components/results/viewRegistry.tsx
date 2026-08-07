import type { ReactElement } from "react";
import type { ConvergeData, MeasuredData, SolveResponse, SweepData } from "../../lib/api";
import type { Projection, View } from "../../lib/view";
import { CurrentCanvas } from "../charts/CurrentCanvas";
import { FarFieldChart } from "../charts/FarFieldChart";
import { SmithChart } from "../charts/SmithChart";
import { SweepChart } from "../charts/SweepChart";
import type { PatternData, PinnedPattern } from "../charts/types";
import { SchematicPanel } from "./SchematicPanel";

// The render half of the view registry (the metadata half — id, label,
// defaultPinned — is VIEWS in lib/view.ts, which stays component-free).
//
// Every view receives the same prop bag: the stage hands out one set of
// inputs and each view takes what it needs, so adding a view is one entry
// here plus its component, with no plumbing at the call sites.
export type ViewRenderProps = {
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
  showWireLabels: boolean;
  showFeedNames: boolean;
  multiFeed: boolean;
  fineNorm?: number | null;
  /** Adaptive resolution (issue #744) is ON for this session — the Smith
   *  chart uses it to draw the sweep as a connected locus (the refined,
   *  frequency-sorted samples finally support one). Optional: thumbnail
   *  call sites omit it and keep the dot trail. */
  refineEnabled?: boolean;
  // A trial impedance to plot INSTEAD of `result`'s, while something drives
  // the design faster than the solve channel can follow — today the streamed
  // optimizer (#773), whose per-eval frames carry Z but do not touch the
  // knobs until the run ends, so `result` sits at the last real solve for the
  // whole run and the dot appears frozen.
  //
  // Structural rather than the optimizer's own type: the view layer does not
  // care who is proposing the point. REQUIRED, not defaulted — a new view
  // surface that forgot it would silently show a frozen dot again, which is
  // the defect this exists to fix, so the compiler names every call site.
  liveZ: { z_in_re: number; z_in_im: number; z0_ohms: number } | null;
  schematicSvg: string | null;
  schematicUnavailable: boolean;
};

// Plain functions, not components: ViewPanel calls the entry rather than
// mounting it, so the rendered tree has exactly the depth it had when this
// was a conditional — no extra fiber between the panel and the chart.
//
// Record<View, …> is the exhaustiveness gate: a new member of the View union
// fails to typecheck until it has an entry.
export const VIEW_RENDERERS: Record<View, (p: ViewRenderProps) => ReactElement> = {
  antenna: (p) => {
    // Fall back to the geometry-only preview while the real solve is in
    // flight, but with the current heatmap/waveform overlays forced off —
    // the preview has no currents, so only the bare wires + feed are drawn.
    const showingPreview = !p.result && !!p.preview;
    return (
      <div className={p.fill ? "antenna-fill" : "antenna-thumb"}
           style={p.fill ? undefined : { width: p.size, height: p.size }}>
        <CurrentCanvas
          result={p.result ?? p.preview}
          projection={p.cameraProjection}
          showHeatmap={showingPreview ? false : p.showHeatmap}
          showEnvelope={showingPreview ? false : p.showEnvelope}
          showWireLabels={p.showWireLabels}
          showFeedNames={p.showFeedNames}
          interactive={p.fill}
        />
      </div>
    );
  },
  azimuth: (p) => (
    <FarFieldChart
      result={p.result}
      pattern={p.pattern}
      pinned={p.pinnedPatterns}
      size={p.size}
      cut="xy"
      azElevDeg={p.azElevDeg}
      elevAzDeg={p.elevAzDeg}
      fineNorm={p.fineNorm}
    />
  ),
  elevation: (p) => (
    <FarFieldChart
      result={p.result}
      pattern={p.pattern}
      pinned={p.pinnedPatterns}
      size={p.size}
      cut="yz"
      azElevDeg={p.azElevDeg}
      elevAzDeg={p.elevAzDeg}
      fineNorm={p.fineNorm}
    />
  ),
  // liveZ wins over result while it is set: during an optimizer run it is the
  // only current impedance there is (see ViewRenderProps.liveZ). The z0
  // fallback chain still ends at result's, so a trial point is plotted on the
  // same reference the settled dot uses.
  smith: (p) => (
    <SmithChart
      r={p.liveZ?.z_in_re ?? p.result?.z_in_re ?? 0}
      x={p.liveZ?.z_in_im ?? p.result?.z_in_im ?? 0}
      z0={p.liveZ?.z0_ohms ?? p.result?.z0_ohms ?? 50}
      trial={p.liveZ != null}
      size={p.size}
      sweep={p.sweep}
      converge={p.converge}
      measured={p.measured}
      measFreqMhz={p.measFreqMhz}
      running={p.sweepRunning}
      convergeRunning={p.convergeRunning}
      feeds={p.result?.feeds}
      multiFeed={p.multiFeed}
      connectSweep={p.refineEnabled ?? false}
    />
  ),
  schematic: (p) => (
    <SchematicPanel
      svg={p.schematicSvg}
      unavailable={p.schematicUnavailable}
      size={p.size}
      fill={p.fill}
    />
  ),
  // |Γ| vs. frequency and VSWR vs. frequency (issue #700 unit 5): one
  // component, `mode` prop, same split FarFieldChart uses for azimuth vs.
  // elevation above. z0 fallback matches the Smith chart's exact fallback —
  // both read the same result field for the same reason.
  gamma: (p) => (
    <SweepChart
      mode="gamma"
      r={p.result?.z_in_re ?? 0}
      x={p.result?.z_in_im ?? 0}
      z0={p.result?.z0_ohms ?? 50}
      size={p.size}
      sweep={p.sweep}
      measFreqMhz={p.measFreqMhz}
      running={p.sweepRunning}
      feeds={p.result?.feeds}
      multiFeed={p.multiFeed}
    />
  ),
  vswr: (p) => (
    <SweepChart
      mode="vswr"
      r={p.result?.z_in_re ?? 0}
      x={p.result?.z_in_im ?? 0}
      z0={p.result?.z0_ohms ?? 50}
      size={p.size}
      sweep={p.sweep}
      measFreqMhz={p.measFreqMhz}
      running={p.sweepRunning}
      feeds={p.result?.feeds}
      multiFeed={p.multiFeed}
    />
  ),
};
