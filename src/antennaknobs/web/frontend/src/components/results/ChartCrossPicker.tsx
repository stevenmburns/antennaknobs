import { useEffect, useState } from "react";
import { createPortal } from "react-dom";
import { useInViewport } from "../charts/useInViewport";

// An analysis chart's engine and ground checkboxes (AK#1757, sweep-framework
// step 5 unit 4): which solver slots and ground slots the chart compares,
// one curve per ticked pair. On the chart, on the output side, because they
// say what the chart compares and not what the design is.
//
// One compact button in the header ("A · 1", the ticked ids) opens the
// boxes in a popover, so the header still fits a phone. The popover is
// portaled to <body> and clamped to the visible viewport, as the axis-range
// popovers are (unit 3), so no carousel page or stale dim can clip it.
//
// The slots are whatever the session holds (ids open-ended, A…E and X, Y, Z, U…):
// the boxes are drawn from the lists handed in, never a fixed three. The
// last ticked box on an axis cannot be unticked: a chart draws at least one
// engine on at least one ground.

export type CrossPickerProps = {
  slots: { id: string; label: string }[];
  grounds: { id: string; label: string }[];
  checkedSlots: string[];
  checkedGrounds: string[];
  onSlots: (ids: string[]) => void;
  onGrounds: (ids: string[]) => void;
  /** The over-cap refusal (lib/chartCells.ts capRefusal), shown in the
   *  popover under the boxes that caused it; null when within the cap. */
  refusal: string | null;
};

function toggle(ids: string[], order: string[], id: string, on: boolean): string[] {
  const next = on ? [...ids, id] : ids.filter((x) => x !== id);
  return order.filter((x) => next.includes(x));
}

function Boxes({
  legend,
  items,
  checked,
  onChange,
}: {
  legend: string;
  items: { id: string; label: string }[];
  checked: string[];
  onChange: (ids: string[]) => void;
}) {
  const order = items.map((i) => i.id);
  return (
    <fieldset className="chart-cross-axis">
      <legend>{legend}</legend>
      {items.map((it) => {
        const on = checked.includes(it.id);
        const last = on && checked.length === 1;
        return (
          <label
            key={it.id}
            className="chart-cross-item"
            title={last ? "A chart draws at least one" : undefined}
          >
            <input
              type="checkbox"
              checked={on}
              disabled={last}
              onChange={(e) => onChange(toggle(checked, order, it.id, e.target.checked))}
            />
            {it.label}
          </label>
        );
      })}
    </fieldset>
  );
}

function CrossPopover({
  at,
  onClose,
  ...p
}: CrossPickerProps & { at: { x: number; y: number }; onClose: () => void }) {
  const box = useInViewport<HTMLDivElement>(at, "left");
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if (e.key === "Escape") onClose();
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [onClose]);
  return createPortal(
    <>
      <div className="knob-menu-backdrop" onClick={onClose} />
      <div
        className="knob-menu chart-cross-menu"
        role="dialog"
        aria-label="Engines and grounds"
        ref={box}
        style={{ left: at.x, top: at.y }}
      >
        <div className="knob-menu-title">Compare: one curve per engine × ground</div>
        <Boxes legend="Engines" items={p.slots} checked={p.checkedSlots} onChange={p.onSlots} />
        <Boxes legend="Grounds" items={p.grounds} checked={p.checkedGrounds} onChange={p.onGrounds} />
        {p.refusal && (
          <div className="chart-cross-refusal" role="alert">
            {p.refusal}
          </div>
        )}
      </div>
    </>,
    document.body,
  );
}

export function ChartCrossPicker(p: CrossPickerProps) {
  const [at, setAt] = useState<{ x: number; y: number } | null>(null);
  // What the viewer ticked, not the chart's curve count: an analysis's own
  // crosses (planes, designs, a family) multiply these, so "N curves" here
  // read wrong beside a legend drawing more (AK#1757 unit 4b review).
  const ne = p.checkedSlots.length;
  const ng = p.checkedGrounds.length;
  return (
    <>
      <button
        type="button"
        className={`zparam-run chart-cross-btn${p.refusal ? " is-refused" : ""}`}
        aria-haspopup="dialog"
        aria-expanded={at !== null}
        aria-label="Engines and grounds"
        title={`Compare engines and grounds: ${ne} engine${ne === 1 ? "" : "s"} × ${ng} ground${ng === 1 ? "" : "s"}${p.refusal ? ` (${p.refusal})` : ""}`}
        data-slots={p.checkedSlots.join(",")}
        data-grounds={p.checkedGrounds.join(",")}
        onClick={(e) => {
          const r = e.currentTarget.getBoundingClientRect();
          setAt({ x: r.right, y: r.bottom + 4 });
        }}
      >
        {p.checkedSlots.join("")} · {p.checkedGrounds.join("")}
      </button>
      {at && <CrossPopover {...p} at={at} onClose={() => setAt(null)} />}
    </>
  );
}
