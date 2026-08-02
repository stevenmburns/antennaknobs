import { useEffect, useRef, useState } from "react";
import type { ExampleDescriptor } from "../../lib/params";

// Searchable antenna picker: merges the old filter box + grouped <select> into
// one combobox (type to filter, ▾ to open) so it fits on one line beside the
// variant select. Keeps the family grouping the native <optgroup> list had.
export function GeometryCombobox({
  groups,
  selected,
  currentLabel,
  filter,
  setFilter,
  onSelect,
}: {
  groups: { fam: string; label: string; items: ExampleDescriptor[] }[];
  selected: string;
  currentLabel: string;
  filter: string;
  setFilter: (s: string) => void;
  onSelect: (name: string) => void;
}) {
  const [open, setOpen] = useState(false);
  const [active, setActive] = useState(0);
  const rootRef = useRef<HTMLDivElement>(null);
  const inputRef = useRef<HTMLInputElement>(null);
  const flat = groups.flatMap((g) => g.items);

  // Close (and clear the filter) on an outside click.
  useEffect(() => {
    if (!open) return;
    const onDoc = (e: MouseEvent) => {
      if (rootRef.current && !rootRef.current.contains(e.target as Node)) {
        setOpen(false);
        setFilter("");
      }
    };
    document.addEventListener("mousedown", onDoc);
    return () => document.removeEventListener("mousedown", onDoc);
  }, [open, setFilter]);

  const choose = (name: string) => {
    onSelect(name);
    setFilter("");
    setOpen(false);
    inputRef.current?.blur();
  };

  const onKey = (e: React.KeyboardEvent) => {
    if (e.key === "ArrowDown") {
      e.preventDefault();
      setOpen(true);
      setActive((i) => Math.min(flat.length - 1, i + 1));
    } else if (e.key === "ArrowUp") {
      e.preventDefault();
      setActive((i) => Math.max(0, i - 1));
    } else if (e.key === "Enter") {
      if (open && flat[active]) {
        e.preventDefault();
        choose(flat[active].name);
      }
    } else if (e.key === "Escape") {
      setOpen(false);
      setFilter("");
      inputRef.current?.blur();
    }
  };

  return (
    <div className="combobox" ref={rootRef}>
      <input
        ref={inputRef}
        className="geometry-filter combobox-input"
        type="text"
        role="combobox"
        aria-expanded={open}
        aria-label="antenna"
        placeholder="search antennas…"
        value={open ? filter : currentLabel}
        onChange={(e) => {
          setFilter(e.target.value);
          setOpen(true);
          setActive(0);
        }}
        onFocus={() => setOpen(true)}
        onKeyDown={onKey}
      />
      <span
        className="combobox-caret"
        aria-hidden="true"
        onMouseDown={(e) => {
          e.preventDefault();
          if (open) {
            setOpen(false);
          } else {
            inputRef.current?.focus();
            setOpen(true);
          }
        }}
      >
        ▾
      </span>
      {open && (
        <ul className="combobox-list" role="listbox">
          {flat.length === 0 ? (
            <li className="combobox-empty">no antennas match</li>
          ) : (
            groups.map((g) => (
              <li key={g.fam} className="combobox-group">
                <div className="combobox-group-label">{g.label}</div>
                <ul>
                  {g.items.map((ex) => {
                    const idx = flat.indexOf(ex);
                    return (
                      <li
                        key={ex.name}
                        role="option"
                        aria-selected={ex.name === selected}
                        className={`combobox-option${
                          ex.name === selected ? " is-selected" : ""
                        }${idx === active ? " is-active" : ""}`}
                        onMouseDown={(e) => {
                          e.preventDefault();
                          choose(ex.name);
                        }}
                        onMouseEnter={() => setActive(idx)}
                      >
                        {ex.label}
                      </li>
                    );
                  })}
                </ul>
              </li>
            ))
          )}
        </ul>
      )}
    </div>
  );
}
