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
  /** What the select reads with nothing picked: "pick…", or what the chart
   *  already shows (the design's own frequency sweep, a new chart's). */
  placeholder?: string;
};

/** The select, one label in the header's row. */
export function AnalysisSelect({
  entries,
  current,
  blocked,
  onPick,
  placeholder = "pick…",
}: AnalysisPickerProps) {
  return (
    <label className="zparam-analysis">
      <span>analysis</span>
      <select
        aria-label="Analysis"
        value={current ?? ""}
        onChange={(e) => {
          const entry = entries.find((a) => a.name === e.target.value);
          if (entry && !blocked(entry)) onPick(entry);
        }}
      >
        <option value="">{placeholder}</option>
        {entries.map((a) => {
          const why = blocked(a);
          return (
            <option key={a.name} value={a.name} disabled={why !== null} title={why ?? a.summary}>
              {why ? `${a.name} (not here yet)` : a.name}
            </option>
          );
        })}
      </select>
    </label>
  );
}

/** Under the row: the picked analysis's note, and every analysis as Python
 *  (read-only, with Copy), the reasons beside the ones the view cannot run. */
export function AnalysisDetails({
  entries,
  current,
  blocked,
}: Omit<AnalysisPickerProps, "onPick">) {
  const note = entries.find((a) => a.name === current)?.workbench;
  return (
    <div className="zparam-analysis-extra">
      {note?.runs && note.note && (
        <div className="zparam-analysis-note" role="note">
          {note.note}
        </div>
      )}
      <details className="zparam-analysis-code">
        <summary>analyses as Python</summary>
        {entries.map((a) => (
          <AnalysisCode key={a.name} entry={a} why={blocked(a)} />
        ))}
      </details>
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
