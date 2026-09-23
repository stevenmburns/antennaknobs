// A sweep's closing-record advisories (AK#1682, carrying #1681's
// FixedFrequencyNT): the hook lifts them off the base sweep's `done` record,
// and the sweep views render them the way a solve's advisories render.
// Absent key = nothing, in both halves.
import { describe, it, expect, vi, beforeEach, afterEach } from "vitest";
import { act, render, renderHook, screen } from "@testing-library/react";
import { useAnalysisRunners } from "../components/session/useAnalysisRunners";
import { SweepAdvisoryOverlay } from "../components/results/StageOverlays";
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

const NT = {
  category: "FixedFrequencyNT",
  text:
    "The deck's NT card #1 is fixed admittance written for 14.175 MHz, and " +
    "this solve runs over 11.34–17.72 MHz: it is applied unchanged (AK#1681).",
};

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

/** What the closing record carries for BASE sweeps in the current test. */
let closing: Record<string, unknown>;

beforeEach(() => {
  vi.useFakeTimers();
  closing = { done: true };
  vi.stubGlobal(
    "fetch",
    vi.fn((url: string, init?: { body?: string }) => {
      if (url === "/sweep") {
        const body = JSON.parse(init?.body ?? "{}");
        const lines = (body.freqs_mhz as number[]).map((f) =>
          JSON.stringify({ freq_mhz: f, z_re: 50, z_im: 0 }),
        );
        // A refinement round's record deliberately carries nothing: only
        // the base sweep's names the whole range.
        lines.push(JSON.stringify(body._refine ? { done: true } : closing));
        return ndjson(lines);
      }
      if (url === "/converge") return ndjson([]);
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

type Props = { req: Record<string, unknown> };

function renderRunners() {
  return renderHook(
    (p: Props) =>
      useAnalysisRunners({
        backend: PYNEC,
        currentVariant: "default",
        currentExample: undefined,
        currentBands: [],
        freqWindowCeiling: 60,
        designFreq: 14.175,
        measFreq: 14.175,
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
        buildRequest: () => ({ ...p.req }) as SolveRequest,
        solveWithheld: () => false,
        seqRef: { current: 0 },
        approvedComboRef: { current: false },
      }),
    { initialProps: { req: { geometry: "@deck.nec" } } },
  );
}

async function settle(ms = 500) {
  await act(async () => {
    vi.advanceTimersByTime(ms);
    for (let i = 0; i < 60; i++) await Promise.resolve();
  });
}

describe("sweep advisories from the closing record", () => {
  it("present: lifted off the base sweep, and kept through refinement", async () => {
    closing = { done: true, advisories: [NT] };
    const { result } = renderRunners();
    await settle();
    expect(result.current.sweepAdvisories).toEqual([NT]);
    await settle(); // refinement rounds, whose records carry no key
    expect(result.current.sweepAdvisories).toEqual([NT]);
  });

  it("absent key: nothing", async () => {
    const { result } = renderRunners();
    await settle();
    expect(result.current.sweep).not.toBeNull();
    expect(result.current.sweepAdvisories).toEqual([]);
  });

  it("cleared with the sweep when the design changes", async () => {
    closing = { done: true, advisories: [NT] };
    const { result, rerender } = renderRunners();
    await settle();
    expect(result.current.sweepAdvisories).toHaveLength(1);
    closing = { done: true };
    rerender({ req: { geometry: "@other.nec" } });
    expect(result.current.sweepAdvisories).toEqual([]);
    await settle();
    expect(result.current.sweepAdvisories).toEqual([]);
  });
});

describe("SweepAdvisoryOverlay", () => {
  it("renders an advisory the way the solve panel does", () => {
    render(<SweepAdvisoryOverlay advisories={[NT]} />);
    const note = screen.getByRole("note", { name: "Sweep advisories" });
    expect(note.textContent).toContain("Advisory");
    expect(note.textContent).toContain("written for 14.175 MHz");
  });

  it("renders nothing for an empty or missing list", () => {
    const { container, rerender } = render(<SweepAdvisoryOverlay advisories={[]} />);
    expect(container.innerHTML).toBe("");
    rerender(<SweepAdvisoryOverlay advisories={undefined} />);
    expect(container.innerHTML).toBe("");
  });
});
