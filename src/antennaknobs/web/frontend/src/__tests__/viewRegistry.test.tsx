// Pins the view registry (unit 1 of docs/plan-view-rail-scaling.md): the
// metadata half in lib/view.ts and the render half in
// components/results/viewRegistry.tsx are two records keyed by the same View
// ids, and ViewPanel is nothing but the lookup between them. What this file
// guards is that the two halves stay in step and that dispatch lands on the
// right component — a wiring swap (schematic's id pointing at the Smith
// renderer) typechecks fine, so only a mounted probe catches it.
import { describe, it, expect, vi } from "vitest";
import { render } from "@testing-library/react";
import { VIEWS, type View } from "../lib/view";
import { VIEW_RENDERERS, type ViewRenderProps } from "../components/results/viewRegistry";
import { ViewPanel } from "../components/results/ViewPanel";

// Azimuth and elevation are the same component differing only by its `cut`
// prop, which drives canvas drawing and leaves no DOM trace. Stubbing that
// one component surfaces `cut` as an attribute so an az↔el swap fails here;
// every other view's component renders for real.
vi.mock("../components/charts/FarFieldChart", () => ({
  FarFieldChart: ({ cut }: { cut: string }) => (
    <canvas className="farfield" data-cut={cut} />
  ),
}));

// jsdom ships no 2-D context, and every chart mounted below already guards on
// a null one and takes its no-draw path. Returning null directly keeps that
// path while dropping jsdom's "not implemented" stack trace per mount.
HTMLCanvasElement.prototype.getContext =
  (() => null) as unknown as HTMLCanvasElement["getContext"];

// Compile-time enumeration of the View union: a missing or misspelled member
// fails tsc (npm run build), so the runtime lists below cannot drift from the
// type.
const EVERY_VIEW: Record<View, true> = {
  antenna: true,
  azimuth: true,
  elevation: true,
  smith: true,
  schematic: true,
  gamma: true,
  vswr: true,
};
const ALL_VIEWS = Object.keys(EVERY_VIEW) as View[];

// --- 1. The two halves cover the union, once each ---------------------------

describe("registry coverage", () => {
  it("has exactly one VIEWS entry per member of the View union", () => {
    expect(VIEWS.map((v) => v.id).sort()).toEqual([...ALL_VIEWS].sort());
    expect(new Set(VIEWS.map((v) => v.id)).size).toBe(VIEWS.length);
  });

  it("has exactly one render entry per member of the View union", () => {
    expect(Object.keys(VIEW_RENDERERS).sort()).toEqual([...ALL_VIEWS].sort());
    for (const id of ALL_VIEWS) {
      expect(typeof VIEW_RENDERERS[id]).toBe("function");
    }
  });
});

// --- 2. Metadata values -----------------------------------------------------

describe("view metadata", () => {
  it("keeps the shipped labels and their rail order", () => {
    expect(VIEWS.map((v) => [v.id, v.label])).toEqual([
      ["antenna", "Antenna"],
      ["azimuth", "Azimuth (xy)"],
      ["elevation", "Elevation (yz)"],
      ["smith", "Smith"],
      ["schematic", "Schematic"],
      ["gamma", "|Γ| vs freq"],
      ["vswr", "VSWR vs freq"],
    ]);
  });

  // The founding four are pinned by default; schematic and every later view
  // ship unpinned (docs/plan-view-rail-scaling.md, "The pin model") — gamma
  // and vswr are the roster's first test of that rule beyond schematic.
  it("defaults exactly the founding four to pinned", () => {
    expect(VIEWS.filter((v) => v.defaultPinned).map((v) => v.id).sort()).toEqual(
      ["antenna", "azimuth", "elevation", "smith"],
    );
  });
});

// --- 3. Dispatch lands on the right component -------------------------------

const PROPS: Omit<ViewRenderProps, "showWireLabels" | "showFeedNames" | "schematicSvg" | "schematicUnavailable"> = {
  size: 180,
  fill: true,
  result: null,
  preview: null,
  sweep: null,
  converge: null,
  measured: null,
  pattern: null,
  pinnedPatterns: [],
  measFreqMhz: 14.1,
  sweepRunning: false,
  convergeRunning: false,
  azElevDeg: 0,
  elevAzDeg: 0,
  cameraProjection: "xy",
  showHeatmap: false,
  showEnvelope: false,
  multiFeed: false,
  fineNorm: null,
};

function mount(view: View, overrides: Partial<React.ComponentProps<typeof ViewPanel>> = {}) {
  return render(<ViewPanel view={view} {...PROPS} {...overrides} />).container;
}

// One selector per view's own component. Each probe asserts its own marker is
// present AND that the neighbours it could be confused with are absent, so a
// swapped pair fails on both sides.
const MARKERS: Record<View, string> = {
  antenna: ".canvas-viewport",
  azimuth: 'canvas.farfield[data-cut="xy"]',
  elevation: 'canvas.farfield[data-cut="yz"]',
  smith: "canvas.smith",
  schematic: ".schematic-fill",
  gamma: 'canvas.sweep[data-mode="gamma"]',
  vswr: 'canvas.sweep[data-mode="vswr"]',
};

describe("dispatch", () => {
  for (const view of ALL_VIEWS) {
    it(`renders only the ${view} view's component`, () => {
      const container = mount(view);
      expect(container.querySelector(MARKERS[view])).not.toBeNull();
      for (const other of ALL_VIEWS) {
        if (other === view) continue;
        expect(container.querySelector(MARKERS[other])).toBeNull();
      }
    });
  }

  it("keeps the antenna view's preview fallback and thumb sizing", () => {
    const preview = { z_in_re: 50, z_in_im: 0 } as ViewRenderProps["preview"];
    const thumb = mount("antenna", { fill: false, size: 96, preview });
    const wrapper = thumb.querySelector(".antenna-thumb") as HTMLElement;
    expect(wrapper).not.toBeNull();
    expect(wrapper.style.width).toBe("96px");
    expect(wrapper.style.height).toBe("96px");
    expect(thumb.querySelector(".antenna-fill")).toBeNull();
    // fill drives the canvas's interactive affordances, so the Fit button is
    // the thumb/stage discriminator.
    expect(thumb.querySelector(".viewport-fit")).toBeNull();
    expect(mount("antenna").querySelector(".viewport-fit")).not.toBeNull();
  });

  it("passes the schematic view its own props", () => {
    const svg = '<svg viewBox="0 0 10 10"><path d="M 0,0 L 10,10" /></svg>';
    expect(mount("schematic", { schematicSvg: svg }).innerHTML).toContain("viewBox");
    const empty = mount("schematic", { schematicUnavailable: true });
    expect(empty.textContent).toMatch(/no feed circuit/i);
    // Thumb sizing is the panel's, not the wrapper div's.
    const thumb = mount("schematic", { fill: false, size: 96 });
    expect(thumb.querySelector(".schematic-thumb")).not.toBeNull();
  });
});
