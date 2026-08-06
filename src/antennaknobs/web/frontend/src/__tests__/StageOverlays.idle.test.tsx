// The layout toggle floats over chart content, so it fades after
// LAYOUT_TOGGLE_IDLE_MS without mouse activity and returns on movement;
// hover and keyboard focus hold it visible (a resting cursor is intent,
// not idleness). The idle class also drops pointer-events (styles.css) so
// faded means the data underneath is hoverable — presence of the class is
// the whole behavioral contract, pinned here.
import { describe, it, expect, vi, beforeEach, afterEach } from "vitest";
import { render, act, fireEvent } from "@testing-library/react";
import {
  LayoutModeToggle,
  LAYOUT_TOGGLE_IDLE_MS,
} from "../components/results/StageOverlays";

function renderToggle() {
  return render(<LayoutModeToggle layout="rail" setLayout={() => {}} />);
}

const toggle = () =>
  document.querySelector(".layout-toggle") as HTMLElement;

beforeEach(() => {
  vi.useFakeTimers();
});
afterEach(() => {
  vi.useRealTimers();
});

describe("layout toggle idle fade", () => {
  it("is visible on mount and fades after the idle window", () => {
    renderToggle();
    expect(toggle().className).not.toContain("layout-toggle-idle");
    act(() => {
      vi.advanceTimersByTime(LAYOUT_TOGGLE_IDLE_MS + 50);
    });
    expect(toggle().className).toContain("layout-toggle-idle");
  });

  it("returns on mouse movement and fades again when it stops", () => {
    renderToggle();
    act(() => {
      vi.advanceTimersByTime(LAYOUT_TOGGLE_IDLE_MS + 50);
    });
    expect(toggle().className).toContain("layout-toggle-idle");
    act(() => {
      fireEvent.mouseMove(window);
    });
    expect(toggle().className).not.toContain("layout-toggle-idle");
    act(() => {
      vi.advanceTimersByTime(LAYOUT_TOGGLE_IDLE_MS + 50);
    });
    expect(toggle().className).toContain("layout-toggle-idle");
  });

  it("never fades while hovered", () => {
    renderToggle();
    act(() => {
      fireEvent.mouseEnter(toggle());
    });
    act(() => {
      vi.advanceTimersByTime(LAYOUT_TOGGLE_IDLE_MS * 3);
    });
    expect(toggle().className).not.toContain("layout-toggle-idle");
    // Leaving without movement re-arms nothing by itself — the NEXT idle
    // window after leaving is what fades it.
    act(() => {
      fireEvent.mouseLeave(toggle());
      fireEvent.mouseMove(window);
    });
    act(() => {
      vi.advanceTimersByTime(LAYOUT_TOGGLE_IDLE_MS + 50);
    });
    expect(toggle().className).toContain("layout-toggle-idle");
  });

  it("never fades while a button inside has keyboard focus", () => {
    renderToggle();
    const btn = toggle().querySelector("button")!;
    act(() => {
      fireEvent.focus(btn);
    });
    act(() => {
      vi.advanceTimersByTime(LAYOUT_TOGGLE_IDLE_MS * 3);
    });
    expect(toggle().className).not.toContain("layout-toggle-idle");
  });
});
