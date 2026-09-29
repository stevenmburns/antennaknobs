// Pins the view registry (unit 1 of docs/plan-view-rail-scaling.md): the
// metadata half in lib/view.ts and the render half in
// components/results/viewRegistry.tsx are two records keyed by the same View
// ids, and ViewPanel is nothing but the lookup between them. What this file
// guards is that the two halves stay in step and that dispatch lands on the
// right component — a wiring swap (schematic's id pointing at the Smith
// renderer) typechecks fine, so only a mounted probe catches it.
import { describe, it, expect, vi } from "vitest";
import { render } from "@testing-library/react";
import { CHART_COPIES, isChartCopy, VIEWS, VIEW_META, type View } from "../lib/view";
import {
  type ChartFrequencyRender,
  VIEW_RENDERERS,
  type ViewRenderProps,
} from "../components/results/viewRegistry";
import { RX_AUTO } from "../lib/paramSweep";
import { DEFAULT_AXES } from "../lib/sweepAxis";
import { ViewPanel } from "../components/results/ViewPanel";
import type { FilesViewData } from "../components/results/FilesPanel";

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
  combined: true,
  schematic: true,
  files: true,
  zparam: true,
  zparam2: true,
  zparam3: true,
  zparam4: true,
};
const ALL_VIEWS = Object.keys(EVERY_VIEW) as View[];
// The roster: every view but a duplicated chart's (AK#1757 step 5 unit 4),
// which the session adds while it is open and the picker never lists.
const ROSTER = ALL_VIEWS.filter((v) => !isChartCopy(v));

// --- 1. The two halves cover the union, once each ---------------------------

describe("registry coverage", () => {
  it("has exactly one VIEWS entry per member of the View union but the chart copies", () => {
    expect(VIEWS.map((v) => v.id).sort()).toEqual([...ROSTER].sort());
    expect(new Set(VIEWS.map((v) => v.id)).size).toBe(VIEWS.length);
    expect(ALL_VIEWS.filter(isChartCopy)).toEqual([...CHART_COPIES]);
  });

  it("gives every chart copy the chart's metadata under its own label", () => {
    for (const [i, id] of CHART_COPIES.entries()) {
      expect(VIEW_META[id]).toEqual({ ...VIEW_META.zparam, id, label: `Sweep ${i + 2}`, defaultPinned: false });
    }
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
      ["combined", "Az + El (combined)"],
      // The analysis chart in the Smith view's old place (AK#1757 step 5
      // unit 3), which folded the Smith, VSWR and S11 views in.
      ["zparam", "Sweep"],
      ["schematic", "Schematic"],
      ["files", "Files"],
    ]);
  });

  // The founding four are pinned by default; schematic and every later view
  // ship unpinned (docs/plan-view-rail-scaling.md, "The pin model"). The
  // fourth is the analysis chart now, which opens on the Smith chart the
  // fourth used to be (AK#1757 step 5 unit 3).
  it("defaults exactly the founding four to pinned", () => {
    expect(VIEWS.filter((v) => v.defaultPinned).map((v) => v.id)).toEqual(
      ["antenna", "azimuth", "elevation", "zparam"],
    );
  });

  // An optimizer run leaves the knobs alone until it finishes, so anything
  // drawn from the last solve describes the PRE-RUN design while the readout
  // ticks through candidates (#773). Those views dim; the ones that stay
  // honest must not, and that is the half worth pinning — dimming the
  // analysis chart would hide its live point (it dims only its swept curve,
  // DesignSession's chart stale rule, as the Smith view it replaced never
  // dimmed), and dimming the schematic would disown a drawing that is still
  // exactly right.
  it("marks every pre-run view stale while optimizing, and only those", () => {
    const stale = VIEWS.filter((v) => v.staleWhileOptimizing).map((v) => v.id);
    expect(stale.sort()).toEqual(["antenna", "azimuth", "combined", "elevation"]);
    expect(VIEW_META.zparam.staleWhileOptimizing).toBe(false);
    expect(VIEW_META.schematic.staleWhileOptimizing).toBe(false);
  });

  // The stage readout floats over every view. It starts minimized only where
  // the view's own content already carries the numbers and the card would
  // cover it: the Files view's printout. The analysis chart's default is the
  // session's, by what it shows (open on the Smith chart it opens on,
  // minimized on a knob sweep's R/X plot).
  it("starts the readout minimized only on the Files view", () => {
    expect(VIEWS.filter((v) => v.readoutStartsCollapsed).map((v) => v.id)).toEqual([
      "files",
    ]);
  });
});

