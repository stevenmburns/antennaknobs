// The Smith chart's dot must follow a streamed optimizer run (issue #773).
//
// Reported from live use: the readout chip ticked toward SWR 1 while the dot
// sat still until the run ended. The cause is structural, not a rendering
// bug — an optimizer run never touches the knobs until it finishes, so the
// /ws solve channel produces nothing and `result` holds the PRE-RUN solve for
// the whole run. The per-eval frames carry the trial Z; `liveZ` is how it
// reaches the chart.
//
// These tests drive the registry entry rather than the hook, because the
// defect lived in which source the chart reads, not in how frames arrive.
import { render } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import { VIEW_RENDERERS, type ViewRenderProps } from "../components/results/viewRegistry";
import type { SolveResponse } from "../lib/api";

// The chart draws to a canvas, so assert on the props it receives rather than
// on pixels: what is under test is the SOURCE the dot comes from.
const smithSpy = vi.hoisted(() => vi.fn());
vi.mock("../components/charts/SmithChart", () => ({
  SmithChart: (props: Record<string, unknown>) => {
    smithSpy(props);
    return <div data-testid="smith" />;
  },
}));

const SETTLED = {
  z_in_re: 22.0,
  z_in_im: -18.0,
  z0_ohms: 50,
  feeds: [{ z_re: 22.0, z_im: -18.0 }],
} as unknown as SolveResponse;

const TRIAL = { z_in_re: 49.4, z_in_im: 1.2, z0_ohms: 50 };

function renderSmith(over: Partial<ViewRenderProps>) {
  smithSpy.mockClear();
  const props = {
    size: 300,
    fill: true,
    result: null,
    liveZ: null,
    preview: null,
    sweep: null,
    converge: null,
    measured: null,
    pattern: null,
    pinnedPatterns: [],
    measFreqMhz: 28.5,
    sweepRunning: false,
    convergeRunning: false,
    azElevDeg: 0,
    elevAzDeg: 0,
    cameraProjection: "xy",
    showHeatmap: false,
    showEnvelope: false,
    showWireLabels: false,
    showFeedNames: false,
    multiFeed: false,
    schematicSvg: null,
    schematicUnavailable: false,
    ...over,
  } as unknown as ViewRenderProps;
  render(VIEW_RENDERERS.smith(props));
  return smithSpy.mock.calls[0][0] as Record<string, unknown>;
}

describe("Smith chart during a streamed optimizer run", () => {
  it("plots the settled solve when nothing is being tried", () => {
    const p = renderSmith({ result: SETTLED });
    expect(p.r).toBe(22.0);
    expect(p.x).toBe(-18.0);
    expect(p.trial).toBe(false);
  });

  it("plots the trial impedance instead, while a run is in flight", () => {
    // The regression: with `liveZ` ignored these would still be the settled
    // 22 − j18, which is exactly the frozen dot that was reported.
    const p = renderSmith({ result: SETTLED, liveZ: TRIAL });
    expect(p.r).toBe(49.4);
    expect(p.x).toBe(1.2);
    expect(p.trial).toBe(true);
  });

  it("keeps a reference impedance when the trial frame carries one", () => {
    // z0 must come from the same place as the point, or a design on a
    // non-50 Ω reference would plot its trial dot against the wrong circles.
    const p = renderSmith({ result: SETTLED, liveZ: { ...TRIAL, z0_ohms: 200 } });
    expect(p.z0).toBe(200);
  });

  it("falls back to the settled solve's reference when there is no trial", () => {
    const p = renderSmith({ result: { ...SETTLED, z0_ohms: 75 } as SolveResponse });
    expect(p.z0).toBe(75);
  });
});
