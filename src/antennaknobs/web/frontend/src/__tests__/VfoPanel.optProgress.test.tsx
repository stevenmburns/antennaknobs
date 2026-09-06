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
    optSeed: false,
    setOptSeed: vi.fn(),
    trackEnabled: false,
    setTrackEnabled: vi.fn(),
    trackRefusal: null,
    trackLatched: null,
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

describe("the seeding phase reads as a phase, not as going backwards (#1176)", () => {
  // The seed samples the WHOLE box, so its objective jumps around. Rendered
  // as "#7 SWR 4.81" that looks like the optimiser losing ground; naming the
  // phase is what stops a working run reading as a fault.
  const seedFrame = (
    seed_index: number,
    seed_total: number,
  ): OptProgress => ({
    n_evals: 4,
    params: { length_factor: 0.9 },
    objective: 4.81,
    metrics: { z_in_re: 12, z_in_im: -80, z0_ohms: 50, swr: 4.81 },
    seed_index,
    seed_total,
  });

  it("shows 'seeding k/N' while the seed is running", () => {
    render(
      <VfoPanel
        {...baseProps()}
        optRunning
        optResult={null}
        optProgress={seedFrame(3, 6)}
      />,
    );
    expect(screen.getByText("seeding 3/6")).toBeTruthy();
    expect(screen.queryByText(/SWR 4\.81/)).toBeNull();
  });

  it("shows the ordinary eval readout once the seed is done", () => {
    // seed_total 0 is the "not seeding" state, so there is no phase machine
    // on the client — one comparison.
    const after: OptProgress = {
      n_evals: 12,
      params: { length_factor: 0.99 },
      objective: 1.2,
      metrics: { z_in_re: 45, z_in_im: 5, z0_ohms: 50, swr: 1.2 },
      seed_index: 0,
      seed_total: 0,
    };
    render(
      <VfoPanel
        {...baseProps()}
        optRunning
        optResult={null}
        optProgress={after}
      />,
    );
    expect(screen.getByText("#12 SWR 1.20")).toBeTruthy();
    expect(screen.queryByText(/seeding/)).toBeNull();
  });

  it("falls back to the eval readout when the server sends no seed fields", () => {
    // An older server, or a cached frame from before #1176. Without the
    // nullish guards this renders "seeding undefined/undefined".
    const legacy: OptProgress = {
      n_evals: 5,
      params: { length_factor: 0.98 },
      objective: 1.5,
      metrics: { z_in_re: 40, z_in_im: 10, z0_ohms: 50, swr: 1.5 },
    };
    render(
      <VfoPanel
        {...baseProps()}
        optRunning
        optResult={null}
        optProgress={legacy}
      />,
    );
    expect(screen.getByText("#5 SWR 1.50")).toBeTruthy();
  });
});

describe("a root-finder shows its residual, not the SWR (#1202)", () => {
  // The point of the root-finding paths is that the residual falls
  // MONOTONICALLY. Showing it is what makes a 4-solve run legible; showing
  // Nelder-Mead's best-so-far instead would be the #1176 seeding problem
  // again, so the phase gates which of the two the readout picks.
  const frame = (over: Partial<OptProgress>): OptProgress => ({
    n_evals: 4,
    params: { length_factor: 0.97 },
    objective: 3.2,
    metrics: { z_in_re: 48.0, z_in_im: -3.2, z0_ohms: 50, swr: 1.07 },
    ...over,
  });

  function show(p: OptProgress, objective: "swr" | "resonance" | "match_z0") {
    render(
      <VfoPanel
        {...baseProps()}
        optObjective={objective}
        optRunning
        optResult={null}
        optProgress={p}
      />,
    );
  }

  it("names |X| on a resonance secant step", () => {
    show(frame({ phase: "secant", residual: 3.2 }), "resonance");
    expect(screen.getByText("#4 |X| 3.20 Ω")).toBeTruthy();
    expect(screen.queryByText(/SWR/)).toBeNull();
  });

  it("names |Z−Z₀| on a match_z0 root step", () => {
    show(frame({ phase: "newton", residual: 3.2 }), "match_z0");
    expect(screen.getByText("#4 |Z−Z₀| 3.20 Ω")).toBeTruthy();
  });

  it("keeps the SWR readout for Nelder-Mead, whose residual is not monotone", () => {
    show(frame({ phase: "nelder-mead", residual: 3.2 }), "resonance");
    expect(screen.getByText("#4 SWR 1.07")).toBeTruthy();
    expect(screen.queryByText(/\|X\|/)).toBeNull();
  });

  it("keeps the SWR readout when the objective is not a root at all", () => {
    // Multi-feed responses send residual: null even on a root objective.
    show(frame({ phase: "secant", residual: null }), "resonance");
    expect(screen.getByText("#4 SWR 1.07")).toBeTruthy();
  });

  it("falls back to SWR when the server sends no phase (an older server)", () => {
    show(frame({}), "resonance");
    expect(screen.getByText("#4 SWR 1.07")).toBeTruthy();
  });

  it("still shows the seeding phase in preference to a residual", () => {
    show(
      frame({ phase: "secant", residual: 3.2, seed_index: 2, seed_total: 6 }),
      "resonance",
    );
    expect(screen.getByText("seeding 2/6")).toBeTruthy();
  });
});