// --- 3. Dispatch lands on the right component -------------------------------

const PROPS: Omit<ViewRenderProps, "showWireLabels" | "showFeedNames" | "schematicSvg" | "schematicUnavailable"> = {
  size: 180,
  fill: true,
  result: null,
  liveZ: null,
  preview: null,
  paramSweep: null,
  measured: null,
  pattern: null,
  pinnedPatterns: [],
  measFreqMhz: 14.1,
  paramSweepRunning: false,
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
  combined: "canvas.farfield[data-fill]",
  schematic: ".schematic-fill",
  files: ".files-fill",
  zparam: "canvas.zparam",
  zparam2: "canvas.zparam",
  zparam3: "canvas.zparam",
  zparam4: "canvas.zparam",
};

describe("dispatch", () => {
  for (const view of ALL_VIEWS) {
    it(`renders only the ${view} view's component`, () => {
      const container = mount(view);
      expect(container.querySelector(MARKERS[view])).not.toBeNull();
      for (const other of ROSTER) {
        if (MARKERS[other] === MARKERS[view]) continue;
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

  // The analysis chart's views (AK#1757 step 5 unit 3): the Smith, VSWR and
  // S11 views folded in, drawn from the chart's own sweep.
  const FREQ: ChartFrequencyRender = {
    view: "Smith",
    sweep: null,
    running: false,
    phase: "idle",
    progress: null,
    settled: true,
    stale: false,
    axes: DEFAULT_AXES,
    threshold: 2,
  };
  const chartOn = (f: Partial<ChartFrequencyRender>, o: Partial<React.ComponentProps<typeof ViewPanel>> = {}) =>
    mount("zparam", { chartFrequency: { ...FREQ, ...f }, ...o });

  it("draws a frequency sweep on the chart's Smith, SWR or S11 view, and a knob sweep as R/X or its Smith trail", () => {
    const smith = chartOn({ view: "Smith" });
    expect(smith.querySelector("canvas.smith")).not.toBeNull();
    expect(smith.querySelector("canvas.zparam")).toBeNull();
    expect(chartOn({ view: "Swr" }).querySelector('canvas.sweep[data-mode="vswr"]')).not.toBeNull();
    expect(chartOn({ view: "S11" }).querySelector('canvas.sweep[data-mode="gamma"]')).not.toBeNull();
    // No frequency sweep: the knob sweep, R/X by default...
    expect(mount("zparam").querySelector("canvas.zparam")).not.toBeNull();
    // ...or on the Smith chart, as the trail the old "param sweep" switch drew.
    const trail = mount("zparam", {
      zparam: { param: "N", label: "N", unit: null, total: 2, currentValue: null, xLog: true, rAxis: RX_AUTO, xAxis: RX_AUTO, z0: 50, view: "Smith" },
      paramSweep: { param: "N", label: "N", values: [3, 5], z_re: [50, 51], z_im: [0, 1] } as ViewRenderProps["paramSweep"],
    });
    expect(trail.querySelector("canvas.zparam")).toBeNull();
    expect(trail.querySelector("canvas.smith")!.getAttribute("data-trail")).toBe("N:3→5:2");
  });

  // Steve's laptop review of AK#1757 unit 4: the end-value callouts belong to
  // the stage. A thumbnail (no axis handlers) draws none, whatever the
  // session's callouts switch says.
  it("draws the knob sweep's end-value callouts on the stage only", () => {
    const sweep = { param: "N", label: "N", values: [3, 5, 7], z_re: [50, 51, 52], z_im: [0, 1, 2] } as ViewRenderProps["paramSweep"];
    const zp = { param: "N", label: "N", unit: null, total: 3, currentValue: null, xLog: true, rAxis: RX_AUTO, xAxis: RX_AUTO, z0: 50, callouts: true };
    const callouts = (o: Partial<React.ComponentProps<typeof ViewPanel>>) =>
      mount("zparam", { zparam: zp, paramSweep: sweep, ...o }).querySelector("canvas.zparam")!.getAttribute("data-callouts");
    expect(callouts({ fill: false, size: 96 })).toBe("0");
    expect(callouts({ onZparamAxisChange: () => {} })).toBe("1");
    expect(callouts({ onZparamAxisChange: () => {}, zparam: { ...zp, callouts: false } })).toBe("0");
  });

  it("keys the Smith locus on refinement enabled AND settled (issue #866)", () => {
    const connect = (settled: boolean, o: Partial<React.ComponentProps<typeof ViewPanel>>) =>
      chartOn({ settled }, o).querySelector("canvas.smith")!.getAttribute("data-connect");
    // Refinement disabled (or omitted, the thumbnail case): dot cloud.
    expect(connect(true, {})).toBe("0");
    expect(connect(true, { refineEnabled: false })).toBe("0");
    // Enabled + settled: the connected locus.
    expect(connect(true, { refineEnabled: true })).toBe("1");
    // Enabled but still refining: dots.
    expect(connect(false, { refineEnabled: true })).toBe("0");
    expect(connect(false, { refineEnabled: false })).toBe("0");
  });

  for (const [view, mode] of [["S11", "gamma"], ["Swr", "vswr"]] as const) {
    it(`passes settledness through to the ${view} view (issue #866)`, () => {
      const settledAttr = (settled: boolean) =>
        chartOn({ view, settled }).querySelector(`canvas.sweep[data-mode="${mode}"]`)!.getAttribute("data-settled");
      expect(settledAttr(true)).toBe("1");
      expect(settledAttr(false)).toBe("0");
    });
  }

  // Unit 2's follow-up: a stale curve dimmed the whole canvas, live marker
  // included. The chart hands `stale` to the chart component, which dims
  // the trace alone; nothing dims the canvas element.
  for (const view of ["Smith", "Swr", "S11"] as const) {
    it(`marks only the ${view} view's trace stale, not the canvas`, () => {
      const c = chartOn({ view, stale: true });
      const canvas = c.querySelector("canvas") as HTMLCanvasElement;
      expect(canvas.dataset.stale).toBe("1");
      expect(c.querySelector(".is-stale")).toBeNull();
      expect(chartOn({ view }).querySelector("canvas")!.getAttribute("data-stale")).toBe("0");
    });
  }

  // AK#1730: the combined view is an alternative, so nobody's rail moves —
  // it is off by default (the founding-four test above pins that too) — and
  // its fill reaches the chart, defaulting to none where a call site omits it.
  it("ships the combined view unpinned, with its fill passed through", () => {
    expect(VIEW_META.combined.defaultPinned).toBe(false);
    const fillOf = (o: Partial<React.ComponentProps<typeof ViewPanel>>) =>
      mount("combined", o).querySelector(MARKERS.combined)!.getAttribute("data-fill");
    expect(fillOf({})).toBe("none");
    expect(fillOf({ combinedFill: "elevation" })).toBe("elevation");
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

  it("passes the files view its own props (AK#1428)", () => {
    const files: FilesViewData = {
      geometry: "g",
      engine: null,
      solved: true,
      ssn: null,
      source: {
        available: true,
        geometry: "g",
        filename: "g.py",
        language: "python",
        text: "SOURCE TEXT",
      },
      engineIo: null,
      stale: false,
    };
    const stage = mount("files", { files });
    expect(stage.querySelector("pre.files-text")?.textContent).toBe("SOURCE TEXT");
    // The rail's thumbnail call site passes no texts, so it draws a label.
    const thumb = mount("files", { fill: false, size: 96 });
    expect(thumb.querySelector(".files-thumb")).not.toBeNull();
    expect(thumb.textContent).not.toContain("SOURCE TEXT");
  });
});
