// View residency gating (issue #715): a background analysis only runs while
// some view that renders it is pinned or active. These tests drive the hook
// directly with the residency booleans DesignSession derives — the hook is
// deliberately layout-agnostic, so the booleans ARE its contract. The
// consumer census and semantics live in docs/plan-view-residency-gating.md;
// the load-bearing claims pinned here:
//   - losing residency aborts + clears; gaining it refetches (debounced);
//   - the norm check has NO residency gate (its consumer is the HUD,
//     resident in every layout);
//   - the user checkbox still wins over residency (off + resident = off).
import { describe, it, expect, vi, beforeEach, afterEach } from "vitest";
import { act, renderHook } from "@testing-library/react";
import { useAnalysisRunners } from "../components/session/useAnalysisRunners";
import type { BackendEntry } from "../lib/backends";
import type { SolveRequest } from "../lib/api";

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
  fetchMock = vi.fn((url: string) => {
    if (url === "/sweep")
      return streamResponse(
        JSON.stringify({ freq_mhz: 28.47, z_re: 44, z_im: -4 }),
      );
    if (url === "/converge")
      return streamResponse(
        JSON.stringify({ n_per_wire: 8, z_re: 44, z_im: -4 }),
      );
    if (url === "/norm_check")
      return Promise.resolve({
        ok: true,
        json: () =>
          Promise.resolve({
            available: true,
            directivity_norm: 1,
            pattern_norm: 1,
            method: "grid",
            radiated_fraction: 1,
            radiation_efficiency: 1,
          }),
      });
    return Promise.resolve({
      ok: true,
      json: () => Promise.resolve({ available: true, az_deg: [], gains_db: [] }),
    });
  });
  vi.stubGlobal("fetch", fetchMock);
});

afterEach(() => {
  vi.unstubAllGlobals();
  vi.useRealTimers();
});

type Residency = {
  sweepResident: boolean;
  convergeResident: boolean;
  patternResident: boolean;
};

function renderRunners(initial: Residency) {
  return renderHook(
    (p: Residency) =>
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
        convergeEnabled: true,
        normCheckEnabled: true,
        necOverlayEnabled: true,
        sweepResident: p.sweepResident,
        convergeResident: p.convergeResident,
        patternResident: p.patternResident,
        autoSim: true,
        active: true,
        comboApproved: false,
        recommendedBackend: null,
        buildRequest: () => ({ geometry: "g" }) as SolveRequest,
        solveWithheld: () => false,
        seqRef: { current: 0 },
        approvedComboRef: { current: false },
      }),
    { initialProps: initial },
  );
}

async function settle() {
  await act(async () => {
    vi.advanceTimersByTime(500);
    await Promise.resolve();
    await Promise.resolve();
    await Promise.resolve();
  });
}

function countFor(url: string) {
  return fetchMock.mock.calls.filter((c) => c[0] === url).length;
}

const ALL_RESIDENT: Residency = {
  sweepResident: true,
  convergeResident: true,
  patternResident: true,
};

describe("view residency gating (issue #715)", () => {
  it("non-resident analyses never fetch; the HUD norm check still does", async () => {
    renderRunners({
      sweepResident: false,
      convergeResident: false,
      patternResident: false,
    });
    await settle();
    expect(countFor("/sweep")).toBe(0);
    expect(countFor("/converge")).toBe(0);
    expect(countFor("/pattern")).toBe(0);
    // The norm check has no residency gate: the HUD renders it everywhere.
    expect(countFor("/norm_check")).toBe(1);
  });

  it("losing residency clears the overlay; regaining it refetches", async () => {
    const { result, rerender } = renderRunners(ALL_RESIDENT);
    await settle();
    expect(countFor("/sweep")).toBe(1);
    expect(result.current.sweep).not.toBeNull();

    rerender({ ...ALL_RESIDENT, sweepResident: false });
    // Cleared synchronously on the gate flip — wrong-for-nobody data must
    // not linger while nothing renders it.
    expect(result.current.sweep).toBeNull();
    await settle();
    expect(countFor("/sweep")).toBe(1); // and no refetch while non-resident

    rerender(ALL_RESIDENT); // pin (or peek) a consumer again
    await settle();
    expect(countFor("/sweep")).toBe(2);
    expect(result.current.sweep).not.toBeNull();
  });

  it("a switched-off checkbox still wins over residency", async () => {
    // Residency is a second gate, not a replacement for the StageOverlays
    // checkboxes: resident + disabled must stay silent.
    renderHook(() =>
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
        sweepEnabled: false,
        convergeEnabled: false,
        normCheckEnabled: true,
        necOverlayEnabled: true,
        ...ALL_RESIDENT,
        autoSim: true,
        active: true,
        comboApproved: false,
        recommendedBackend: null,
        buildRequest: () => ({ geometry: "g" }) as SolveRequest,
        solveWithheld: () => false,
        seqRef: { current: 0 },
        approvedComboRef: { current: false },
      }),
    );
    return settle().then(() => {
      expect(countFor("/sweep")).toBe(0);
      expect(countFor("/converge")).toBe(0);
    });
  });

  it("the residency gates are independent per analysis", async () => {
    renderRunners({
      sweepResident: true,
      convergeResident: false,
      patternResident: true,
    });
    await settle();
    expect(countFor("/sweep")).toBe(1);
    expect(countFor("/converge")).toBe(0);
    expect(countFor("/pattern")).toBe(1);
  });
});
