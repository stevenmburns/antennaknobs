import type { ReactNode, RefObject } from "react";
import type { View, ViewMeta } from "../../lib/view";

// Grid layout mode's stage (unit 3, docs/plan-view-rail-scaling.md "Layout
// modes"): equal cells over the caller's displayed views, no primary. Purely
// presentational — `cells` (already sliced to the first ≤4 pins, in pin
// order — see useViewPrefs' gridCells) and `renderCell` come from the
// caller, so this file has no dependency on the solve/session state that
// makes DesignSession itself too heavy to mount in a test.
//
// The solve-readout HUD is deliberately NOT rendered here: unit 3 puts it
// once at the stage level (a sibling of this component), matching
// renderOutput's own "the HUD stays OUT of it" contract (DesignSession.tsx).
export function ViewGrid({
  gridRef,
  cells,
  view,
  setView,
  onMaximize,
  cellSize,
  rows,
  cols,
  renderCell,
}: {
  // Attached to the measured element (components/hooks.ts useGridCellSize) —
  // rows/cols must be the exact numbers that hook was called with, or the
  // measured cell size disagrees with the grid-template below.
  gridRef: RefObject<HTMLDivElement>;
  cells: ViewMeta[];
  view: View;
  setView: (v: View) => void;
  // Maximize glyph or double-click (Blender's cell↔full toggle): jump to
  // rail mode with this view primary. DesignSession supplies the
  // setView+setLayout("rail") pair as one callback.
  onMaximize: (v: View) => void;
  cellSize: number;
  rows: number;
  cols: number;
  renderCell: (v: View, size: number) => ReactNode;
}) {
  return (
    <div
      className="view-grid"
      ref={gridRef}
      style={{
        gridTemplateColumns: `repeat(${cols}, 1fr)`,
        gridTemplateRows: `repeat(${rows}, 1fr)`,
      }}
    >
      {cells.map((v) => (
        <div
          key={v.id}
          className={`grid-cell${v.id === view ? " grid-cell-focus" : ""}`}
          role="button"
          tabIndex={0}
          aria-label={`Focus ${v.label}`}
          aria-pressed={v.id === view}
          onClick={() => setView(v.id)}
          onDoubleClick={() => onMaximize(v.id)}
        >
          <button
            type="button"
            className="grid-cell-maximize"
            title={`Maximize ${v.label}`}
            onClick={(e) => {
              // Without this the click also bubbles to the cell's own
              // onClick above — harmless (setView to the view this cell
              // already is), but stopping it keeps "maximize" a single,
              // unambiguous action rather than two.
              e.stopPropagation();
              onMaximize(v.id);
            }}
          >
            ⛶
          </button>
          {renderCell(v.id, cellSize)}
        </div>
      ))}
      {/* A 3-pin grid still draws a 2×2 (see gridShape) — the 4th slot is an
          invitation, not a blank hole. Not a cell: no view, no focus ring,
          no maximize glyph. */}
      {cells.length === 3 && (
        <div className="grid-cell grid-cell-hint">Pin a 4th view</div>
      )}
    </div>
  );
}
