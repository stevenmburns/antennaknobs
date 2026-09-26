import {
  DENSITY,
  isDensity,
  MAX_POINTS,
  MIN_POINTS,
  type ParamSweepSpec,
  pointsProblem,
} from "../../lib/paramSweep";
import { CommitNumber } from "./CommitNumber";
import type { SchemaParamSpec } from "../../lib/params";

// The Z-vs-parameter view's header (docs/design/z-vs-param-view.md): which
// parameter, over what range, how many points, lin or log spacing. Every
// edit is a new spec, and a new spec is a new sweep (after the usual dwell).
// One row, so it clears the chart below it; the ladder as solved is the
// points field's tooltip, and the sweep's advisory sits bottom-left with
// the other sweep advisories (SweepAdvisoryOverlay).
export function ZParamControls({
  spec,
  knobs,
  densityLabel,
  onSpec,
  onParam,
  onReset,
  isDefault,
  values,
  run,
  costHint = null,
}: {
  spec: ParamSweepSpec;
  /** The design's sweepable knobs (lib/paramSweep sweepableKnobs). */
  knobs: readonly SchemaParamSpec[];
  densityLabel: string;
  onSpec: (next: ParamSweepSpec) => void;
  /** Pick a parameter: its default range, points and spacing. */
  onParam: (param: string) => void;
  onReset: () => void;
  /** The spec is its parameter's default (the reset button has nothing to do). */
  isDefault: boolean;
  /** The values the spec sweeps, for the tooltip. */
  values: readonly number[];
  /** The sweep in hand: its progress, and the Stop / Run it offers. */
  run: {
    running: boolean;
    received: number;
    partial: boolean;
    done: boolean;
    onStop: () => void;
    onRun: () => void;
  };
  /** A word on cost when the request is large, or null. */
  costHint?: string | null;
}) {
  const set = (patch: Partial<ParamSweepSpec>) => onSpec({ ...spec, ...patch });
  // The arrow keys step the range by a hundredth of its span, at a round
  // magnitude (0.01 on 0.8…1.25, 1 on 8…68, 10 on 10…500).
  const span = Math.abs(spec.hi - spec.lo) || Math.abs(spec.hi) || 1;
  const rangeStep = 10 ** Math.floor(Math.log10(span / 10));
  return (
    <div className="zparam-overlay">
      <div className="zparam-controls" role="group" aria-label="Parameter sweep">
        <label>
          <span>sweep</span>
          <select
            aria-label="Parameter"
            value={spec.param}
            onChange={(e) => onParam(e.target.value)}
          >
            <option value={DENSITY}>{densityLabel}</option>
            {knobs.map((k) => (
              <option key={k.name} value={k.name}>
                {k.label}
              </option>
            ))}
          </select>
        </label>
        <label>
          <span>from</span>
          <CommitNumber label="from" value={spec.lo} step={rangeStep} onCommit={(v) => set({ lo: v })} />
        </label>
        <label>
          <span>to</span>
          <CommitNumber label="to" value={spec.hi} step={rangeStep} onCommit={(v) => set({ hi: v })} />
        </label>
        <label
          className="zparam-points"
          // The ladder itself, as solved: a rounded integer ladder can hold
          // fewer points than asked for.
          title={`${values.length} points (${MIN_POINTS}–${MAX_POINTS}): ${values.join(", ")}`}
        >
          <span>points</span>
          <CommitNumber
            label="points"
            value={spec.points}
            problem={pointsProblem}
            onCommit={(v) => set({ points: v })}
          />
          {/* A rounded integer ladder (density, an int knob) drops repeats,
              so a big count over a narrow range solves fewer: say so. */}
          {values.length !== spec.points && (
            <span className="zparam-actual">
              → {values.length} {isDensity(spec.param) ? "rungs" : "points"}
            </span>
          )}
        </label>
        <label
          className="zparam-log"
          title="Space the points by a fixed ratio (SimNEC's logStep) instead of a fixed step. An integer parameter is rounded to whole values."
        >
          <input
            type="checkbox"
            checked={spec.log}
            onChange={(e) => set({ log: e.target.checked })}
          />
          log spacing
        </label>
        {/* Stop while it runs (the count is the progress); Run when it was
            stopped, refused, or has not started — a stopped sweep does not
            restart by itself. */}
        {run.running ? (
          <button
            type="button"
            className="zparam-run is-running"
            title="Stop the sweep: keep the points so far, solve no more"
            onClick={run.onStop}
          >
            {run.received}/{values.length} · stop
          </button>
        ) : run.done ? (
          <span className="zparam-run-done" title="The sweep has finished">
            {run.received}/{values.length}
          </span>
        ) : (
          <button
            type="button"
            className="zparam-run"
            title={run.partial ? "Run the whole sweep again" : "Run the sweep"}
            onClick={run.onRun}
          >
            {run.partial ? `${run.received}/${values.length} · run` : "run"}
          </button>
        )}
        <button
          type="button"
          className="zparam-reset"
          disabled={isDefault}
          title="Back to this parameter's default range"
          onClick={onReset}
        >
          ↺
        </button>
        {costHint && (
          <div className="zparam-cost" role="note">
            {costHint}
          </div>
        )}
      </div>
    </div>
  );
}
