import type { ReactElement } from "react";
import type { KnobView } from "../../lib/analysisChart";
import type { MeasuredData, ParamSweepData, SolveResponse, SweepData } from "../../lib/api";
import { DENSITY, RX_AUTO, type RxAxisChoice } from "../../lib/paramSweep";
import type { SweepProgress } from "../../lib/sweep";
import type { SweepPhase } from "../session/useAnalysisRunners";
import type { FrequencyView } from "../../lib/analyses";
import type { SweepAxes, SweepAxisChoice, SweepMode } from "../../lib/sweepAxis";
import type {
  CanvasCamera,
  CombinedFill,
  Projection,
  View,
} from "../../lib/view";
import { CombinedPatternChart } from "../charts/CombinedPatternChart";
import { CurrentCanvas } from "../charts/CurrentCanvas";
import { FarFieldChart } from "../charts/FarFieldChart";
import { type RxAxis, ZParamChart } from "../charts/ZParamChart";
import type {
  FarFieldCaptions,
  PatternData,
  PinnedPattern,
} from "../charts/types";
import { ChartFrequency, ChartKnobSmith } from "./ChartFrequency";
import { FilesPanel, type FilesViewData } from "./FilesPanel";
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
  /** The analysis chart's knob or density sweep (docs/design/z-vs-param-view.md):
   *  R/X against the knob, or its trail on the Smith chart. */
  paramSweep: ParamSweepData | null;
  measured: MeasuredData | null;
  pattern: PatternData | null;
  pinnedPatterns: PinnedPattern[];
  measFreqMhz: number;
  paramSweepRunning: boolean;
  /** The Z-vs-parameter view's settings. Optional: omitted, the view draws a
   *  density sweep on a log axis with both ranges on Auto. */
  zparam?: ZParamViewSettings;
  /** Given, the view's chart opens its range popovers and the lin/log x
   *  toggle. The stage passes these; thumbnails do not. */
  onZparamAxisChange?: (axis: RxAxis, c: RxAxisChoice) => void;
  onZparamXLogChange?: (log: boolean) => void;
  azElevDeg: number;
  elevAzDeg: number;
  cameraProjection: Projection;
  /** The antenna canvas's zoom and pan, held by the session so that leaving
   *  the view and coming back does not throw away the framing (AK#1542).
   *  Optional: a call site that omits it — every thumbnail — gets a canvas
   *  with its own camera, always at the fit view. */
  canvasCamera?: CanvasCamera | undefined;
  /** The Smith chart zooms and pans (wheel, drag, keys). The stage passes
   *  true; thumbnails omit it and draw the whole chart, unzoomed — a thumb is
   *  a button. (`fill` cannot say this: the Smith chart never fills.) */
  chartZoom?: boolean;
  showHeatmap: boolean;
  showEnvelope: boolean;
  showWireLabels: boolean;
  showFeedNames: boolean;
  multiFeed: boolean;
  fineNorm?: number | null;
  /** The stage's far-field charts hand their corner captions up to this
   *  instead of printing them, so the overlay stacks can show them where no
   *  control covers them. Thumbnail call sites omit it and keep the print. */
  onFarFieldCaptions?: (c: FarFieldCaptions) => void;
  /** Adaptive resolution (issue #744) is ON for this session — the Smith
   *  chart uses it to draw the sweep as a connected locus (the refined,
   *  frequency-sorted samples finally support one), once the sweep has
   *  settled (ChartFrequencyRender.settled). Optional: omitted, the dot
   *  trail. */
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
  //
  // `feeds`/`worst_feed` ride along on a multi-feed design (#789): the trial
  // point is then a whole port table, and `z_in_re`/`z_in_im` are just its
  // feed 0. Optional so a single-feed proposer stays a three-field object.
  liveZ: {
    z_in_re: number;
    z_in_im: number;
    z0_ohms: number;
    feeds?: Array<{ z_re: number; z_im: number }>;
    worst_feed?: number;
  } | null;
  schematicSvg: string | null;
  schematicUnavailable: boolean;
  /** The Files view's texts (AK#1428). Optional: thumbnail call sites omit
   *  it, and the panel's thumb carries no text anyway. */
  files?: FilesViewData | null;
  /** The combined Az + El view's fill and its highlighted designs (AK#1730).
   *  Optional: omitted, the plot is unfilled with nothing highlighted. */
  combinedFill?: CombinedFill;
  combinedHighlight?: readonly string[];
  /** The analysis chart showing a frequency sweep (AK#1757, step 5 units 2
   *  and 3): the zparam view draws the chart's sweep on its Swr, S11 or
   *  Smith view, instead of a knob sweep. Null or omitted: the knob sweep. */
  chartFrequency?: ChartFrequencyRender | null;
};

