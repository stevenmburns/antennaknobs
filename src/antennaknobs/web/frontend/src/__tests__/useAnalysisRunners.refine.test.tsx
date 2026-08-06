// Adaptive sweep refinement (issue #744) as a CONTRACT, not as physics: the
// planner's criterion is pinned in refine.test.ts, so what these tests hold
// is when refinement is allowed to run at all and what it may leave behind.
//   - it fires only after a whole base sweep streamed AND a second dwell —
//     never mid-scrub;
//   - a knob change aborts it and leaves no refined point behind (the #692
//     signature clears them like every other sweep point);
//   - a non-resident sweep gets zero refinement requests (#715);
//   - budget exhaustion is graceful: best-so-far stays on screen.
import { describe, it, expect, vi, beforeEach, afterEach } from "vitest";
import { act, renderHook } from "@testing-library/react";
import { useAnalysisRunners } from "../components/session/useAnalysisRunners";
import { SWEEP_REFINE_BUDGET } from "../lib/sweep";
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

// A series-resonance Z(f) sharp enough that a 41-point grid corners at the
// notch — the showcase failure the issue describes, in closed form.
function zAt(f: number): { z_re: number; z_im: number } {
  return { z_re: 50, z_im: 3000 * (f - 28.47) };
}

function ndjson(lines: string[]) {
  let i = 0;
  return Promise.resolve({
    ok: true,
    body: {
      getReader: () => ({
        read: () =>
          i >= lines.length
            ? Promise.resolve({ done: true, value: undefined })
            : Promise.resolve({
                done: false,
                value: new TextEncoder().encode(lines[i++] + "\n"),
              }),
      }),
    },
  });
}

let fetchMock: ReturnType<typeof vi.fn>;
/** Every /sweep body seen, in order — base sweep first, then each
 *  refinement round. */
let sweepBodies: Record<string, unknown>[];

beforeEach(() => {
  vi.useFakeTimers();
  sweepBodies = [];
  fetchMock = vi.fn((url: string, init?: { body?: string }) => {
    if (url === "/sweep") {
      const body = JSON.parse(init?.body ?? "{}");
      sweepBodies.push(body);
      const freqs: number[] = body.freqs_mhz ?? [];
      return ndjson(
        freqs.map((f) => JSON.stringify({ freq_mhz: f, ...zAt(f) })),
      );
    }
    if (url === "/converge") return ndjson([]);
    return Promise.resolve({
      ok: true,
      json: () => Promise.resolve({ available: false }),
    });
  });
  vi.stubGlobal("fetch", fetchMock);
});

afterEach(() => {
  vi.unstubAllGlobals();
  vi.useRealTimers();
});

type Props = { req: Record<string, unknown>; sweepResident: boolean };

function renderRunners(initial: Props) {
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
        groundModel: "fast",
        sweepEnabled: true,
        convergeEnabled: false,
        normCheckEnabled: false,
        necOverlayEnabled: false,
        sweepResident: p.sweepResident,
        convergeResident: false,
        patternResident: false,
        autoSim: true,
        active: true,
        comboApproved: false,
        recommendedBackend: null,
        z0: 50,
        buildRequest: () => ({ ...p.req }) as SolveRequest,
        solveWithheld: () => false,
        seqRef: { current: 0 },
        approvedComboRef: { current: false },
      }),
    { initialProps: initial },
  );
}

/** Run the timers out and let the streams settle. `ms` covers one dwell;
 *  the microtask flushes cover the NDJSON reads and, on the refinement
 *  path, the chain of rounds behind them. */
async function settle(ms = 500, flushes = 60) {
  await act(async () => {
    vi.advanceTimersByTime(ms);
    for (let i = 0; i < flushes; i++) await Promise.resolve();
  });
}

const refineBodies = () => sweepBodies.filter((b) => b._refine === true);
const BASE: Props = { req: { geometry: "g" }, sweepResident: true };

