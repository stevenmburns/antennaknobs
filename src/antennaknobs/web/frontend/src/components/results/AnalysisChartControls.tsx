import { chartDataAttrs, type ChartView, patternViewLabel } from "../../lib/analysisChart";
import type { PatternViewSpec } from "../../lib/analyses";
import type { MeasuredData } from "../../lib/api";
import type { SweepRange } from "../../lib/sweep";
import {
  AnalysisDetails,
  type AnalysisPickerProps,
  AnalysisSelect,
  chartNotes,
} from "./AnalysisPicker";
import { ChartCrossPicker, type CrossPickerProps } from "./ChartCrossPicker";
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
  /** The engine and ground checkboxes (unit 4): what the chart compares.
   *  Omitted, the chart draws the session's active slot and ground. */
  cross?: CrossPickerProps;
  /** Another chart like this one, in the grid (unit 4); omitted when four
   *  charts are open already. */
  onDuplicate?: () => void;
  /** Close this chart: a duplicate's only (the first chart unpins). */
  onClose?: () => void;
  /** Pin the chart's curves as they stand (AK#1757 item 1): one pin per
   *  drawn curve. `blocked` is why it cannot now (a run in flight, a
   *  refused curve, nothing drawn yet), or null. Omitted: no Pin button. */
  pin?: { onPin: () => void; blocked: string | null };
  /** "Copy as analysis" and "keep as study" (AK#1757 step 7 unit 4): each
   *  opens its dialog; `*Blocked` is why it cannot (no analysis picked, a
   *  chart of other designs for a copy), or null. Omitted: no buttons. */
  keep?: {
    onCopy: () => void;
    copyBlocked: string | null;
    onKeep: () => void;
    keepBlocked: string | null;
  };
};

/** The chart's own chrome: the dwell switch, what it compares, and
 *  duplicate / close. */
export function ChartChromeControls(chrome: ChartChrome) {
  return (
    <>
      <DwellSwitch dwell={chrome.dwell} onDwell={chrome.onDwell} />
      {chrome.cross && <ChartCrossPicker {...chrome.cross} />}
      {chrome.pin && (
        <button
          type="button"
          className="zparam-reset chart-pin"
          aria-label="Pin this chart's curves"
          disabled={chrome.pin.blocked !== null}
          title={
            chrome.pin.blocked ??
            "Freeze this chart's curves as pins: dashed, never re-solved, to compare what you change next against"
          }
          // Not also a click on the grid cell under it (as duplicate).
          onClick={(e) => {
            e.stopPropagation();
            chrome.pin?.onPin();
          }}
        >
          pin
        </button>
      )}
      {chrome.keep && (
        <>
          <button
            type="button"
            className="zparam-reset chart-copy-analysis"
            aria-label="Copy this chart as an analysis"
            disabled={chrome.keep.copyBlocked !== null}
            title={
              chrome.keep.copyBlocked ??
              "Copy as analysis: this chart as Python, to paste into the design's build_analyses()"
            }
            onClick={(e) => {
              e.stopPropagation();
              chrome.keep?.onCopy();
            }}
          >
            copy
          </button>
          <button
            type="button"
            className="zparam-reset chart-keep-study"
            aria-label="Keep this chart as a study"
            disabled={chrome.keep.keepBlocked !== null}
            title={
              chrome.keep.keepBlocked ??
              "Keep as study: this chart as a study function, copied or saved to your studies folder"
            }
            onClick={(e) => {
              e.stopPropagation();
              chrome.keep?.onKeep();
            }}
          >
            keep
          </button>
        </>
      )}
      {chrome.onDuplicate && (
        <button
          type="button"
          className="zparam-reset chart-duplicate"
          aria-label="Duplicate this chart"
          title="Another chart like this one, with its own analysis, switch, range and views (up to four charts)"
          // Not also a click on the grid cell under it, which would focus
          // this chart instead of the new one.
          onClick={(e) => {
            e.stopPropagation();
            chrome.onDuplicate?.();
          }}
        >
          ⧉
        </button>
      )}
      {chrome.onClose && (
        <button
          type="button"
          className="zparam-reset chart-close"
          aria-label="Close this chart"
          title="Close this chart"
          // Not also a click on the grid cell under it, which would focus
          // the chart just closed.
          onClick={(e) => {
            e.stopPropagation();
            chrome.onClose?.();
          }}
        >
          ×
        </button>
      )}
    </>
  );
}

