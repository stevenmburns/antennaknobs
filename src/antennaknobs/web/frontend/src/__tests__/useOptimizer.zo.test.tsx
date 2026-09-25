// AK#1735: a new reference impedance re-tunes the reactive optimizer, the way
// a new objective does, and the /optimize body carries it as `z0_ohms` (it
// rides in through buildRequest, the same body the live solve sends).
import { describe, it, expect, vi, beforeEach, afterEach } from "vitest";
import { act, renderHook } from "@testing-library/react";
import { useOptimizer } from "../components/session/useOptimizer";
import type { SolveRequest } from "../lib/api";

function jsonResponse(body: unknown): Response {
  return {
    headers: { get: () => "application/json" },
    json: async () => body,
  } as unknown as Response;
}

const RESULT = {
  objective: "match_z0",
  params: {},
  objective_before: 2.0,
  objective_after: 0.01,
  metrics_before: { z_in_re: 60, z_in_im: 20, z0_ohms: 75, swr: 1.4 },
  metrics_after: { z_in_re: 75, z_in_im: 0, z0_ohms: 75, swr: 1.0 },
  n_evals: 9,
  improved: true,
};

let fetchMock: ReturnType<typeof vi.fn>;

beforeEach(() => {
  vi.useFakeTimers();
  fetchMock = vi.fn(async () => jsonResponse(RESULT));
  vi.stubGlobal("fetch", fetchMock);
});

afterEach(() => {
  vi.unstubAllGlobals();
  vi.useRealTimers();
});

function mount(initialZo: number | null) {
  return renderHook(
    ({ zo }: { zo: number | null }) =>
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
        // DesignSession's buildRequest adds z0_ohms exactly when overridden.
        buildRequest: () =>
          ({
            geometry: "dipoles.probe",
            ...(zo === null ? {} : { z0_ohms: zo }),
          }) as SolveRequest,
        setParamAtPath: vi.fn(),
        zoOverride: zo,
      }),
    { initialProps: { zo: initialZo } },
  );
}

async function settle() {
  await act(async () => {
    vi.advanceTimersByTime(400);
    await Promise.resolve();
    await Promise.resolve();
  });
}

const optimizeBodies = () =>
  fetchMock.mock.calls.map(
    ([, init]) => JSON.parse(String((init as RequestInit).body)) as Record<string, unknown>,
  );

describe("useOptimizer and the Zo override (AK#1735)", () => {
  it("a Zo edit re-tunes, and each run's body carries the reference it was for", async () => {
    const { result, rerender } = mount(null);
    act(() => {
      result.current.setKnobOpt({
        "dipoles.probe": {
          length_factor: { vary: true, optMin: 0.8, optMax: 1.2, dispMin: 0.8, dispMax: 1.2, step: 0.001 },
        },
      });
      result.current.setOptObjective("match_z0");
    });
    act(() => result.current.setOptEnabled(true));
    await settle();
    expect(fetchMock).toHaveBeenCalledTimes(1);
    expect("z0_ohms" in optimizeBodies()[0]).toBe(false);

    rerender({ zo: 75 });
    await settle();
    expect(fetchMock).toHaveBeenCalledTimes(2);
    const second = optimizeBodies()[1];
    expect(second.z0_ohms).toBe(75);
    expect((second.optimize as { objective: string }).objective).toBe("match_z0");

    // Nothing else moved: no third run.
    rerender({ zo: 75 });
    await settle();
    expect(fetchMock).toHaveBeenCalledTimes(2);
  });
});
