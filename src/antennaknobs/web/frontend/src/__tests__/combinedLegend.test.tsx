// The combined view's legend (AK#1730): colour says which cut, so with pins
// on screen the legend is what says which design. Each shown pin gets a named
// row, clicking a row focuses it (and clicking it again clears), and the fill
// switch reports the chosen fill.
import { describe, it, expect, vi } from "vitest";
import { fireEvent, render, screen } from "@testing-library/react";
import { CombinedLegend } from "../components/results/StageOverlays";
import { LIVE_ENTITY } from "../components/charts/combined";
import type { PinnedPattern } from "../components/charts/types";
import type { SolveResponse } from "../lib/api";

const pin = (id: string, label: string, enabled = true, colorIdx = 0): PinnedPattern => ({
  id,
  label,
  result: {} as SolveResponse,
  metrics: null,
  enabled,
  colorIdx,
});

function mount(over: Partial<Parameters<typeof CombinedLegend>[0]> = {}) {
  const props = {
    pinnedPatterns: [pin("a", "legs 30°"), pin("b", "legs 60°", true, 1), pin("c", "hidden", false)],
    focus: null,
    setFocus: vi.fn(),
    fill: "none" as const,
    setFill: vi.fn(),
    ...over,
  };
  render(<CombinedLegend {...props} />);
  return props;
}

describe("CombinedLegend", () => {
  it("names the live design and every SHOWN pin", () => {
    mount();
    expect(screen.getByRole("button", { name: /live/ })).toBeTruthy();
    expect(screen.getByRole("button", { name: /legs 30°/ })).toBeTruthy();
    expect(screen.getByRole("button", { name: /legs 60°/ })).toBeTruthy();
    expect(screen.queryByRole("button", { name: /hidden/ })).toBeNull();
  });

  it("has no design rows without pins: colour alone names the cuts", () => {
    mount({ pinnedPatterns: [] });
    expect(screen.queryByRole("button", { name: /live/ })).toBeNull();
  });

  it("focuses a row on click", () => {
    const p = mount();
    fireEvent.click(screen.getByRole("button", { name: /legs 60°/ }));
    expect(p.setFocus).toHaveBeenLastCalledWith("b");
  });

  it("clears a focused row, and marks the others dim", () => {
    const p = mount({ focus: "a" });
    const a = screen.getByRole("button", { name: /legs 30°/ });
    expect(a.getAttribute("aria-pressed")).toBe("true");
    expect(screen.getByRole("button", { name: /live/ }).className).toContain("is-dim");
    fireEvent.click(a);
    expect(p.setFocus).toHaveBeenLastCalledWith(null);
  });

  it("treats a focus on a hidden pin as no focus", () => {
    mount({ focus: "c" });
    expect(screen.getByRole("button", { name: /live/ }).className).not.toContain("is-dim");
  });

  it("switches the fill", () => {
    const p = mount();
    expect(screen.getByRole("button", { name: "none" }).getAttribute("aria-pressed")).toBe("true");
    fireEvent.click(screen.getByRole("button", { name: "el" }));
    expect(p.setFill).toHaveBeenLastCalledWith("elevation");
  });

  it("uses the live entity id the chart uses", () => {
    const p = mount();
    fireEvent.click(screen.getByRole("button", { name: /live/ }));
    expect(p.setFocus).toHaveBeenLastCalledWith(LIVE_ENTITY);
  });
});