/** The per-chart dwell switch: today's freq-sweep checkbox, moved onto the
 *  chart and applied to whatever it shows. */
export function DwellSwitch({ dwell, onDwell }: Pick<ChartChrome, "dwell" | "onDwell">) {
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

const VIEW_LABEL: Record<string, string> = {
  Rx: "R / X",
  Swr: "SWR",
  S11: "S11 (dB)",
  Smith: "Smith",
  Table: "Table",
  // A knob analysis's MetricPlot (AK#1828).
  Metric: "Metric",
  Knobs: "Knobs",
};

/** The chart's view, and on the Smith chart its measured overlay: what the
 *  standalone Smith / VSWR / S11 views were, as a choice on the chart
 *  (AK#1757 step 5 unit 3). */
export type ChartViewPickProps = {
  /** The views the chart's kind can draw: R / X, Smith or Table for a knob sweep,
   *  SWR, S11, Smith, R / X or Table for a frequency sweep. */
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
  /** A pattern's views (AK#1757 step 7), which name their own: the view
   *  id `pattern:<k>` is the k-th of these. */
  patternViews?: readonly PatternViewSpec[];
};

export function ChartViewPick({ views, view, onView, measured, patternViews }: ChartViewPickProps) {
  const label = (v: ChartView): string => {
    if (v.startsWith("pattern:")) {
      const spec = patternViews?.[Number(v.slice("pattern:".length))];
      return spec ? patternViewLabel(spec) : v;
    }
    return VIEW_LABEL[v] ?? v;
  };
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
                {label(v)}
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

/** The header of a chart showing a pattern (AK#1757 step 7): the picker,
 *  the view (a cut or the table), Run / Stop and the chart's chrome. A
 *  pattern has no range: each cell is one solve at its own frequency. */
export function PatternChartControls({
  analyses,
  viewPick,
  run,
  chrome,
}: {
  analyses: AnalysisPickerProps;
  viewPick: ChartViewPickProps;
  run: {
    running: boolean;
    /** Cells solved so far, and how many there are. */
    solved: number;
    total: number;
    stale: boolean;
    onStop: () => void;
    onRun: () => void;
  };
  chrome: ChartChrome;
}) {
  return (
    <div
      className="zparam-overlay"
      role="group"
      aria-label="Analysis chart"
      {...chartDataAttrs("pattern", chrome.dwell, analyses.current)}
    >
      <div className="zparam-controls" role="group" aria-label="Pattern">
        <AnalysisSelect {...analyses} />
        <ChartViewPick {...viewPick} />
        {run.running ? (
          <button
            type="button"
            className="zparam-run is-running"
            title="Stop: keep the patterns solved so far"
            onClick={run.onStop}
          >
            {run.solved}/{run.total} · stop
          </button>
        ) : (
          <button
            type="button"
            className={run.stale ? "zparam-run is-stale" : "zparam-run"}
            title={
              run.stale
                ? "The design changed since these patterns were solved: solve them again"
                : "Solve this chart's patterns again"
            }
            onClick={run.onRun}
          >
            {run.stale ? "run · re-run?" : "run"}
          </button>
        )}
        <ChartChromeControls {...chrome} />
      </div>
      <AnalysisDetails
        entries={analyses.entries}
        notes={chartNotes(analyses.entries, analyses.current)}
        blocked={analyses.blocked}
      />
    </div>
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
        {range.exact && range.freqs && (
          // An analysis's explicit frequency list (step 5 unit 5): the
          // sweep is these values, not a range; an edit of from / to makes
          // it one, and ↺ brings the list back.
          <span
            className="chart-freq-list"
            data-values={range.freqs.join(",")}
            title={`Swept at exactly ${range.freqs.join(", ")} MHz. An edit of from / to makes it a range; ↺ brings the list back.`}
          >
            {range.freqs.length} value{range.freqs.length === 1 ? "" : "s"}
          </span>
        )}
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
        <ChartChromeControls {...chrome} />
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
