import { chartDataAttrs } from "../../lib/analysisChart";
import type { MapQuantity } from "../../lib/mapGrid";
import { MAX_POINTS, MIN_POINTS, type ParamSweepSpec, pointsProblem } from "../../lib/paramSweep";
import {
  AnalysisDetails,
  type AnalysisPickerProps,
  AnalysisSelect,
  chartNotes,
} from "./AnalysisPicker";
import { type ChartChrome, ChartChromeControls, DwellSwitch } from "./AnalysisChartControls";
import { CommitNumber } from "./CommitNumber";

// The header of a chart showing a two-knob map (docs/design/
// sweep-framework-map.md, unit 3): the picker, the two axes (each the knob
// chart's own range editor: from, to, points, log spacing), ↺ back to the
// analysis's own axes, what the map is coloured by, ONE solver slot and ONE
// ground slot as radios (decision 15: each ticked slot would be another
// whole grid), the cost line beside Run, Run / Stop and the dwell switch
// (off by default, decision 7), and the chart's chrome.

/** "825 solves · ~6 s": the grid's solve count, and the time at the live
 *  solve's own pace (null: no solve timed yet). */
export function mapCostLine(points: number, solveMs: number | null): string {
  const n = `${points} solve${points === 1 ? "" : "s"}`;
  if (solveMs === null || !Number.isFinite(solveMs) || solveMs <= 0) return n;
  const s = (points * solveMs) / 1000;
  const t = s < 1 ? "<1 s" : s < 90 ? `~${Math.round(s)} s` : `~${Math.round(s / 60)} min`;
  return `${n} · ${t}`;
}

/** Why Run is refused on the hosted instance, or null: over its map cap. */
export function mapOverLimit(points: number, limit: { points: number } | null): string | null {
  if (!limit || points <= limit.points) return null;
  return `${points} points is over the live limit of ${limit.points}: reduce the points on x or y`;
}

type Radio = { id: string; label: string };

function RadioGroup({
  label,
  items,
  checked,
  onPick,
}: {
  label: string;
  items: readonly Radio[];
  checked: string | null;
  onPick: (id: string) => void;
}) {
  if (items.length < 2) return null;
  return (
    <span className="zparam-group map-radios" role="radiogroup" aria-label={label}>
      <span>{label}</span>
      {items.map((it) => (
        <label key={it.id}>
          <input
            type="radio"
            name={`${label}-${items.map((i) => i.id).join("")}`}
            checked={checked === it.id}
            onChange={() => onPick(it.id)}
          />
          {it.label}
        </label>
      ))}
    </span>
  );
}

function AxisEditor({
  axis,
  label,
  spec,
  values,
  onSpec,
}: {
  axis: "x" | "y";
  label: string;
  spec: ParamSweepSpec;
  values: readonly number[];
  onSpec: (next: ParamSweepSpec) => void;
}) {
  // An edit drops an analysis's explicit ladder, as the knob header's does.
  const set = (patch: Partial<Omit<ParamSweepSpec, "values">>) => {
    const next: ParamSweepSpec = { ...spec, ...patch };
    delete next.values;
    onSpec(next);
  };
  const span = Math.abs(spec.hi - spec.lo) || Math.abs(spec.hi) || 1;
  const rangeStep = 10 ** Math.floor(Math.log10(span / 10));
  return (
    <span className="zparam-group map-axis" role="group" aria-label={`${axis} axis`}>
      <span className="map-axis-name">
        {axis}: {label}
      </span>
      <label>
        <span>from</span>
        <CommitNumber label={`${axis} from`} value={spec.lo} step={rangeStep} onCommit={(v) => set({ lo: v })} />
      </label>
      <label>
        <span>to</span>
        <CommitNumber label={`${axis} to`} value={spec.hi} step={rangeStep} onCommit={(v) => set({ hi: v })} />
      </label>
      <label
        className="zparam-points"
        title={`${values.length} points (${MIN_POINTS}–${MAX_POINTS}): ${values.join(", ")}`}
      >
        <span>points</span>
        <CommitNumber
          label={`${axis} points`}
          value={spec.points}
          problem={pointsProblem}
          onCommit={(v) => set({ points: v })}
        />
      </label>
      <label className="zparam-log" title="Space the points by a fixed ratio instead of a fixed step">
        <input
          type="checkbox"
          aria-label={`${axis} log spacing`}
          checked={spec.log}
          onChange={(e) => set({ log: e.target.checked })}
        />
        log
      </label>
    </span>
  );
}

