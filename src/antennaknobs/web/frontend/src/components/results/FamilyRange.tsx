import { FAMILY_CAP, familyStep, stepEdit } from "../../lib/analysisChart";
import { MIN_POINTS, type ParamSweepSpec } from "../../lib/paramSweep";
import { CommitNumber } from "./CommitNumber";

// A knob's family of patterns (AK#1935): which knob, and its values. Steve
// (2026-10-06): "you specify which knob you want with the starting and
// ending values and step size (linear) or number of steps (linear/log)".
// The knob sweep's own spec (lo, hi, points, log) is the family's, edited
// in place, so R / X and the patterns are one knob and range apart by a
// view. The step box is that spec's step, not a field of its own: a step
// sets the points and moves `to` onto the last value it reaches
// (lib/analysisChart stepEdit). At most FAMILY_CAP values (the chart's
// curve cap): the points box refuses more, and so does the step box.

export type FamilyRangeProps = {
  spec: ParamSweepSpec;
  /** What the family can step: the design's sweepable knobs, and the
   *  measurement frequency where the design has one. */
  knobs: readonly { name: string; label: string }[];
  /** The values the spec steps, as solved (an int knob rounded). */
  values: readonly number[];
  onSpec: (next: ParamSweepSpec) => void;
  onParam: (param: string) => void;
  onReset: () => void;
  /** The spec is the knob's own default (↺ has nothing to do). */
  isDefault: boolean;
};

const pointsProblem = (n: number): string | null =>
  Number.isInteger(n) && n >= MIN_POINTS && n <= FAMILY_CAP ? null : `${MIN_POINTS}–${FAMILY_CAP}`;

export function FamilyRange({ spec, knobs, values, onSpec, onParam, onReset, isDefault }: FamilyRangeProps) {
  // An edit is the range's own ladder again: an analysis's explicit values
  // do not survive it.
  const set = (patch: Partial<Omit<ParamSweepSpec, "values">>) => {
    const next: ParamSweepSpec = { ...spec, ...patch };
    delete next.values;
    onSpec(next);
  };
  const span = Math.abs(spec.hi - spec.lo) || Math.abs(spec.hi) || 1;
  const rangeStep = 10 ** Math.floor(Math.log10(span / 10));
  const step = familyStep(spec);
  return (
    <span className="zparam-group chart-family" role="group" aria-label="Pattern family">
      <label>
        <span>over</span>
        <select aria-label="Parameter" value={spec.param} onChange={(e) => onParam(e.target.value)}>
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
      {step !== null && (
        <label
          className="chart-family-step"
          title="The step between values: from, from + step, … up to `to`. A step that does not divide the range moves `to` down onto the last value it reaches."
        >
          <span>step</span>
          <CommitNumber
            label="step"
            value={step}
            step={rangeStep}
            problem={(v) => stepEdit(spec, v).problem}
            onCommit={(v) => {
              const r = stepEdit(spec, v);
              if (r.spec) onSpec(r.spec);
            }}
          />
        </label>
      )}
      <label
        className="zparam-points"
        title={`${values.length} values (${MIN_POINTS}–${FAMILY_CAP}, the chart's curve cap): ${values.join(", ")}`}
      >
        <span>values</span>
        <CommitNumber label="values" value={spec.points} problem={pointsProblem} onCommit={(v) => set({ points: v })} />
        {values.length !== spec.points && <span className="zparam-actual">→ {values.length}</span>}
      </label>
      <label
        className="zparam-log"
        title="Space the values by a fixed ratio instead of a fixed step. An integer knob is rounded to whole values."
      >
        <input type="checkbox" checked={spec.log} onChange={(e) => set({ log: e.target.checked })} />
        log spacing
      </label>
      <button
        type="button"
        className="zparam-reset"
        disabled={isDefault}
        title="Back to this knob's own range"
        onClick={onReset}
      >
        ↺
      </button>
    </span>
  );
}
