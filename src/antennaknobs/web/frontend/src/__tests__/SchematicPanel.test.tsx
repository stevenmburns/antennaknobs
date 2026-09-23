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
import { fireEvent, render, screen } from "@testing-library/react";
import { SchematicPanel } from "../components/results/SchematicPanel";
import { FIT_CAP, naturalSize, stepZoom, ZOOM_STEPS } from "../lib/schematicZoom";

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

// --- 3. Readable sizing on the stage (AK#1682) -----------------------------
//
// jsdom lays nothing out, so what is pinned is the contract the CSS reads:
// the natural size parsed from schemdraw's pt attributes, the fit cap and the
// zoom multiple published as custom properties, and the scroll mode class.

// schemdraw's own header shape: height/width in pt, height first.
const WIDE =
  '<svg xmlns="http://www.w3.org/2000/svg" height="150pt" width="600pt" viewBox="0 0 600 150"><path d="M 0,0 L 600,150" /></svg>';

describe("naturalSize / stepZoom", () => {
  it("reads schemdraw's pt size as CSS px", () => {
    expect(naturalSize(WIDE)).toEqual({ w: 800, h: 200 });
    expect(naturalSize('<svg width="30px" height="20px"></svg>')).toEqual({ w: 30, h: 20 });
    expect(naturalSize(SVG)).toBeNull();
  });

  it("steps through the ladder from wherever the view is", () => {
    expect(stepZoom(1, 1)).toBe(1.25);
    expect(stepZoom(0.83, 1)).toBe(1); // from a fit scale between steps
    expect(stepZoom(0.83, -1)).toBe(0.75);
    expect(stepZoom(ZOOM_STEPS[0], -1)).toBe(ZOOM_STEPS[0]);
    expect(stepZoom(ZOOM_STEPS.at(-1)!, 1)).toBe(ZOOM_STEPS.at(-1));
  });
});

describe("stage zoom", () => {
  const scroll = (c: HTMLElement) => c.querySelector(".schematic-scroll") as HTMLElement;

  it("fits by default, capping the upscale at FIT_CAP × natural size", () => {
    const { container } = renderPanel({ svg: WIDE });
    const box = scroll(container);
    expect(box.dataset.zoom).toBe("fit");
    expect(box.className).toContain("schematic-fit");
    expect(box.style.getPropertyValue("--schem-max-w")).toBe(`${800 * FIT_CAP}px`);
    expect(box.style.getPropertyValue("--schem-max-h")).toBe(`${200 * FIT_CAP}px`);
    expect(
      screen.getByRole("button", { name: "Fit to panel" }).getAttribute("aria-pressed"),
    ).toBe("true");
  });

  it("zooms to exact multiples of natural size in a scrolling box, and back to fit", () => {
    const { container } = renderPanel({ svg: WIDE });
    // No layout in jsdom: the fit scale reads as natural size (1), so the
    // first press is one step up from there.
    fireEvent.click(screen.getByRole("button", { name: "Zoom in" }));
    let box = scroll(container);
    expect(box.dataset.zoom).toBe("1.25");
    expect(box.className).toContain("schematic-zoomed");
    expect(box.style.getPropertyValue("--schem-w")).toBe("1000px");
    expect(box.style.getPropertyValue("--schem-h")).toBe("250px");
    expect(screen.getByRole("button", { name: "Fit to panel" }).textContent).toBe("125%");

    fireEvent.click(screen.getByRole("button", { name: "Zoom out" }));
    fireEvent.click(screen.getByRole("button", { name: "Zoom out" }));
    box = scroll(container);
    expect(box.dataset.zoom).toBe("0.75");

    fireEvent.click(screen.getByRole("button", { name: "Fit to panel" }));
    expect(scroll(container).dataset.zoom).toBe("fit");
  });

  it("keeps the zoom across a re-rendered drawing (every knob tweak refetches)", () => {
    const { container, rerender } = renderPanel({ svg: WIDE });
    fireEvent.click(screen.getByRole("button", { name: "Zoom in" }));
    rerender(
      <SchematicPanel
        svg={WIDE.replace("600,150", "590,150")}
        unavailable={false}
        size={180}
        fill
      />,
    );
    expect(scroll(container).dataset.zoom).toBe("1.25");
  });

  it("disables the top of the ladder", () => {
    renderPanel({ svg: WIDE });
    const zin = screen.getByRole("button", { name: "Zoom in" });
    for (let i = 0; i < ZOOM_STEPS.length + 2; i++) fireEvent.click(zin);
    expect((zin as HTMLButtonElement).disabled).toBe(true);
  });

  it("thumbnails stay shrink-to-fit with no zoom control", () => {
    const { container } = renderPanel({ svg: WIDE, fill: false });
    expect(container.querySelector(".schematic-scroll")).toBeNull();
    expect(screen.queryByRole("group", { name: "Schematic zoom" })).toBeNull();
    expect(container.querySelector(".schematic-thumb svg")).not.toBeNull();
  });

  it("a drawing without a size still fits, with no zoom to offer", () => {
    const { container } = renderPanel({ svg: SVG });
    expect(scroll(container).dataset.zoom).toBe("fit");
    expect(screen.queryByRole("group", { name: "Schematic zoom" })).toBeNull();
  });
});
