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
  onEdit: (next: SweepRange) => void;
  onRevert: () => void;
  onClose: () => void;
}) {
  const range = resolved.range;
  const n = grid.freqs.length;
  const d = effectiveDensity(range, n);
  const round = (v: number, sig = 6) => Number(v.toPrecision(sig));
  const set = (patch: Partial<SweepRange>) => {
    const next = editSweepRange(range, n, patch);
    if (next) onEdit(next);
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
          <KnobMenuNumber value={round(range.lo)} onChange={(v) => set({ lo: v })} />
          <KnobMenuNumber value={round(range.hi)} onChange={(v) => set({ hi: v })} />
        </div>
        {range.spacing === "lin" ? (
          <div className="knob-menu-row">
            <span>Step (MHz)</span>
            <KnobMenuNumber value={round(d.step, 4)} onChange={(v) => set({ step: v })} />
          </div>
        ) : (
          <div className="knob-menu-row">
            <span>Points / decade</span>
            <KnobMenuNumber
              value={round(d.pointsPerDecade, 4)}
              onChange={(v) => set({ pointsPerDecade: v })}
            />
          </div>
        )}
        <div className="knob-menu-row">
          <span>Spacing</span>
          <select
            aria-label="sweep spacing"
            value={range.spacing}
            onChange={(e) => set({ spacing: e.target.value as SweepRange["spacing"] })}
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
          onClick={onRevert}
        >
          ↺ design range
        </button>
      </div>
    </>
  );
}
