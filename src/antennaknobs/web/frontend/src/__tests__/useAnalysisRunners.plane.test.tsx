// A measurement-plane flip (issue #652 c) must invalidate every background
// analysis: the freq sweep and convergence sweep read the driving-point
// impedance, so the previous plane's curves on screen are wrong data, not
// stale decoration. Pins that changing `plane` (alone — same knobs, same
// freqs) clears the overlays and refetches with the plane in the body.
import { describe, it, expect, vi, beforeEach, afterEach } from "vitest";
import { act, renderHook } from "@testing-library/react";
import { useAnalysisRunners } from "../components/session/useAnalysisRunners";
import type { BackendEntry } from "../lib/backends";
import type { SolveRequest } from "../lib/api";

const BACKEND: BackendEntry = {
  name: "bspline",
  label: "B-spline",
  kind: "momwire",
  supports_ground: true,
  options_schema: [],
  panel: null,
  default_n_per_wire: 8,
  accelerator: false,
  dense_family: false,
};

// A one-line NDJSON stream, enough for the accumulator loops to complete.
function streamResponse(line: string) {
  let sent = false;
  return Promise.resolve({
    ok: true,
    body: {
      getReader: () => ({
        read: () =>
          sent
            ? Promise.resolve({ done: true, value: undefined })
            : ((sent = true),
              Promise.resolve({
                done: false,
                value: new TextEncoder().encode(line + "\n"),
              })),
      }),
    },
  });
}

let fetchMock: ReturnType<typeof vi.fn>;

beforeEach(() => {
  vi.useFakeTimers();
  fetchMock = vi.fn((url: string) =>
    streamResponse(
      url === "/converge"
        ? JSON.stringify({ n: 8, z_re: 44, z_im: -4 })
        : JSON.stringify({ freq_mhz: 28.47, z_re: 44, z_im: -4 }),
    ),
  );
  vi.stubGlobal("fetch", fetchMock);
});

afterEach(() => {
  vi.unstubAllGlobals();
  vi.useRealTimers();
});

type Props = { plane: string | null };

function renderRunners() {
  return renderHook(
    (p: Props) =>
      useAnalysisRunners({
        backend: BACKEND,
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
        sweepResident: true,
        convergeResident: true,
        patternResident: true,
        convergeEnabled: true,
        normCheckEnabled: false,
        necOverlayEnabled: false,
        autoSim: true,
        active: true,
        comboApproved: false,
        recommendedBackend: null,
        buildRequest: () =>
          ({
            geometry: "dipoles.invvee_coax_station",
            ...(p.plane ? { plane: p.plane } : {}),
          }) as SolveRequest,
        solveWithheld: () => false,
        seqRef: { current: 0 },
        approvedComboRef: { current: false },
      }),
    { initialProps: { plane: null } as Props },
  );
}

// Run the 500 ms debounce out and let the stream promises settle.
async function settle() {
  await act(async () => {
    vi.advanceTimersByTime(500);
    await Promise.resolve();
    await Promise.resolve();
    await Promise.resolve();
  });
}

function bodiesFor(url: string) {
  return fetchMock.mock.calls
    .filter((c) => c[0] === url)
    .map((c) => JSON.parse((c[1] as { body: string }).body));
}

describe("plane flip invalidates the background analyses", () => {
  it("clears and refetches the freq sweep and convergence sweep", async () => {
    const { result, rerender } = renderRunners();
    await settle();
    expect(bodiesFor("/sweep")).toHaveLength(1);
    expect(bodiesFor("/converge")).toHaveLength(1);
    expect(result.current.sweep).not.toBeNull();
    expect(result.current.converge).not.toBeNull();
    // No plane picked: the field is absent.
    expect("plane" in bodiesFor("/sweep")[0]).toBe(false);

    rerender({ plane: "feed" });
    // The previous plane's curves must not linger while the refetch runs —
    // they are wrong for the new plane, not merely stale.
    expect(result.current.sweep).toBeNull();
    expect(result.current.converge).toBeNull();

    await settle();
    expect(bodiesFor("/sweep")).toHaveLength(2);
    expect(bodiesFor("/converge")).toHaveLength(2);
    expect(bodiesFor("/sweep")[1].plane).toBe("feed");
    expect(bodiesFor("/converge")[1].plane).toBe("feed");
  });
});
