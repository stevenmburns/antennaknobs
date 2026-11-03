// Stopping a run early, and watching it (Steve, 2026-11-03): turning
// Optimize off mid-run cancels the run and, when its best point so far beats
// where it started, offers to keep it; the knobs never move on their own
// while it runs. The server sends the best point on every frame (`best`),
// whole, so it survives frames the stream drops.
import { describe, it, expect, vi, beforeEach, afterEach } from "vitest";
import { act, render, renderHook, screen } from "@testing-library/react";
import { useOptimizer } from "../components/session/useOptimizer";
import type { OptProgress } from "../components/session/VfoPanel";
import type { SolveRequest } from "../lib/api";
import { ParamForm } from "../components/params/ParamForm";

type QueuedRead = { done: boolean; value?: Uint8Array };

function makeSseReader() {
  const queue: QueuedRead[] = [];
  let waiting: ((r: QueuedRead) => void) | null = null;
  let canceled = false;
  const encoder = new TextEncoder();

  function feed(item: QueuedRead) {
    if (waiting) {
      const resolve = waiting;
      waiting = null;
      resolve(item);
    } else {
      queue.push(item);
    }
  }

  return {
    reader: {
      read: () =>
        new Promise<QueuedRead>((resolve) => {
          if (queue.length > 0) resolve(queue.shift()!);
          else waiting = resolve;
        }),
      cancel: () => {
        canceled = true;
        // Real ReadableStream semantics: canceling resolves a pending read
        // as done, rather than leaving it hanging forever.
        feed({ done: true });
        return Promise.resolve();
      },
      releaseLock: () => {},
    },
    push(event: string, data: unknown) {
      feed({
        done: false,
        value: encoder.encode(`event: ${event}\ndata: ${JSON.stringify(data)}\n\n`),
      });
    },
    close() {
      feed({ done: true });
    },
    get canceled() {
      return canceled;
    },
  };
}

function sseResponse(reader: ReturnType<typeof makeSseReader>["reader"]) {
  return {
    headers: { get: (k: string) => (k.toLowerCase() === "content-type" ? "text/event-stream" : null) },
    body: { getReader: () => reader } as unknown as ReadableStream<Uint8Array>,
  } as unknown as Response;
}

const METRICS = { z_in_re: 48.2, z_in_im: -3.1, z0_ohms: 50.0, swr: 1.12 };

type SetParamAtPath = (path: (string | number)[], value: number | string | boolean) => void;

let fetchMock: ReturnType<typeof vi.fn>;
let setParamAtPath: ReturnType<typeof vi.fn> & SetParamAtPath;

beforeEach(() => {
  vi.useFakeTimers();
  setParamAtPath = vi.fn() as unknown as ReturnType<typeof vi.fn> & SetParamAtPath;
});

afterEach(() => {
  vi.unstubAllGlobals();
  vi.useRealTimers();
});

function mount() {
  return renderHook(() =>
    useOptimizer({
      geometry: "dipoles.probe",
      currentValues: { length_factor: 1.0 },
      currentValuesKey: "length_factor=1",
      currentSchema: [],
      backend: "momwire",
      designFreq: 14.1,
      measFreq: 14.1,
      autoSim: true,
      active: true,
      buildRequest: () => ({ geometry: "dipoles.probe" }) as SolveRequest,
      setParamAtPath,
    }),
  );
}

// Marks length_factor as free and turns Optimize on, then advances the
// 400ms reactive-retune debounce so runOptimize actually fires.
async function armAndFire(result: { current: ReturnType<typeof useOptimizer> }) {
  act(() => {
    result.current.setKnobOpt({
      "dipoles.probe": {
        length_factor: { vary: true, optMin: 0.8, optMax: 1.2, dispMin: 0.8, dispMax: 1.2, step: 0.001 },
      },
    });
  });
  act(() => {
    result.current.setOptEnabled(true);
  });
  await act(async () => {
    vi.advanceTimersByTime(400);
    await Promise.resolve();
  });
}


function frame(n_evals: number, objective: number, best: { lf: number; objective: number }): OptProgress {
  return {
    n_evals,
    params: { length_factor: 0.95 + n_evals / 1000 },
    objective,
    metrics: METRICS,
    best: { params: { length_factor: best.lf }, objective: best.objective, metrics: METRICS },
  };
}

async function flush() {
  await act(async () => {
    await Promise.resolve();
    await Promise.resolve();
  });
}

