// The rail/grid segmented control (unit 3, docs/plan-view-rail-scaling.md).
// Placement (desktop only, stage top-right) is DesignSession's job, not this
// component's — see DesignSession.layoutPlacement.test.tsx (#718), which
// mounts the real DesignSession to check it.
import { describe, it, expect, vi } from "vitest";
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { LayoutModeToggle } from "../components/results/StageOverlays";

describe("LayoutModeToggle", () => {
  it("marks rail active when layout is rail", () => {
    render(<LayoutModeToggle layout="rail" setLayout={vi.fn()} />);
    expect(screen.getByTitle(/^Rail:/).className).toContain("active");
    expect(screen.getByTitle(/^Grid:/).className).not.toContain("active");
  });

  it("marks grid active when layout is grid", () => {
    render(<LayoutModeToggle layout="grid" setLayout={vi.fn()} />);
    expect(screen.getByTitle(/^Grid:/).className).toContain("active");
    expect(screen.getByTitle(/^Rail:/).className).not.toContain("active");
  });

  it("calls setLayout('grid') from rail", async () => {
    const user = userEvent.setup();
    const setLayout = vi.fn();
    render(<LayoutModeToggle layout="rail" setLayout={setLayout} />);
    await user.click(screen.getByTitle(/^Grid:/));
    expect(setLayout).toHaveBeenCalledWith("grid");
  });

  it("calls setLayout('rail') from grid", async () => {
    const user = userEvent.setup();
    const setLayout = vi.fn();
    render(<LayoutModeToggle layout="grid" setLayout={setLayout} />);
    await user.click(screen.getByTitle(/^Rail:/));
    expect(setLayout).toHaveBeenCalledWith("rail");
  });
});
