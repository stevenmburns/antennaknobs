// The background analyses key their physics invalidation on a request
// signature (issue #692), not hand-listed deps. These tests pin the two
// halves of that contract:
//  - the deliberate exemptions hold: a cut-angle drag re-runs nothing, a
//    terrain knob skips the impedance-only sweep/converge but DOES re-run
//    the norm check (its pattern integral runs over the facets);
//  - the safe default holds: a brand-new SolveRequest field — one no dep
//    array ever heard of — invalidates all four analyses.
import { describe, it, expect, vi, beforeEach, afterEach } from "vitest";
import { act, renderHook } from "@testing-library/react";
import { useAnalysisRunners } from "../components/session/useAnalysisRunners";
import type { BackendEntry } from "../lib/backends";
import type { GroundModel } from "../lib/ground";
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

function jsonResponse(data: Record<string, unknown>) {
  return Promise.resolve({ ok: true, json: () => Promise.resolve(data) });
}

let fetchMock: ReturnType<typeof vi.fn>;

beforeEach(() => {
  vi.useFakeTimers();
  fetchMock = vi.fn((url: string) => {
    if (url === "/sweep")
      return streamResponse(JSON.stringify({ freq_mhz: 28.47, z_re: 44, z_im: -4 }));
    if (url === "/converge")
      return streamResponse(JSON.stringify({ n_per_wire: 8, z_re: 44, z_im: -4 }));
    if (url === "/norm_check")
      return jsonResponse({
        available: true,
        directivity_norm: 1,
        pattern_norm: 1,
        method: "grid",
        radiated_fraction: 1,
        radiation_efficiency: 1,
      });
    // /pattern
    return jsonResponse({ available: true, az_deg: [], gains_db: [] });
  });
  vi.stubGlobal("fetch", fetchMock);
});

afterEach(() => {
  vi.unstubAllGlobals();
  vi.useRealTimers();
});

type Props = { req: Record<string, unknown> };

function renderRunners(opts: {
  initialReq: Record<string, unknown>;
  groundModel?: GroundModel;
  necOverlayEnabled?: boolean;
}) {
  return renderHook(
    (p: Props) =>
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
        groundModel: opts.groundModel ?? "fast",
        sweepEnabled: true,
        convergeEnabled: true,
        normCheckEnabled: true,
        necOverlayEnabled: opts.necOverlayEnabled ?? false,
        autoSim: true,
        active: true,
        comboApproved: false,
        recommendedBackend: null,
        buildRequest: () => ({ ...p.req }) as SolveRequest,
        solveWithheld: () => false,
        seqRef: { current: 0 },
        approvedComboRef: { current: false },
      }),
    { initialProps: { req: opts.initialReq } as Props },
  );
}

// Run the 500 ms debounce out and let the stream/json promises settle.
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

describe("request-signature invalidation (issue #692)", () => {
  it("dragging a cut angle re-runs nothing and keeps the overlays", async () => {
    const req = { geometry: "g", az_elev_deg: 30, elev_az_deg: 60 };
    const { result, rerender } = renderRunners({
      initialReq: req,
      necOverlayEnabled: true,
    });
    await settle();
    expect(countFor("/sweep")).toBe(1);
    expect(countFor("/converge")).toBe(1);
    expect(countFor("/norm_check")).toBe(1);
    expect(countFor("/pattern")).toBe(1);

    rerender({ req: { ...req, az_elev_deg: 45, elev_az_deg: 15 } });
    await settle();
    expect(countFor("/sweep")).toBe(1);
    expect(countFor("/converge")).toBe(1);
    expect(countFor("/norm_check")).toBe(1);
    expect(countFor("/pattern")).toBe(1);
    // The overlays were never cleared — the effects did not re-fire.
    expect(result.current.sweep).not.toBeNull();
    expect(result.current.converge).not.toBeNull();
    expect(result.current.normCheck).not.toBeNull();
    expect(result.current.pattern).not.toBeNull();
  });

  it("a terrain knob skips the sweep/converge but re-runs the norm check", async () => {
    const req = {
      geometry: "g",
      ground: true,
      ground_model: "terrain",
      terrain: { preset: "levee", slope_deg: 10 },
    };
    const { result, rerender } = renderRunners({
      initialReq: req,
      groundModel: "terrain",
    });
    await settle();
    expect(countFor("/sweep")).toBe(1);
    expect(countFor("/converge")).toBe(1);
    expect(countFor("/norm_check")).toBe(1);

    rerender({ req: { ...req, terrain: { preset: "levee", slope_deg: 12 } } });
    await settle();
    // Impedance-only analyses: every preset shares the crest medium, so the
    // curves are terrain-param-independent and must not clear or refetch.
    expect(countFor("/sweep")).toBe(1);
    expect(countFor("/converge")).toBe(1);
    expect(result.current.sweep).not.toBeNull();
    expect(result.current.converge).not.toBeNull();
    // The norm check integrates over the facets: it must refetch.
    expect(countFor("/norm_check")).toBe(2);
  });

  it("a brand-new request field invalidates all four analyses by default", async () => {
    const req = { geometry: "g" };
    const { rerender } = renderRunners({
      initialReq: req,
      necOverlayEnabled: true,
    });
    await settle();
    expect(countFor("/sweep")).toBe(1);
    expect(countFor("/converge")).toBe(1);
    expect(countFor("/norm_check")).toBe(1);
    expect(countFor("/pattern")).toBe(1);

    // A field no dep array has ever heard of — the #652-c plane bug shape.
    rerender({ req: { ...req, future_physics_knob: 1 } });
    await settle();
    expect(countFor("/sweep")).toBe(2);
    expect(countFor("/converge")).toBe(2);
    expect(countFor("/norm_check")).toBe(2);
    expect(countFor("/pattern")).toBe(2);
  });
});
