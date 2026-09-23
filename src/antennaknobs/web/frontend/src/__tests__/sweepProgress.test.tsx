// Sweep progress (AK#1682): the charts' status line counts points that
// actually LANDED — k/N for the base grid, then a distinct refinement count
// with the budget shown as a ceiling. The hook half drives a hand-cranked
// NDJSON stream one record at a time, so "k" is observed moving per record
// rather than inferred from the finished sweep.
import { describe, it, expect, vi, beforeEach, afterEach } from "vitest";
import { act, render, renderHook } from "@testing-library/react";
import { useAnalysisRunners } from "../components/session/useAnalysisRunners";
import { SmithChart } from "../components/charts/SmithChart";
import { SweepChart } from "../components/charts/SweepChart";
import {
  sweepProgressAttr,
  sweepStatusText,
} from "../components/charts/sweepStatus";
import {
  SWEEP_REFINE_BUDGET,
  sweepProgressFraction,
  sweepProgressLabel,
} from "../lib/sweep";
import type { BackendEntry } from "../lib/backends";
import type { SolveRequest } from "../lib/api";

HTMLCanvasElement.prototype.getContext =
  (() => null) as unknown as HTMLCanvasElement["getContext"];

const PYNEC: BackendEntry = {
  name: "pynec",
  label: "PyNEC",
  kind: "pynec",
  supports_ground: true,
  options_schema: [],
  panel: null,
  default_n_per_wire: 8,
  accelerator: false,
  dense_family: false,
};

// Sharp enough that refinement finds a corner to densify.
function zAt(f: number) {
  return { z_re: 50, z_im: 3000 * (f - 28.47) };
}

/** A reader that hands out one line per `release()` — the base sweep's
 *  stream is cranked by hand so the counter can be read between records. */
function crankedStream(lines: string[]) {
  let i = 0;
  const waiters: Array<() => void> = [];
  let released = 0;
  const release = (n = 1) => {
    released += n;
    while (waiters.length) waiters.shift()!();
  };
  const read = async (): Promise<{ done: boolean; value?: Uint8Array }> => {
    while (i >= released && i < lines.length) {
      await new Promise<void>((r) => waiters.push(r));
    }
    if (i >= lines.length) return { done: true };
    return { done: false, value: new TextEncoder().encode(lines[i++] + "\n") };
  };
  return {
    release,
    response: Promise.resolve({ ok: true, body: { getReader: () => ({ read }) } }),
  };
}

function eagerStream(lines: string[]) {
  const s = crankedStream(lines);
  s.release(lines.length);
  return s.response;
}

let base: ReturnType<typeof crankedStream> | null;
let refines: ReturnType<typeof crankedStream>[];

beforeEach(() => {
  vi.useFakeTimers();
  base = null;
  refines = [];
  vi.stubGlobal(
    "fetch",
    vi.fn((url: string, init?: { body?: string }) => {
      if (url === "/sweep") {
        const body = JSON.parse(init?.body ?? "{}");
        const lines = (body.freqs_mhz as number[]).map((f) =>
          JSON.stringify({ freq_mhz: f, ...zAt(f) }),
        );
        lines.push(JSON.stringify({ done: true }));
        const st = crankedStream(lines);
        if (body._refine) refines.push(st);
        else base = st;
        return st.response;
      }
      if (url === "/converge") return eagerStream([]);
      return Promise.resolve({
        ok: true,
        json: () => Promise.resolve({ available: false }),
      });
    }),
  );
});

afterEach(() => {
  vi.unstubAllGlobals();
  vi.useRealTimers();
});

function renderRunners() {
  return renderHook(() =>
    useAnalysisRunners({
      backend: PYNEC,
      currentVariant: "default",
      currentExample: undefined,
      currentBands: [],
      freqWindowCeiling: 60,
      designFreq: 28.47,
      measFreq: 28.47,
      measLocked: false,
      groundEnabled: false,
      groundModel: "fast",
      sweepEnabled: true,
      convergeEnabled: false,
      normCheckEnabled: false,
      necOverlayEnabled: false,
      sweepResident: true,
      convergeResident: false,
      patternResident: false,
      autoSim: true,
      active: true,
      comboApproved: false,
      recommendedBackend: null,
      z0: 50,
      buildRequest: () => ({ geometry: "g" }) as SolveRequest,
      solveWithheld: () => false,
      seqRef: { current: 0 },
      approvedComboRef: { current: false },
    }),
  );
}

async function flush(ms = 0, n = 60) {
  await act(async () => {
    if (ms) vi.advanceTimersByTime(ms);
    for (let i = 0; i < n; i++) await Promise.resolve();
  });
}

