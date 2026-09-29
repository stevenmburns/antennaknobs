// Steve's phone (2026-09-29), three findings on the analysis chart:
//   1. the y axis's range popover did not appear: it now opens in a portal on
//      <body>, clamped to the part of the page that is visible (the visual
//      viewport: a pinch-zoomed phone shows a window inside the layout
//      viewport that position:fixed is measured in), inside a 390 × 844
//      viewport from a tap at either edge; a desktop click still opens it at
//      the click;
//   2. a long chart note (the convergence pick's) took lines from the plot:
//      a note is now one line under the controls, the line that is there
//      note or none, and opens as a panel laid over the chart;
//   3. the knob sweep's end-value boxes covered a phone's plot: they start
//      off on a phone (on on a desktop, as before), and the chart's one
//      "values" toggle flips them, for the session only.
//
// Mutation notes (run by hand, 2026-09-29):
//   - the portal removed (popover back inside the chart): "portals to body"
//     fails on both the SWR and the R/X popovers;
//   - the clamp ignoring the visual viewport's offset: the pinch-zoom unit
//     test fails;
//   - the open note put back in the flow (its CSS position static): the
//     stylesheet test fails;
//   - the callouts' phone default dropped (on everywhere): the phone test
//     fails; the desktop one passes, as it should.
import { describe, it, expect, afterEach, beforeEach, vi } from "vitest";
import css from "../styles.css?raw";
import { fireEvent, render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { clampToViewport } from "../components/charts/useInViewport";
import { AnalysisDetails } from "../components/results/AnalysisPicker";
import type { ExampleDescriptor } from "../lib/params";
import { HARNESS_EXAMPLE, mountReady, untilDom } from "./designSessionHarness";

vi.setConfig({ testTimeout: 20_000 });

const PHONE = { width: 390, height: 844 };
const BOX = { width: 294, height: 151 }; // the SWR popover as a phone draws it

const within = (p: { left: number; top: number }, size = BOX, vp = PHONE) =>
  p.left >= 0 && p.top >= 0 && p.left + size.width <= vp.width && p.top + size.height <= vp.height;

describe("the axis popover's placement (unit)", () => {
  it("stays inside a 390 × 844 viewport from a tap at the right, the left or the bottom", () => {
    for (const at of [
      { x: 380, y: 600 },
      { x: 4, y: 600 },
      { x: 200, y: 840 },
      { x: 385, y: 830 },
    ]) {
      for (const side of ["right", "left"] as const) {
        const p = clampToViewport(at, BOX, PHONE, side);
        expect(within(p), JSON.stringify({ at, side, p })).toBe(true);
      }
    }
  });

  it("on a pinch-zoomed phone, stays inside the visible window, not the layout viewport", () => {
    // Zoomed 2× into the lower right: 195 × 422 visible, from (180, 400).
    const vis = { left: 180, top: 400, width: 195, height: 422 };
    const box = { width: 180, height: 151 };
    const p = clampToViewport({ x: 300, y: 700 }, box, vis);
    expect(p.left).toBeGreaterThanOrEqual(vis.left);
    expect(p.top).toBeGreaterThanOrEqual(vis.top);
    expect(p.left + box.width).toBeLessThanOrEqual(vis.left + vis.width);
    expect(p.top + box.height).toBeLessThanOrEqual(vis.top + vis.height);
  });

  it("on a desktop, opens at the click as before", () => {
    expect(clampToViewport({ x: 200, y: 300 }, BOX, { width: 1280, height: 800 })).toEqual({
      left: 200,
      top: 300,
    });
    // Leftward from a right-hand axis: its right edge at the click.
    expect(
      clampToViewport({ x: 900, y: 300 }, BOX, { width: 1280, height: 800 }, "left"),
    ).toEqual({ left: 900 - BOX.width, top: 300 });
  });
});

const DESIGN: ExampleDescriptor = {
  ...HARNESS_EXAMPLE,
  param_schema: [
    {
      name: "gap",
      label: "Gap",
      default: 0.25,
      kind: "float",
      min: 0,
      max: 1,
      step: 0.05,
      precision: 2,
      unit: null,
      visible_when: null,
    },
  ],
};

function ndjson(lines: string[]): Response {
  const chunks = [new TextEncoder().encode(lines.join("\n") + "\n")];
  return {
    ok: true,
    status: 200,
    body: {
      getReader: () => ({
        read: async () =>
          chunks.length > 0 ? { done: false, value: chunks.shift() } : { done: true, value: undefined },
      }),
    },
  } as unknown as Response;
}

const ROUTES = {
  "/param_sweep": (_url: string, init?: RequestInit) => {
    const b = JSON.parse(String(init?.body ?? "{}")) as { param: string; values: number[] };
    const lines = b.values.map((v) =>
      JSON.stringify({ param: b.param, value: v, z_re: 60 + 20 * v, z_im: -30 + 60 * v, solver: "momwire" }),
    );
    lines.push(JSON.stringify({ done: true, solver: "momwire" }));
    return ndjson(lines);
  },
};

// jsdom lays nothing out: the popover measures as the size a phone draws it.
const realRect = HTMLElement.prototype.getBoundingClientRect;
beforeEach(() => {
  HTMLElement.prototype.getBoundingClientRect = function (this: HTMLElement) {
    if (this.classList.contains("sweep-axis-menu")) {
      return { ...BOX, x: 0, y: 0, left: 0, top: 0, right: BOX.width, bottom: BOX.height, toJSON() {} } as DOMRect;
    }
    return realRect.call(this);
  };
});
afterEach(() => {
  HTMLElement.prototype.getBoundingClientRect = realRect;
  vi.unstubAllGlobals();
});

function phoneViewport() {
  vi.stubGlobal("innerWidth", PHONE.width);
  vi.stubGlobal("innerHeight", PHONE.height);
}
const placed = (el: HTMLElement) => ({
  left: parseFloat(el.style.left),
  top: parseFloat(el.style.top),
});

describe("the axis popover on a phone (session)", () => {
  it("SWR: portals to body and opens inside the viewport from a tap at the right edge", async () => {
    phoneViewport();
    const { container } = await mountReady({ mobile: true, pinned: ["vswr", "antenna"] });
    const btn = await untilDom(() => container.querySelector<HTMLElement>(".sweep-axis-btn"));
    fireEvent.click(btn, { clientX: 380, clientY: 800 });
    const menu = screen.getByRole("dialog", { name: "VSWR range" });
    expect(menu.parentElement).toBe(document.body);
    expect(container.contains(menu)).toBe(false);
    expect(within(placed(menu))).toBe(true);
    // The backdrop closes it, as before.
    fireEvent.click(document.body.querySelector(".knob-menu-backdrop") as HTMLElement);
    expect(screen.queryByRole("dialog", { name: "VSWR range" })).toBeNull();
  });

  it("R/X: the X axis's popover (opening leftward) portals and stays inside from the left edge", async () => {
    phoneViewport();
    await mountReady({ mobile: true, examples: [DESIGN], pinned: ["zparam", "antenna"], routes: ROUTES });
    fireEvent.contextMenu(screen.getByRole("slider", { name: "Gap" }));
    fireEvent.click(screen.getByRole("button", { name: "Sweep this knob…" }));
    const x = await untilDom(() => screen.queryByRole("button", { name: "X range" }));
    fireEvent.click(x, { clientX: 6, clientY: 820 });
    const menu = screen.getByRole("dialog", { name: "X range" });
    expect(menu.parentElement).toBe(document.body);
    expect(within(placed(menu))).toBe(true);
  });

  it("on a desktop, the popover still opens at the click", async () => {
    vi.stubGlobal("innerWidth", 1280);
    vi.stubGlobal("innerHeight", 800);
    const { container } = await mountReady({ pinned: ["vswr", "antenna"] });
    fireEvent.click(container.querySelector(".thumbstrip canvas.sweep") as HTMLElement);
    const btn = await untilDom(() =>
      [...container.querySelectorAll<HTMLElement>(".sweep-axis-btn")].find((b) => !b.closest(".thumbstrip")) ?? null,
    );
    fireEvent.click(btn, { clientX: 200, clientY: 300 });
    const menu = screen.getByRole("dialog", { name: "VSWR range" });
    // SweepChart anchors 8 px right of and above the click (unchanged).
    expect(placed(menu)).toEqual({ left: 208, top: 292 });
  });
});

const LONG =
  "crossed over engines: the workbench draws this session's engine; `antennaknobs analyze` draws all 3; the analysis names ground finite:13,0.005; the workbench uses this session's ground";

describe("a chart note never sizes the plot", () => {
  // The layout contract, as the stylesheet states it: the note line is one
  // line (nowrap, ellipsized), it is there note or none (min-height), and the
  // open note is laid over the chart (absolute), out of the header's flow.
  const rule = (sel: string) => {
    const at = css.indexOf(`${sel} {`);
    expect(at, sel).toBeGreaterThanOrEqual(0);
    return css.slice(at, css.indexOf("}", at));
  };

  it("the stylesheet: one fixed line, and the open note out of the flow", () => {
    expect(rule(".zparam-analysis-extra")).toMatch(/min-height:/);
    expect(rule(".zparam-analysis-extra")).toMatch(/position: relative/);
    expect(rule(".chart-note-btn")).toMatch(/white-space: nowrap/);
    expect(rule(".chart-note-btn")).toMatch(/text-overflow: ellipsis/);
    expect(rule(".chart-note-pop")).toMatch(/position: absolute/);
  });

  it("with a note or without, the header holds the same rows; the note opens only on a tap", async () => {
    const user = userEvent.setup();
    const shape = (root: HTMLElement) =>
      [...root.querySelectorAll(":scope > div > *")].map((e) => `${e.tagName}.${e.className}`);
    const without = render(<AnalysisDetails entries={[]} notes={[]} blocked={() => null} />);
    const withNote = render(<AnalysisDetails entries={[]} notes={[LONG]} blocked={() => null} />);
    // One line in both, and the note shut: nothing but its button in the line.
    expect(without.container.querySelectorAll(".zparam-analysis-extra")).toHaveLength(1);
    expect(shape(withNote.container)).toEqual(["BUTTON.chart-note-btn"]);
    expect(withNote.container.querySelector(".chart-note-pop")).toBeNull();
    await user.click(screen.getByRole("button", { name: "Show the chart's note" }));
    const pop = screen.getByRole("note", { name: "Chart note" });
    expect(pop.textContent).toBe(LONG);
    expect(pop.className).toBe("chart-note-pop");
    await user.click(screen.getByRole("button", { name: "Hide the chart's note" }));
    expect(screen.queryByRole("note", { name: "Chart note" })).toBeNull();
  });
});

describe("the knob sweep's end-value callouts", () => {
  it("start collapsed on a phone; the chart's values toggle expands them; nothing is stored", async () => {
    const user = userEvent.setup();
    await mountReady({ mobile: true, examples: [DESIGN], pinned: ["zparam", "antenna"], routes: ROUTES });
    const stored = JSON.stringify({ ...localStorage });
    fireEvent.contextMenu(screen.getByRole("slider", { name: "Gap" }));
    await user.click(screen.getByRole("button", { name: "Sweep this knob…" }));
    const chart = () => document.querySelector<HTMLElement>(".mobile-screen canvas.zparam")!;
    await untilDom(() => chart()?.dataset.points === "11" || null);
    expect(chart().dataset.callouts).toBe("0");
    const toggle = screen.getByRole("button", { name: "Show the end values" });
    expect(toggle.getAttribute("aria-pressed")).toBe("false");
    await user.click(toggle);
    expect(chart().dataset.callouts).toBe("1");
    expect(screen.getByRole("button", { name: "Hide the end values" }).getAttribute("aria-pressed")).toBe("true");
    expect(JSON.stringify({ ...localStorage })).toBe(stored);
  });

  it("on a desktop, are drawn as before, the toggle on", async () => {
    const { container } = await mountReady({ examples: [DESIGN], pinned: ["zparam", "antenna"], routes: ROUTES });
    fireEvent.contextMenu(screen.getByRole("slider", { name: "Gap" }));
    fireEvent.click(screen.getByRole("button", { name: "Sweep this knob…" }));
    const chart = () =>
      [...container.querySelectorAll<HTMLElement>("canvas.zparam")].find((c) => !c.closest(".thumbstrip"));
    await untilDom(() => chart()?.dataset.points === "11" || null);
    expect(chart()!.dataset.callouts).toBe("1");
    expect(screen.getByRole("button", { name: "Hide the end values" })).toBeTruthy();
  });
});
