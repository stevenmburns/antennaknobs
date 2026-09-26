// AK#1542: the Antenna view keeps its zoom and position when you leave the
// rail view and come back. The stage renders ONE view and unmounts the rest,
// so the canvas's own zoom/pan state died with the component: every return to
// the antenna was a fresh fit, after the work of finding the detail. The
// session lends the canvas a camera that outlives the mount instead.
//
// Switching rail views IS unmount/remount here — that is the whole mechanism,
// and mounting the panel twice around the same camera reproduces it without
// standing up a session.
import { describe, it, expect, beforeEach, afterEach } from "vitest";
import { fireEvent, render } from "@testing-library/react";
import { useState } from "react";
import { ViewPanel } from "../components/results/ViewPanel";
import type { ViewRenderProps } from "../components/results/viewRegistry";
import { fitCamera, type CanvasCamera } from "../lib/view";

// The canvas binds its wheel/pointer handlers only once it has a 2-D context,
// which jsdom does not give it (setup.ts returns null by default). Nothing
// here reads what was drawn, so every call is a no-op.
const stubContext = () =>
  new Proxy(
    {},
    {
      get: (_t, prop) =>
        prop === "measureText" ? () => ({ width: 0 }) : () => undefined,
      set: () => true,
    },
  ) as unknown as CanvasRenderingContext2D;

const realGetContext = HTMLCanvasElement.prototype.getContext;

beforeEach(() => {
  HTMLCanvasElement.prototype.getContext =
    (() => stubContext()) as unknown as HTMLCanvasElement["getContext"];
});
afterEach(() => {
  HTMLCanvasElement.prototype.getContext = realGetContext;
});

const PROPS = {
  size: 480,
  fill: true,
  result: null,
  liveZ: null,
  preview: null,
  sweep: null,
  paramSweep: null,
  measured: null,
  pattern: null,
  pinnedPatterns: [],
  measFreqMhz: 14.1,
  sweepRunning: false,
  paramSweepRunning: false,
  azElevDeg: 0,
  elevAzDeg: 0,
  cameraProjection: "xy",
  showHeatmap: false,
  showEnvelope: false,
  showWireLabels: false,
  showFeedNames: false,
  multiFeed: false,
  fineNorm: null,
  schematicSvg: null,
  schematicUnavailable: false,
} as unknown as ViewRenderProps;

/** The rail with the antenna view on the stage, or with it swapped out. */
function Stage({
  showing,
  camera,
}: {
  showing: "antenna" | "smith";
  camera?: CanvasCamera;
}) {
  return <ViewPanel view={showing} {...PROPS} canvasCamera={camera} />;
}

/** Wheel the canvas in, as a scroll gesture over it does. */
function zoomIn(container: HTMLElement) {
  const canvas = container.querySelector("canvas") as HTMLCanvasElement;
  fireEvent.wheel(canvas, { deltaY: -500, clientX: 0, clientY: 0 });
}

const zoomChip = (c: HTMLElement) =>
  c.querySelector(".viewport-zoom")?.textContent ?? null;

describe("the antenna camera survives a rail view switch", () => {
  it("comes back at the zoom it was left at", () => {
    const camera = fitCamera();
    const utils = render(<Stage showing="antenna" camera={camera} />);
    expect(zoomChip(utils.container)).toBeNull(); // at fit, no chip

    zoomIn(utils.container);
    const zoomed = zoomChip(utils.container);
    expect(zoomed).not.toBeNull();
    expect(camera.zoom).toBeGreaterThan(1);

    // Look at something else: the antenna canvas is unmounted.
    utils.rerender(<Stage showing="smith" camera={camera} />);
    expect(utils.container.querySelector(".canvas-viewport")).toBeNull();

    // ...and come back.
    utils.rerender(<Stage showing="antenna" camera={camera} />);
    expect(zoomChip(utils.container)).toBe(zoomed);
    expect(utils.container.querySelector<HTMLButtonElement>(".viewport-fit")!.disabled)
      .toBe(false);
  });

  it("without a camera of the session's, a remount re-fits — the defect", () => {
    // The same sequence with the canvas keeping its own camera: this is what
    // every return to the view used to do, and what a thumbnail still does.
    const { container, rerender } = render(<Stage showing="antenna" />);
    zoomIn(container);
    expect(zoomChip(container)).not.toBeNull();
    rerender(<Stage showing="smith" />);
    rerender(<Stage showing="antenna" />);
    expect(zoomChip(container)).toBeNull();
  });

  it("is one camera for the session, made once and kept", () => {
    // useViewState makes it once, with a setter-less useState. A camera
    // rebuilt on each render would be no camera at all.
    const seen: CanvasCamera[] = [];
    function Probe() {
      const [camera] = useState<CanvasCamera>(fitCamera);
      seen.push(camera);
      return <Stage showing="antenna" camera={camera} />;
    }
    const { container, rerender } = render(<Probe />);
    zoomIn(container);
    rerender(<Probe />);
    expect(seen.length).toBeGreaterThan(1);
    expect(seen[1]).toBe(seen[0]);
    expect(zoomChip(container)).not.toBeNull();
  });

  it("re-fits when the DESIGN changes, camera or no camera", () => {
    // The camera is a place to look from, not a promise to keep looking
    // there: the old framing means nothing for new wires.
    const camera = fitCamera();
    // Enough of a solve for the canvas to take its draw path: which design
    // it is, and no wires to frame.
    const design = (geometry: string) => ({
      ...PROPS,
      result: {
        geometry,
        wires: [],
        lambda_design_m: 20,
      } as unknown as ViewRenderProps["result"],
    });
    const { container, rerender } = render(
      <ViewPanel view="antenna" {...design("dipoles.invvee")} canvasCamera={camera} />,
    );
    zoomIn(container);
    expect(camera.zoom).toBeGreaterThan(1);

    rerender(
      <ViewPanel view="antenna" {...design("yagis.yagi3")} canvasCamera={camera} />,
    );
    expect(camera.zoom).toBe(1);
    expect(zoomChip(container)).toBeNull();
  });
});
