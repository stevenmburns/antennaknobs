// Pins the conditional-rendering matrix of the schematic view's panel
// (src/components/results/SchematicPanel.tsx, issue #652): the three states
// the useSchematic hook can hand it — loading gap (no svg, not yet declared
// unavailable), the bare-antenna empty state, and an inlined server-rendered
// drawing — plus the fill/thumb sizing split. Every presence assertion is
// paired with an absence assertion on a state that must NOT show the element,
// matching the SolveOverlays precedent.
//
// The SVG arrives as a markup string and is inlined via dangerouslySetInnerHTML
// (so its currentColor strokes inherit the theme), which is why the drawing
// assertions query the container's innerHTML/child rather than a React child.
import { describe, it, expect } from "vitest";
import { render, screen } from "@testing-library/react";
import { SchematicPanel } from "../components/results/SchematicPanel";

const SVG = '<svg viewBox="0 0 10 10"><path d="M 0,0 L 10,10" /></svg>';
const EMPTY_MSG = /no feed circuit/i;

function renderPanel(
  overrides: Partial<{
    svg: string | null;
    unavailable: boolean;
    size: number;
    fill: boolean;
  }> = {},
) {
  return render(
    <SchematicPanel
      svg={null}
      unavailable={false}
      size={180}
      fill={true}
      {...overrides}
    />,
  );
}

// --- 1. The three data states ----------------------------------------------

describe("data states", () => {
  it("renders nothing but the container while loading (no svg, not unavailable)", () => {
    const { container } = renderPanel();
    expect(screen.queryByText(EMPTY_MSG)).toBeNull();
    expect(container.querySelector("svg")).toBeNull();
  });

  it("shows the bare-antenna message once the server said no feed circuit", () => {
    renderPanel({ unavailable: true });
    expect(screen.queryByText(EMPTY_MSG)).not.toBeNull();
  });

  it("inlines the drawing, and the empty message stays out", () => {
    const { container } = renderPanel({ svg: SVG });
    const svg = container.querySelector("svg");
    expect(svg).not.toBeNull();
    expect(svg!.getAttribute("viewBox")).toBe("0 0 10 10");
    expect(screen.queryByText(EMPTY_MSG)).toBeNull();
  });

  it("prefers the drawing when svg and unavailable are both set", () => {
    // The hook never produces this pair (each response sets one and clears
    // the other), but the panel's precedence should not depend on that.
    const { container } = renderPanel({ svg: SVG, unavailable: true });
    expect(container.querySelector("svg")).not.toBeNull();
    expect(screen.queryByText(EMPTY_MSG)).toBeNull();
  });
});

// --- 2. fill vs thumb sizing -------------------------------------------------

describe("fill/thumb split", () => {
  it("fill mode stretches (class), no fixed size", () => {
    const { container } = renderPanel({ svg: SVG, fill: true });
    const el = container.firstElementChild as HTMLElement;
    expect(el.className).toBe("schematic-fill");
    expect(el.style.width).toBe("");
  });

  it("thumb mode pins the square from the size prop", () => {
    const { container } = renderPanel({ svg: SVG, fill: false, size: 150 });
    const el = container.firstElementChild as HTMLElement;
    expect(el.className).toBe("schematic-thumb");
    expect(el.style.width).toBe("150px");
    expect(el.style.height).toBe("150px");
  });
});