describe("stopping a run early", () => {
  it("offers the best point so far when it beats the start, and moves nothing until asked", async () => {
    const sse = makeSseReader();
    fetchMock = vi.fn(async () => sseResponse(sse.reader));
    vi.stubGlobal("fetch", fetchMock);
    const { result } = mount();
    await armAndFire(result);

    act(() => sse.push("progress", frame(1, 2.0, { lf: 1.0, objective: 2.0 })));
    act(() => sse.push("progress", frame(6, 1.6, { lf: 0.973, objective: 1.31 })));
    await flush();
    expect(result.current.optRunning).toBe(true);

    act(() => result.current.stopOptimize());
    await flush();
    expect(sse.canceled).toBe(true);
    expect(result.current.optEnabled).toBe(false);
    expect(setParamAtPath).not.toHaveBeenCalled();
    expect(result.current.optStopped).toEqual({
      params: { length_factor: 0.973 },
      objectiveStart: 2.0,
      objectiveBest: 1.31,
      nEvals: 6,
      improved: true,
    });

    act(() => result.current.keepBest());
    expect(setParamAtPath).toHaveBeenCalledWith(["length_factor"], 0.973);
    expect(result.current.optStopped).toBeNull();
  });

  it("Discard leaves the knobs where they started", async () => {
    const sse = makeSseReader();
    fetchMock = vi.fn(async () => sseResponse(sse.reader));
    vi.stubGlobal("fetch", fetchMock);
    const { result } = mount();
    await armAndFire(result);
    act(() => sse.push("progress", frame(1, 2.0, { lf: 1.0, objective: 2.0 })));
    act(() => sse.push("progress", frame(4, 1.5, { lf: 0.98, objective: 1.5 })));
    await flush();
    act(() => result.current.stopOptimize());
    await flush();
    expect(result.current.optStopped).not.toBeNull();
    act(() => result.current.discardBest());
    expect(result.current.optStopped).toBeNull();
    expect(setParamAtPath).not.toHaveBeenCalled();
  });

  it("says the run stopped with nothing better, and offers nothing to keep, when it has not beaten its start", async () => {
    const sse = makeSseReader();
    fetchMock = vi.fn(async () => sseResponse(sse.reader));
    vi.stubGlobal("fetch", fetchMock);
    const { result } = mount();
    await armAndFire(result);
    act(() => sse.push("progress", frame(1, 2.0, { lf: 1.0, objective: 2.0 })));
    act(() => sse.push("progress", frame(3, 2.4, { lf: 1.0, objective: 2.0 })));
    await flush();
    act(() => result.current.stopOptimize());
    await flush();
    expect(result.current.optStopped?.improved).toBe(false);
    act(() => result.current.keepBest());
    expect(setParamAtPath).not.toHaveBeenCalled();
    expect(result.current.optStopped).toBeNull();
  });

  it("uses the server's starting objective when the first frame was dropped", async () => {
    const sse = makeSseReader();
    fetchMock = vi.fn(async () => sseResponse(sse.reader));
    vi.stubGlobal("fetch", fetchMock);
    const { result } = mount();
    await armAndFire(result);
    // Frame 1 never arrives (the stream dropped it); frame 9 carries the start.
    act(() =>
      sse.push("progress", { ...frame(9, 1.7, { lf: 0.975, objective: 1.35 }), objective_start: 2.0 }),
    );
    await flush();
    act(() => result.current.stopOptimize());
    await flush();
    expect(result.current.optStopped).toMatchObject({ objectiveStart: 2.0, objectiveBest: 1.35, improved: true });
  });

  it("a new run clears an unanswered prompt", async () => {
    const sse = makeSseReader();
    fetchMock = vi.fn(async () => sseResponse(sse.reader));
    vi.stubGlobal("fetch", fetchMock);
    const { result } = mount();
    await armAndFire(result);
    act(() => sse.push("progress", frame(1, 2.0, { lf: 1.0, objective: 2.0 })));
    act(() => sse.push("progress", frame(5, 1.4, { lf: 0.97, objective: 1.4 })));
    await flush();
    act(() => result.current.stopOptimize());
    await flush();
    expect(result.current.optStopped).not.toBeNull();
    const sse2 = makeSseReader();
    fetchMock.mockImplementation(async () => sseResponse(sse2.reader));
    await armAndFire(result);
    expect(result.current.optStopped).toBeNull();
  });
});

describe("watching the trial values", () => {
  const schema = [
    { name: "length_factor", label: "length_factor", kind: "float", default: 1.0, min: 0.8, max: 1.2, step: 0.001, precision: 4 },
    { name: "base", label: "base", kind: "float", default: 7.0, min: 1.0, max: 16.0, step: 0.01, precision: 3 },
  ] as unknown as Parameters<typeof ParamForm>[0]["schema"];
  const ko = { vary: true, optMin: 0.8, optMax: 1.2, dispMin: 0.8, dispMax: 1.2, step: 0.001 };

  it("shows the run's trial under each marked knob, and nothing under the rest", () => {
    render(
      <ParamForm
        schema={schema}
        values={{ length_factor: 1.0, base: 7.0 }}
        onChange={() => {}}
        opt={{
          settings: { length_factor: ko },
          onContext: () => {},
          onToggleVary: () => {},
          trial: { length_factor: 0.97312, base: 9.0 },
        }}
      />,
    );
    expect(screen.getByText("trial 0.9731")).toBeTruthy();
    // base is not marked, so its value from the frame is not shown.
    expect(screen.queryByText(/trial 9/)).toBeNull();
  });

  it("shows nothing when no run is in flight", () => {
    render(
      <ParamForm
        schema={schema}
        values={{ length_factor: 1.0, base: 7.0 }}
        onChange={() => {}}
        opt={{ settings: { length_factor: ko }, onContext: () => {}, onToggleVary: () => {}, trial: null }}
      />,
    );
    expect(screen.queryByText(/^trial/)).toBeNull();
  });
});

