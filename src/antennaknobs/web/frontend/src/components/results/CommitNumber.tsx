import { useState } from "react";

// A number box that edits as free text and commits on blur, Enter, or an
// arrow-key step — never per keystroke (Steve, 2026-09-26: typing 101 into
// the Z-vs-parameter "points" box jumped to 20, then 40, because each
// keystroke was committed and clamped, and the clamped value rewrote the
// text mid-entry). While focused the box shows exactly what was typed. A
// value `problem` refuses on commit reverts to the last committed value and
// shows the problem as a short hint beside the box until the next edit.
export function CommitNumber({
  value,
  onCommit,
  problem = () => null,
  step = 1,
  label,
}: {
  value: number;
  onCommit: (v: number) => void;
  /** Why `v` cannot be committed ("2–201"), or null to accept it. */
  problem?: (v: number) => string | null;
  /** The arrow keys' step. */
  step?: number;
  label: string;
}) {
  // `draft` is the text while editing; null means "show the committed value".
  const [draft, setDraft] = useState<string | null>(null);
  const [hint, setHint] = useState<string | null>(null);
  const commit = (text: string) => {
    const v = Number(text);
    const why = text.trim() === "" || !Number.isFinite(v) ? "a number" : problem(v);
    setDraft(null);
    if (why) {
      setHint(why);
      return;
    }
    setHint(null);
    if (v !== value) onCommit(v);
  };
  const stepBy = (dir: 1 | -1) => {
    const base = Number(draft ?? value);
    const v = Number(((Number.isFinite(base) ? base : value) + dir * step).toPrecision(12));
    commit(String(v));
  };
  return (
    <span className="commit-number">
      <input
        type="text"
        inputMode="decimal"
        aria-label={label}
        aria-invalid={hint ? true : undefined}
        data-invalid={hint ? true : undefined}
        value={draft ?? String(value)}
        onChange={(e) => {
          setDraft(e.target.value);
          setHint(null);
        }}
        onBlur={() => {
          if (draft !== null) commit(draft);
        }}
        onKeyDown={(e) => {
          if (e.key === "Enter") {
            e.preventDefault();
            if (draft !== null) commit(draft);
          } else if (e.key === "Escape") {
            setDraft(null);
            setHint(null);
          } else if (e.key === "ArrowUp" || e.key === "ArrowDown") {
            e.preventDefault();
            stepBy(e.key === "ArrowUp" ? 1 : -1);
          }
        }}
      />
      {hint && (
        <span className="commit-number-hint" role="status">
          {hint}
        </span>
      )}
    </span>
  );
}
