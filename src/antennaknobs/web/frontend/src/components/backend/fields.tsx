import { useState } from "react";

// A text draft of a numeric prop, re-synced whenever the prop changes from
// outside (backend swap, auto-seed, reset) but left alone while you type.
//
// Adjusted DURING RENDER rather than in an effect (issue #768). The effect
// spelling — `useEffect(() => setDraft(String(value)), [value])` — is the
// anti-pattern React's "You Might Not Need an Effect" is about: it paints the
// stale draft first and corrects it on a second pass. Comparing against the
// last-synced value here means React re-renders before committing to the DOM,
// so the stale text is never shown. Behaviour is otherwise identical: the
// guard is false while typing (committing a parsed value leaves `value`
// unchanged), which is what keeps a half-typed "1.50" from snapping to "1.5".
function useNumericDraft(value: number) {
  const [draft, setDraft] = useState(String(value));
  const [synced, setSynced] = useState(value);
  if (value !== synced) {
    setSynced(value);
    setDraft(String(value));
  }
  return [draft, setDraft] as const;
}

// Bare numeric input with the same clear-without-snapping-to-0 draft treatment
// as NumberField (which carries its own label/value chrome and doesn't fit the
// knob menu's grid rows).
export function KnobMenuNumber({
  value,
  onChange,
}: {
  value: number;
  onChange: (v: number) => void;
}) {
  const [draft, setDraft] = useNumericDraft(value);
  return (
    <input
      type="number"
      step="any"
      value={draft}
      onChange={(e) => {
        const text = e.target.value;
        setDraft(text); // allow "", partial, or leading-zero input while typing
        if (text.trim() === "") return; // empty: don't commit (no snap to 0)
        const v = Number(text);
        if (!Number.isNaN(v)) onChange(v);
      }}
      // Normalize on blur: drop any leading zeros / revert an empty field to
      // the last committed value.
      onBlur={() => setDraft(String(value))}
    />
  );
}

export function NumberField({
  label,
  title,
  value,
  min,
  max,
  step,
  onChange,
}: {
  label: string;
  // Hover text for a bound that is not self-explanatory — e.g. a cap that
  // comes from the solver rather than from physics.
  title?: string;
  value: number;
  min?: number;
  max?: number;
  step?: number;
  onChange: (v: number) => void;
}) {
  // Local text draft so the field can be emptied mid-edit. Binding the input
  // straight to the number coerced "" → 0 on backspace (you couldn't clear it,
  // and the forced 0 left a leading zero when you typed again). The draft holds
  // raw text; a value is only committed when it parses.
  const [draft, setDraft] = useNumericDraft(value);
  return (
    <div className="field">
      <label title={title}>
        <span>{label}</span>
        <span>{value}</span>
      </label>
      <input
        type="number"
        title={title}
        value={draft}
        min={min}
        max={max}
        step={step}
        onChange={(e) => {
          const text = e.target.value;
          setDraft(text); // allow "", partial, or leading-zero input while typing
          if (text.trim() === "") return; // empty: don't commit (no snap to 0)
          const v = Number(text);
          if (!Number.isNaN(v)) onChange(v);
        }}
        // Normalize on blur: drop any leading zeros / revert an empty field to
        // the last committed value.
        onBlur={() => setDraft(String(value))}
      />
    </div>
  );
}

// A number that spans decades: σ runs 1e-4 to 5 S/m, four and a half of
// them, and a linear slider would put every soil but sea water in the first
// 0.1% of its travel (issue #1173).
//
// The slider is log-scaled; the text box stays LINEAR and authoritative, so
// an exact value ("0.0303") is typeable and round-trips. Committing from the
// slider quantises to 3 significant figures — a 200-step slider otherwise
// emits 0.005012435... and that noise would reach the cache key and the
// exported GN card.
export function LogNumberField({
  label,
  title,
  value,
  min,
  max,
  onChange,
}: {
  label: string;
  title?: string;
  value: number;
  min: number;
  max: number;
  onChange: (v: number) => void;
}) {
  const [draft, setDraft] = useNumericDraft(value);
  // Guard the transform rather than trusting the caller: log of a
  // non-positive bound is NaN, which would silently render a dead slider.
  const safeMin = min > 0 ? min : 1e-6;
  const safeMax = max > safeMin ? max : safeMin * 10;
  const STEPS = 200;
  const toSlider = (v: number) => {
    const clamped = Math.min(Math.max(v, safeMin), safeMax);
    const t =
      (Math.log(clamped) - Math.log(safeMin)) /
      (Math.log(safeMax) - Math.log(safeMin));
    return Math.round(t * STEPS);
  };
  const fromSlider = (i: number) => {
    const t = i / STEPS;
    const raw = Math.exp(
      Math.log(safeMin) + t * (Math.log(safeMax) - Math.log(safeMin)),
    );
    return Number(raw.toPrecision(3));
  };
  return (
    <div className="field">
      <label title={title}>
        <span>{label}</span>
        <span>{value}</span>
      </label>
      <input
        type="range"
        aria-label={`${label} (log slider)`}
        title={title}
        min={0}
        max={STEPS}
        step={1}
        value={toSlider(value)}
        onChange={(e) => onChange(fromSlider(Number(e.target.value)))}
      />
      <input
        type="number"
        aria-label={label}
        title={title}
        value={draft}
        min={min}
        max={max}
        step="any"
        onChange={(e) => {
          const text = e.target.value;
          setDraft(text);
          if (text.trim() === "") return;
          const v = Number(text);
          if (!Number.isNaN(v)) onChange(v);
        }}
        onBlur={() => setDraft(String(value))}
      />
    </div>
  );
}
