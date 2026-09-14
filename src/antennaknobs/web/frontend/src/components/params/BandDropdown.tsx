import { useEffect, useRef, useState } from "react";
import type { BandSpec } from "../../lib/params";
import { customBandError, defaultCustomSpan } from "../../lib/bands";

// Band picker — a click-only dropdown, deliberately NOT a native <select>.
// A focused <select> captures the arrow keys, which would fight the sticky
// meas-freq dial (the "physical dial survives focus loss" affordance): the dial
// shows armed but arrows would drive the pulldown. This is a plain <button> +
// popover, so it never captures arrows — they always flow to the armed knob.
//
// With `onCustom`, the list ends in "Custom…" (#1487): a small form for a
// centre frequency and a span, for a design that lives between the served
// bands. Its inputs do take the arrow keys, but only while the user is typing
// into them; the form closes on Apply, Cancel, Escape or a click outside.
export function BandDropdown({
  bands,
  value,
  onSelect,
  disabled,
  ariaLabel,
  onCustom,
  customSeedMhz,
}: {
  bands: BandSpec[];
  value: string;
  onSelect: (key: string) => void;
  disabled?: boolean;
  ariaLabel: string;
  onCustom?: ((centerMhz: number, spanMhz: number) => void) | undefined;
  /** Prefills the custom centre: the frequency the control sits on now. */
  customSeedMhz?: number | undefined;
}) {
  const [open, setOpen] = useState(false);
  const [mode, setMode] = useState<"list" | "custom">("list");
  const [centre, setCentre] = useState("");
  const [span, setSpan] = useState("");
  const [spanTouched, setSpanTouched] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const rootRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (!open) return;
    const onDoc = (e: MouseEvent) => {
      // The event's path, not contains(e.target): a mousedown on "Custom…"
      // swaps the list for the form before this document listener runs, so
      // the target is already detached and contains() would read it as a
      // click outside and close the form it just opened (#1487).
      if (rootRef.current && !e.composedPath().includes(rootRef.current)) {
        setOpen(false);
      }
    };
    document.addEventListener("mousedown", onDoc);
    return () => document.removeEventListener("mousedown", onDoc);
  }, [open]);

  const current = bands.find((b) => b.key === value) ?? bands[0];

  function openCustom() {
    const seed =
      customSeedMhz != null && Number.isFinite(customSeedMhz) && customSeedMhz > 0
        ? Number(customSeedMhz.toFixed(3))
        : null;
    setCentre(seed != null ? String(seed) : "");
    setSpan(seed != null ? String(defaultCustomSpan(seed)) : "");
    setSpanTouched(false);
    setError(null);
    setMode("custom");
  }

  function close() {
    setOpen(false);
    setMode("list");
  }

  function apply() {
    const c = Number(centre);
    const s = span.trim() === "" ? defaultCustomSpan(c) : Number(span);
    const why = centre.trim() === "" ? "centre must be a positive frequency" : customBandError(c, s);
    if (why) {
      setError(why);
      return;
    }
    onCustom?.(c, s);
    close();
  }

  return (
    <div className="band-dropdown" ref={rootRef}>
      <button
        type="button"
        className="band-select band-dropdown-trigger"
        aria-haspopup="listbox"
        aria-expanded={open}
        aria-label={ariaLabel}
        disabled={disabled}
        onClick={() => {
          setMode("list");
          setOpen((o) => !o);
        }}
      >
        <span className="band-dropdown-value">{current?.label ?? ""}</span>
        <span className="band-dropdown-caret" aria-hidden="true">
          ▾
        </span>
      </button>
      {open && !disabled && mode === "list" && (
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
                close();
              }}
            >
              {b.label}
            </li>
          ))}
          {onCustom && (
            <li
              role="option"
              aria-selected={false}
              className="band-dropdown-option is-custom"
              onMouseDown={(e) => {
                e.preventDefault();
                openCustom();
              }}
            >
              Custom…
            </li>
          )}
        </ul>
      )}
      {open && !disabled && mode === "custom" && (
        <form
          className="band-dropdown-custom"
          aria-label={`${ariaLabel} custom`}
          onSubmit={(e) => {
            e.preventDefault();
            apply();
          }}
          onKeyDown={(e) => {
            if (e.key === "Escape") {
              e.preventDefault();
              close();
            }
          }}
        >
          <label>
            <span>centre</span>
            <input
              type="number"
              aria-label="centre (MHz)"
              min="0"
              step="any"
              autoFocus
              value={centre}
              onChange={(e) => {
                const v = e.target.value;
                setCentre(v);
                setError(null);
                if (!spanTouched) {
                  const c = Number(v);
                  setSpan(Number.isFinite(c) && c > 0 ? String(defaultCustomSpan(c)) : "");
                }
              }}
            />
            <span className="band-dropdown-unit">MHz</span>
          </label>
          <label>
            <span>span</span>
            <input
              type="number"
              aria-label="span (MHz)"
              min="0"
              step="any"
              value={span}
              onChange={(e) => {
                setSpan(e.target.value);
                setSpanTouched(true);
                setError(null);
              }}
            />
            <span className="band-dropdown-unit">MHz</span>
          </label>
          {error && (
            <div className="band-dropdown-error" role="alert">
              {error}
            </div>
          )}
          <div className="band-dropdown-actions">
            <button type="button" onClick={close}>
              Cancel
            </button>
            <button type="submit">Apply</button>
          </div>
        </form>
      )}
    </div>
  );
}
