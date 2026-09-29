import type { ReactElement } from "react";
import type { SweepAxisChoice, SweepMode } from "../../lib/sweepAxis";
import { SmithChart } from "../charts/SmithChart";
import { SweepChart } from "../charts/SweepChart";
import type { ChartFrequencyRender, ViewRenderProps } from "./viewRegistry";

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
  if (f.view === "Smith") {
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
      />
    </div>
  );
}
