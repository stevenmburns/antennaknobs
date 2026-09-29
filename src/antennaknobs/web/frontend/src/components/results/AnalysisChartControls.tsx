import type { FrequencyView } from "../../lib/analyses";
import { chartDataAttrs } from "../../lib/analysisChart";
import type { SweepRange } from "../../lib/sweep";
import { AnalysisDetails, type AnalysisPickerProps, AnalysisSelect } from "./AnalysisPicker";
import { CommitNumber } from "./CommitNumber";

// The analysis chart's own controls (AK#1757, sweep-framework step 5 unit 2).
// They sit ON the chart, on the right-hand (output) side: what the chart
// computes and how it draws it, never a design input. The knob sweep's header
// is ZParamControls, which carries the same picker, Run and dwell switch; the
// frequency analysis's is FrequencyChartControls below. Both mark their root
// with the chart's kind, dwell switch and pick (`chartDataAttrs`), which is
// what a test reads rather than the pixels.

/** What every analysis chart header carries beside its own inputs. */
export type ChartChrome = {
  /** The dwell switch: re-run after the knobs settle. */
  dwell: boolean;
  onDwell: (on: boolean) => void;
};

/** The per-chart dwell switch: today's freq-sweep checkbox, moved onto the
 *  chart and applied to whatever it shows. */
export function DwellSwitch({ dwell, onDwell }: ChartChrome) {
  return (
    <label
      className="zparam-log chart-dwell"
      title="Re-run this chart's analysis once the knobs have stopped moving (500 ms). Off, a change marks the curve stale and Run re-runs it. The live point follows every change either way."
    >
      <input type="checkbox" checked={dwell} onChange={(e) => onDwell(e.target.checked)} />
      auto re-run
    </label>
  );
}

const VIEW_LABEL: Record<FrequencyView, string> = { Swr: "SWR", S11: "S11 (dB)", Smith: "Smith" };

/** The header of a chart showing a frequency analysis: the picker, the view
 *  (when the analysis names more than one), the range, Run / Stop, the dwell
 *  switch, and back to the analysis's own range. */
export function FrequencyChartControls({
  analyses,
  views,
  view,
  onView,
  range,
  onRange,
  onResetRange,
  rangeIsOwn,
  run,
  chrome,
}: {
  analyses: AnalysisPickerProps;
  views: readonly FrequencyView[];
  view: FrequencyView;
  onView: (v: FrequencyView) => void;
  range: SweepRange;
  onRange: (lo: number, hi: number) => void;
  onResetRange: () => void;
  /** The range is the analysis's own (the reset has nothing to do). */
  rangeIsOwn: boolean;
  run: {
    running: boolean;
    received: number;
    stale: boolean;
    onStop: () => void;
    onRun: () => void;
  };
  chrome: ChartChrome;
}) {
  const span = range.hi - range.lo || range.hi || 1;
  const step = 10 ** Math.floor(Math.log10(span / 10));
  const positive = (v: number) => (v > 0 ? null : "> 0");
  return (
    <div
      className="zparam-overlay"
      role="group"
      aria-label="Analysis chart"
      {...chartDataAttrs("frequency", chrome.dwell, analyses.current)}
    >
      <div className="zparam-controls" role="group" aria-label="Frequency sweep">
        <AnalysisSelect {...analyses} />
        {views.length > 1 && (
          <label>
            <span>view</span>
            <select
              aria-label="Chart view"
              value={view}
              onChange={(e) => onView(e.target.value as FrequencyView)}
            >
              {views.map((v) => (
                <option key={v} value={v}>
                  {VIEW_LABEL[v]}
                </option>
              ))}
            </select>
          </label>
        )}
        <label>
          <span>from</span>
          <CommitNumber
            label="from MHz"
            value={range.lo}
            step={step}
            problem={positive}
            onCommit={(v) => onRange(v, range.hi)}
          />
        </label>
        <label>
          <span>to</span>
          <CommitNumber
            label="to MHz"
            value={range.hi}
            step={step}
            problem={positive}
            onCommit={(v) => onRange(range.lo, v)}
          />
          <span>MHz</span>
        </label>
        {run.running ? (
          <button
            type="button"
            className="zparam-run is-running"
            title="Stop the sweep: keep the points so far"
            onClick={run.onStop}
          >
            {run.received} · stop
          </button>
        ) : (
          <button
            type="button"
            className={run.stale ? "zparam-run is-stale" : "zparam-run"}
            title={
              run.stale
                ? "The design changed since this sweep ran: run it again"
                : "Run this chart's analysis again"
            }
            onClick={run.onRun}
          >
            {run.stale ? "run · re-run?" : "run"}
          </button>
        )}
        <DwellSwitch {...chrome} />
        <button
          type="button"
          className="zparam-reset"
          disabled={rangeIsOwn}
          title="Back to the analysis's own range"
          onClick={onResetRange}
        >
          ↺
        </button>
      </div>
      <AnalysisDetails
        entries={analyses.entries}
        current={analyses.current}
        blocked={analyses.blocked}
      />
    </div>
  );
}
