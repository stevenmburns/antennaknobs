// Live optimizer progress over SSE (issue #773 unit 4), against the pinned
// contract: `Accept: text/event-stream` opts in, the server answers with
// `event: progress` frames and exactly one terminal `event: result` or
// `event: error`. The backend doesn't stream yet — these tests stub the
// transport and drive it by hand.
//
// The reader stub below queues frames and resolves reads on demand rather
// than inline, and its `cancel()` resolves any read that's still pending
// with `{done: true}` — exactly what a real ReadableStream does when a
// reader is canceled mid-read. That's the behavior the abort test depends
// on: useOptimizer's abort handler calls `reader.cancel()` rather than
// trusting fetch's own AbortSignal wiring, because a stubbed transport has
// none of that wiring to trust.
import { describe, it, expect, vi, beforeEach, afterEach } from "vitest";
import { act, renderHook } from "@testing-library/react";
import { useOptimizer } from "../components/session/useOptimizer";
import type { OptimizeResult, OptProgress } from "../components/session/VfoPanel";
import type { SolveRequest } from "../lib/api";

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

function progressFrame(n_evals: number): OptProgress {
  return {
    n_evals,
    params: { length_factor: 0.981 },
    objective: 1.34,
    metrics: METRICS,
  };
}

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

describe("useOptimizer SSE progress (#773 unit 4)", () => {
  it("progress events update n_evals, objective, and Z/SWR live, before any terminal event", async () => {
    const sse = makeSseReader();
    fetchMock = vi.fn(async () => sseResponse(sse.reader));
    vi.stubGlobal("fetch", fetchMock);

    const { result } = mount();
    await armAndFire(result);

    expect(fetchMock).toHaveBeenCalledTimes(1);
    const [, init] = fetchMock.mock.calls[0] as [string, RequestInit];
    expect((init.headers as Record<string, string>).Accept).toBe("text/event-stream");
    expect(result.current.optRunning).toBe(true);

    act(() => sse.push("progress", progressFrame(1)));
    await act(async () => {
      await Promise.resolve();
    });
    expect(result.current.optProgress?.n_evals).toBe(1);
    expect(result.current.optProgress?.metrics.swr).toBeCloseTo(1.12);
    // Still running — no terminal event yet, and no params applied.
    expect(result.current.optRunning).toBe(true);
    expect(setParamAtPath).not.toHaveBeenCalled();

    act(() => sse.push("progress", progressFrame(7)));
    await act(async () => {
      await Promise.resolve();
    });
    expect(result.current.optProgress?.n_evals).toBe(7);
  });

  it("a terminal result event applies params through setParamAtPath, same as the non-streaming path", async () => {
    const sse = makeSseReader();
    fetchMock = vi.fn(async () => sseResponse(sse.reader));
    vi.stubGlobal("fetch", fetchMock);

    const { result } = mount();
    await armAndFire(result);

    act(() => sse.push("progress", progressFrame(3)));
    act(() => sse.push("result", RESULT));
    act(() => sse.close());
    await act(async () => {
      await Promise.resolve();
      await Promise.resolve();
    });

    expect(result.current.optResult).toEqual(RESULT);
    expect(setParamAtPath).toHaveBeenCalledWith(["length_factor"], 0.99);
    expect(result.current.optRunning).toBe(false);
  });

  it("a terminal error event surfaces via optError, same path as today's data.error", async () => {
    const sse = makeSseReader();
    fetchMock = vi.fn(async () => sseResponse(sse.reader));
    vi.stubGlobal("fetch", fetchMock);

    const { result } = mount();
    await armAndFire(result);

    act(() => sse.push("error", { detail: "no feasible point" }));
    act(() => sse.close());
    await act(async () => {
      await Promise.resolve();
      await Promise.resolve();
    });

    expect(result.current.optError).toBe("no feasible point");
    expect(result.current.optResult).toBeNull();
    expect(setParamAtPath).not.toHaveBeenCalled();
    expect(result.current.optRunning).toBe(false);
  });

  it("abort mid-stream tears the reader down and stops further updates", async () => {
    // Each fetch call gets ITS OWN reader — a superseded run's frames must
    // not leak into the run that replaced it, only its abort/cancel should.
    const streams: ReturnType<typeof makeSseReader>[] = [];
    fetchMock = vi.fn(async () => {
      const s = makeSseReader();
      streams.push(s);
      return sseResponse(s.reader);
    });
    vi.stubGlobal("fetch", fetchMock);

    const { result } = mount();
    await armAndFire(result);
    const sse = streams[0];

    act(() => sse.push("progress", progressFrame(1)));
    await act(async () => {
      await Promise.resolve();
    });
    expect(result.current.optProgress?.n_evals).toBe(1);

    // A knob change marked free re-triggers the reactive effect with a new
    // signature, which supersedes the in-flight run — the same path a real
    // fixed-input edit takes.
    act(() => {
      result.current.setKnobOpt({
        "dipoles.probe": {
          length_factor: { vary: true, optMin: 0.7, optMax: 1.3, dispMin: 0.7, dispMax: 1.3, step: 0.001 },
        },
      });
    });
    await act(async () => {
      vi.advanceTimersByTime(400);
      await Promise.resolve();
    });

    // The superseded run's reader was torn down...
    expect(sse.canceled).toBe(true);
    // ...and a frame pushed to the now-abandoned stream after that must not
    // land: this is exactly what breaks if the `ctrl.signal.aborted` guard
    // inside the SSE loop is dropped.
    act(() => sse.push("progress", progressFrame(99)));
    await act(async () => {
      await Promise.resolve();
    });
    expect(result.current.optProgress?.n_evals).not.toBe(99);

    // A fresh run is what's actually in flight now.
    expect(fetchMock).toHaveBeenCalledTimes(2);
  });

  it("without a streaming content-type, falls back to the plain-JSON path unchanged", async () => {
    fetchMock = vi.fn(async () => ({
      headers: { get: () => "application/json" },
      json: async () => RESULT,
    }));
    vi.stubGlobal("fetch", fetchMock);

    const { result } = mount();
    await armAndFire(result);
    await act(async () => {
      await Promise.resolve();
      await Promise.resolve();
    });

    expect(result.current.optResult).toEqual(RESULT);
    expect(setParamAtPath).toHaveBeenCalledWith(["length_factor"], 0.99);
    expect(result.current.optProgress).toBeNull();
  });
});
