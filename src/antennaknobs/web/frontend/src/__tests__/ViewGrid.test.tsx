// The grid-mode stage's presentational component (unit 3, docs/plan-view-
// rail-scaling.md). Decoupled from DesignSession's solve/session state on
// purpose (see ViewGrid.tsx's own comment) so it can be mounted directly
// instead of needing the fetch/WebSocket harness a real DesignSession mount
// would — matching this suite's existing precedent of testing pieces PULLED
// OUT of DesignSession (SolveOverlays.test.tsx, ViewPicker.test.tsx) rather
// than the monolith itself.
import { describe, it, expect, vi } from "vitest";
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { createRef } from "react";
import { VIEW_META, type View } from "../lib/view";
import { ViewGrid } from "../components/results/ViewGrid";

const cellsOf = (ids: View[]) => ids.map((id) => VIEW_META[id]);

function renderGrid(overrides: Partial<Parameters<typeof ViewGrid>[0]> = {}) {
  const setView = vi.fn();
  const onMaximize = vi.fn();
  const renderCell = vi.fn((v: View, size: number) => (
    <div data-testid={`cell-content-${v}`}>{`${v}@${size}`}</div>
  ));
  const props = {
    gridRef: createRef<HTMLDivElement>(),
    cells: cellsOf(["antenna", "azimuth", "elevation", "smith"]),
    view: "antenna" as View,
    setView,
    onMaximize,
    cellSize: 240,
    rows: 2,
    cols: 2,
    renderCell,
    ...overrides,
  };
  const view = render(<ViewGrid {...props} />);
  return { ...view, setView, onMaximize, renderCell, props };
}

// --- 1. Cell order and shape ------------------------------------------------

describe("cell order and shape", () => {
  // Mutation probe 4(a) target: reversing (or otherwise reordering) the
  // `cells` prop before it reaches ViewGrid must fail this.
  it("renders cells in exactly the given (pin) order", () => {
    renderGrid({ cells: cellsOf(["smith", "antenna", "azimuth"]), rows: 2, cols: 2 });
    const ids = screen
      .getAllByRole("button", { name: /^Focus / })
      .map((el) => el.getAttribute("aria-label"));
    expect(ids).toEqual(["Focus Smith", "Focus Antenna", "Focus Azimuth (xy)"]);
  });

  it("1x2 for two pins: two cells, no hint", () => {
    renderGrid({ cells: cellsOf(["antenna", "azimuth"]), rows: 1, cols: 2 });
    expect(screen.getAllByRole("button", { name: /^Focus / })).toHaveLength(2);
    expect(screen.queryByText("Pin a 4th view")).toBeNull();
  });

  it("2x2 for four pins: four cells, no hint", () => {
    renderGrid({ cells: cellsOf(["antenna", "azimuth", "elevation", "smith"]), rows: 2, cols: 2 });
    expect(screen.getAllByRole("button", { name: /^Focus / })).toHaveLength(4);
    expect(screen.queryByText("Pin a 4th view")).toBeNull();
  });

  it("2x2 with a hint cell for three pins", () => {
    renderGrid({ cells: cellsOf(["antenna", "azimuth", "elevation"]), rows: 2, cols: 2 });
    expect(screen.getAllByRole("button", { name: /^Focus / })).toHaveLength(3);
    expect(screen.getByText("Pin a 4th view")).not.toBeNull();
  });

  it("one full cell for a single pin", () => {
    renderGrid({ cells: cellsOf(["antenna"]), rows: 1, cols: 1 });
    expect(screen.getAllByRole("button", { name: /^Focus / })).toHaveLength(1);
  });

  it("sets the grid-template from rows/cols", () => {
    const { container } = renderGrid({ rows: 2, cols: 2 });
    const grid = container.querySelector(".view-grid") as HTMLElement;
    expect(grid.style.gridTemplateColumns).toBe("repeat(2, 1fr)");
    expect(grid.style.gridTemplateRows).toBe("repeat(2, 1fr)");
  });

  it("passes cellSize through to renderCell", () => {
    const { renderCell } = renderGrid({ cellSize: 333 });
    expect(renderCell).toHaveBeenCalledWith("antenna", 333);
  });
});

// --- 2. Focus ring -----------------------------------------------------------

describe("focus ring", () => {
  it("marks the cell matching `view` and no other", () => {
    const { container } = renderGrid({ view: "elevation" });
    const focused = container.querySelectorAll(".grid-cell-focus");
    expect(focused).toHaveLength(1);
    expect(focused[0].querySelector(".grid-cell-maximize")?.getAttribute("title")).toBe(
      "Maximize Elevation (yz)",
    );
  });
});

// --- 3. Click vs. maximize ----------------------------------------------------

describe("cell click vs. maximize", () => {
  it("clicking a cell body focuses it without maximizing", async () => {
    const user = userEvent.setup();
    const { setView, onMaximize } = renderGrid();
    await user.click(screen.getByTestId("cell-content-azimuth"));
    expect(setView).toHaveBeenCalledWith("azimuth");
    expect(onMaximize).not.toHaveBeenCalled();
  });

  it("clicking the maximize glyph maximizes without also focusing", async () => {
    const user = userEvent.setup();
    const { setView, onMaximize } = renderGrid();
    await user.click(screen.getByTitle("Maximize Smith"));
    expect(onMaximize).toHaveBeenCalledWith("smith");
    expect(setView).not.toHaveBeenCalled();
  });

  it("double-clicking a cell body maximizes it", async () => {
    const user = userEvent.setup();
    const { onMaximize } = renderGrid();
    await user.dblClick(screen.getByTestId("cell-content-elevation"));
    expect(onMaximize).toHaveBeenCalledWith("elevation");
  });
});

// --- 4. The HUD never renders per-cell ---------------------------------------

describe("solve-readout HUD", () => {
  it("is never rendered by ViewGrid itself (unit 3 renders it once, at the stage level)", () => {
    const { container } = renderGrid();
    expect(container.querySelectorAll(".stage-readout")).toHaveLength(0);
    expect(container.querySelectorAll(".readout")).toHaveLength(0);
  });
});
