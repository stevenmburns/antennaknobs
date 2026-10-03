import type { ReactElement } from "react";
import type { SweepData } from "../../lib/api";
import { chartTable, type TableCurve, type TableKind } from "../../lib/chartTable";
import { metricColumns, relativeAt } from "../../lib/metricPlot";
import { isDensity, type ParamSweepData, RX_AUTO } from "../../lib/paramSweep";
import type { SweepAxisChoice, SweepMode } from "../../lib/sweepAxis";
import { ChartTable } from "../charts/ChartTable";
import type { ExtraCurve } from "../charts/curves";
import { SmithChart } from "../charts/SmithChart";
import { SweepChart } from "../charts/SweepChart";
import { ZParamChart } from "../charts/ZParamChart";
import type { ChartFrequencyRender, ViewRenderProps } from "./viewRegistry";

/** The x a frequency sweep is drawn against on the R/X plot (the knob
 *  sweep's chart, AK#1757 step 5 unit 5): the name ZParamChart matches its
 *  data on. */
export const FREQUENCY_PARAM = "frequency";

/** A frequency sweep as the R/X plot's data: frequency on x, Z at port 0. */
export function frequencyAsParam(s: SweepData | null | undefined, stale = false): ParamSweepData | null {
  if (!s) return null;
  return {
    param: FREQUENCY_PARAM,
    label: "f",
    values: s.freqs_mhz,
    z_re: s.z_re,
    z_im: s.z_im,
    z_re_extrap: null,
    z_im_extrap: null,
    ...(stale ? { stale: true } : {}),
  };
}

// A curve's label for the table: the drawn cells' labels, in runner order.
function labelAt(p: ViewRenderProps, k: number): string {
  return p.chartCellLabels?.[k] ?? "";
}

/** The Table view of a frequency sweep: MHz, and R, X and SWR per curve. */
function frequencyTable(p: ViewRenderProps, f: ChartFrequencyRender): ReactElement {
  const z0 = p.zparam?.z0 ?? p.result?.z0_ohms ?? 50;
  const curves: TableCurve[] = [];
  const add = (s: SweepData | null | undefined, k: number) => {
    if (s && s.freqs_mhz.length > 0) {
      curves.push({ label: labelAt(p, k), xs: s.freqs_mhz, re: s.z_re, im: s.z_im });
    }
  };
  add(f.sweep, 0);
  (p.chartCurves ?? []).forEach((c, k) => add(c.sweep, k + 1));
  const n = f.sweep?.freqs_mhz.length ?? 0;
  const status = f.running
    ? `sweeping ${n}/${f.progress?.phase === "base" ? f.progress.planned : n}…`
    : curves.length === 0
      ? "no sweep yet"
      : null;
  return <ChartTable table={chartTable("frequency", FREQUENCY_PARAM, curves, z0)} size={p.size} status={status} design={p.chartDesign ?? ""} />;
}

/** The Table view of a knob or density sweep: the knob (nominal_N), and R
 *  and X (N_ach and |ΔΓ| for a density ladder) per curve, and a MetricPlot's
 *  metric (AK#1867). */
