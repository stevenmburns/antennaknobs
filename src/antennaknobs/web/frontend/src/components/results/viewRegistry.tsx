import type { ReactElement } from "react";
import type { MeasuredData, ParamSweepData, SolveResponse, SweepData } from "../../lib/api";
import { DENSITY, RX_AUTO, type RxAxisChoice } from "../../lib/paramSweep";
import type { SweepProgress } from "../../lib/sweep";
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
import { SmithChart } from "../charts/SmithChart";
import { SweepChart } from "../charts/SweepChart";
import { type RxAxis, ZParamChart } from "../charts/ZParamChart";
import type {
  FarFieldCaptions,
  PatternData,
  PinnedPattern,
} from "../charts/types";
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
  sweep: SweepData | null;
  /** The parameter sweep (density or a knob, docs/design/z-vs-param-view.md):
   *  the Smith chart's trail and the Z-vs-parameter view's chart. */
  paramSweep: ParamSweepData | null;
  measured: MeasuredData | null;
  pattern: PatternData | null;
  pinnedPatterns: PinnedPattern[];
  measFreqMhz: number;
  sweepRunning: boolean;
  /** Points received by the sweep in flight (AK#1682). Optional so a call
   *  site that omits it keeps the bare "sweeping…" status. */
  sweepProgress?: SweepProgress | null;
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
   *  frequency-sorted samples finally support one). Optional: thumbnail
   *  call sites omit it and keep the dot trail. */
  refineEnabled?: boolean;
  /** The sweep's shape is final (issue #866): no refinement pass is running
   *  or was cut short. While false, the sweep-trace views (smith / vswr /
   *  gamma) draw unconnected dots — a polyline through a still-densifying
   *  set renders transient kinks that shift as points land. Optional so
   *  thumbnail call sites can omit it (defaults settled, today's look). */
  sweepSettled?: boolean;
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
  /** The VSWR / S11 charts' ranges and SWR threshold (AK#1738), from the
   *  view prefs. Optional: omitted, both charts are on Auto at 2:1. */
  sweepAxes?: SweepAxes;
  swrThreshold?: number;
  /** Given, the sweep charts' y axis opens the range popover. The stage
   *  passes these; thumbnails do not (a thumb is a button). */
  onSweepAxisChange?: (mode: SweepMode, c: SweepAxisChoice) => void;
  onSwrThresholdChange?: (t: number) => void;
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

// The AK#1738 props a sweep chart takes from the bag, for either mode.
function sweepAxisProps(p: ViewRenderProps, mode: SweepMode) {
  const onChange = p.onSweepAxisChange;
  return {
    ...(p.sweepAxes ? { axis: p.sweepAxes[mode] } : {}),
    ...(p.swrThreshold !== undefined ? { swrThreshold: p.swrThreshold } : {}),
    ...(onChange ? { onAxisChange: (c: SweepAxisChoice) => onChange(mode, c) } : {}),
    ...(p.onSwrThresholdChange ? { onThresholdChange: p.onSwrThresholdChange } : {}),
  };
}

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
      trialFeeds={p.liveZ?.feeds}
      trialWorstFeed={p.liveZ?.worst_feed}
      size={p.size}
      sweep={p.sweep}
      paramSweep={p.paramSweep}
      measured={p.measured}
      measFreqMhz={p.measFreqMhz}
      running={p.sweepRunning}
      progress={p.sweepProgress}
      paramSweepRunning={p.paramSweepRunning}
      feeds={p.result?.feeds}
      multiFeed={p.multiFeed}
      connectSweep={(p.refineEnabled ?? false) && (p.sweepSettled ?? true)}
      interactive={p.chartZoom ?? false}
      designKey={p.result?.geometry ?? ""}
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
      progress={p.sweepProgress}
      settled={p.sweepSettled ?? true}
      feeds={p.result?.feeds}
      multiFeed={p.multiFeed}
      {...sweepAxisProps(p, "gamma")}
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
      progress={p.sweepProgress}
      settled={p.sweepSettled ?? true}
      feeds={p.result?.feeds}
      multiFeed={p.multiFeed}
      {...sweepAxisProps(p, "vswr")}
    />
  ),
  files: (p) => <FilesPanel data={p.files ?? null} size={p.size} fill={p.fill} />,
  // The Z-vs-parameter view (docs/design/z-vs-param-view.md). The live R/X
  // ride on the current-value guide; liveZ wins while an optimizer run is
  // proposing points, as on the Smith chart.
  zparam: (p) => {
    const z = p.zparam ?? DEFAULT_ZPARAM;
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
        {...(p.onZparamXLogChange ? { onXLogChange: p.onZparamXLogChange } : {})}
        {...(p.onZparamAxisChange ? { onAxisChange: p.onZparamAxisChange } : {})}
      />
    );
  },
};