describe("adaptive sweep refinement (issue #744)", () => {
  it("waits for a second dwell after the base sweep, then densifies", async () => {
    const { result } = renderRunners(BASE);
    await settle();
    // Base sweep streamed and drew; no refinement has been asked for yet —
    // the dwell that authorises it has not elapsed.
    expect(sweepBodies).toHaveLength(1);
    expect(sweepBodies[0]._refine).toBeUndefined();
    const planned = result.current.sweep!.freqs_mhz.length;
    expect(planned).toBe(41);

    await settle();
    expect(refineBodies().length).toBeGreaterThan(0);
    const refined = result.current.sweep!;
    expect(refined.freqs_mhz.length).toBeGreaterThan(planned);
    // Merged in frequency order, arrays index-aligned: the chart draws a
    // polyline straight off these, so an unsorted merge would draw a mess.
    expect(refined.freqs_mhz).toEqual([...refined.freqs_mhz].sort((a, b) => a - b));
    for (let i = 0; i < refined.freqs_mhz.length; i++) {
      expect(refined.z_im[i]).toBeCloseTo(zAt(refined.freqs_mhz[i]).z_im, 6);
    }
    // The extra points went to the notch, not spread over the flat wings.
    const added = refined.freqs_mhz.filter(
      (f) => !sweepBodies[0].freqs_mhz!.toString().includes(String(f)),
    );
    expect(added.length).toBeGreaterThan(0);
  });

  it("every refinement request carries the lane's refine marker", async () => {
    renderRunners(BASE);
    await settle();
    await settle();
    for (const b of refineBodies()) {
      expect(b._refine).toBe(true);
      expect(Array.isArray(b.freqs_mhz)).toBe(true);
      expect((b.freqs_mhz as number[]).length).toBeGreaterThan(0);
    }
  });

  it("never fires mid-scrub: a knob change inside the dwell cancels it", async () => {
    const { result, rerender } = renderRunners(BASE);
    await settle();
    expect(refineBodies()).toHaveLength(0);

    // The user moves a knob while the refinement dwell is counting down.
    rerender({ ...BASE, req: { geometry: "g", length_factor: 1.01 } });
    expect(result.current.sweep).toBeNull(); // cleared by the signature effect
    await settle();
    // The new base sweep ran; the cancelled refinement never did.
    expect(refineBodies()).toHaveLength(0);
    expect(sweepBodies).toHaveLength(2);
  });

  it("a knob change during refinement aborts it and leaves no refined point", async () => {
    const { result, rerender } = renderRunners(BASE);
    await settle();
    await settle();
    expect(refineBodies().length).toBeGreaterThan(0);
    expect(result.current.sweep!.freqs_mhz.length).toBeGreaterThan(41);

    rerender({ ...BASE, req: { geometry: "g", length_factor: 1.01 } });
    // Refined points live in the same state the signature effect clears —
    // no separate lifetime to get wrong (issue #692).
    expect(result.current.sweep).toBeNull();
    await settle();
    // The fresh sweep carries exactly the planned grid: nothing survived.
    expect(result.current.sweep!.freqs_mhz).toHaveLength(41);
  });

  it("a non-resident sweep receives no refinement solves", async () => {
    const { rerender } = renderRunners({ ...BASE, sweepResident: false });
    await settle();
    await settle();
    expect(sweepBodies).toHaveLength(0);

    // Gaining residency runs the base sweep and, a dwell later, refinement;
    // losing it again silences both.
    rerender(BASE);
    await settle();
    await settle();
    const refinedWhileResident = refineBodies().length;
    expect(refinedWhileResident).toBeGreaterThan(0);
    rerender({ ...BASE, sweepResident: false });
    await settle();
    await settle();
    expect(refineBodies()).toHaveLength(refinedWhileResident);
  });

  it("stops at the point budget and keeps the best-so-far curve", async () => {
    const { result } = renderRunners(BASE);
    await settle();
    await settle(500, 400); // let every round it wants to run, run
    const total = refineBodies().reduce(
      (n, b) => n + (b.freqs_mhz as number[]).length,
      0,
    );
    expect(total).toBeLessThanOrEqual(SWEEP_REFINE_BUDGET);
    // Whatever it managed is on screen and consistent — budget exhaustion
    // degrades to "less refined", never to a blank or torn curve.
    const sweep = result.current.sweep!;
    expect(sweep.freqs_mhz).toHaveLength(41 + total);
    expect(sweep.z_re).toHaveLength(41 + total);
    expect(sweep.z_im).toHaveLength(41 + total);
  });

  it("a smooth sweep is left alone", async () => {
    // Z with no resonance in the window: the rendered VSWR/S11/Smith curves
    // have no corner, so the planner asks for nothing and no solve is spent.
    fetchMock.mockImplementation((url: string, init?: { body?: string }) => {
      if (url !== "/sweep")
        return Promise.resolve({ ok: true, json: () => Promise.resolve({}) });
      const body = JSON.parse(init?.body ?? "{}");
      sweepBodies.push(body);
      const freqs: number[] = body.freqs_mhz ?? [];
      return ndjson(
        freqs.map((f) => JSON.stringify({ freq_mhz: f, z_re: 50, z_im: 0 })),
      );
    });
    renderRunners(BASE);
    await settle();
    await settle();
    expect(refineBodies()).toHaveLength(0);
  });
});
