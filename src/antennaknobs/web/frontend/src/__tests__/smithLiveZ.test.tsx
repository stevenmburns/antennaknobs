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

// Issue #789: on a multi-feed design the trial frame carries the whole port
// table, not just feed 0. `z_in_re`/`z_in_im` remain feed 0 — so a chart
// reading only those describes one element of an array whose OTHER element is
// the one the minimax objective is driving.
describe("the trial point's per-feed table reaches the chart", () => {
  const MULTI = {
    z_in_re: 50.0,
    z_in_im: 0.0,
    z0_ohms: 50,
    worst_feed: 1,
    n_feeds: 2,
    feeds: [
      { z_re: 50.0, z_im: 0.0 },
      { z_re: 91.0, z_im: -34.0 },
    ],
  };

  it("passes the trial feeds and the worst-feed index through", () => {
    const p = renderSmith({ result: SETTLED, liveZ: MULTI, multiFeed: true });
    expect(p.trial).toBe(true);
    expect(p.trialFeeds).toEqual(MULTI.feeds);
    expect(p.trialWorstFeed).toBe(1);
    // r/x still carry feed 0, unchanged — the chart's fallback for a
    // proposer with no table, and the readout the rest of the UI shows.
    expect(p.r).toBe(50.0);
  });

  it("keeps the settled feeds separate from the trial ones", () => {
    // Both props are populated during a run and they disagree on purpose:
    // `feeds` is the pre-run solve, `trialFeeds` is this eval.
    const p = renderSmith({ result: SETTLED, liveZ: MULTI, multiFeed: true });
    expect(p.feeds).toEqual(SETTLED.feeds);
    expect(p.trialFeeds).not.toEqual(p.feeds);
  });

  it("sends no trial table for a single-feed run", () => {
    // The single-feed payload omits `feeds`/`worst_feed` entirely (pinned
    // server-side as byte-compatible), so both props must arrive undefined
    // rather than as an empty array the chart would have to special-case.
    const p = renderSmith({ result: SETTLED, liveZ: TRIAL });
    expect(p.trialFeeds).toBeUndefined();
    expect(p.trialWorstFeed).toBeUndefined();
  });

  it("stops feeding the chart a trial table once the run ends", () => {
    const p = renderSmith({ result: SETTLED, liveZ: null });
    expect(p.trial).toBe(false);
    expect(p.trialFeeds).toBeUndefined();
  });
});
