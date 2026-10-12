// The reference impedance field (AK#1735), shared by the top gear menu, where
// it lives with this design's other settings (AK#1985), and the optimizer's
// menu for a caller with no session to open that one.
import { useState } from "react";
import { formatZo, parseZo } from "../../lib/zoOverride";

// The gear menu's reference impedance (AK#1735). `value` is the Zo this
// session measures against — the override when there is one, else the
// design's own `design` — and `set(null)` returns to the design's.
export type ZoControl = {
  value: number;
  design: number;
  set: (zo: number | null) => void;
  /** Open the top gear menu at this field (AK#1985). Absent: a caller with
   *  no session behind it, which shows the field where it is. */
  open?: () => void;
};


// The Zo field. Commits on Enter or blur; text that is not a positive, finite
// number of ohms is refused where it was typed (red, with the reason), and
// the reference stays what it was — never quietly 50. Typing the design's
// own value clears the override rather than storing a copy of it, so a
// design whose file later names another Zo is not pinned to the old one.
export function ZoField({
  zo,
  autoFocus,
}: {
  zo: ZoControl;
  autoFocus?: boolean | undefined;
}) {
  const [text, setText] = useState(() => formatZo(zo.value));
  const [error, setError] = useState<string | null>(null);
  // Re-seed when the reference moves under the field (a design's own Zo
  // landing on its first response, or a reset) — the render-time reset
  // idiom, not an effect, so there is no second render with stale text.
  const [seededFrom, setSeededFrom] = useState(zo.value);
  if (seededFrom !== zo.value) {
    setSeededFrom(zo.value);
    setText(formatZo(zo.value));
    setError(null);
  }
  const overridden = zo.value !== zo.design;
  function commit() {
    const v = parseZo(text);
    if (v === null) {
      setError("Zo must be a number of ohms greater than 0");
      return;
    }
    setError(null);
    zo.set(v === zo.design ? null : v);
    setText(formatZo(v));
  }
  return (
    <div className="opt-zo" role="group" aria-label="Reference impedance">
      <label className="opt-zo-row">
        <span className="opt-zo-label">Z₀</span>
        <input
          className={`opt-zo-input${error ? " is-invalid" : ""}`}
          type="text"
          inputMode="decimal"
          aria-label="Reference impedance Zo, ohms"
          autoFocus={autoFocus}
          aria-invalid={error ? true : undefined}
          aria-describedby={error ? "opt-zo-error" : undefined}
          value={text}
          onChange={(e) => {
            setText(e.target.value);
            if (error) setError(null);
          }}
          onBlur={commit}
          onKeyDown={(e) => {
            if (e.key === "Enter") commit();
            else if (e.key === "Escape") {
              setText(formatZo(zo.value));
              setError(null);
            }
          }}
        />
        <span className="opt-zo-unit">Ω</span>
        {overridden && (
          <button
            type="button"
            className="opt-zo-reset"
            title={`Back to the design's own ${formatZo(zo.design)} Ω`}
            onClick={() => zo.set(null)}
          >
            reset
          </button>
        )}
      </label>
      {error ? (
        <div id="opt-zo-error" className="opt-zo-error" role="alert">
          {error}
        </div>
      ) : (
        <div className="gear-menu-hint opt-zo-hint">
          {overridden
            ? `design: ${formatZo(zo.design)} Ω`
            : "the design's own"}
          {" — SWR and Match Z₀ are measured against it"}
        </div>
      )}
    </div>
  );
}
