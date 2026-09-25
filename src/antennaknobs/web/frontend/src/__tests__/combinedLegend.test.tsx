// The combined view's key (AK#1730): beside the plot there is only the cut key
// and the fill switch. Which design is which belongs to the compare table.
import { describe, it, expect, vi } from "vitest";
import { fireEvent, render, screen } from "@testing-library/react";
import { CombinedLegend } from "../components/results/StageOverlays";

describe("CombinedLegend", () => {
  it("shows the cut key and the fill switch, and no per-design rows", () => {
    render(<CombinedLegend fill="none" setFill={() => {}} />);
    const key = screen.getByLabelText("Combined pattern key");
    expect(key.textContent).toContain("az");
    expect(key.textContent).toContain("el");
    // Exactly the two fill buttons: nothing that picks a design.
    expect(screen.getAllByRole("button").map((b) => b.textContent)).toEqual([
      "none",
      "el",
    ]);
  });

  it("switches the fill, and shows which fill is on", () => {
    const setFill = vi.fn();
    render(<CombinedLegend fill="none" setFill={setFill} />);
    expect(screen.getByRole("button", { name: "none" }).getAttribute("aria-pressed")).toBe("true");
    fireEvent.click(screen.getByRole("button", { name: "el" }));
    expect(setFill).toHaveBeenLastCalledWith("elevation");
  });
});
