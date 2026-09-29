import type { ReactElement } from "react";
import type { SweepAxisChoice, SweepMode } from "../../lib/sweepAxis";
import { SmithChart } from "../charts/SmithChart";
import { SweepChart } from "../charts/SweepChart";
import type { ChartFrequencyRender, ViewRenderProps } from "./viewRegistry";

// The analysis chart's frequency analysis, on its view: the same chart
// components the standalone views use, fed the chart's own sweep. The live
// point is the session's (liveZ while an optimizer run proposes points, else
// the last solve), so it follows a drag whether or not the curve waits.
export function ChartFrequency({ p, f }: { p: ViewRenderProps; f: ChartFrequencyRender }) {
  const r = p.liveZ?.z_in_re ?? p.result?.z_in_re ?? 0;
  const x = p.liveZ?.z_in_im ?? p.result?.z_in_im ?? 0;
  const z0 = p.liveZ?.z0_ohms ?? p.result?.z0_ohms ?? 50;
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
        {...(onAxis ? { onAxisChange: (c: SweepAxisChoice) => onAxis(mode, c) } : {})}
        {...(f.onThresholdChange ? { onThresholdChange: f.onThresholdChange } : {})}
      />
    );
  }
  return (
    <div
      className={f.stale ? "analysis-chart-freq is-stale" : "analysis-chart-freq"}
      data-stale={f.stale ? "1" : "0"}
    >
      {chart}
    </div>
  );
}
