// Behavioral replacement for gridLayoutPlacement.test.ts (#718): the two
// unit-3 placement facts (docs/plan-view-rail-scaling.md "Layout modes") —
// the layout segmented control is desktop-only, and the grid-mode HUD renders
// once at the stage level rather than per cell — checked by mounting the real
// <DesignSession> (via designSessionHarness.tsx) instead of slicing its
// source with Vite's `?raw`. That harness didn't exist when the old file was
// written; #728's global jsdom gap-fillers plus the mobile test's mounting
// recipe make a real mount cheap now, so the structural check no longer pays
// for itself.
//
// The old file's other two checks aren't reproduced here: its "both anchors,
// in the expected order" assertion was sanity-checking the slicing technique
// itself, which this file has no equivalent of (there's nothing to slice);
// and its "ViewGrid never contains `SolveReadout`" source check is already
// covered behaviorally by ViewGrid.test.tsx's "solve-readout HUD" describe
// block, which mounts ViewGrid directly and asserts it renders no
// `.readout`/`.stage-readout` element itself — the same fact, checked at the
// component boundary instead of in DesignSession.tsx's source.
import { describe, it, expect, afterEach, vi } from "vitest";
import { screen, waitFor } from "@testing-library/react";
import { mountDesignSession } from "./designSessionHarness";

afterEach(() => {
  vi.unstubAllGlobals();
});

describe("DesignSession's mobile/desktop branch split", () => {
  it("shows the layout segmented control on desktop", async () => {
    mountDesignSession({ mobile: false, layout: "rail" });
    // LayoutModeToggle renders as a single `role="group"` (StageOverlays.tsx)
    // — a stable, semantics-based query with no data-testid needed.
    await waitFor(() =>
      expect(screen.getByRole("group", { name: "Stage layout" })).toBeTruthy(),
    );
  });

  it("never shows the layout segmented control on mobile", async () => {
    const { container } = mountDesignSession({ mobile: true });
    await waitFor(() =>
      expect(container.querySelector(".mobile-carousel")).not.toBeNull(),
    );
    expect(screen.queryByRole("group", { name: "Stage layout" })).toBeNull();
  });

  it("renders exactly one stage-level solve-readout HUD in grid layout, not one per cell", async () => {
    const { container } = mountDesignSession({
      mobile: false,
      layout: "grid",
    });
    await waitFor(() =>
      expect(container.querySelector(".view-grid")).not.toBeNull(),
    );
    // The harness's default pinned set is the four founding views, so grid
    // mode renders a full 2x2 (four cells, GRID_CELL_CAP) — if the HUD
    // rendered per cell instead of once at the stage, this count would be 4.
    // SolveReadout's own root div always carries the "readout" class
    // (SolveReadout.tsx), a stable query with no data-testid needed.
    expect(container.querySelectorAll(".readout")).toHaveLength(1);
    expect(container.querySelector(".stage-readout")).not.toBeNull();
  });
});
