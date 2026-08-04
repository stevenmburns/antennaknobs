// Pins SweepChart (src/components/charts/SweepChart.tsx, issue #700 unit 5):
// the shared |Γ|/VSWR-vs-frequency component behind the "gamma" and "vswr"
// views. jsdom ships no 2-D canvas context, so — like every other chart —
// the draw effect's ctx-null guard takes the no-draw path; what's asserted
// here is the pure-derivation data-* attributes computed at render time
// (data-mode/data-points/data-feeds/data-y-values/data-current), which are
// available regardless of whether a real context exists. data-y-values in
// particular is the mutation catcher: it carries the actual per-mode
// numbers, so a conversion swap (gamma math running under the vswr label,
// or vice versa) changes the string even though data-mode stays correct.
import { describe, it, expect } from "vitest";
import { render } from "@testing-library/react";
import { SweepChart } from "../components/charts/SweepChart";
import type { SweepData } from "../lib/api";

HTMLCanvasElement.prototype.getContext =
  (() => null) as unknown as HTMLCanvasElement["getContext"];

// Three points chosen from the closed-form oracle pairs pinned in
// math.test.ts: Z=50+0j -> matched (S11 floored at -60 dB, VSWR=1);
// Z=100+0j and Z=25+0j -> the 2:1 real mismatch (|Γ|=1/3 ⇒ S11 -9.5424 dB,
// VSWR=2) from either side of Z0=50.
const SWEEP: SweepData = {
  freqs_mhz: [10, 14, 18],
  z_re: [50, 100, 25],
  z_im: [0, 0, 0],
};

function renderChart(
  mode: "gamma" | "vswr",
  overrides: Partial<React.ComponentProps<typeof SweepChart>> = {},
) {
  return render(
    <SweepChart
      mode={mode}
      r={0}
      x={0}
      z0={50}
      size={180}
      sweep={null}
      measFreqMhz={14}
      running={false}
      multiFeed={false}
      {...overrides}
    />,
  );
}

describe("mode dispatch", () => {
  it("renders the gamma canvas with its own marker", () => {
    const { container } = renderChart("gamma");
    const canvas = container.querySelector('canvas.sweep[data-mode="gamma"]');
    expect(canvas).not.toBeNull();
    expect(container.querySelector('canvas.sweep[data-mode="vswr"]')).toBeNull();
  });

  it("renders the vswr canvas with its own marker", () => {
    const { container } = renderChart("vswr");
    const canvas = container.querySelector('canvas.sweep[data-mode="vswr"]');
    expect(canvas).not.toBeNull();
    expect(container.querySelector('canvas.sweep[data-mode="gamma"]')).toBeNull();
  });
});

describe("empty/loading state", () => {
  it("renders the frame with no trace and does not crash when sweep is null", () => {
    const { container } = renderChart("gamma", { sweep: null });
    const canvas = container.querySelector("canvas.sweep") as HTMLCanvasElement;
    expect(canvas).not.toBeNull();
    expect(canvas.dataset.points).toBe("0");
    expect(canvas.dataset.feeds).toBe("0");
    expect(canvas.dataset.yValues).toBe("");
  });

  it("shows no current marker before any solve (r=x=0, no feeds)", () => {
    const { container } = renderChart("vswr", { sweep: null, r: 0, x: 0 });
    const canvas = container.querySelector("canvas.sweep") as HTMLCanvasElement;
    expect(canvas.dataset.current).toBe("");
  });
});

describe("a synthetic 3-point sweep produces a trace", () => {
  it("gamma mode: y-values are S11 in dB, not VSWR, per sample", () => {
    const { container } = renderChart("gamma", { sweep: SWEEP });
    const canvas = container.querySelector("canvas.sweep") as HTMLCanvasElement;
    expect(canvas.dataset.points).toBe("3");
    expect(canvas.dataset.feeds).toBe("1");
    expect(canvas.dataset.yValues).toBe("-60.0000,-9.5424,-9.5424");
  });

  it("vswr mode: y-values are VSWR, not S11 dB, per sample", () => {
    const { container } = renderChart("vswr", { sweep: SWEEP });
    const canvas = container.querySelector("canvas.sweep") as HTMLCanvasElement;
    expect(canvas.dataset.points).toBe("3");
    expect(canvas.dataset.yValues).toBe("1.0000,2.0000,2.0000");
  });

  it("the two modes never render identical y-values for the same sweep", () => {
    const gamma = render(<SweepChart mode="gamma" r={0} x={0} z0={50} size={180} sweep={SWEEP} measFreqMhz={14} running={false} multiFeed={false} />);
    const vswr = render(<SweepChart mode="vswr" r={0} x={0} z0={50} size={180} sweep={SWEEP} measFreqMhz={14} running={false} multiFeed={false} />);
    const gVals = (gamma.container.querySelector("canvas.sweep") as HTMLCanvasElement).dataset.yValues;
    const vVals = (vswr.container.querySelector("canvas.sweep") as HTMLCanvasElement).dataset.yValues;
    expect(gVals).not.toBe(vVals);
  });

  it("current-Z marker reflects the live result, converted by the chart's own mode", () => {
    const gamma = renderChart("gamma", { sweep: SWEEP, r: 100, x: 0, z0: 50 });
    const gCanvas = gamma.container.querySelector("canvas.sweep") as HTMLCanvasElement;
    expect(gCanvas.dataset.current).toBe("-9.5424");

    const vswr = renderChart("vswr", { sweep: SWEEP, r: 100, x: 0, z0: 50 });
    const vCanvas = vswr.container.querySelector("canvas.sweep") as HTMLCanvasElement;
    expect(vCanvas.dataset.current).toBe("2.0000");
  });
});

describe("multi-feed sweeps (mirrors SmithChart's feeds_z_re/feeds_z_im policy)", () => {
  it("uses the per-feed arrays when present and shaped for it", () => {
    const multi: SweepData = {
      freqs_mhz: [10, 14, 18],
      z_re: [50, 100, 25], // legacy single-trace fields, should be ignored
      z_im: [0, 0, 0],
      feeds_z_re: [
        [50, 200],
        [100, 200],
        [25, 200],
      ],
      feeds_z_im: [
        [0, 0],
        [0, 0],
        [0, 0],
      ],
    };
    const { container } = renderChart("gamma", { sweep: multi });
    const canvas = container.querySelector("canvas.sweep") as HTMLCanvasElement;
    expect(canvas.dataset.feeds).toBe("2");
    // Feed-0's trace is what data-y-values reports (the legacy single-trace
    // convention), and it must come from feeds_z_re[*][0], not the
    // top-level z_re — same fallback order as SmithChart's zAt().
    expect(canvas.dataset.yValues).toBe("-60.0000,-9.5424,-9.5424");
  });

  it("falls back to the legacy single trace when feeds_z_re is absent or too short", () => {
    const { container } = renderChart("gamma", { sweep: SWEEP });
    const canvas = container.querySelector("canvas.sweep") as HTMLCanvasElement;
    expect(canvas.dataset.feeds).toBe("1");
  });
});