export function knobTable(p: ViewRenderProps, param: string): ReactElement {
  const z0 = p.zparam?.z0 ?? p.result?.z0_ohms ?? 50;
  const curves: TableCurve[] = [];
  // A MetricPlot's columns (AK#1867): each curve's metric off its own
  // sweep, and its difference off the plot's series, which already paired
  // it with its reference (lib/metricPlot.ts). The series are the drawn
  // cells in order: the chart's own curve is the first, every other is
  // found by its key.
  const cm = p.chartMetric ?? null;
  const add = (d: ParamSweepData | null | undefined, k: number, key: string | null) => {
    if (d && d.param === param && (d.values.length > 0 || (d.gaps?.length ?? 0) > 0)) {
      const s = cm ? (key === null ? cm.series[0] : cm.series.find((x) => x.key === key)) : undefined;
      curves.push({
        label: labelAt(p, k),
        xs: d.values,
        re: d.z_re,
        im: d.z_im,
        ...(d.n_seg ? { nAch: d.n_seg } : {}),
        // A held sweep's knobs and gaps (AK#1757 step 6).
        ...(d.held ? { held: d.held } : {}),
        ...(d.gaps && d.gaps.length > 0 ? { gaps: d.gaps } : {}),
        ...(cm ? { metric: d.values.map((_, i) => d.metric?.[i] ?? null) } : {}),
        ...(cm && cm.metric.relativeTo !== null ? { relative: relativeAt(s, d.values) } : {}),
      });
    }
  };
  add(p.paramSweep, 0, null);
  (p.chartCurves ?? []).forEach((c, k) => add(c.paramSweep, k + 1, c.key));
  const kind: TableKind = isDensity(param) ? "density" : "knob";
  const status = p.paramSweepRunning
    ? `sweeping ${p.paramSweep?.param === param ? p.paramSweep.values.length : 0}/${p.zparam?.total ?? "?"}…`
    : curves.length === 0
      ? "no sweep yet"
      : null;
  const table = chartTable(kind, param, curves, z0, cm ? metricColumns(cm.metric) : null);
  return <ChartTable table={table} size={p.size} status={status} design={p.chartDesign ?? ""} />;
}

/** R and X against frequency: the knob sweep's R/X chart with frequency
 *  on x, the dashed guide at the measurement frequency with the live R and
 *  X on it, and the other curves in their legend colours. */
function frequencyRx(p: ViewRenderProps, f: ChartFrequencyRender): ReactElement {
  const r = p.liveZ?.z_in_re ?? p.result?.z_in_re ?? null;
  const x = p.liveZ?.z_in_im ?? p.result?.z_in_im ?? null;
  const rx = f.rx ?? { r: RX_AUTO, x: RX_AUTO, xLog: false };
  const curves: ExtraCurve[] | undefined = p.chartCurves?.map((c) => ({
    ...c,
    paramSweep: frequencyAsParam(c.sweep, c.stale),
  }));
  const n = f.sweep?.freqs_mhz.length ?? 0;
  const z = p.zparam;
  const onRxAxis = f.onRxAxisChange;
  const onRxLog = f.onRxXLogChange;
  return (
    <ZParamChart
      data={frequencyAsParam(f.sweep, f.stale)}
      param={FREQUENCY_PARAM}
      label="f"
      unit="MHz"
      total={f.progress?.phase === "base" ? f.progress.planned : n}
      currentValue={p.measFreqMhz}
      liveR={r}
      liveX={x}
      size={p.size}
      running={f.running}
      xLog={rx.xLog}
      rAxis={rx.r}
      xAxis={rx.x}
      z0={p.liveZ?.z0_ohms ?? z?.z0 ?? p.result?.z0_ohms ?? 50}
      phase={f.phase === "refining" ? "running" : f.phase}
      callouts={onRxAxis ? (z?.callouts ?? true) : false}
      {...(z?.onCalloutsChange && onRxAxis ? { onCalloutsChange: z.onCalloutsChange } : {})}
      {...(onRxLog ? { onXLogChange: onRxLog } : {})}
      {...(onRxAxis ? { onAxisChange: onRxAxis } : {})}
      {...(curves ? { curves } : {})}
      {...(p.chartPins ? { pins: p.chartPins } : {})}
    />
  );
}

// The live point every view of the analysis chart draws: liveZ while an
// optimizer run proposes points, else the last solve. It follows a drag
// whether or not the swept curve waits (AK#1757 step 5).
function livePoint(p: ViewRenderProps) {
  return {
    r: p.liveZ?.z_in_re ?? p.result?.z_in_re ?? 0,
    x: p.liveZ?.z_in_im ?? p.result?.z_in_im ?? 0,
    z0: p.liveZ?.z0_ohms ?? p.result?.z0_ohms ?? 50,
  };
}