/** A frequency sweep as the analysis chart draws it: the chart's sweep
 *  runner's output and the chart's own scales (the standalone Smith / VSWR /
 *  S11 views' options, moved onto the chart in unit 3). */
export type ChartFrequencyRender = {
  view: FrequencyView;
  sweep: SweepData | null;
  running: boolean;
  phase: SweepPhase;
  progress: SweepProgress | null;
  settled: boolean;
  /** Drawn for inputs that have since changed (the dwell switch off), or of
   *  the pre-run design while an optimizer run proposes points. Only the
   *  swept curve dims; the live point does not (unit 3). */
  stale: boolean;
  axes: SweepAxes;
  threshold: number;
  onAxisChange?: (mode: SweepMode, c: SweepAxisChoice) => void;
  onThresholdChange?: (t: number) => void;
};

/** What the Z-vs-parameter view draws against: the parameter chosen (the
 *  sweep in hand may still be a previous one's), how to label it, where the
 *  live solve sits on it, and the chart's axis choices. */
export type ZParamViewSettings = {
  param: string;
  label: string;
  unit: string | null;
  /** Points the sweep asks for, for the "k/N" status. */
  total: number;
  currentValue: number | null;
  xLog: boolean;
  rAxis: RxAxisChoice;
  xAxis: RxAxisChoice;
  /** The reference impedance: the design's Zo or the session's override
   *  (AK#1735), the value the VSWR chart measures against. */
  z0: number;
  /** The runner's phase (idle / queued / running), published on the chart
   *  for tests that must show no sweep follows. Optional. */
  phase?: "idle" | "queued" | "running";
  /** R/X against the knob, or the sweep's trail on the Smith chart (the old
   *  Smith view's "param sweep" switch, AK#1757 step 5 unit 3). Optional:
   *  omitted, R/X. */
  view?: KnobView;
};

const DEFAULT_ZPARAM: ZParamViewSettings = {
  param: DENSITY,
  label: "N",
  unit: null,
  total: 7,
  currentValue: null,
  xLog: true,
  rAxis: RX_AUTO,
  xAxis: RX_AUTO,
  z0: 50,
};

const NO_HIGHLIGHT: readonly string[] = [];

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
          // Tied to `fill` for the same reason `interactive` is: the camera
          // belongs to the one canvas a drag can reach, and a thumbnail
          // drawing the stage's zoom would be a crop of an antenna, not a
          // picture of one.
          camera={p.fill ? p.canvasCamera : undefined}
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
      onCaptions={p.onFarFieldCaptions}
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
      onCaptions={p.onFarFieldCaptions}
    />
  ),
  combined: (p) => (
    <CombinedPatternChart
      result={p.result}
      pattern={p.pattern}
      pinned={p.pinnedPatterns}
      size={p.size}
      azElevDeg={p.azElevDeg}
      elevAzDeg={p.elevAzDeg}
      fill={p.combinedFill ?? "none"}
      highlight={p.combinedHighlight ?? NO_HIGHLIGHT}
      onCaptions={p.onFarFieldCaptions}
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
  files: (p) => <FilesPanel data={p.files ?? null} size={p.size} fill={p.fill} />,
  // The analysis chart (AK#1757 step 5): a frequency sweep on its Swr, S11
  // or Smith view (the old standalone views, unit 3), or a knob sweep as R/X
  // against the knob (docs/design/z-vs-param-view.md) or as its trail on the
  // Smith chart. The live R/X ride on the current-value guide; liveZ wins
  // while an optimizer run is proposing points, as on the Smith chart.
  zparam: (p) => {
    if (p.chartFrequency) return <ChartFrequency p={p} f={p.chartFrequency} />;
    const z = p.zparam ?? DEFAULT_ZPARAM;
    if (z.view === "Smith") return <ChartKnobSmith p={p} />;
    const r = p.liveZ?.z_in_re ?? p.result?.z_in_re ?? null;
    const x = p.liveZ?.z_in_im ?? p.result?.z_in_im ?? null;
    return (
      <ZParamChart
        data={p.paramSweep}
        param={z.param}
        label={z.label}
        unit={z.unit}
        total={z.total}
        currentValue={z.currentValue}
        liveR={r}
        liveX={x}
        size={p.size}
        running={p.paramSweepRunning}
        xLog={z.xLog}
        rAxis={z.rAxis}
        xAxis={z.xAxis}
        // The trial point's reference during an optimizer run, as the Smith
        // chart does; else the session's.
        z0={p.liveZ?.z0_ohms ?? z.z0}
        {...(z.phase ? { phase: z.phase } : {})}
        {...(p.onZparamXLogChange ? { onXLogChange: p.onZparamXLogChange } : {})}
        {...(p.onZparamAxisChange ? { onAxisChange: p.onZparamAxisChange } : {})}
      />
    );
  },
};
