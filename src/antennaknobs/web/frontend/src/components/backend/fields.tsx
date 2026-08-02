import { useEffect, useState } from "react";

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
  const [draft, setDraft] = useState(String(value));
  useEffect(() => {
    setDraft(String(value));
  }, [value]);
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
  value,
  min,
  max,
  step,
  onChange,
}: {
  label: string;
  value: number;
  min?: number;
  max?: number;
  step?: number;
  onChange: (v: number) => void;
}) {
  // Local text draft so the field can be emptied mid-edit. Binding the input
  // straight to the number coerced "" → 0 on backspace (you couldn't clear it,
  // and the forced 0 left a leading zero when you typed again). The draft holds
  // raw text; a value is only committed when it parses, and re-syncs whenever
  // `value` changes from outside (backend swap, auto-seed, reset).
  const [draft, setDraft] = useState(String(value));
  useEffect(() => {
    setDraft(String(value));
  }, [value]);
  return (
    <div className="field">
      <label>
        <span>{label}</span>
        <span>{value}</span>
      </label>
      <input
        type="number"
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
