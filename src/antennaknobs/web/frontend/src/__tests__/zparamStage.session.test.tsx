// The Z-vs-parameter view's overlays, pinned to the chart (AC6LA, QRZ #166):
// the sweep bar above the plot at its upper-left, the solve readout inside
// the plot at its lower-left, both anchored to the chart's own box rather
// than to the slide's corners, so window size and browser zoom cannot move
// them onto the axis labels. jsdom has no layout, so this pins the STRUCTURE
// and the CSS contract; the geometry was measured in a real browser at
// 1280×800 / 1920×1080 / 1100×950 and at 80 % / 125 % zoom (see the PR).
import { describe, it, expect, afterEach, vi } from "vitest";
import { fireEvent, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { HARNESS_EXAMPLE, mountReady, untilDom } from "./designSessionHarness";
import type { ExampleDescriptor, SchemaParamSpec } from "../lib/params";
import { ZPARAM_HEAD_GAP, ZPARAM_PLOT_MARGIN, zparamChartSize } from "../lib/zparamLayout";
import stylesSrc from "../styles.css?raw";

vi.setConfig({ testTimeout: 15_000 });

describe("the chart's size under the sweep bar", () => {
  it("takes the bar's measured height off a short box, never the width bound", () => {
    // Box 800 tall, bar 60: 800 − 16 − 60 − gap.
    expect(zparamChartSize(720, 800, 60, 96)).toBe(800 - 16 - 60 - ZPARAM_HEAD_GAP);
    // A tall box: the width bound (the caller's square) wins.
    expect(zparamChartSize(500, 1400, 60, 96)).toBe(500);
    // Unmeasured (the first frame, or jsdom): the caller's size less the
    // fallback reserve.
    expect(zparamChartSize(600, 0, 0, 60)).toBe(540);
    // Never below the floor, however tall the bar wraps.
    expect(zparamChartSize(600, 300, 400, 60)).toBe(160);
  });
});

describe("the stylesheet anchors the readout inside the plot's axes", () => {
  const rule = (sel: string) => {
    const m = [...stylesSrc.matchAll(/([^{}]+)\{([^{}]*)\}/g)].find(
      (r) => r[1].replace(/\/\*[\s\S]*?\*\//g, "").trim() === sel,
    );
    return m ? m[2] : "";
  };
  it("left and bottom come from the chart's own margins, not the slide", () => {
    const body = rule(".zparam-plot .stage-readout");
    expect(body).toMatch(/left:\s*calc\(var\(--zparam-plot-l\)/);
    expect(body).toMatch(/bottom:\s*calc\(var\(--zparam-plot-b\)/);
  });
  it("the sweep's notes stack above it there", () => {
    const body = rule(".zparam-plot .sweep-advisory-overlay");
    expect(body).toMatch(/var\(--zparam-plot-l\)/);
    expect(body).toMatch(/var\(--stage-readout-h/);
  });
  it("the bar is in the flow above the chart, not floating at a corner", () => {
    expect(rule(".zparam-area .zparam-overlay")).toMatch(/position:\s*static/);
    expect(rule(".zparam-area")).toMatch(/flex-direction:\s*column/);
    expect(rule(".zparam-plot")).toMatch(/position:\s*relative/);
  });
});

const knob = (over: Partial<SchemaParamSpec>): SchemaParamSpec => ({
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
  ...over,
});

const EXAMPLE: ExampleDescriptor = { ...HARNESS_EXAMPLE, param_schema: [knob({})] };

afterEach(() => {
  vi.unstubAllGlobals();
});

describe("on the rail's stage", () => {
  it("the bar heads the chart and the readout sits inside its plot, once", async () => {
    const user = userEvent.setup();
    const { container } = await mountReady({
      examples: [EXAMPLE],
      pinned: ["antenna", "zparam"],
    });
    const slide = () => container.querySelector(".carousel-slide") as HTMLElement;
    // On the antenna view the readout is the slide's own, as before.
    expect(slide().querySelector(":scope > .stage-readout")).not.toBeNull();

    fireEvent.contextMenu(screen.getByRole("slider", { name: "Gap" }));
    await user.click(screen.getByRole("button", { name: "Sweep this knob…" }));
    await untilDom(() => slide().querySelector(".zparam-area") !== null);

    const area = slide().querySelector(".zparam-area") as HTMLElement;
    const [head, plot] = [...area.children] as HTMLElement[];
    // The bar first, in its own row above the plot.
    expect(head.className).toBe("zparam-head");
    expect(head.querySelector('[role="group"][aria-label="Parameter sweep"]')).not.toBeNull();
    // The plot box holds the chart and the readout, and publishes the
    // chart's margins for the readout's offsets.
    expect(plot.className).toBe("zparam-plot");
    expect(plot.querySelector("canvas.zparam")).not.toBeNull();
    expect(plot.querySelector(".stage-readout")).not.toBeNull();
    expect(plot.style.getPropertyValue("--zparam-plot-l")).toBe(`${ZPARAM_PLOT_MARGIN.l}px`);
    expect(plot.style.getPropertyValue("--zparam-plot-b")).toBe(`${ZPARAM_PLOT_MARGIN.b}px`);
    // One readout, moved, not duplicated; the slide no longer floats one.
    expect(container.querySelectorAll(".stage-readout")).toHaveLength(1);
    expect(slide().querySelector(":scope > .stage-readout")).toBeNull();
    // Its height is published on the plot box, where the notes stack on it.
    expect(plot.style.getPropertyValue("--stage-readout-h")).not.toBe("");

    // Back to the antenna view: the readout returns to the slide.
    await user.click(screen.getByTitle("Switch to Antenna"));
    await untilDom(() => slide().querySelector(".zparam-area") === null);
    expect(slide().querySelector(":scope > .stage-readout")).not.toBeNull();
    expect(container.querySelectorAll(".stage-readout")).toHaveLength(1);
  });
});
