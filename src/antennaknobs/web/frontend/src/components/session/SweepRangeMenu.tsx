import { useState } from "react";
import { KnobMenuNumber } from "../backend/fields";
import {
  effectiveDensity,
  editSweepRange,
  MAX_SWEEP_POINTS,
  type ResolvedSweepRange,
  type SweepGrid,
  type SweepRange,
  type SweepRangeLevel,
} from "../../lib/sweep";

// Which field the user is editing (Steve, 2026-09-23): `editSweepRange`
// already refuses a bad value (step ≤ 0, a sub-2 point count, lo ≤ 0,
// hi ≤ lo) by returning null, but that alone left the field showing what was
// typed with no sign the edit never happened. This tracks which field's
// LAST attempted value was refused, so it can be marked `data-invalid` until
// corrected or reverted (blur / Escape, handled by KnobMenuNumber itself).
type SweepField = "lo" | "hi" | "step" | "points";

// Where "↺ design range" lands, in the words the menu uses for it.
const LEVEL_LABEL: Record<SweepRangeLevel, string> = {
  session: "your edit",
  file: "the file's sweep",
  design: "the design's range",
  policy: "the design's sweep policy",
  default: "the default window",
};

// The measurement dial's right-click menu (AK#1682): the dial's travel IS
// the sweep range, and this is where it is edited. Same pattern and classes
// as KnobOptMenu — a full-screen backdrop takes the outside click (no
// document listener, so no contains(e.target) trap), fixed at the click.
export function SweepRangeMenu({
  menu,
  resolved,
  design,
  grid,
  refineEnabled,
  onEdit,
  onRevert,
  onClose,
}: {
  /** `touch`: opened by a long press, whose finger is still down when the
   *  menu appears — Android then fires its own contextmenu at the point
   *  under it, which is now the backdrop and must not close the menu. */
  menu: { x: number; y: number; touch?: boolean };
  /** The range in force and the rung it came from. */
  resolved: ResolvedSweepRange;
  /** Where "↺ design range" would land (levels 2–5). */
  design: ResolvedSweepRange;
  /** The grid the sweep runs for `resolved` (its point count + clamp). */
  grid: SweepGrid;
  /** Adaptive refinement is on for this session (AK#1682 follow-up): the
   *  log "points" field is then the BASE grid refinement starts from, so
   *  the menu labels it "base points" rather than "points". */
  refineEnabled?: boolean;
  onEdit: (next: SweepRange) => void;
  onRevert: () => void;
  onClose: () => void;
}) {
  const range = resolved.range;
  const n = grid.freqs.length;
  const d = effectiveDensity(range, n);
  const round = (v: number, sig = 6) => Number(v.toPrecision(sig));
  const [invalidFields, setInvalidFields] = useState<ReadonlySet<SweepField>>(
    new Set(),
  );
  const markValid = (field: SweepField) =>
    setInvalidFields((s) => {
      if (!s.has(field)) return s;
      const next = new Set(s);
      next.delete(field);
      return next;
    });
  const set = (field: SweepField, patch: Partial<SweepRange>) => {
    const next = editSweepRange(range, n, patch);
    if (next) {
      onEdit(next);
      markValid(field);
    } else {
      setInvalidFields((s) => (s.has(field) ? s : new Set(s).add(field)));
    }
  };
  const edited = resolved.level === "session";
  return (
    <>
      <div
        className="knob-menu-backdrop"
        onClick={onClose}
        onContextMenu={(e) => {
          e.preventDefault();
          if (!menu.touch) onClose();
        }}
      />
      <div
        className="knob-menu sweep-range-menu"
        role="dialog"
        aria-label="sweep range"
        style={{ left: menu.x, top: menu.y }}
        onContextMenu={(e) => e.preventDefault()}
      >
        <div className="knob-menu-title">Sweep range</div>
        <div className="knob-menu-row">
          <span>Sweep range lo / hi (MHz)</span>
          <KnobMenuNumber
            value={round(range.lo)}
            onChange={(v) => set("lo", { lo: v })}
            invalid={invalidFields.has("lo")}
            onRevert={() => markValid("lo")}
          />
          <KnobMenuNumber
            value={round(range.hi)}
            onChange={(v) => set("hi", { hi: v })}
            invalid={invalidFields.has("hi")}
            onRevert={() => markValid("hi")}
          />
        </div>
        {range.spacing === "lin" ? (
          <div className="knob-menu-row">
            <span>Step (MHz)</span>
            <KnobMenuNumber
              value={round(d.step, 4)}
              onChange={(v) => set("step", { step: v })}
              invalid={invalidFields.has("step")}
              onRevert={() => markValid("step")}
            />
            <span className="knob-menu-note">{n} points</span>
          </div>
        ) : (
          <div className="knob-menu-row">
            <span>{refineEnabled ? "Base points" : "Points"}</span>
            <KnobMenuNumber
              value={Math.round(d.points)}
              onChange={(v) => set("points", { points: Math.round(v) })}
              invalid={invalidFields.has("points")}
              onRevert={() => markValid("points")}
            />
          </div>
        )}
        {range.spacing === "log" && refineEnabled ? (
          <div className="knob-menu-note">
            refinement adds points where the curve bends
          </div>
        ) : null}
        <div className="knob-menu-row">
          <span>Spacing</span>
          <select
            aria-label="sweep spacing"
            value={range.spacing}
            onChange={(e) => {
              // Never refused (a valid range's own spacing always re-applies
              // cleanly), so this bypasses the per-field invalid tracking
              // `set` above does for the numeric fields.
              const next = editSweepRange(range, n, {
                spacing: e.target.value as SweepRange["spacing"],
              });
              if (next) onEdit(next);
            }}
          >
            <option value="lin">lin</option>
            <option value="log">log</option>
          </select>
        </div>
        <div className="knob-menu-note" data-clamped={grid.clamped || undefined}>
          {grid.clamped
            ? `${grid.requested} points asked; clamped to ${MAX_SWEEP_POINTS}, the hosted limit.`
            : `${n} points${edited ? "" : ` · from ${LEVEL_LABEL[resolved.level]}`}`}
        </div>
        <button
          type="button"
          className="knob-menu-revert"
          disabled={!edited}
          title={`Return to ${LEVEL_LABEL[design.level]}: ${round(design.range.lo)}–${round(design.range.hi)} MHz`}
          onClick={() => {
            setInvalidFields(new Set());
            onRevert();
          }}
        >
          ↺ design range
        </button>
      </div>
    </>
  );
}
