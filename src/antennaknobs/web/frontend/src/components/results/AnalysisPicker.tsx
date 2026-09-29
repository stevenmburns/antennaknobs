import { useState } from "react";
import type { AnalysisEntry } from "../../lib/analyses";

// The Z-vs-parameter header's "analysis" picker (AK#1757, sweep-framework
// step 3): the design's analyses (POST /analyses), one pick running the one
// the view can draw. What it cannot draw yet is listed, disabled, with why.

export type AnalysisPickerProps = {
  entries: readonly AnalysisEntry[];
  /** The picked analysis while the view's spec is still its own, else null. */
  current: string | null;
  /** Why an entry cannot run in this view, or null when it can. */
  blocked: (entry: AnalysisEntry) => string | null;
  onPick: (entry: AnalysisEntry) => void;
  /** What the select reads with nothing it names on screen. */
  placeholder?: string;
  /** The chart's own frequency sweep (the design's band, a new chart's):
   *  offered first, and `own` says the chart is showing it. */
  onPickOwn?: () => void;
  own?: boolean;
  /** "Sweep a knob": switch the chart to a knob sweep of the knob in its
   *  parameter list, and run it. `sweepingKnob` says the chart shows one
   *  that no analysis names. Omitted, no entry (a design with no knob). */
  onSweepKnob?: () => void;
  sweepingKnob?: boolean;
};

// Option values for what is not an analysis: an analysis is named by its
// own name, so these carry a prefix no analysis name starts with (a name is
// Python's, and never begins with a control character).
const OWN = "\u0001freq";
const KNOB = "\u0001knob";

/** The select, one label in the header's row (Steve's phone, 2026-09-29:
 *  "there is no sweep item to choose, a lot of greyed-out analyses"). Three
 *  parts, the obvious first:
 *   - what runs here: the chart's own frequency sweep, then the analyses the
 *     chart can run (the design's and the library's), in the served order;
 *   - "Sweep a knob", ONE entry (a design can have twenty knobs, and the
 *     chart's parameter list already chooses among them): it runs the knob
 *     in that list (the last knob swept, else the design's first) over its
 *     own range, as the knob menu's "Sweep this knob…" does; changing the
 *     list then re-runs for the new knob;
 *   - "Not in the workbench yet": the analyses it cannot run, disabled, each
 *     with its reason.
 *  A native <select> with an <optgroup> for the last part: a phone draws it
 *  as its own picker, group and disabled rows included, with nothing to lay
 *  out on a 390 px screen. */
export function AnalysisSelect({
  entries,
  current,
  blocked,
  onPick,
  placeholder = "pick…",
  onPickOwn,
  own = false,
  onSweepKnob,
  sweepingKnob = false,
}: AnalysisPickerProps) {
  const runnable = entries.filter((a) => blocked(a) === null);
  const later = entries.filter((a) => blocked(a) !== null);
  const value =
    current ?? (own && onPickOwn ? OWN : sweepingKnob && onSweepKnob ? KNOB : "");
  return (
    <label className="zparam-analysis">
      <span>analysis</span>
      <select
        aria-label="Analysis"
        value={value}
        onChange={(e) => {
          const v = e.target.value;
          if (v === OWN) {
            onPickOwn?.();
            return;
          }
          if (v === KNOB) {
            onSweepKnob?.();
            return;
          }
          const entry = entries.find((a) => a.name === v);
          if (entry && !blocked(entry)) onPick(entry);
        }}
      >
        {value === "" && <option value="">{placeholder}</option>}
        {onPickOwn && (
          <option value={OWN} title="A frequency sweep over the measurement dial's range">
            freq sweep (the design's band)
          </option>
        )}
        {runnable.map((a) => (
          <option key={a.name} value={a.name} title={a.summary}>
            {a.name}
          </option>
        ))}
        {onSweepKnob && (
          <option value={KNOB} title="R and X against the knob in the chart's parameter list, over its own range">
            Sweep a knob
          </option>
        )}
        {later.length > 0 && (
          <optgroup label="Not in the workbench yet">
            {later.map((a) => {
              const why = blocked(a) as string;
              return (
                <option key={a.name} value={a.name} disabled title={why}>
                  {`${a.name} (not here yet)`}
                </option>
              );
            })}
          </optgroup>
        )}
      </select>
    </label>
  );
}

/** The notes a chart carries (the picked analysis's `note`, a word on cost):
 *  what applies, with the notes of an analysis that is not the one running
 *  left out. */
export function chartNotes(
  entries: readonly AnalysisEntry[],
  current: string | null,
  extra: readonly (string | null | undefined)[] = [],
): string[] {
  const w = entries.find((a) => a.name === current)?.workbench;
  const own = w?.runs && w.note ? [w.note] : [];
  return [...own, ...extra.filter((n): n is string => !!n)];
}

/** Under the header's controls: ONE line, whatever the notes say (Steve's
 *  phone, 2026-09-29: the convergence pick's two-clause note wrapped to four
 *  lines and took them from the plot). The notes are an "ⓘ note" button on
 *  that line; tapped, they open in a panel laid OVER the chart, out of the
 *  flow, so the header, and so the plot under it, is the same height with a
 *  note or without one, open or shut. Beside it, every analysis as Python
 *  (read-only, with Copy), the reasons beside the ones the chart cannot run.
 *  The line is there on every chart header, note or none. */
export function AnalysisDetails({
  entries,
  notes,
  blocked,
}: {
  entries: readonly AnalysisEntry[];
  notes: readonly string[];
  blocked: (entry: AnalysisEntry) => string | null;
}) {
  const [open, setOpen] = useState(false);
  const shown = open && notes.length > 0;
  const summary = notes.join(" · ");
  return (
    <div className="zparam-analysis-extra">
      {notes.length > 0 && (
        <button
          type="button"
          className="chart-note-btn"
          aria-expanded={shown}
          aria-label={shown ? "Hide the chart's note" : "Show the chart's note"}
          title={summary}
          onClick={() => setOpen((o) => !o)}
        >
          <span aria-hidden="true">ⓘ</span> <span className="chart-note-peek">{summary}</span>
        </button>
      )}
      {shown && (
        <div className="chart-note-pop" role="note" aria-label="Chart note">
          {notes.map((n) => (
            <p key={n}>{n}</p>
          ))}
        </div>
      )}
      {entries.length > 0 && (
        <details className="zparam-analysis-code">
          <summary>analyses as Python</summary>
          {entries.map((a) => (
            <AnalysisCode key={a.name} entry={a} why={blocked(a)} />
          ))}
        </details>
      )}
    </div>
  );
}

function AnalysisCode({ entry, why }: { entry: AnalysisEntry; why: string | null }) {
  const [copied, setCopied] = useState(false);
  const copy = () => {
    void navigator.clipboard?.writeText(entry.code).then(
      () => setCopied(true),
      () => setCopied(false),
    );
  };
  return (
    <div className="zparam-analysis-item">
      <div className="zparam-analysis-head">
        <strong>{entry.name}</strong>
        <span className="zparam-analysis-summary">{entry.summary}</span>
        <button
          type="button"
          className="zparam-analysis-copy"
          aria-label={`Copy ${entry.name} as Python`}
          onClick={copy}
        >
          {copied ? "copied" : "copy"}
        </button>
      </div>
      {why && <div className="zparam-analysis-why">{why}</div>}
      <pre aria-label={`${entry.name} as Python`}>{entry.code}</pre>
    </div>
  );
}
