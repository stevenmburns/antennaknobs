import { useEffect, useRef, useState } from "react";
import type { BandSpec } from "../../lib/params";

// Band picker — a click-only dropdown, deliberately NOT a native <select>.
// A focused <select> captures the arrow keys, which would fight the sticky
// meas-freq dial (the "physical dial survives focus loss" affordance): the dial
// shows armed but arrows would drive the pulldown. This is a plain <button> +
// popover, so it never captures arrows — they always flow to the armed knob.
export function BandDropdown({
  bands,
  value,
  onSelect,
  disabled,
  ariaLabel,
}: {
  bands: BandSpec[];
  value: string;
  onSelect: (key: string) => void;
  disabled?: boolean;
  ariaLabel: string;
}) {
  const [open, setOpen] = useState(false);
  const rootRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (!open) return;
    const onDoc = (e: MouseEvent) => {
      if (rootRef.current && !rootRef.current.contains(e.target as Node)) {
        setOpen(false);
      }
    };
    document.addEventListener("mousedown", onDoc);
    return () => document.removeEventListener("mousedown", onDoc);
  }, [open]);

  const current = bands.find((b) => b.key === value) ?? bands[0];

  return (
    <div className="band-dropdown" ref={rootRef}>
      <button
        type="button"
        className="band-select band-dropdown-trigger"
        aria-haspopup="listbox"
        aria-expanded={open}
        aria-label={ariaLabel}
        disabled={disabled}
        onClick={() => setOpen((o) => !o)}
      >
        <span className="band-dropdown-value">{current?.label ?? ""}</span>
        <span className="band-dropdown-caret" aria-hidden="true">
          ▾
        </span>
      </button>
      {open && !disabled && (
        <ul className="band-dropdown-list" role="listbox" aria-label={ariaLabel}>
          {bands.map((b) => (
            <li
              key={b.key}
              role="option"
              aria-selected={b.key === value}
              className={`band-dropdown-option${
                b.key === value ? " is-selected" : ""
              }`}
              onMouseDown={(e) => {
                e.preventDefault();
                onSelect(b.key);
                setOpen(false);
              }}
            >
              {b.label}
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}
