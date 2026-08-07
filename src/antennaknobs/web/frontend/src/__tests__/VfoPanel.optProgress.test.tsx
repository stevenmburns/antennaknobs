// The live optimizer progress readout (issue #773 unit 4) as rendered DOM,
// not just hook state — useOptimizer.streaming.test.tsx pins the state
// transitions; this pins that optRunning/optProgress actually reach the
// screen, and that the settled optResult readout takes over once a run ends.
import { describe, it, expect, vi } from "vitest";
import { render, screen } from "@testing-library/react";
import { VfoPanel } from "../components/session/VfoPanel";
import type { OptimizeResult, OptProgress } from "../components/session/VfoPanel";

const METRICS = { z_in_re: 48.2, z_in_im: -3.1, z0_ohms: 50.0, swr: 1.12 };

const PROGRESS: OptProgress = {
  n_evals: 7,
  params: { length_factor: 0.981 },
  objective: 1.34,
  metrics: METRICS,
};

const RESULT: OptimizeResult = {
  objective: "swr",
  params: { length_factor: 0.99 },
  objective_before: 2.0,
  objective_after: 1.05,
  metrics_before: METRICS,
  metrics_after: { ...METRICS, swr: 1.05 },
  n_evals: 12,
  improved: true,
};

function baseProps() {
  return {
    currentBands: [],
    measLocked: false,
    measFreq: 14.1,
    bandContaining: () => null,
    measBand: "",
    selectMeasBand: vi.fn(),
    currentExample: undefined,
    measBandAnchor: 14.1,
    freqWindowCeiling: 30,
    setMeasFreq: vi.fn(),
    measLockable: false,
    linkMeas: false,
    toggleLink: vi.fn(),
    autoSim: true,
    setAutoSim: vi.fn(),
    optEnabled: true,
    setOptEnabled: vi.fn(),
    setOptPausedBy: vi.fn(),
    optObjective: "swr" as const,
    setOptObjective: vi.fn(),
    optError: null,
    optPausedBy: null,
  };
}

describe("VfoPanel live optimizer readout (#773 unit 4)", () => {
  it("shows the live eval count and SWR while a run is in flight", () => {
    render(
      <VfoPanel
        {...baseProps()}
        optRunning
        optResult={null}
        optProgress={PROGRESS}
      />,
    );
    expect(screen.getByText("#7 SWR 1.12")).toBeTruthy();
  });

  it("shows nothing extra before the first progress frame lands", () => {
    render(
      <VfoPanel {...baseProps()} optRunning optResult={null} optProgress={null} />,
    );
    expect(screen.queryByText(/SWR/)).toBeNull();
  });

  it("switches to the settled result readout once the run ends", () => {
    render(
      <VfoPanel
        {...baseProps()}
        optRunning={false}
        optResult={RESULT}
        optProgress={PROGRESS}
      />,
    );
    // The final metrics_after figure, not the last-seen progress frame.
    expect(screen.getByText("SWR 1.05")).toBeTruthy();
    expect(screen.queryByText("#7 SWR 1.12")).toBeNull();
  });
});