export function MapChartControls({
  analyses,
  x,
  y,
  onAxis,
  onRestore,
  edited,
  quantity,
  onQuantity,
  slots,
  grounds,
  cost,
  run,
  chrome,
}: {
  analyses: AnalysisPickerProps;
  x: { label: string; spec: ParamSweepSpec; values: readonly number[] };
  y: { label: string; spec: ParamSweepSpec; values: readonly number[] };
  /** An axis edit: asks for that map (it arms). */
  onAxis: (axis: "x" | "y", next: ParamSweepSpec) => void;
  /** ↺: the analysis's own axes again. */
  onRestore: () => void;
  edited: boolean;
  quantity: MapQuantity;
  onQuantity: (q: MapQuantity) => void;
  /** The solver slots and ground slots, one of each picked. */
  slots: { items: readonly Radio[]; checked: string | null; onPick: (id: string) => void };
  grounds: { items: readonly Radio[]; checked: string | null; onPick: (id: string) => void };
  /** The cost line, and why Run is refused (the hosted cap), or null. */
  cost: { line: string; refused: string | null };
  run: {
    running: boolean;
    received: number;
    total: number;
    done: boolean;
    partial: boolean;
    stale: boolean;
    onStop: () => void;
    onRun: () => void;
  };
  chrome: ChartChrome;
}) {
  const { cross: _cross, ...chromeRest } = chrome;
  void _cross;
  const runLabel = run.stale
    ? "run · re-run?"
    : run.done || run.partial
      ? `${run.received}/${run.total} · run`
      : "run";
  return (
    <div
      className="zparam-overlay"
      role="group"
      aria-label="Analysis chart"
      {...chartDataAttrs("map", chrome.dwell, analyses.current)}
    >
      <div className="zparam-controls" role="group" aria-label="Map">
        <AnalysisSelect {...analyses} />
        <AxisEditor axis="x" label={x.label} spec={x.spec} values={x.values} onSpec={(s) => onAxis("x", s)} />
        <AxisEditor axis="y" label={y.label} spec={y.spec} values={y.values} onSpec={(s) => onAxis("y", s)} />
        <button
          type="button"
          className="zparam-reset"
          disabled={!edited}
          title="Back to the analysis's own axes"
          onClick={onRestore}
        >
          ↺
        </button>
        <label className="zparam-group">
          <span>colour</span>
          <select
            aria-label="Map quantity"
            value={quantity}
            onChange={(e) => onQuantity(e.target.value as MapQuantity)}
          >
            <option value="rho">|Γ|</option>
            <option value="reciprocal">1 − 1/SWR</option>
          </select>
        </label>
        <RadioGroup label="solver" {...slots} />
        <RadioGroup label="ground" {...grounds} />
        <span className="zparam-group">
          <span
            className="map-cost"
            aria-label="Map cost"
            {...(cost.refused ? { title: cost.refused } : {})}
          >
            {cost.refused ?? cost.line}
          </span>
          {run.running ? (
            <button
              type="button"
              className="zparam-run is-running"
              title="Stop the map: keep the nodes solved so far, solve no more"
              onClick={run.onStop}
            >
              {run.received}/{run.total} · stop
            </button>
          ) : (
            <button
              type="button"
              className={run.stale ? "zparam-run is-stale" : "zparam-run"}
              disabled={cost.refused !== null}
              title={
                cost.refused ??
                (run.stale
                  ? "The design changed since this map ran; a map re-runs only when asked"
                  : "Run the map")
              }
              onClick={run.onRun}
            >
              {runLabel}
            </button>
          )}
          <DwellSwitch dwell={chrome.dwell} onDwell={chrome.onDwell} />
        </span>
        <ChartChromeControls {...chromeRest} />
      </div>
      <AnalysisDetails
        entries={analyses.entries}
        notes={chartNotes(analyses.entries, analyses.current)}
        blocked={analyses.blocked}
      />
    </div>
  );
}
