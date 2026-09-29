import { chartDataAttrs, type ChartView } from "../../lib/analysisChart";
import type { MeasuredData } from "../../lib/api";
import type { SweepRange } from "../../lib/sweep";
import {
  AnalysisDetails,
  type AnalysisPickerProps,
  AnalysisSelect,
  chartNotes,
} from "./AnalysisPicker";
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

const VIEW_LABEL: Record<ChartView, string> = {
  Rx: "R / X",
  Swr: "SWR",
  S11: "S11 (dB)",
  Smith: "Smith",
};

/** The chart's view, and on the Smith chart its measured overlay: what the
 *  standalone Smith / VSWR / S11 views were, as a choice on the chart
 *  (AK#1757 step 5 unit 3). */
export type ChartViewPickProps = {
  /** The views the chart's kind can draw: R / X or Smith for a knob sweep,
   *  SWR, S11 or Smith for a frequency sweep. */
  views: readonly ChartView[];
  view: ChartView;
  onView: (v: ChartView) => void;
  /** The measured .s1p overlay (issue #595), on the Smith view only (null
   *  elsewhere): the file control the Smith view's overlay carried. */
  measured: {
    data: MeasuredData | null;
    onLoad: (f: File) => void;
    onClear: () => void;
  } | null;
};

export function ChartViewPick({ views, view, onView, measured }: ChartViewPickProps) {
  return (
    <>
      {views.length > 1 && (
        <label>
          <span>view</span>
          <select
            aria-label="Chart view"
            value={view}
            onChange={(e) => onView(e.target.value as ChartView)}
          >
            {views.map((v) => (
              <option key={v} value={v}>
                {VIEW_LABEL[v]}
              </option>
            ))}
          </select>
        </label>
      )}
      {measured && (
        <label
          className="overlay-file chart-measured"
          title="Overlay a measured VNA sweep (one-port Touchstone .s1p, e.g. from a NanoVNA) against the modeled locus"
        >
          <input
            type="file"
            accept=".s1p,.S1P"
            onChange={(e) => {
              const f = e.target.files?.[0];
              // Reset the input so re-picking the same file (after a
              // re-measure) fires onChange again.
              e.target.value = "";
              if (f) measured.onLoad(f);
            }}
          />
          {measured.data ? `measured: ${measured.data.label}` : "measured .s1p…"}
        </label>
      )}
      {measured?.data && (
        <button
          type="button"
          className="overlay-clear"
          title="Remove the measured overlay"
          onClick={measured.onClear}
        >
          clear
        </button>
      )}
    </>
  );
}

/** The header of a chart showing a frequency sweep: the picker, the view,
 *  the range, Run / Stop, the dwell switch, and back to the analysis's own
 *  range. */
export function FrequencyChartControls({
  analyses,
  viewPick,
  range,
  onRange,
  onResetRange,
  rangeIsOwn,
  run,
  chrome,
}: {
  analyses: AnalysisPickerProps;
  viewPick: ChartViewPickProps;
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
        <ChartViewPick {...viewPick} />
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
        notes={chartNotes(analyses.entries, analyses.current)}
        blocked={analyses.blocked}
      />
    </div>
  );
}