// The analysis chart's frequency sweep, on its view: the chart components
// the standalone Smith / VSWR / S11 views were, fed the chart's sweep and
// scales (unit 3 folded those views in). A stale curve dims on its own; the
// live point and the axes stay bright (the charts' `stale` prop).
export function ChartFrequency({ p, f }: { p: ViewRenderProps; f: ChartFrequencyRender }) {
  const { r, x, z0 } = livePoint(p);
  let chart: ReactElement;
  if (f.view === "Rx") {
    chart = frequencyRx(p, f);
  } else if (f.view === "Table") {
    chart = frequencyTable(p, f);
  } else if (f.view === "Smith") {
    chart = (
      <SmithChart
        r={r}
        x={x}
        z0={z0}
        trial={p.liveZ != null}
        trialFeeds={p.liveZ?.feeds}
        trialWorstFeed={p.liveZ?.worst_feed}
        size={p.size}
        sweep={f.sweep}
        paramSweep={null}
        measured={p.measured}
        measFreqMhz={p.measFreqMhz}
        running={f.running}
        progress={f.progress}
        phase={f.phase}
        paramSweepRunning={false}
        feeds={p.result?.feeds}
        multiFeed={p.multiFeed}
        connectSweep={(p.refineEnabled ?? false) && f.settled}
        interactive={p.chartZoom ?? false}
        designKey={p.result?.geometry ?? ""}
        stale={f.stale}
        {...(p.chartCurves ? { curves: p.chartCurves } : {})}
        {...(p.chartPins ? { pins: p.chartPins } : {})}
      />
    );
  } else {
    const mode: SweepMode = f.view === "Swr" ? "vswr" : "gamma";
    const onAxis = f.onAxisChange;
    chart = (
      <SweepChart
        mode={mode}
        r={r}
        x={x}
        z0={z0}
        size={p.size}
        sweep={f.sweep}
        measFreqMhz={p.measFreqMhz}
        running={f.running}
        progress={f.progress}
        settled={f.settled}
        phase={f.phase}
        feeds={p.result?.feeds}
        multiFeed={p.multiFeed}
        axis={f.axes[mode]}
        swrThreshold={f.threshold}
        stale={f.stale}
        {...(p.chartCurves ? { curves: p.chartCurves } : {})}
        {...(p.chartPins ? { pins: p.chartPins } : {})}
        {...(onAxis ? { onAxisChange: (c: SweepAxisChoice) => onAxis(mode, c) } : {})}
        {...(f.onThresholdChange ? { onThresholdChange: f.onThresholdChange } : {})}
      />
    );
  }
  return (
    <div className="analysis-chart-freq" data-stale={f.stale ? "1" : "0"}>
      {chart}
    </div>
  );
}

// A knob or density sweep on the Smith chart: its trail, labelled with its
// end values (and Z∞ for a density sweep), which the Smith view drew when its
// "param sweep" switch was on. No frequency locus here: the chart shows one
// analysis, and this one sweeps a knob. The measured overlay stays, as it
// did on the Smith view whatever it swept.
export function ChartKnobSmith({ p }: { p: ViewRenderProps }) {
  const { r, x, z0 } = livePoint(p);
  const stale = !!p.paramSweep?.stale;
  return (
    <div className="analysis-chart-freq" data-stale={stale ? "1" : "0"}>
      <SmithChart
        r={r}
        x={x}
        z0={z0}
        trial={p.liveZ != null}
        trialFeeds={p.liveZ?.feeds}
        trialWorstFeed={p.liveZ?.worst_feed}
        size={p.size}
        sweep={null}
        paramSweep={p.paramSweep}
        measured={p.measured}
        measFreqMhz={p.measFreqMhz}
        running={false}
        paramSweepRunning={p.paramSweepRunning}
        feeds={p.result?.feeds}
        multiFeed={p.multiFeed}
        interactive={p.chartZoom ?? false}
        designKey={p.result?.geometry ?? ""}
        stale={stale}
        {...(p.chartCurves ? { curves: p.chartCurves } : {})}
        {...(p.chartPins ? { pins: p.chartPins } : {})}
      />
    </div>
  );
}