describe("sweep progress in the analysis runners (AK#1682)", () => {
  it("counts k/N as base records arrive, then refinement distinctly", async () => {
    const { result } = renderRunners();
    expect(result.current.sweepProgress).toBeNull();

    await flush(500); // the dwell elapses; the base request goes out
    expect(base).not.toBeNull();
    // Planned count known before any record lands: 0 of the lean grid.
    expect(result.current.sweepProgress).toEqual({
      phase: "base",
      received: 0,
      planned: 17,
    });

    base!.release(1);
    await flush();
    expect(result.current.sweepProgress).toEqual({
      phase: "base",
      received: 1,
      planned: 17,
    });

    base!.release(4);
    await flush();
    expect(result.current.sweepProgress).toMatchObject({ received: 5 });
    // The count IS the curve: never ahead of the points on screen.
    expect(result.current.sweep!.freqs_mhz).toHaveLength(5);

    base!.release(13); // the rest, plus the closing record
    await flush();
    // Stream finished: no request in flight during the refinement dwell,
    // so no counter claims one.
    expect(result.current.sweepRunning).toBe(false);
    expect(result.current.sweepProgress).toBeNull();

    // Refinement: crank each round's stream one record at a time and read
    // the counter between records (state only flushes at act boundaries).
    const seen: unknown[] = [];
    await flush(500);
    for (let guard = 0; guard < 400; guard++) {
      const open = refines.at(-1);
      if (!open) break;
      open.release(1);
      await flush();
      if (result.current.sweepProgress) seen.push(result.current.sweepProgress);
      else if (refines.at(-1) === open) break; // pass concluded
    }
    const refine = seen.filter(
      (p) => (p as { phase: string }).phase === "refine",
    ) as Array<{ phase: "refine"; received: number; budget: number }>;
    expect(refine.length).toBeGreaterThan(0);
    expect(refine.every((p) => p.budget === SWEEP_REFINE_BUDGET)).toBe(true);
    const counts = refine.map((p) => p.received);
    // Monotone and bounded by what actually landed.
    expect(counts).toEqual([...counts].sort((a, b) => a - b));
    const added = result.current.sweep!.freqs_mhz.length - 17;
    expect(added).toBeGreaterThan(0);
    expect(Math.max(...counts)).toBe(added);
    // Pass over: the counter goes away.
    expect(result.current.sweepProgress).toBeNull();
  });
});

describe("status text and bar fraction", () => {
  it("labels the base grid as k/N and refinement against a ceiling", () => {
    expect(sweepProgressLabel({ phase: "base", received: 3, planned: 17 })).toBe(
      "sweeping 3/17",
    );
    expect(sweepProgressLabel({ phase: "refine", received: 8, budget: 48 })).toBe(
      "refining +8 (≤48)",
    );
  });

  it("only the base grid gets a bar fraction", () => {
    expect(sweepProgressFraction({ phase: "base", received: 5, planned: 20 })).toBe(
      0.25,
    );
    expect(
      sweepProgressFraction({ phase: "refine", received: 5, budget: 48 }),
    ).toBeNull();
    expect(sweepProgressFraction({ phase: "base", received: 0, planned: 0 })).toBeNull();
  });

  it("falls back to the bare label without progress, and to nothing idle", () => {
    expect(sweepStatusText(true, null)).toBe("sweeping…");
    expect(sweepStatusText(false, null)).toBeNull();
    // Refinement streams with running=false and still owns the line.
    expect(
      sweepStatusText(false, { phase: "refine", received: 2, budget: 48 }),
    ).toBe("refining +2 (≤48)");
  });
});

describe("the charts carry the progress they were handed", () => {
  const P = { phase: "base", received: 4, planned: 17 } as const;

  it("SmithChart", () => {
    const { container } = render(
      <SmithChart
        r={50}
        x={0}
        z0={50}
        size={200}
        sweep={null}
        converge={null}
        measured={null}
        measFreqMhz={14}
        running
        progress={P}
        convergeRunning={false}
        multiFeed={false}
      />,
    );
    expect(container.querySelector("canvas.smith")!.getAttribute("data-progress")).toBe(
      "base:4/17",
    );
  });

  it("SweepChart, and idle is empty", () => {
    const { container, rerender } = render(
      <SweepChart
        mode="vswr"
        r={50}
        x={0}
        z0={50}
        size={200}
        sweep={null}
        measFreqMhz={14}
        running={false}
        progress={{ phase: "refine", received: 6, budget: 48 }}
        multiFeed={false}
      />,
    );
    const canvas = () => container.querySelector("canvas.sweep")!;
    expect(canvas().getAttribute("data-progress")).toBe("refine:6/48");
    rerender(
      <SweepChart
        mode="vswr"
        r={50}
        x={0}
        z0={50}
        size={200}
        sweep={null}
        measFreqMhz={14}
        running={false}
        progress={null}
        multiFeed={false}
      />,
    );
    expect(canvas().getAttribute("data-progress")).toBe("");
    expect(sweepProgressAttr(null)).toBe("");
  });
});
